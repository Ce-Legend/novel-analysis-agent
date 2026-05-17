from __future__ import annotations

from pathlib import Path
import re

from .analysis.book import aggregate_book, build_split_diagnostics, postprocess_book_analysis, repair_delivery_weak_slots
from .analysis.chapter import analyze_chapter
from .config import AppSettings, ExportFormat
from .evals import build_reference_alignment_review, evaluate_run, review_delivery_quality
from .exporters import (
    build_delivery_integrity_review,
    build_delivery_report,
    export_docx,
    export_pdf,
    render_markdown,
    repair_delivery_report_blocks,
)
from .ingest import ingest_book
from .providers import resolve_book_provider
from .providers.base import LLMProvider
from .runtime import RunContext, read_json, write_json
from .schemas import (
    BookAnalysis,
    ChapterAnalysis,
    ChapterFailureRecord,
    ChapterStatusSummary,
    ChapterRecord,
    EvalReport,
    IngestedBook,
    InputType,
    RunSummary,
    RunStatsSummary,
    RunManifest,
    StageStats,
)
from .splitter import split_into_chapters
from .utils import jsonl_append, jsonl_dump, jsonl_load, jsonl_upsert


def run_pipeline(
    *,
    ctx: RunContext,
    settings: AppSettings,
    input_path: Path,
    input_type: InputType,
    provider: LLMProvider,
    export_formats: list[ExportFormat],
    profile: str,
    force: bool = False,
) -> dict[str, Path]:
    ctx.acquire_lock()
    ctx.logger.info("Run lock acquired: %s", ctx.lock_path.name)
    try:
        return _run_pipeline_locked(
            ctx=ctx,
            settings=settings,
            input_path=input_path,
            input_type=input_type,
            provider=provider,
            export_formats=export_formats,
            profile=profile,
            force=force,
        )
    finally:
        ctx.release_lock()


def finalize_delivery(
    *,
    ctx: RunContext,
    export_formats: list[ExportFormat],
) -> dict[str, Path]:
    ctx.acquire_lock()
    ctx.logger.info("Run lock acquired for finalize-delivery: %s", ctx.lock_path.name)
    try:
        return _finalize_delivery_locked(
            ctx=ctx,
            export_formats=export_formats,
        )
    finally:
        ctx.release_lock()


def _finalize_delivery_locked(
    *,
    ctx: RunContext,
    export_formats: list[ExportFormat],
) -> dict[str, Path]:
    book_analysis_path = ctx.aggregate_dir / "book_analysis.json"
    chapter_analysis_path = ctx.chapter_dir / "chapter_analysis.jsonl"
    chapter_failures_path = ctx.chapter_dir / "chapter_failures.jsonl"

    if not book_analysis_path.exists():
        raise RuntimeError(f"Missing aggregate artifact: {book_analysis_path}")
    if not chapter_analysis_path.exists():
        raise RuntimeError(f"Missing chapter analysis artifact: {chapter_analysis_path}")

    chapter_analyses = _load_existing_chapter_analyses(chapter_analysis_path)
    chapter_failures = _load_existing_chapter_failures(chapter_failures_path)
    if not chapter_analyses:
        raise RuntimeError("No chapter analyses available for finalize-delivery")
    if chapter_failures:
        ctx.logger.warning(
            "Finalize-delivery proceeding with %s failed chapters still recorded; exports will be partial",
            len(chapter_failures),
        )

    book_analysis = postprocess_book_analysis(BookAnalysis.model_validate(read_json(book_analysis_path)), chapter_analyses)
    book_analysis = repair_delivery_weak_slots(book_analysis, chapter_analyses)
    write_json(book_analysis_path, book_analysis.model_dump(mode="json"))

    expected_chapters = _resolve_expected_chapter_count(
        ctx=ctx,
        analyzed_chapters=len(chapter_analyses),
        failed_chapters=len(chapter_failures),
    )
    outputs, *_ = _finalize_delivery_outputs(
        ctx=ctx,
        book_analysis=book_analysis,
        chapter_analyses=chapter_analyses,
        export_formats=export_formats,
        expected_chapters=expected_chapters,
        chapter_failures=chapter_failures,
    )
    return outputs


def _run_pipeline_locked(
    *,
    ctx: RunContext,
    settings: AppSettings,
    input_path: Path,
    input_type: InputType,
    provider: LLMProvider,
    export_formats: list[ExportFormat],
    profile: str,
    force: bool = False,
) -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    book_provider = resolve_book_provider(provider, settings.book_provider)
    ctx.acquire_lock()
    manifest_path = ctx.ingest_dir / "manifest.json"
    normalized_path = ctx.ingest_dir / "normalized.txt"
    chapters_path = ctx.split_dir / "chapters.jsonl"
    chapter_analysis_path = ctx.chapter_dir / "chapter_analysis.jsonl"
    chapter_failures_path = ctx.chapter_dir / "chapter_failures.jsonl"
    chapter_status_path = ctx.chapter_dir / "chapter_status.json"
    book_analysis_path = ctx.aggregate_dir / "book_analysis.json"
    eval_path = ctx.eval_dir / "eval_report.json"
    stage_stats_path = ctx.eval_dir / "stage_stats.json"
    run_summary_path = ctx.eval_dir / "run_summary.json"
    quality_review_path = ctx.eval_dir / "quality_review.json"
    split_diagnostics_path = ctx.eval_dir / "chapter_split_diagnostics.json"
    reference_alignment_review_path = ctx.eval_dir / "reference_alignment_review.json"
    delivery_integrity_review_path = ctx.eval_dir / "delivery_integrity_review.json"
    stats_history_path = ctx.eval_dir / "stage_stats_history.jsonl"
    stats_baseline_path = ctx.eval_dir / "stage_stats_baseline.json"
    all_stats: list[StageStats] = []
    current_stage = "ingest"
    chapters: list[ChapterRecord] = []
    chapter_analyses: list[ChapterAnalysis] = []
    chapter_failures: list[ChapterFailureRecord] = []
    existing_analyses: list[ChapterAnalysis] = []
    completed_ids: set[str] = set()
    seed_totals = {
        "total_calls": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_latency_ms": 0,
        "estimated_cost_cny": 0.0,
    }
    seed_warnings: list[str] = []
    seed_stage_counts: dict[str, int] = {}

    def load_stage_history() -> list[StageStats]:
        if not stats_history_path.exists():
            return []
        return [StageStats.model_validate(row) for row in jsonl_load(stats_history_path)]

    def load_stats_baseline() -> None:
        nonlocal seed_totals, seed_warnings, seed_stage_counts
        if not stats_baseline_path.exists():
            return
        baseline = read_json(stats_baseline_path)
        seed_totals = {
            "total_calls": int(baseline.get("total_calls", 0)),
            "total_input_tokens": int(baseline.get("total_input_tokens", 0)),
            "total_output_tokens": int(baseline.get("total_output_tokens", 0)),
            "total_latency_ms": int(baseline.get("total_latency_ms", 0)),
            "estimated_cost_cny": float(baseline.get("estimated_cost_cny", 0.0) or 0.0),
        }
        seed_warnings = list(baseline.get("warnings", []))
        seed_stage_counts = {str(k): int(v) for k, v in baseline.get("stages", {}).items()}

    def write_stats_baseline_from_summary(summary: RunSummary) -> None:
        write_json(
            stats_baseline_path,
            {
                "total_calls": summary.total_calls,
                "total_input_tokens": summary.total_input_tokens,
                "total_output_tokens": summary.total_output_tokens,
                "total_latency_ms": summary.total_latency_ms,
                "estimated_cost_cny": summary.estimated_cost_cny,
                "warnings": summary.warnings,
                "stages": seed_stage_counts,
            },
        )

    def reset_stage_history() -> None:
        if stats_history_path.exists():
            stats_history_path.unlink()
        if stats_baseline_path.exists():
            stats_baseline_path.unlink()

    def append_stage_stats(stats: list[StageStats]) -> None:
        for stat in stats:
            jsonl_append(stats_history_path, stat.model_dump(mode="json"))

    def rewrite_stage_history(stats: list[StageStats]) -> None:
        if not stats:
            if stats_history_path.exists():
                stats_history_path.unlink()
            return
        jsonl_dump(stats_history_path, [stat.model_dump(mode="json") for stat in stats])

    def load_persisted_chapter_truth() -> tuple[list[ChapterAnalysis], list[ChapterFailureRecord]]:
        def dedupe_rows(rows: list[dict], key_field: str) -> list[dict]:
            ordered: dict[str, dict] = {}
            missing: list[dict] = []
            for row in rows:
                key = row.get(key_field)
                if key is None:
                    missing.append(row)
                    continue
                if key in ordered:
                    ordered.pop(key)
                ordered[key] = row
            return missing + list(ordered.values())

        def chapter_sort_key(chapter_id: str) -> tuple[int, str]:
            try:
                return int(chapter_id.split("-")[-1]), chapter_id
            except ValueError:
                return 10**9, chapter_id

        persisted_analysis_rows = jsonl_load(chapter_analysis_path) if chapter_analysis_path.exists() else []
        deduped_analysis_rows = dedupe_rows(persisted_analysis_rows, "chapter_id")
        deduped_analysis_rows.sort(key=lambda row: chapter_sort_key(str(row.get("chapter_id", ""))))
        if chapter_analysis_path.exists() and len(deduped_analysis_rows) != len(persisted_analysis_rows):
            jsonl_dump(chapter_analysis_path, deduped_analysis_rows)

        persisted_failure_rows = jsonl_load(chapter_failures_path) if chapter_failures_path.exists() else []
        deduped_failure_rows = dedupe_rows(persisted_failure_rows, "chapter_id")
        deduped_failure_rows.sort(key=lambda row: int(row.get("order", 10**9)))
        if chapter_failures_path.exists() and len(deduped_failure_rows) != len(persisted_failure_rows):
            jsonl_dump(chapter_failures_path, deduped_failure_rows)

        persisted_analyses = [ChapterAnalysis.model_validate(row) for row in deduped_analysis_rows]
        persisted_failures = [ChapterFailureRecord.model_validate(row) for row in deduped_failure_rows]
        return persisted_analyses, persisted_failures

    def chapter_title_map() -> dict[str, str]:
        return {chapter.chapter_id: chapter.title for chapter in chapters}

    def write_chapter_status(
        *,
        current_stage_name: str,
        latest_completed: ChapterRecord | None = None,
        latest_failed: ChapterFailureRecord | None = None,
    ) -> None:
        persisted_analyses, persisted_failures = load_persisted_chapter_truth()
        titles = chapter_title_map()
        latest_completed_row = persisted_analyses[-1] if persisted_analyses else None
        latest_failed_row = persisted_failures[-1] if persisted_failures else None
        completed_count = len(persisted_analyses)
        failed_count = len(persisted_failures)
        summary = ChapterStatusSummary(
            total_chapters=len(chapters),
            completed_chapters=completed_count,
            failed_chapters=failed_count,
            pending_chapters=max(len(chapters) - completed_count - failed_count, 0),
            latest_completed_chapter_id=(latest_completed.chapter_id if latest_completed else None)
            or (latest_completed_row.chapter_id if latest_completed_row else None),
            latest_completed_title=(latest_completed.title if latest_completed else None)
            or (titles.get(latest_completed_row.chapter_id) if latest_completed_row else None),
            latest_failed_chapter_id=(latest_failed.chapter_id if latest_failed else None)
            or (latest_failed_row.chapter_id if latest_failed_row else None),
            latest_failed_title=(latest_failed.title if latest_failed else None)
            or (titles.get(latest_failed_row.chapter_id) if latest_failed_row else None),
            current_stage=current_stage_name,
        )
        write_json(chapter_status_path, summary.model_dump(mode="json"))

    def write_run_summary(current_stage_name: str) -> None:
        persisted_analyses, persisted_failures = load_persisted_chapter_truth()
        titles = chapter_title_map()
        chapter_stats = [stat for stat in all_stats if stat.stage_name.startswith("chapter_")]
        merge_stats = [stat for stat in all_stats if stat.stage_name == "chapter_merge"]
        aggregate_stats = [stat for stat in all_stats if stat.stage_name.startswith("aggregate_")]
        aggregate_used_file_id_path = any(
            "structured_provider_mode:bailian_long_fileid" in stat.warnings for stat in all_stats
        )
        degraded_split_chapters = sum(1 for chapter in chapters if chapter.split_warnings)
        warning_list = list(seed_warnings) + [warning for stat in all_stats for warning in stat.warnings]
        if persisted_failures:
            warning_list.append(f"failed_chapters:{len(persisted_failures)}")
        total_calls = seed_totals["total_calls"] + len(all_stats)
        total_input_tokens = seed_totals["total_input_tokens"] + sum(stat.input_tokens for stat in all_stats)
        total_output_tokens = seed_totals["total_output_tokens"] + sum(stat.output_tokens for stat in all_stats)
        total_latency_ms = seed_totals["total_latency_ms"] + sum(stat.latency_ms or 0 for stat in all_stats)
        estimated_cost_cny = _merge_estimated_cost(seed_totals["estimated_cost_cny"], _estimate_cost_cny(all_stats))
        latest_completed_row = persisted_analyses[-1] if persisted_analyses else None
        latest_failed_row = persisted_failures[-1] if persisted_failures else None
        summary = RunSummary(
            run_id=ctx.run_id,
            book_id=ctx.book_id,
            input_path=str(input_path),
            provider=provider.name,
            book_provider=book_provider.name,
            chapter_model=settings.model_settings.chapter_model,
            book_model=settings.model_settings.book_model,
            total_chapters=len(chapters),
            completed_chapters=len(persisted_analyses),
            failed_chapters=len(persisted_failures),
            degraded_split_chapters=degraded_split_chapters,
            latest_completed_chapter_id=latest_completed_row.chapter_id if latest_completed_row else None,
            latest_completed_title=titles.get(latest_completed_row.chapter_id) if latest_completed_row else None,
            latest_failed_chapter_id=latest_failed_row.chapter_id if latest_failed_row else None,
            latest_failed_title=titles.get(latest_failed_row.chapter_id) if latest_failed_row else None,
            current_stage=current_stage_name,
            aggregate_used_file_id_path=aggregate_used_file_id_path,
            total_calls=total_calls,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            total_latency_ms=total_latency_ms,
            average_chapter_latency_ms=int(sum((stat.latency_ms or 0) for stat in chapter_stats) / len(chapter_stats))
            if chapter_stats
            else 0,
            chapter_merge_latency_ms=sum(stat.latency_ms or 0 for stat in merge_stats),
            aggregate_latency_ms=sum(stat.latency_ms or 0 for stat in aggregate_stats),
            estimated_cost_cny=estimated_cost_cny,
            split_quality_note=_build_split_quality_note(chapters, degraded_split_chapters),
            warnings=warning_list,
        )
        write_json(run_summary_path, summary.model_dump(mode="json"))

    if force:
        reset_stage_history()
    else:
        load_stats_baseline()
        if stats_history_path.exists():
            all_stats = load_stage_history()
        elif run_summary_path.exists():
            previous_summary = RunSummary.model_validate(read_json(run_summary_path))
            if stage_stats_path.exists():
                previous_stage_stats = RunStatsSummary.model_validate(read_json(stage_stats_path))
                seed_stage_counts = dict(previous_stage_stats.stages)
            seed_totals = {
                "total_calls": previous_summary.total_calls,
                "total_input_tokens": previous_summary.total_input_tokens,
                "total_output_tokens": previous_summary.total_output_tokens,
                "total_latency_ms": previous_summary.total_latency_ms,
                "estimated_cost_cny": previous_summary.estimated_cost_cny or 0.0,
            }
            seed_warnings = list(previous_summary.warnings) + ["stats_seeded_from_previous_run_summary"]
            write_stats_baseline_from_summary(previous_summary)

    if force or not manifest_path.exists() or not normalized_path.exists():
        ctx.logger.info("Stage ingest started")
        ingested = ingest_book(input_path, input_type, settings)
        normalized_path.write_text(ingested.normalized_text, encoding="utf-8")
        manifest = RunManifest(
            run_id=ctx.run_id,
            book_id=ctx.book_id,
            input_path=str(input_path),
            input_type=input_type,
            profile=profile,
            provider=provider.name,
            book_provider=book_provider.name,
            export_formats=[item.value for item in export_formats],
        )
        write_json(manifest_path, manifest.model_dump(mode="json"))
    else:
        ctx.logger.info("Stage ingest reused")
    write_run_summary(current_stage)

    current_stage = "split"
    if force or not chapters_path.exists():
        ctx.logger.info("Stage split started")
        normalized_text = normalized_path.read_text(encoding="utf-8")
        ingested = IngestedBook(
            book_id=ctx.book_id,
            title=input_path.stem,
            input_path=str(input_path),
            input_type=input_type,
            normalized_text=normalized_text,
        )
        chapters = split_into_chapters(ingested, settings)
        jsonl_dump(chapters_path, [chapter.model_dump(mode="json") for chapter in chapters])
    else:
        ctx.logger.info("Stage split reused")
    chapter_rows = jsonl_load(chapters_path)
    chapters = [ChapterRecord.model_validate(row) for row in chapter_rows]

    existing_analysis_rows: list[dict] = []
    if chapter_analysis_path.exists() and not force:
        existing_analysis_rows = [row.model_dump(mode="json") for row in load_persisted_chapter_truth()[0]]
    existing_analyses = [ChapterAnalysis.model_validate(row) for row in existing_analysis_rows]
    completed_ids = {row.chapter_id for row in existing_analyses}
    pending_chapters = [chapter for chapter in chapters if chapter.chapter_id not in completed_ids]

    if force:
        if chapter_analysis_path.exists():
            chapter_analysis_path.unlink()
        if chapter_failures_path.exists():
            chapter_failures_path.unlink()
        existing_analyses = []
        completed_ids = set()
        pending_chapters = list(chapters)
        chapter_analyses = []
        chapter_failures = []
    elif chapter_failures_path.exists():
        chapter_failures_path.unlink()

    chapter_stage_mutated = force or bool(pending_chapters)
    current_stage = "chapter-analyze"
    write_chapter_status(current_stage_name=current_stage)
    write_run_summary(current_stage)

    if pending_chapters:
        ctx.logger.info(
            "Stage chapter-analyze started (%s/%s completed, %s pending)",
            len(completed_ids),
            len(chapters),
            len(pending_chapters),
        )
        if not chapter_analysis_path.exists():
            chapter_analysis_path.parent.mkdir(parents=True, exist_ok=True)
            chapter_analysis_path.touch()

        chapter_positions = {chapter.chapter_id: index for index, chapter in enumerate(chapters, start=1)}
        chapter_retry_attempts = max(int(settings.pipeline.max_retries), 1)
        for chapter in pending_chapters:
            persisted_completed_ids = {row.chapter_id for row in load_persisted_chapter_truth()[0]}
            if chapter.chapter_id in persisted_completed_ids:
                completed_ids.add(chapter.chapter_id)
                chapter_index = chapter_positions[chapter.chapter_id]
                ctx.logger.info(
                    "Chapter %s/%s skipped because it already exists in persisted outputs: %s",
                    chapter_index,
                    len(chapters),
                    chapter.chapter_id,
                )
                write_chapter_status(current_stage_name=current_stage)
                write_run_summary(current_stage)
                continue
            chapter_index = chapter_positions[chapter.chapter_id]
            ctx.logger.info(
                "Chapter %s/%s started: %s (%s chars, %s split warnings)",
                chapter_index,
                len(chapters),
                chapter.chapter_id,
                len(chapter.raw_text),
                len(chapter.split_warnings),
            )

            def log_chunk_progress(
                event: str,
                chunk_index: int,
                total_chunks: int,
                *,
                _chapter=chapter,
                _chapter_index=chapter_index,
            ) -> None:
                remaining_chapters = len(chapters) - _chapter_index
                if event == "chunk_start":
                    ctx.logger.info(
                        "Chapter %s/%s chunk %s/%s analyzing for %s (remaining chapters after this: %s)",
                        _chapter_index,
                        len(chapters),
                        chunk_index,
                        total_chunks,
                        _chapter.chapter_id,
                        remaining_chapters,
                    )
                elif event == "chunk_done":
                    ctx.logger.info(
                        "Chapter %s/%s chunk %s/%s completed for %s",
                        _chapter_index,
                        len(chapters),
                        chunk_index,
                        total_chunks,
                        _chapter.chapter_id,
                    )
                elif event == "merge_start":
                    ctx.logger.info(
                        "Chapter %s/%s merge started for %s",
                        _chapter_index,
                        len(chapters),
                        _chapter.chapter_id,
                    )
                elif event == "merge_done":
                    ctx.logger.info(
                        "Chapter %s/%s merge completed for %s",
                        _chapter_index,
                        len(chapters),
                        _chapter.chapter_id,
                    )

            final_exc: Exception | None = None
            for chapter_attempt in range(1, chapter_retry_attempts + 1):
                try:
                    analysis, stats = analyze_chapter(
                        chapter=chapter,
                        provider=provider,
                        settings=settings,
                        model_name=settings.model_settings.chapter_model,
                        progress_callback=log_chunk_progress,
                    )
                    jsonl_upsert(chapter_analysis_path, analysis.model_dump(mode="json"), key_field="chapter_id")
                    existing_analyses.append(analysis)
                    completed_ids.add(chapter.chapter_id)
                    append_stage_stats(stats)
                    all_stats.extend(stats)
                    write_chapter_status(current_stage_name=current_stage, latest_completed=chapter)
                    write_run_summary(current_stage)
                    fallback_count = sum(
                        1 for stat in stats if "structured_path:chat.completions.json_object" in stat.warnings
                    )
                    total_latency_ms = sum(stat.latency_ms or 0 for stat in stats)
                    ctx.logger.info(
                        "Chapter %s/%s completed: %s with %s LLM calls (%s fallback calls, %sms total latency)",
                        chapter_index,
                        len(chapters),
                        chapter.chapter_id,
                        len(stats),
                        fallback_count,
                        total_latency_ms,
                    )
                    final_exc = None
                    break
                except Exception as exc:
                    final_exc = exc
                    if chapter_attempt < chapter_retry_attempts:
                        ctx.logger.warning(
                            "Chapter %s/%s attempt %s/%s failed: %s (%s); retrying",
                            chapter_index,
                            len(chapters),
                            chapter_attempt,
                            chapter_retry_attempts,
                            chapter.chapter_id,
                            type(exc).__name__,
                        )
                        continue

            if final_exc is not None:
                failure = ChapterFailureRecord(
                    chapter_id=chapter.chapter_id,
                    title=chapter.title,
                    order=chapter.order,
                    error_type=type(final_exc).__name__,
                    error_message=str(final_exc),
                )
                chapter_failures.append(failure)
                jsonl_upsert(chapter_failures_path, failure.model_dump(mode="json"), key_field="chapter_id")
                write_chapter_status(current_stage_name=current_stage, latest_failed=failure)
                write_run_summary(current_stage)
                ctx.logger.exception(
                    "Chapter %s/%s failed after %s attempts: %s (%s)",
                    chapter_index,
                    len(chapters),
                    chapter_retry_attempts,
                    chapter.chapter_id,
                    type(final_exc).__name__,
                    exc_info=(type(final_exc), final_exc, final_exc.__traceback__),
                )
        ctx.logger.info(
            "Stage chapter-analyze completed (%s/%s succeeded, %s failed)",
            len(completed_ids),
            len(chapters),
            len(chapter_failures),
        )
    else:
        ctx.logger.info("Stage chapter-analyze reused (%s/%s completed)", len(completed_ids), len(chapters))

    chapter_analyses, chapter_failures = load_persisted_chapter_truth()

    if chapter_failures:
        ctx.logger.warning(
            "Stage chapter-analyze completed with %s failed chapters; continuing to aggregate/export partial delivery",
            len(chapter_failures),
        )

    current_stage = "aggregate"
    write_run_summary(current_stage)
    if chapter_stage_mutated or not book_analysis_path.exists():
        ctx.logger.info("Stage aggregate started")
        if not chapter_analyses:
            raise RuntimeError("No successful chapter analyses available for aggregation")
        if all_stats:
            retained_stats = [stat for stat in all_stats if not stat.stage_name.startswith("aggregate_")]
            if len(retained_stats) != len(all_stats):
                all_stats = retained_stats
                rewrite_stage_history(all_stats)

        def log_aggregate_progress(event: str, batch_index: int, total_batches: int, stat: StageStats | None) -> None:
            if event == "batch_start":
                ctx.logger.info("Aggregate batch %s/%s started", batch_index, total_batches)
            elif event == "batch_done" and stat is not None:
                ctx.logger.info(
                    "Aggregate batch %s/%s completed (%sms, %s input / %s output, %s)",
                    batch_index,
                    total_batches,
                    stat.latency_ms or 0,
                    stat.input_tokens,
                    stat.output_tokens,
                    ", ".join(stat.warnings) if stat.warnings else "no warnings",
                )
            elif event == "final_start":
                ctx.logger.info("Aggregate final book merge started")
            elif event == "final_done" and stat is not None:
                ctx.logger.info(
                    "Aggregate final book merge completed (%sms, %s input / %s output, %s)",
                    stat.latency_ms or 0,
                    stat.input_tokens,
                    stat.output_tokens,
                    ", ".join(stat.warnings) if stat.warnings else "no warnings",
                )

        book_analysis, stats = aggregate_book(
            title=input_path.stem,
            chapter_analyses=chapter_analyses,
            batch_provider=provider,
            book_provider=book_provider,
            settings=settings,
            batch_model_name=settings.model_settings.chapter_model,
            book_model_name=settings.model_settings.book_model,
            artifact_dir=ctx.aggregate_dir,
            progress_callback=log_aggregate_progress,
        )
        write_json(book_analysis_path, book_analysis.model_dump(mode="json"))
        append_stage_stats(stats)
        all_stats.extend(stats)
        write_run_summary(current_stage)
        fallback_count = sum(1 for stat in stats if "structured_path:chat.completions.json_object" in stat.warnings)
        total_latency_ms = sum(stat.latency_ms or 0 for stat in stats)
        ctx.logger.info(
            "Aggregated book analysis with %s LLM calls using %s (%s fallback calls, %sms total latency)",
            len(stats),
            book_provider.name,
            fallback_count,
            total_latency_ms,
        )
    else:
        ctx.logger.info("Stage aggregate reused")
    book_analysis = postprocess_book_analysis(BookAnalysis.model_validate(read_json(book_analysis_path)), chapter_analyses)
    book_analysis = repair_delivery_weak_slots(book_analysis, chapter_analyses)
    write_json(book_analysis_path, book_analysis.model_dump(mode="json"))

    current_stage = "export"
    write_run_summary(current_stage)
    ctx.logger.info("Stage export started")
    finalized_outputs, eval_report, split_diagnostics, delivery_integrity_review, markdown_text = _finalize_delivery_outputs(
        ctx=ctx,
        book_analysis=book_analysis,
        chapter_analyses=chapter_analyses,
        export_formats=export_formats,
        expected_chapters=len(chapters),
        chapter_failures=chapter_failures,
    )
    outputs.update(finalized_outputs)
    stages: dict[str, int] = dict(seed_stage_counts)
    warnings: list[str] = []
    for stat in all_stats:
        if stat.stage_name != "resume_seed":
            stages[stat.stage_name] = stages.get(stat.stage_name, 0) + 1
        warnings.extend(stat.warnings)
    stage_stats = RunStatsSummary(
        total_calls=seed_totals["total_calls"] + len(all_stats),
        total_input_tokens=seed_totals["total_input_tokens"] + sum(stat.input_tokens for stat in all_stats),
        total_output_tokens=seed_totals["total_output_tokens"] + sum(stat.output_tokens for stat in all_stats),
        total_latency_ms=seed_totals["total_latency_ms"] + sum(stat.latency_ms or 0 for stat in all_stats),
        stages=stages,
        warnings=seed_warnings + warnings,
    )
    write_json(stage_stats_path, stage_stats.model_dump(mode="json"))
    final_stage = "completed_with_failures" if chapter_failures else "completed"
    write_run_summary(final_stage)
    write_chapter_status(current_stage_name=final_stage)
    outputs["eval"] = eval_path
    outputs["stage_stats"] = stage_stats_path
    outputs["run_summary"] = run_summary_path
    outputs["quality_review"] = quality_review_path
    outputs["reference_alignment_review"] = reference_alignment_review_path
    outputs["delivery_integrity_review"] = delivery_integrity_review_path
    outputs["split_diagnostics"] = split_diagnostics_path
    outputs["manifest"] = manifest_path
    outputs["chapters"] = chapters_path
    outputs["chapter_analysis"] = chapter_analysis_path
    if chapter_failures_path.exists():
        outputs["chapter_failures"] = chapter_failures_path
    outputs["book_analysis"] = book_analysis_path
    ctx.release_lock()
    return outputs


def _load_existing_chapter_analyses(path: Path) -> list[ChapterAnalysis]:
    if not path.exists():
        return []
    return [ChapterAnalysis.model_validate(row) for row in jsonl_load(path)]


def _load_existing_chapter_failures(path: Path) -> list[ChapterFailureRecord]:
    if not path.exists():
        return []
    return [ChapterFailureRecord.model_validate(row) for row in jsonl_load(path)]


def _resolve_expected_chapter_count(
    *,
    ctx: RunContext,
    analyzed_chapters: int,
    failed_chapters: int,
) -> int:
    chapters_path = ctx.split_dir / "chapters.jsonl"
    if chapters_path.exists():
        return len(jsonl_load(chapters_path))
    eval_path = ctx.eval_dir / "eval_report.json"
    if eval_path.exists():
        eval_report = EvalReport.model_validate(read_json(eval_path))
        if eval_report.expected_chapters > 0:
            return eval_report.expected_chapters
        if eval_report.total_chapters > 0:
            return eval_report.total_chapters
    return analyzed_chapters + failed_chapters


def _finalize_delivery_outputs(
    *,
    ctx: RunContext,
    book_analysis: BookAnalysis,
    chapter_analyses: list[ChapterAnalysis],
    export_formats: list[ExportFormat],
    expected_chapters: int,
    chapter_failures: list[ChapterFailureRecord],
) -> tuple[dict[str, Path], EvalReport, dict, object, str]:
    outputs: dict[str, Path] = {}
    book_analysis_path = ctx.aggregate_dir / "book_analysis.json"
    eval_path = ctx.eval_dir / "eval_report.json"
    quality_review_path = ctx.eval_dir / "quality_review.json"
    split_diagnostics_path = ctx.eval_dir / "chapter_split_diagnostics.json"
    reference_alignment_review_path = ctx.eval_dir / "reference_alignment_review.json"
    delivery_integrity_review_path = ctx.eval_dir / "delivery_integrity_review.json"

    write_json(book_analysis_path, book_analysis.model_dump(mode="json"))

    final_report_blocks = build_delivery_report(book_analysis, chapter_analyses, include_debug=False)
    integrity_round_issue_counts: list[int] = []
    delivery_integrity_review = None
    for round_index in range(2):
        markdown_text = render_markdown(final_report_blocks)
        delivery_integrity_review = build_delivery_integrity_review(
            final_report_blocks,
            rendered_report=markdown_text,
            round_issue_counts=integrity_round_issue_counts[:],
        )
        integrity_round_issue_counts.append(delivery_integrity_review.total_issue_count)
        should_retry_placeholders = _report_has_delivery_placeholders(markdown_text) and round_index == 0
        should_retry_integrity = (
            delivery_integrity_review.repairable_issue_count > 0
            and delivery_integrity_review.total_issue_count > 0
            and round_index == 0
        )
        if not should_retry_placeholders and not should_retry_integrity:
            break
        if should_retry_placeholders:
            ctx.logger.info("Delivery inspection found weak placeholders; applying repair rerender")
            book_analysis = repair_delivery_weak_slots(book_analysis, chapter_analyses)
            write_json(book_analysis_path, book_analysis.model_dump(mode="json"))
            final_report_blocks = build_delivery_report(book_analysis, chapter_analyses, include_debug=False)
        if should_retry_integrity:
            ctx.logger.info(
                "Delivery integrity review found %s issues; applying targeted report repair",
                delivery_integrity_review.total_issue_count,
            )
            final_report_blocks = repair_delivery_report_blocks(final_report_blocks)

    markdown_path = ctx.export_dir / "book_analysis.md"
    markdown_text = render_markdown(final_report_blocks)
    final_integrity_issue_count = build_delivery_integrity_review(final_report_blocks, rendered_report=markdown_text).total_issue_count
    delivery_integrity_review = build_delivery_integrity_review(
        final_report_blocks,
        rendered_report=markdown_text,
        round_issue_counts=integrity_round_issue_counts + [final_integrity_issue_count],
    )
    write_json(delivery_integrity_review_path, delivery_integrity_review.model_dump(mode="json"))
    markdown_path.write_text(markdown_text, encoding="utf-8")
    outputs["markdown"] = markdown_path

    debug_markdown_path = ctx.export_dir / "book_analysis.debug.md"
    debug_markdown = render_markdown(build_delivery_report(book_analysis, chapter_analyses, include_debug=True))
    debug_markdown_path.write_text(debug_markdown, encoding="utf-8")
    outputs["markdown_debug"] = debug_markdown_path

    produced_exports = ["markdown"]
    if ExportFormat.DOCX in export_formats:
        docx_path = ctx.export_dir / "book_analysis.docx"
        export_docx(final_report_blocks, docx_path)
        outputs["docx"] = docx_path
        produced_exports.append("docx")
    if ExportFormat.PDF in export_formats:
        pdf_path = ctx.export_dir / "book_analysis.pdf"
        export_pdf(final_report_blocks, pdf_path)
        outputs["pdf"] = pdf_path
        produced_exports.append("pdf")

    split_diagnostics = build_split_diagnostics(chapter_analyses)
    write_json(split_diagnostics_path, split_diagnostics)

    eval_report = evaluate_run(
        book_analysis,
        chapter_analyses,
        produced_exports,
        expected_chapters=expected_chapters,
        failures=chapter_failures,
    )
    write_json(eval_path, eval_report.model_dump(mode="json"))

    quality_review = review_delivery_quality(
        book_analysis,
        chapter_analyses,
        eval_report,
        exported_formats=produced_exports,
        rendered_report=markdown_text,
        degraded_split_chapters=sum(1 for chapter in chapter_analyses if getattr(chapter, "split_warnings", [])),
        split_group_count=int(split_diagnostics["group_count"]),
        delivery_integrity_review=delivery_integrity_review,
    )
    write_json(quality_review_path, quality_review.model_dump(mode="json"))

    reference_alignment_review = build_reference_alignment_review(
        book_analysis,
        chapter_analyses,
        rendered_report=markdown_text,
    )
    write_json(reference_alignment_review_path, reference_alignment_review.model_dump(mode="json"))

    outputs["eval"] = eval_path
    outputs["quality_review"] = quality_review_path
    outputs["reference_alignment_review"] = reference_alignment_review_path
    outputs["delivery_integrity_review"] = delivery_integrity_review_path
    outputs["split_diagnostics"] = split_diagnostics_path
    outputs["book_analysis"] = book_analysis_path
    return outputs, eval_report, split_diagnostics, delivery_integrity_review, markdown_text


def _estimate_cost_cny(stats: list[StageStats]) -> float | None:
    if not stats:
        return None
    total_cost = 0.0
    counted = 0
    for stat in stats:
        if not stat.model:
            continue
        cost = _estimate_model_cost_cny(stat)
        if cost is None:
            continue
        total_cost += cost
        counted += 1
    if counted == 0:
        return None
    return round(total_cost, 4)


def _merge_estimated_cost(seed_cost: float | None, current_cost: float | None) -> float | None:
    if seed_cost is None and current_cost is None:
        return None
    return round((seed_cost or 0.0) + (current_cost or 0.0), 4)


def _report_has_delivery_placeholders(markdown_text: str) -> bool:
    return bool(re.search(r"信息仍需进一步提炼|未命名条目", markdown_text))


def _estimate_model_cost_cny(stat: StageStats) -> float | None:
    model = (stat.model or "").lower()
    input_tokens = stat.input_tokens or 0
    output_tokens = stat.output_tokens or 0
    if "qwen-long" in model:
        return (input_tokens / 1000.0) * 0.0005 + (output_tokens / 1000.0) * 0.002
    if "qwen-plus" in model:
        return (input_tokens / 1_000_000.0) * 0.8 + (output_tokens / 1_000_000.0) * 2.0
    if "qwen-flash" in model:
        return (input_tokens / 1_000_000.0) * 0.2 + (output_tokens / 1_000_000.0) * 0.6
    return None


def _build_split_quality_note(chapters: list[ChapterRecord], degraded_split_chapters: int) -> str:
    if not chapters:
        return "未切出章节。"
    if degraded_split_chapters == 0:
        return f"共切出 {len(chapters)} 个章节，未命中降级切块。"
    return (
        f"共切出 {len(chapters)} 个章节/块，其中 {degraded_split_chapters} 个包含 split warnings。"
        "当前文本切章依赖降级切块，后续需要重点观察是否影响章节纲要和情感线阶段表达。"
    )
