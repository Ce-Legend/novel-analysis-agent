from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
import re

from ..config import AppSettings
from ..providers.base import LLMProvider
from ..schemas import (
    AudiencePositioning,
    BatchSummary,
    BeatRhythmItem,
    BookAnalysis,
    ChapterAnalysis,
    ChapterOutlineItem,
    CharacterProfile,
    CPAnalysis,
    CPTopic,
    DeliveryUnit,
    HighlightSummaryItem,
    OpeningCraft,
    OutlineBeat,
    PhaseOutlineItem,
    PlotOutline,
    RelationshipProgression,
    RelationshipStage,
    SceneQuoteItem,
    SellingPointItem,
    StageStats,
    StyleSummary,
    StoryHookLayers,
    StoryLineItem,
    StyleSignal,
    TitleIntroAnalysis,
    WritingBreakdown,
)
from ..utils import batched


@dataclass
class NarrativeUnit:
    base_title: str
    chapters: list[ChapterAnalysis] = field(default_factory=list)
    boundary_signals: list[str] = field(default_factory=list)


def aggregate_book(
    *,
    title: str,
    chapter_analyses: list[ChapterAnalysis],
    batch_provider: LLMProvider,
    book_provider: LLMProvider,
    settings: AppSettings,
    batch_model_name: str,
    book_model_name: str,
    artifact_dir: Path | None = None,
    progress_callback: Callable[[str, int, int, StageStats | None], None] | None = None,
) -> tuple[BookAnalysis, list[StageStats]]:
    stats: list[StageStats] = []
    batch_summaries: list[BatchSummary] = []
    batches = list(batched(chapter_analyses, settings.pipeline.aggregate_batch_size))

    for index, batch in enumerate(batches, start=1):
        if progress_callback is not None:
            progress_callback("batch_start", index, len(batches), None)
        result, batch_stats = batch_provider.generate_structured(
            response_model=BatchSummary,
            model=batch_model_name,
            system_prompt=_batch_system_prompt(),
            user_prompt=_batch_user_prompt(title, index, batch),
            metadata={
                "batch_label": f"batch-{index:02d}",
                "chapter_analyses": batch,
            },
        )
        batch_stats.stage_name = "aggregate_batch"
        batch_summaries.append(result)
        stats.append(batch_stats)
        if progress_callback is not None:
            progress_callback("batch_done", index, len(batches), batch_stats)

    if progress_callback is not None:
        progress_callback("final_start", len(batches), len(batches), None)
    final_user_prompt = _book_user_prompt(title, batch_summaries, chapter_analyses)
    final_metadata = {
        "title": title,
        "batch_summaries": batch_summaries,
        "chapter_analyses": chapter_analyses,
    }
    if artifact_dir is not None and book_provider.name == "bailian-long":
        aggregate_input_path = artifact_dir / "qwen_long_book_input.json"
        aggregate_input_path.write_text(
            json.dumps(
                {
                    "title": title,
                    "batch_summaries": [item.model_dump(mode="json") for item in batch_summaries],
                    "chapter_analyses": [item.model_dump(mode="json") for item in chapter_analyses],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        final_user_prompt = _book_file_user_prompt(title, len(batch_summaries), len(chapter_analyses))
        final_metadata["aggregate_input_path"] = str(aggregate_input_path)
        final_metadata["aggregate_upload_metadata_path"] = str(artifact_dir / "qwen_long_upload.json")

    final_result, final_stats = book_provider.generate_structured(
        response_model=BookAnalysis,
        model=book_model_name,
        system_prompt=_book_system_prompt(),
        user_prompt=final_user_prompt,
        metadata=final_metadata,
    )
    final_stats.stage_name = "aggregate_book"
    stats.append(final_stats)
    final_result = postprocess_book_analysis(final_result, chapter_analyses)
    if progress_callback is not None:
        progress_callback("final_done", len(batches), len(batches), final_stats)
    return final_result, stats


def postprocess_book_analysis(book: BookAnalysis, chapter_analyses: list[ChapterAnalysis]) -> BookAnalysis:
    rebuilt_outlines = _rebuild_chapter_outlines(book, chapter_analyses)
    delivery_units = build_delivery_units(chapter_analyses)
    normalized_characters = _normalize_character_profiles(book, chapter_analyses, delivery_units)
    rebuilt_timeline = _normalize_relationship_timeline(book, chapter_analyses, delivery_units, normalized_characters)
    rebuilt_main_outline = _normalize_main_outline(book, delivery_units)
    normalized_style_summary = _normalize_style_summary(book, chapter_analyses, delivery_units)
    normalized_cp_analysis = _normalize_cp_analysis(book, rebuilt_timeline, delivery_units, chapter_analyses, normalized_characters)
    normalized_plot_outline = _normalize_plot_outline(
        book.model_copy(update={"cp_analysis": normalized_cp_analysis}),
        rebuilt_main_outline,
        chapter_analyses,
        delivery_units,
        rebuilt_timeline,
    )
    normalized_opening_craft = _normalize_opening_craft(
        book.model_copy(update={"character_profiles": normalized_characters}),
        chapter_analyses,
    )

    return book.model_copy(
        update={
            "highlights_summary": _normalize_highlights_summary(book),
            "selling_points_detail": _normalize_selling_points_detail(book),
            "story_hook_layers": _normalize_story_hook_layers(book),
            "title_intro_analysis": _normalize_title_intro_analysis(book, delivery_units),
            "audience_positioning": _normalize_audience_positioning(book),
            "character_profiles": normalized_characters,
            "cp_analysis": normalized_cp_analysis,
            "main_outline": rebuilt_main_outline,
            "plot_outline": normalized_plot_outline,
            "opening_craft": normalized_opening_craft,
            "chapter_outlines": rebuilt_outlines,
            "delivery_units": delivery_units,
            "relationship_timeline": rebuilt_timeline,
            "style_summary": normalized_style_summary,
            "writing_breakdown": _normalize_writing_breakdown(book, chapter_analyses, normalized_style_summary, delivery_units),
        }
    )


def repair_delivery_weak_slots(book: BookAnalysis, chapter_analyses: list[ChapterAnalysis]) -> BookAnalysis:
    delivery_units = _repair_delivery_units(book.delivery_units or build_delivery_units(chapter_analyses))
    normalized_characters = _normalize_character_profiles(book, chapter_analyses, delivery_units)
    relationship_timeline = _repair_relationship_timeline(book.relationship_timeline, delivery_units, chapter_analyses)
    cp_analysis = _normalize_cp_analysis(book, relationship_timeline, delivery_units, chapter_analyses, normalized_characters)
    plot_outline = _repair_plot_outline(
        book.model_copy(update={"cp_analysis": cp_analysis}),
        delivery_units,
        relationship_timeline,
        chapter_analyses,
    )
    opening_craft = _normalize_opening_craft(
        book.model_copy(update={"character_profiles": normalized_characters}),
        chapter_analyses,
    )
    return book.model_copy(
        update={
            "delivery_units": delivery_units,
            "relationship_timeline": relationship_timeline,
            "cp_analysis": cp_analysis,
            "plot_outline": plot_outline,
            "opening_craft": opening_craft,
        }
    )


def build_delivery_units(chapter_analyses: list[ChapterAnalysis]) -> list[DeliveryUnit]:
    narrative_units = _build_narrative_units(chapter_analyses)
    return [_narrative_unit_to_delivery_unit(index, unit) for index, unit in enumerate(narrative_units, start=1)]


def build_split_diagnostics(chapter_analyses: list[ChapterAnalysis]) -> dict[str, object]:
    groups = _build_narrative_units(chapter_analyses)

    return {
        "group_count": len(groups),
        "analysis_unit_count": len(chapter_analyses),
        "groups": [
            {
                "base_title": group.base_title,
                "chapter_count": len(group.chapters),
                "chapter_ids": [chapter.chapter_id for chapter in group.chapters],
                "chapter_range": _chapter_range([chapter.chapter_id for chapter in group.chapters]),
                "titles": [chapter.title for chapter in group.chapters[:3]],
                "boundary_signals": group.boundary_signals,
                "summary_preview": _join_preview([_build_one_line(chapter) for chapter in group.chapters]),
            }
            for group in groups
        ],
    }


def _rebuild_chapter_outlines(book: BookAnalysis, chapter_analyses: list[ChapterAnalysis]) -> list[ChapterOutlineItem]:
    outline_map = {item.chapter_id: item for item in book.chapter_outlines}
    rebuilt_outlines: list[ChapterOutlineItem] = []
    for chapter in chapter_analyses:
        existing = outline_map.get(chapter.chapter_id)
        rebuilt_outlines.append(
            ChapterOutlineItem(
                chapter_id=chapter.chapter_id,
                title=chapter.title,
                one_line=(existing.one_line if existing and existing.one_line.strip() else _build_one_line(chapter)),
                key_conflict=(
                    existing.key_conflict
                    if existing and existing.key_conflict.strip()
                    else _build_key_conflict(chapter)
                ),
                emotional_progression=(
                    existing.emotional_progression
                    if existing and existing.emotional_progression.strip()
                    else _build_emotional_progression(chapter)
                ),
                plot=(existing.plot if existing and existing.plot.strip() else _build_plot_card(chapter)),
                crisis=(existing.crisis if existing and existing.crisis.strip() else _first_nonempty(chapter.crisis, _build_key_conflict(chapter))),
                foreshadowing=(
                    existing.foreshadowing
                    if existing and existing.foreshadowing.strip()
                    else _first_nonempty(chapter.foreshadowing, "伏笔待补充。")
                ),
                suspense=(
                    existing.suspense
                    if existing and existing.suspense.strip()
                    else _first_nonempty(chapter.suspense, "悬念待补充。")
                ),
                climax=(
                    existing.climax
                    if existing and existing.climax.strip()
                    else _first_nonempty(chapter.climax, "高潮待补充。")
                ),
                payoff=(
                    existing.payoff
                    if existing and existing.payoff.strip()
                    else _first_nonempty(chapter.highlights or chapter.payoff, "爽点待补充。")
                ),
                beats=(existing.beats if existing and existing.beats else [_format_beat_card(item) for item in chapter.beat_rhythm[:4]]),
                signature_scenes=(
                    existing.signature_scenes
                    if existing and existing.signature_scenes
                    else [_format_scene_card(item) for item in chapter.scene_quotes[:3]]
                ),
                relationship_progress=(
                    existing.relationship_progress
                    if existing and existing.relationship_progress
                    else [_format_relationship_card(item) for item in chapter.relationship_progression[:4]]
                ),
                style_signals=(
                    existing.style_signals
                    if existing and existing.style_signals
                    else [_format_style_card(item) for item in chapter.style_signals[:4]]
                ),
            )
        )
    return rebuilt_outlines


def _normalize_main_outline(book: BookAnalysis, delivery_units: list[DeliveryUnit]) -> list[OutlineBeat]:
    rebuilt = [
        OutlineBeat(
            label=beat.label.strip() or "主线阶段",
            chapter_refs=sorted(beat.chapter_refs, key=_chapter_sort_key),
            description=beat.description.strip(),
        )
        for beat in book.main_outline
        if beat.description.strip()
    ]
    if rebuilt:
        return rebuilt

    fallback: list[OutlineBeat] = []
    for unit in delivery_units[: min(len(delivery_units), 8)]:
        fallback.append(
            OutlineBeat(
                label=unit.title,
                chapter_refs=unit.chapter_refs,
                description=unit.summary,
            )
        )
    return fallback


def _normalize_relationship_timeline(
    book: BookAnalysis,
    chapter_analyses: list[ChapterAnalysis],
    delivery_units: list[DeliveryUnit],
    character_profiles: list[CharacterProfile],
) -> list[RelationshipStage]:
    dominant_pair = _resolve_primary_pair(chapter_analyses, character_profiles)
    target_groups = _target_stage_group_count(delivery_units)
    return _build_synthetic_relationship_timeline(
        delivery_units,
        chapter_analyses,
        dominant_pair,
        target_groups=target_groups,
    )


def _dedupe_relationship_stages(stages: list[RelationshipStage]) -> list[RelationshipStage]:
    deduped: list[RelationshipStage] = []
    seen: set[str] = set()
    for stage in stages:
        key = "|".join(
            [
                stage.pair.strip(),
                stage.stage_label.strip(),
                stage.chapter_range or _chapter_range(stage.chapter_refs) or "",
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(_with_chapter_range(stage))
    return deduped


def _resolve_primary_pair(
    chapter_analyses: list[ChapterAnalysis],
    character_profiles: list[CharacterProfile],
) -> str:
    counts: dict[str, int] = {}
    for chapter in chapter_analyses:
        for item in chapter.relationship_progression:
            counterpart = item.counterpart.strip()
            if counterpart:
                counts[counterpart] = counts.get(counterpart, 0) + 1
    if counts:
        pair_like = [(name, score) for name, score in counts.items() if "&" in name]
        if pair_like:
            return max(pair_like, key=lambda item: item[1])[0]
    top_names = [profile.name.strip() for profile in character_profiles if profile.name.strip()][:4]
    if len(top_names) >= 2:
        return f"{top_names[0]} & {top_names[1]}"
    if counts:
        return max(counts.items(), key=lambda item: (item[1], len(item[0])))[0]
    return "核心关系"


def _build_synthetic_relationship_timeline(
    delivery_units: list[DeliveryUnit],
    chapter_analyses: list[ChapterAnalysis],
    dominant_pair: str,
    *,
    target_groups: int = 4,
) -> list[RelationshipStage]:
    if not delivery_units:
        return []
    chapter_map = {chapter.chapter_id: chapter for chapter in chapter_analyses}
    pair_names = [part.strip() for part in re.split(r"\s*&\s*", dominant_pair) if part.strip()]
    relevant_units = _filter_units_for_pair(delivery_units, chapter_map, pair_names)
    source_units = relevant_units if len(relevant_units) >= 4 else delivery_units
    if len(source_units) < 4:
        source_units = _chapters_to_delivery_units(chapter_analyses, pair_names)[: max(4, min(6, len(chapter_analyses)))]
    labels = ["试探启动", "关系升温", "战略共谋", "危机拉扯", "创伤共担", "终局确认"]
    groups = _chunk_units(source_units, target_groups=min(target_groups, len(source_units)))
    stages: list[RelationshipStage] = []
    for index, group in enumerate(groups):
        chapter_refs = [ref for unit in group for ref in unit.chapter_refs]
        core_change = _extract_stage_signal(group, source="summary", fallback="关系进入新的推进阶段。")
        pressure = _extract_stage_signal(group, source="pressure", fallback="现实压力同步压上。")
        payoff = _extract_stage_signal(group, source="payoff", fallback="阶段性情感回收形成新的关系锚点。")
        stages.append(
            RelationshipStage(
                pair=dominant_pair,
                stage_label=labels[index] if index < len(labels) else f"阶段{index + 1}",
                chapter_refs=chapter_refs,
                description=_build_synthetic_stage_description(core_change, pressure, payoff),
                core_change=core_change,
                pressure=pressure,
                payoff=payoff,
            )
        )
    return [_with_chapter_range(_strengthen_relationship_stage(stage)) for stage in stages]


def _target_stage_group_count(delivery_units: list[DeliveryUnit]) -> int:
    count = len(delivery_units)
    if count >= 30:
        return 6
    if count >= 18:
        return 5
    return 4


def _chunk_units(units: list[DeliveryUnit], *, target_groups: int) -> list[list[DeliveryUnit]]:
    if not units:
        return []
    if target_groups <= 1:
        return [units]
    chunk_size = max(1, len(units) // target_groups)
    groups: list[list[DeliveryUnit]] = []
    start = 0
    for index in range(target_groups):
        remaining_groups = target_groups - index
        remaining_items = len(units) - start
        size = max(1, remaining_items // remaining_groups)
        groups.append(units[start : start + size])
        start += size
    if start < len(units):
        groups[-1].extend(units[start:])
    return [group for group in groups if group]


def _filter_units_for_pair(
    delivery_units: list[DeliveryUnit],
    chapter_map: dict[str, ChapterAnalysis],
    pair_names: list[str],
) -> list[DeliveryUnit]:
    if not pair_names:
        return []
    results: list[DeliveryUnit] = []
    for unit in delivery_units:
        matched = False
        for chapter_id in unit.chapter_refs:
            chapter = chapter_map.get(chapter_id)
            if chapter is None:
                continue
            if any(name in chapter.key_characters for name in pair_names):
                matched = True
            for item in chapter.relationship_progression:
                counterpart = item.counterpart.strip()
                if any(name and name in counterpart for name in pair_names):
                    matched = True
                    break
            if matched:
                break
        if matched:
            results.append(unit)
    return results


def _extract_stage_signal(units: list[DeliveryUnit], *, source: str, fallback: str) -> str:
    candidates = _collect_stage_signal_candidates(units, source=source)
    detailed = _join_detailed_sentences(candidates, limit=2)
    return detailed or fallback


def _collect_stage_signal_candidates(units: list[DeliveryUnit], *, source: str) -> list[str]:
    candidates: list[str] = []
    for unit in units:
        if source == "summary":
            candidates.extend(
                value
                for value in (
                    unit.summary,
                    *unit.highlights[:1],
                    *[item.change for item in unit.relationship_progression[:1]],
                    *[item.details for item in unit.beat_rhythm[:1] if hasattr(item, "details")],
                )
                if value
            )
        elif source == "pressure":
            candidates.extend(value for value in (*unit.crisis[:2], *unit.suspense[:2], unit.summary) if value)
        elif source == "payoff":
            candidates.extend(value for value in (*unit.highlights[:2], *unit.payoff[:2], *unit.climax[:1], unit.summary) if value)
    cleaned = [_clean_delivery_sentence(value) for value in candidates]
    return _unique_nonempty([value for value in cleaned if value])


def _clean_delivery_sentence(text: str) -> str:
    cleaned = _first_sentence(text).strip("；：，、 ")
    if not cleaned:
        return ""
    if _needs_delivery_repair(cleaned) or _is_weak_book_copy(cleaned):
        return ""
    return cleaned


def _join_detailed_sentences(values: list[str], *, limit: int) -> str:
    selected: list[str] = []
    for value in values:
        cleaned = _clean_delivery_sentence(value)
        if not cleaned or cleaned in selected:
            continue
        selected.append(cleaned)
        if len(selected) >= limit:
            break
    return "；".join(selected)


def _chapters_to_delivery_units(chapter_analyses: list[ChapterAnalysis], pair_names: list[str]) -> list[DeliveryUnit]:
    results: list[DeliveryUnit] = []
    for index, chapter in enumerate(chapter_analyses, start=1):
        if pair_names and not (
            any(name in chapter.key_characters for name in pair_names)
            or any(any(name in item.counterpart for name in pair_names) for item in chapter.relationship_progression)
        ):
            continue
        results.append(
            DeliveryUnit(
                unit_id=f"synthetic-unit-{index:03d}",
                title=chapter.title,
                chapter_refs=[chapter.chapter_id],
                chapter_range=_chapter_range([chapter.chapter_id]),
                summary=chapter.summary,
                crisis=chapter.crisis,
                foreshadowing=chapter.foreshadowing,
                suspense=chapter.suspense,
                climax=chapter.climax,
                payoff=chapter.payoff,
                highlights=chapter.highlights,
                beat_rhythm=chapter.beat_rhythm,
                scene_quotes=chapter.scene_quotes,
                relationship_progression=chapter.relationship_progression,
                style_signals=chapter.style_signals,
            )
        )
    return results


def _build_synthetic_stage_description(core_change: str, pressure: str, payoff: str) -> str:
    return "；".join(
        part
        for part in [
            f"这一阶段，{core_change.strip()}" if core_change.strip() else "",
            f"压力：{pressure.strip()}" if pressure.strip() else "",
            f"回收：{payoff.strip()}" if payoff.strip() else "",
        ]
        if part
    )


def _strengthen_relationship_stage(stage: RelationshipStage) -> RelationshipStage:
    core_change = stage.core_change.strip()
    if _needs_delivery_repair(core_change):
        core_change = _fallback_stage_core_change(stage.stage_label)
    pressure = stage.pressure.strip()
    if _needs_delivery_repair(pressure):
        pressure = _fallback_stage_pressure(stage.stage_label)
    payoff = stage.payoff.strip()
    if _needs_delivery_repair(payoff) or not _is_relational_payoff(payoff):
        payoff = _fallback_stage_payoff(stage.stage_label)
    description = stage.description.strip()
    if not description or _is_weak_book_copy(description):
        description = f"{core_change}，但{pressure}，最终{payoff}。"
    return stage.model_copy(
        update={
            "core_change": core_change,
            "pressure": pressure,
            "payoff": payoff,
            "description": description,
        }
    )


def _fallback_stage_core_change(stage_label: str) -> str:
    fallback_map = {
        "试探启动": "两人的关系从谨慎试探转入可感知的相互牵引",
        "关系升温": "关系从试探推进到更明确的靠近",
        "战略共谋": "情感与主线利益开始被放到同一张牌桌上",
        "危机拉扯": "关系在现实阻力中被迫重新站队",
        "创伤共担": "双方开始把旧伤和代价一起扛起来",
        "终局确认": "关系通过共同选择完成最终确认",
    }
    return fallback_map.get(stage_label, "关系进入新的阶段判断")


def _fallback_stage_pressure(stage_label: str) -> str:
    fallback_map = {
        "试探启动": "双方都不愿先交底，边界感仍然很强",
        "关系升温": "靠近之后反而更难维持原有防线",
        "战略共谋": "主线决策与身份压力不断把关系往前推",
        "危机拉扯": "外部阻力和内部误会同时挤压关系空间",
        "创伤共担": "旧伤回潮让两人必须面对更深层的脆弱",
        "终局确认": "终局代价要求双方给出明确答案",
    }
    return fallback_map.get(stage_label, "现实压力持续压在关系线上")


def _fallback_stage_payoff(stage_label: str) -> str:
    fallback_map = {
        "试探启动": "后续更深层的靠近有了成立基础",
        "关系升温": "亲密关系第一次获得阶段性确认",
        "战略共谋": "关系从情绪拉扯推进到共同决策",
        "危机拉扯": "前期埋下的矛盾被集中推到台前",
        "创伤共担": "信任开始从情绪安慰转向共同承担",
        "终局确认": "前文所有拉扯都获得了明确回收",
    }
    return fallback_map.get(stage_label, "这一阶段形成新的关系锚点")


def _rebuild_genre_labels(book: BookAnalysis) -> str:
    collected: list[str] = []
    sources = [
        book.title_intro_analysis.genre,
        *book.positioning,
        *book.selling_points,
        *book.core_hooks,
        *book.story_hook_layers.short_term,
        *book.story_hook_layers.mid_term,
        *book.story_hook_layers.long_term,
        book.overview,
        book.title_intro_analysis.title_analysis,
        book.title_intro_analysis.intro_analysis,
    ]
    tag_patterns = [
        ("都市情感", [r"都市情感", r"都市恋爱", r"都市关系"]),
        ("金融职场", [r"金融职场", r"金融", r"投行", r"咨询", r"职场"]),
        ("百合向", [r"百合向", r"百合", r"女女", r"双女主"]),
        ("商战", [r"商战", r"资本博弈"]),
        ("双强", [r"双强"]),
    ]
    for text in sources:
        cleaned = text.strip()
        if not cleaned:
            continue
        for label, patterns in tag_patterns:
            if label in collected:
                continue
            if any(re.search(pattern, cleaned, flags=re.IGNORECASE) for pattern in patterns):
                collected.append(label)
    if collected:
        return " / ".join(collected[:3])

    raw = book.title_intro_analysis.genre.strip()
    if raw and not _is_weak_book_copy(raw):
        parts = [part.strip() for part in re.split(r"[+／/｜|、，,\s]+", raw) if part.strip()]
        if parts:
            return " / ".join(_unique_nonempty(parts)[:3])
    return ""


def _normalize_title_intro_analysis(book: BookAnalysis, delivery_units: list[DeliveryUnit]) -> TitleIntroAnalysis:
    analysis = book.title_intro_analysis.model_copy()
    if not analysis.title_analysis.strip():
        analysis.title_analysis = f"{book.title} 直接点题核心关系和主线冲突。"
    if not analysis.core_hook.strip():
        analysis.core_hook = (book.core_hooks[0] if book.core_hooks else "") or (
            book.selling_points[0] if book.selling_points else ""
        )
    rebuilt_genre = _rebuild_genre_labels(book)
    if rebuilt_genre:
        analysis.genre = rebuilt_genre
    elif not analysis.genre.strip() and book.positioning:
        analysis.genre = book.positioning[0]
    if not analysis.intro_analysis.strip() or _is_weak_book_copy(analysis.intro_analysis):
        analysis.intro_analysis = _first_sentence(book.overview) or book.overview
    if not analysis.chapter_name_analysis.strip():
        if delivery_units:
            analysis.chapter_name_analysis = "章节/单元标题围绕关系推进和关键冲突组织，便于拆书汇总。"
        else:
            analysis.chapter_name_analysis = "章节命名分析待结合完整产物补充。"
    return analysis


def _normalize_highlights_summary(book: BookAnalysis) -> list[HighlightSummaryItem]:
    items = [
        HighlightSummaryItem(
            title=item.title.strip() or _short_label(item.detail, fallback="核心亮点"),
            detail=item.detail.strip() or item.title.strip(),
        )
        for item in book.highlights_summary
        if item.title.strip() or item.detail.strip()
    ]
    if items:
        return items

    source = book.selling_points or book.core_hooks or [_first_sentence(book.overview)]
    return [
        HighlightSummaryItem(
            title=_short_label(text, fallback=f"亮点{index}"),
            detail=text.strip(),
        )
        for index, text in enumerate(source[:4], start=1)
        if text.strip()
    ]


def _normalize_selling_points_detail(book: BookAnalysis) -> list[SellingPointItem]:
    items = [
        SellingPointItem(
            category=item.category.strip() or f"卖点{index}",
            detail=item.detail.strip(),
        )
        for index, item in enumerate(book.selling_points_detail, start=1)
        if item.category.strip() or item.detail.strip()
    ]
    if items:
        return items

    fallback_categories = ["情感向", "人设向", "题材向", "剧情向", "关系向", "情绪向"]
    source = book.selling_points or book.core_hooks
    rebuilt: list[SellingPointItem] = []
    for index, text in enumerate(source[: len(fallback_categories)]):
        cleaned = text.strip()
        if not cleaned:
            continue
        rebuilt.append(SellingPointItem(category=fallback_categories[index], detail=cleaned))
    return rebuilt


def _normalize_story_hook_layers(book: BookAnalysis) -> StoryHookLayers:
    layers = book.story_hook_layers.model_copy()
    if not layers.short_term:
        layers.short_term = list(book.audience_positioning.short_term_hooks[:4]) or list(book.selling_points[:2])
    if not layers.mid_term:
        layers.mid_term = list(book.audience_positioning.mid_term_hooks[:4]) or list(book.selling_points[2:4])
    if not layers.long_term:
        layers.long_term = list(book.audience_positioning.long_term_hooks[:4]) or list(book.core_hooks[:3])
    return layers


def _normalize_audience_positioning(book: BookAnalysis) -> AudiencePositioning:
    positioning = book.audience_positioning.model_copy()
    if not positioning.reader_profile:
        positioning.reader_profile = list(book.positioning[:3])
    if not positioning.marketing_keywords:
        positioning.marketing_keywords = list(book.core_hooks[:5])
    if not positioning.short_term_hooks:
        positioning.short_term_hooks = list(book.story_hook_layers.short_term[:4]) or list(book.selling_points[:2])
    if not positioning.mid_term_hooks:
        positioning.mid_term_hooks = list(book.story_hook_layers.mid_term[:4]) or list(book.selling_points[2:4])
    if not positioning.long_term_hooks:
        positioning.long_term_hooks = list(book.story_hook_layers.long_term[:4]) or list(book.core_hooks[:2])
    return positioning


def _normalize_character_profiles(
    book: BookAnalysis,
    chapter_analyses: list[ChapterAnalysis],
    delivery_units: list[DeliveryUnit],
) -> list[CharacterProfile]:
    synthesized = _synthesize_character_profiles(chapter_analyses, delivery_units)
    rebuilt: list[CharacterProfile] = []
    for character in book.character_profiles:
        personality_traits = list(character.personality_traits or character.traits)
        major_experiences = list(character.major_experiences)
        if not major_experiences and character.arc.strip():
            major_experiences = [character.arc.strip()]
        fallback = next((item for item in synthesized if item.name.strip() == character.name.strip()), None)
        appearance = _clean_character_appearance(character.appearance)
        if not appearance and fallback is not None:
            appearance = _clean_character_appearance(fallback.appearance)
        if not appearance:
            appearance = _infer_character_appearance(character.name, chapter_analyses, delivery_units)
        rebuilt.append(
            character.model_copy(
                update={
                    "basic_info": character.basic_info.strip() or character.role.strip() or (fallback.basic_info if fallback else "核心角色"),
                    "appearance": appearance,
                    "personality_traits": personality_traits or (list(fallback.personality_traits) if fallback else []),
                    "major_experiences": major_experiences or (list(fallback.major_experiences) if fallback else []),
                    "relationships": list(character.relationships) or (list(fallback.relationships) if fallback else []),
                }
            )
        )
    if not rebuilt:
        return synthesized
    seen = {item.name.strip() for item in rebuilt if item.name.strip()}
    for item in synthesized:
        name = item.name.strip()
        if not name or name in seen:
            continue
        rebuilt.append(item)
        seen.add(name)
        if len(rebuilt) >= 4:
            break
    return _prune_low_signal_character_profiles(rebuilt)


def _normalize_cp_analysis(
    book: BookAnalysis,
    timeline: list[RelationshipStage],
    delivery_units: list[DeliveryUnit],
    chapter_analyses: list[ChapterAnalysis],
    character_profiles: list[CharacterProfile],
) -> CPAnalysis:
    cp_analysis = book.cp_analysis.model_copy()
    primary_pair = timeline[0].pair if timeline else _resolve_primary_pair(chapter_analyses, character_profiles)
    cp_analysis.summary = _build_cp_summary(primary_pair, timeline)
    if not cp_analysis.relationship_tension:
        cp_analysis.relationship_tension = [stage.description for stage in timeline[:3] if stage.description.strip()]
    if not cp_analysis.stage_progression:
        cp_analysis.stage_progression = [
            _format_stage_progression(stage) for stage in timeline[:5] if stage.stage_label.strip()
        ]
    if not cp_analysis.catalyst_roles:
        cp_analysis.catalyst_roles = [
            character.name
            for character in character_profiles[2:5]
            if character.name.strip()
        ]
    if not cp_analysis.emotional_hooks:
        cp_analysis.emotional_hooks = list(book.selling_points[:3]) or list(book.core_hooks[:3])
    existing_topics = [
        _editorialize_cp_topic(
            CPTopic(
                topic=item.topic.strip(),
                analysis=item.analysis.strip(),
                supporting_moments=[moment.strip() for moment in item.supporting_moments if moment.strip()],
            ),
            primary_pair,
        )
        for item in cp_analysis.topics
        if item.topic.strip() and item.analysis.strip()
    ]
    generated_topics = _build_cp_topics(book, timeline, delivery_units, chapter_analyses)
    if len(existing_topics) < 6:
        cp_analysis.topics = generated_topics[:6]
        return cp_analysis
    topic_map: dict[str, CPTopic] = {}
    for item in existing_topics + generated_topics:
        key = item.topic.strip()
        if key not in topic_map:
            topic_map[key] = item
            continue
        merged_supporting = topic_map[key].supporting_moments + item.supporting_moments
        topic_map[key] = topic_map[key].model_copy(
            update={
                "analysis": topic_map[key].analysis.strip() or item.analysis.strip(),
                "supporting_moments": _prioritize_detailed_moments(merged_supporting, limit=4),
            }
        )
    cp_analysis.topics = list(topic_map.values())[:6]
    if not cp_analysis.summary.strip() and cp_analysis.topics:
        cp_analysis.summary = cp_analysis.topics[0].analysis
    return cp_analysis


def _build_cp_topics(
    book: BookAnalysis,
    timeline: list[RelationshipStage],
    delivery_units: list[DeliveryUnit],
    chapter_analyses: list[ChapterAnalysis],
) -> list[CPTopic]:
    pair = timeline[0].pair if timeline else _resolve_primary_pair(chapter_analyses, [])
    first_unit = delivery_units[0] if delivery_units else None
    second_unit = delivery_units[min(1, len(delivery_units) - 1)] if delivery_units else None
    middle_unit = delivery_units[len(delivery_units) // 2] if delivery_units else None
    final_unit = delivery_units[-1] if delivery_units else None
    topic_specs = [
        (
            "初期建设",
            timeline[0].description if timeline else "开篇先用高辨识互动把吸引、边界和危险感同时立住。",
            _supporting_moments_from_units([first_unit, second_unit]),
        ),
        (
            "试探拉扯",
            book.cp_analysis.relationship_tension[0] if book.cp_analysis.relationship_tension else "两人的关系在试探、保留和反制中升温，一直有勾着读者往下看的拉扯感。",
            _supporting_moments_from_units([first_unit, second_unit, middle_unit]),
        ),
        (
            "权力博弈",
            "这对的好嗑点在身份、资源和主线决策持续改写关系位置，亲密和博弈始终并行。",
            _supporting_moments_from_units([middle_unit, final_unit], prefer="crisis"),
        ),
        (
            "身体记忆",
            "关键动作和身体细节反复回收，会替代直白告白，直接把关系确认落到可感知的记忆点上。",
            _supporting_moments_from_units(delivery_units[:3] + delivery_units[-2:], prefer="scene"),
        ),
        (
            "外部催化",
            "第三方角色、家族压力和事业风险不断逼两人表态，所以这条感情线始终和主线冲突捆在一起推进。",
            _supporting_moments_from_units([first_unit, middle_unit, final_unit], prefer="conflict"),
        ),
        (
            "终局确认",
            timeline[-1].description if timeline else "后段通过站队、承诺和共同面对代价完成关系闭环，让前期所有拉扯都有明确回收。",
            _supporting_moments_from_units([final_unit], prefer="payoff"),
        ),
    ]
    topics: list[CPTopic] = []
    for topic, analysis, moments in topic_specs:
        topics.append(
            _editorialize_cp_topic(
                CPTopic(
                    topic=topic,
                    analysis=analysis.strip(),
                    supporting_moments=_unique_nonempty(moments)[:4],
                ),
                pair,
            )
        )
    return topics


def _build_cp_summary(primary_pair: str, timeline: list[RelationshipStage]) -> str:
    if not timeline:
        return f"{primary_pair}的关系张力来自吸引、试探与现实压力的同步推进。"
    labels = "、".join(_unique_nonempty([stage.stage_label for stage in timeline[:5] if stage.stage_label.strip()]))
    last_payoff = timeline[-1].payoff.strip() if timeline[-1].payoff.strip() else timeline[-1].core_change.strip()
    if not _is_relational_payoff(last_payoff):
        last_payoff = _fallback_stage_payoff(timeline[-1].stage_label.strip() or "终局确认")
    closing = "并完成终局确认" if timeline[-1].stage_label.strip() == "终局确认" else f"一路推进到{timeline[-1].stage_label.strip() or '关系确认'}"
    return f"{primary_pair}：关系会从{labels}{closing}，真正抓人的点在于情感吸引、现实压力与阶段性回收始终叠在一起；最终回收到{last_payoff or '关系确认'}。"


def _supporting_moments_from_units(
    units: list[DeliveryUnit | None],
    *,
    prefer: str = "summary",
) -> list[str]:
    moments: list[str] = []
    for unit in units:
        if unit is None:
            continue
        moments.extend(_cp_unit_story_candidates(unit, prefer=prefer))
    cleaned_moments = [text for text in _unique_nonempty(moments) if text and not _is_low_signal_supporting_moment(text)]
    return _prioritize_detailed_moments(cleaned_moments, limit=6)


def _cp_unit_story_candidates(unit: DeliveryUnit, *, prefer: str) -> list[str]:
    candidates: list[str] = []
    scene_items = [
        _clean_delivery_sentence(_cp_scene_moment_text(item, unit.summary))
        for item in unit.scene_quotes[:2]
        if (item.scene or item.quote or item.purpose or unit.summary).strip()
    ]
    beat_items = [
        _clean_delivery_sentence(item.beat)
        for item in unit.beat_rhythm[:2]
        if item.beat.strip()
    ]
    summary_item = _clean_delivery_sentence(unit.summary) if unit.summary.strip() else ""
    if prefer == "scene":
        candidates.extend(scene_items)
        candidates.extend(beat_items[:1])
        if summary_item:
            candidates.append(summary_item)
        candidates.extend(_clean_delivery_sentence(text) for text in unit.highlights[:1] if text.strip())
        return [item for item in candidates if item]
    if prefer == "conflict":
        candidates.extend(beat_items[:1])
        candidates.extend(scene_items[:1])
        if summary_item:
            candidates.append(summary_item)
        candidates.extend(_clean_delivery_sentence(text) for text in unit.crisis[:2] if text.strip())
        candidates.extend(_clean_delivery_sentence(text) for text in unit.suspense[:1] if text.strip())
        return [item for item in candidates if item]
    if prefer == "payoff":
        candidates.extend(beat_items[:1])
        candidates.extend(scene_items[:1])
        candidates.extend(_clean_delivery_sentence(text) for text in unit.climax[:1] if text.strip())
        candidates.extend(_clean_delivery_sentence(text) for text in unit.payoff[:1] if text.strip())
        if summary_item:
            candidates.append(summary_item)
        candidates.extend(_clean_delivery_sentence(text) for text in unit.highlights[:1] if text.strip())
        return [item for item in candidates if item]
    candidates.extend(beat_items)
    candidates.extend(scene_items[:1])
    if summary_item:
        candidates.append(summary_item)
    candidates.extend(_clean_delivery_sentence(text) for text in unit.highlights[:1] if text.strip())
    candidates.extend(_clean_delivery_sentence(text) for text in unit.crisis[:1] if text.strip())
    return [item for item in candidates if item]


def _cp_scene_moment_text(scene: SceneQuoteItem, fallback: str) -> str:
    scene_name = scene.scene.strip()
    quote = scene.quote.strip().strip("“”")
    purpose = scene.purpose.strip()
    if scene_name and quote and purpose:
        return f"在{scene_name}这场戏里，{quote}，{purpose}"
    if scene_name and quote:
        return f"在{scene_name}这场戏里，{quote}"
    if scene_name and purpose:
        return f"在{scene_name}这场戏里，{purpose}"
    return scene_name or quote or purpose or fallback


def _unique_nonempty(values: list[str]) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        results.append(cleaned)
    return results


def _normalize_plot_outline(
    book: BookAnalysis,
    main_outline: list[OutlineBeat],
    chapter_analyses: list[ChapterAnalysis],
    delivery_units: list[DeliveryUnit],
    relationship_timeline: list[RelationshipStage],
) -> PlotOutline:
    plot_outline = book.plot_outline.model_copy()
    if not plot_outline.story_lines:
        story_lines = [
            StoryLineItem(
                name="核心主线",
                category="主线",
                content=_first_sentence(book.overview) or "全书主线围绕核心冲突与关系变化展开。",
                key_points=[beat.label.strip() for beat in main_outline[:3] if beat.label.strip()],
            )
        ]
        if book.cp_analysis.summary.strip():
            story_lines.append(
                StoryLineItem(
                    name="核心关系线",
                    category="情感主线",
                    content=book.cp_analysis.summary.strip(),
                    key_points=list(book.cp_analysis.stage_progression[:4]),
                )
            )
        plot_outline.story_lines = story_lines
    plot_outline.story_lines = _detailize_story_lines(
        plot_outline.story_lines,
        delivery_units,
        chapter_analyses,
        relationship_timeline,
        book.overview,
        book.cp_analysis.summary,
    )
    if not plot_outline.phase_outline:
        plot_outline.phase_outline = [
            PhaseOutlineItem(
                phase=beat.label.strip() or f"阶段{index}",
                chapter_range=_chapter_range(beat.chapter_refs) or "",
                events=_split_outline_events(beat.description),
            )
            for index, beat in enumerate(main_outline[:8], start=1)
            if beat.description.strip()
        ]
    plot_outline.phase_outline = _detailize_phase_outline_items(plot_outline.phase_outline, chapter_analyses)
    return plot_outline


def _repair_plot_outline(
    book: BookAnalysis,
    delivery_units: list[DeliveryUnit],
    relationship_timeline: list[RelationshipStage],
    chapter_analyses: list[ChapterAnalysis],
) -> PlotOutline:
    main_outline = _normalize_main_outline(book, delivery_units)
    return _normalize_plot_outline(book, main_outline, chapter_analyses, delivery_units, relationship_timeline)


def _normalize_opening_craft(book: BookAnalysis, chapter_analyses: list[ChapterAnalysis]) -> OpeningCraft:
    craft = book.opening_craft.model_copy()
    first_chapters = chapter_analyses[:3]
    craft.core_payoffs = _build_opening_payoff_items(craft.core_payoffs, first_chapters, book)
    craft.core_pain_points = _build_opening_pain_items(craft.core_pain_points, first_chapters)
    craft.flirty_moments = _build_opening_flirty_items(craft.flirty_moments, first_chapters)
    craft.character_building = _build_opening_character_items(craft.character_building, book, first_chapters)
    craft.dialogue_design = _build_opening_dialogue_items(craft.dialogue_design, book, first_chapters)
    craft.action_details = _build_opening_action_items(craft.action_details, book, first_chapters)
    return craft


def _detailize_story_lines(
    story_lines: list[StoryLineItem],
    delivery_units: list[DeliveryUnit],
    chapter_analyses: list[ChapterAnalysis],
    relationship_timeline: list[RelationshipStage],
    overview: str,
    cp_summary: str,
) -> list[StoryLineItem]:
    detailed: list[StoryLineItem] = []
    fallback_line = StoryLineItem(
        name="核心主线",
        category="主线",
        content=overview.strip() or cp_summary.strip() or "全书主线围绕核心冲突与关系变化展开。",
        key_points=[],
    )
    for index, item in enumerate(story_lines or [fallback_line], start=1):
        relevant_units = _match_story_line_units(item, delivery_units)
        content = item.content.strip()
        detailed_content = _build_story_line_content(item, relevant_units, relationship_timeline, overview, cp_summary)
        if _story_line_needs_detail(item):
            content = detailed_content
        else:
            cleaned_content = _clean_delivery_sentence(content) or content
            content = detailed_content or cleaned_content
        key_points = _normalize_story_line_key_points(item, relevant_units)
        if not key_points:
            key_points = [f"第{index}条故事线的关键推进待结合章节补齐"]
        detailed.append(
            item.model_copy(
                update={
                    "name": item.name.strip() or f"故事线{index}",
                    "category": item.category.strip() or "线索",
                    "content": content.strip(),
                    "key_points": key_points,
                }
            )
        )
    return detailed[:4]


def _story_line_needs_detail(item: StoryLineItem) -> bool:
    content = item.content.strip()
    if _needs_delivery_repair(content) or _is_weak_book_copy(content):
        return True
    compact_length = len(re.sub(r"\s+", "", content))
    if compact_length < 32:
        return True
    if compact_length < 48 and not re.search(r"[，；。]", content):
        return True
    if compact_length < 56 and re.search(r"(?:从.+到.+|围绕.+展开|持续推进|逐步实施|螺旋演进|权力重组)$", content):
        return True
    return "内容待补充" in content or content in {"线索", "主线", "副线"}


def _story_line_is_relationship_line(item: StoryLineItem) -> bool:
    item_text = " ".join([item.name, item.category]).lower()
    return any(keyword in item_text for keyword in ("情感", "关系", "cp", "暧昧", "告白", "结婚", "亲密"))


def _match_story_line_units(item: StoryLineItem, delivery_units: list[DeliveryUnit]) -> list[DeliveryUnit]:
    keyword_buckets = {
        "情感": ("情感", "关系", "暧昧", "告白", "结婚", "恋", "cp", "亲密", "试探"),
        "复仇": ("复仇", "报复", "姐姐", "遇害", "真相", "遗嘱"),
        "资本": ("资本", "公司", "高科", "并购", "融资", "股改", "董事", "项目", "咨询", "收购"),
        "家族": ("家族", "父亲", "母亲", "卓家", "康家", "哥哥", "姐妹", "婚约", "软禁"),
    }
    item_text = " ".join([item.name, item.category, item.content, *item.key_points]).lower()
    selected_keywords: set[str] = set()
    for keywords in keyword_buckets.values():
        if any(keyword.lower() in item_text for keyword in keywords):
            selected_keywords.update(keywords)
    if not selected_keywords:
        selected_keywords.update([token for token in item.key_points if token.strip()])

    scored: list[tuple[int, int, DeliveryUnit]] = []
    for index, unit in enumerate(delivery_units):
        haystack = " ".join(
            [
                unit.title,
                unit.summary,
                *unit.highlights,
                *unit.crisis,
                *unit.payoff,
                *unit.climax,
                *[item.change for item in unit.relationship_progression],
            ]
        ).lower()
        score = 0
        for keyword in selected_keywords:
            if keyword.lower() and keyword.lower() in haystack:
                score += 2
        for point in item.key_points:
            if point.strip() and point.lower() in haystack:
                score += 3
        if "情感" in item_text and unit.relationship_progression:
            score += 1
        if "cp" in item_text and unit.relationship_progression:
            score += 1
        if score > 0:
            scored.append((score, -index, unit))
    if scored:
        return [unit for _, _, unit in sorted(scored, key=lambda row: (-row[0], row[1]))[:3]]
    return delivery_units[:3]


def _collect_story_line_segments(units: list[DeliveryUnit], *, limit: int) -> list[str]:
    segments: list[str] = []
    for unit in units:
        candidates = [
            unit.summary,
            *unit.highlights[:1],
            *unit.payoff[:1],
            *unit.crisis[:1],
            *[scene.scene for scene in unit.scene_quotes[:1]],
        ]
        for candidate in candidates:
            cleaned = _clean_delivery_sentence(candidate)
            if not cleaned or cleaned in segments:
                continue
            segments.append(cleaned)
            if len(segments) >= limit:
                return segments
    return segments


def _build_story_line_content(
    item: StoryLineItem,
    relevant_units: list[DeliveryUnit],
    relationship_timeline: list[RelationshipStage],
    overview: str,
    cp_summary: str,
) -> str:
    relationship_summary = _synthesize_relationship_story_line(item, relationship_timeline)
    if relationship_summary:
        return relationship_summary
    synthesized = _synthesize_story_line_from_key_points(item)
    if synthesized and not _story_line_is_relationship_line(item):
        return synthesized
    segments = _collect_story_line_segments(relevant_units, limit=3)
    if _story_line_is_relationship_line(item) and relationship_timeline:
        timeline_segments = _unique_nonempty(
            [
                _clean_delivery_sentence(relationship_timeline[0].core_change),
                _clean_delivery_sentence(relationship_timeline[-1].payoff),
            ]
        )
        for segment in timeline_segments:
            if segment and segment not in segments:
                segments.append(segment)
        for point in item.key_points[:2]:
            cleaned_point = point.strip()
            if not cleaned_point:
                continue
            if any(cleaned_point in segment for segment in segments):
                continue
            segments.append(f"关系后续进一步推进到{cleaned_point}这一层。")
    existing = _clean_delivery_sentence(item.content)
    if existing and existing not in segments:
        segments.append(existing)
    if not segments and item.category.strip() == "情感主线" and relationship_timeline:
        timeline_summary = _clean_delivery_sentence(relationship_timeline[0].description)
        if timeline_summary:
            segments.append(timeline_summary)
    if not segments:
        fallback = _clean_delivery_sentence(cp_summary) or _clean_delivery_sentence(overview)
        if fallback:
            segments.append(fallback)
    return "；".join(_unique_nonempty(segments)[:5]) or _fallback_story_line_content(item, BookAnalysis(overview=overview, cp_analysis=CPAnalysis(summary=cp_summary)), relevant_units, relationship_timeline)


def _synthesize_relationship_story_line(item: StoryLineItem, relationship_timeline: list[RelationshipStage]) -> str:
    if not _story_line_is_relationship_line(item):
        return ""
    points = _unique_nonempty([point.strip() for point in item.key_points if point.strip()])[:3]
    if len(points) < 2:
        return ""
    opening = relationship_timeline[0].stage_label if relationship_timeline else "试探启动"
    ending = relationship_timeline[-1].stage_label if relationship_timeline else "终局确认"
    middle = points[1] if len(points) >= 2 else points[0]
    closing = points[2] if len(points) >= 3 else points[-1]
    return (
        f"{item.name or '情感主线'}先以{points[0]}把关系从{opening}直接推到高压亲密，"
        f"中段再借{middle}把暧昧拉进生活与站队，"
        f"最后用{closing}完成{ending}，"
        "所以这条线始终是“具体桥段先推进、人物站位再改写”的核心主线。"
    )


def _synthesize_story_line_from_key_points(item: StoryLineItem) -> str:
    points = _unique_nonempty([point.strip() for point in item.key_points if point.strip()])[:4]
    if len(points) < 2:
        return ""
    point_text = "、".join(points)
    item_text = " ".join([item.name, item.category, item.content]).lower()
    if any(keyword in item_text for keyword in ("资本", "商业", "并购", "收购", "股改", "公司")):
        return f"{item.name or '资本主线'}围绕{point_text}等关键节点层层推进，高科股改、资本博弈与权力格局也因此持续改写。"
    if any(keyword in item_text for keyword in ("家族", "父亲", "母亲", "卓家", "康家", "姐妹")):
        return f"{item.name or '家族主线'}通过{point_text}等节点持续把私人关系拖入家族秩序与权力斗争，外部压力也因此层层加码。"
    if any(keyword in item_text for keyword in ("复仇", "报复", "旧案", "真相", "姐姐")):
        return f"{item.name or '复仇主线'}沿着{point_text}等关键节点逐步展开，把旧案回收、身份反杀与长期布局收束成一条完整的复仇链路。"
    return f"{item.name or '这条故事线'}主要沿着{point_text}这些关键桥段推进，并持续改写人物关系和主线局势。"


def _normalize_story_line_key_points(item: StoryLineItem, relevant_units: list[DeliveryUnit]) -> list[str]:
    points = _unique_nonempty([point.strip() for point in item.key_points if point.strip()])
    if points:
        return points[:4]
    derived: list[str] = []
    for unit in relevant_units:
        derived.extend(_short_label(scene.scene or unit.title, fallback="关键点") for scene in unit.scene_quotes[:1] if scene.scene.strip())
        derived.extend(_short_label(value, fallback="关键点") for value in unit.highlights[:2] if value.strip())
        if len(derived) >= 4:
            break
    return _unique_nonempty([point for point in derived if point and point != "关键点"])[:4]


def _detailize_phase_outline_items(
    phase_outline: list[PhaseOutlineItem],
    chapter_analyses: list[ChapterAnalysis],
) -> list[PhaseOutlineItem]:
    detailed: list[PhaseOutlineItem] = []
    for index, item in enumerate(phase_outline, start=1):
        chapter_range = item.chapter_range or ""
        phase_chapters = _chapters_for_phase_range(chapter_analyses, chapter_range)
        group_count = min(max(len(item.events) or 1, 1), max(1, min(len(phase_chapters), 4))) if phase_chapters else max(1, min(len(item.events) or 1, 4))
        chapter_groups = _chunk_phase_chapters(phase_chapters, group_count)
        events: list[str] = []
        for event_index in range(group_count):
            raw_event = item.events[event_index] if event_index < len(item.events) else ""
            current_group = chapter_groups[event_index] if event_index < len(chapter_groups) else []
            if _phase_event_is_detailed(raw_event):
                events.append(raw_event.strip())
                continue
            events.append(_build_phase_event_text(raw_event, current_group, event_index + 1))
        detailed.append(
            item.model_copy(
                update={
                    "phase": _clean_phase_label(item.phase, events, index),
                    "events": events or [f"{_clean_phase_label(item.phase, item.events, index)}：对应阶段剧情待结合章节补齐。"],
                }
            )
        )
    return detailed


def _chapters_for_phase_range(chapters: list[ChapterAnalysis], chapter_range: str) -> list[ChapterAnalysis]:
    bounds = _parse_chapter_range_bounds(chapter_range)
    if bounds is None:
        return []
    start, end = bounds
    return [
        chapter
        for chapter in chapters
        if (number := _chapter_number(chapter.chapter_id)) is not None and start <= number <= end
    ]


def _parse_chapter_range_bounds(chapter_range: str) -> tuple[int, int] | None:
    cleaned = chapter_range.strip()
    if not cleaned:
        return None
    match = re.search(r"第(\d+)(?:-(\d+))?章", cleaned)
    if match:
        start = int(match.group(1))
        end = int(match.group(2) or start)
        return start, end
    match = re.search(r"ch-(\d+)\s*[–~-]\s*ch-(\d+)", cleaned)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.search(r"ch-(\d+)", cleaned)
    if match:
        number = int(match.group(1))
        return number, number
    return None


def _chunk_phase_chapters(chapters: list[ChapterAnalysis], group_count: int) -> list[list[ChapterAnalysis]]:
    if not chapters or group_count <= 0:
        return []
    size, remainder = divmod(len(chapters), group_count)
    groups: list[list[ChapterAnalysis]] = []
    cursor = 0
    for index in range(group_count):
        current_size = size + (1 if index < remainder else 0)
        if current_size <= 0:
            current_size = 1
        groups.append(chapters[cursor : cursor + current_size])
        cursor += current_size
    if cursor < len(chapters) and groups:
        groups[-1].extend(chapters[cursor:])
    return [group for group in groups if group]


def _phase_event_is_detailed(text: str) -> bool:
    cleaned = text.strip()
    return "：" in cleaned and len(re.sub(r"\s+", "", cleaned)) >= 20 and not _needs_delivery_repair(cleaned)


def _build_phase_event_text(raw_event: str, chapters: list[ChapterAnalysis], index: int) -> str:
    title = raw_event.split("：", 1)[0].strip() if "：" in raw_event else raw_event.strip()
    if not title:
        title = _derive_phase_event_title_from_chapters(chapters, index)
    detail = raw_event.split("：", 1)[1].strip() if "：" in raw_event else ""
    if not detail or _needs_delivery_repair(detail) or len(re.sub(r"\s+", "", detail)) < 18:
        detail = _build_phase_event_detail_from_chapters(chapters)
    return f"{title}：{detail}" if detail else title


def _derive_phase_event_title_from_chapters(chapters: list[ChapterAnalysis], index: int) -> str:
    for chapter in chapters:
        for event in chapter.plot_events[:2]:
            label = _short_label(event.label or event.details, fallback="")
            if label:
                return label
    for chapter in chapters:
        candidate = _short_label(chapter.summary, fallback="")
        if candidate:
            return candidate
    return f"阶段事件{index}"


def _build_phase_event_detail_from_chapters(chapters: list[ChapterAnalysis]) -> str:
    segments: list[str] = []
    for chapter in chapters:
        for event in chapter.plot_events[:2]:
            cleaned = _clean_delivery_sentence(event.details or event.label)
            if cleaned and cleaned not in segments:
                segments.append(cleaned)
            if len(segments) >= 2:
                return "；".join(segments)
        for candidate in (chapter.summary, *chapter.highlights[:1], *chapter.climax[:1], *chapter.payoff[:1]):
            cleaned = _clean_delivery_sentence(candidate)
            if cleaned and cleaned not in segments:
                segments.append(cleaned)
            if len(segments) >= 2:
                return "；".join(segments)
    return "对应阶段剧情待结合章节补齐。"


def _build_opening_payoff_items(values: list[str], chapters: list[ChapterAnalysis], book: BookAnalysis) -> list[str]:
    candidates = _opening_detail_candidates(chapters, mode="payoff")
    items = _detailize_opening_items(
        values,
        suffix="这一步会把开篇爽点直接落到关系启动和局面改写上。",
        candidates=candidates,
        mode="payoff",
    )
    for chapter in chapters:
        for event in chapter.plot_events[:2]:
            _append_opening_item(
                items,
                event.details or event.label,
                suffix="这一步会直接把开篇爽点兑现成关系启动和局面改写。",
                candidates=candidates,
                mode="payoff",
            )
        for highlight in chapter.highlights[:1]:
            _append_opening_item(
                items,
                highlight,
                suffix="这样读者能在很短篇幅里拿到明确回报。",
                candidates=candidates,
                mode="payoff",
            )
    if not items:
        items.extend(_detailize_opening_items([item.detail for item in book.highlights_summary[:4]], suffix="这会直接抬高开篇吸引力。", mode="payoff"))
        items.extend(_detailize_opening_items(list(book.selling_points[:4]), suffix="这会直接抬高开篇吸引力。", mode="payoff"))
    return _finalize_opening_items(items, limit=5, mode="payoff")


def _build_opening_pain_items(values: list[str], chapters: list[ChapterAnalysis]) -> list[str]:
    candidates = _opening_detail_candidates(chapters, mode="pain")
    items = _detailize_opening_items(
        values,
        suffix="所以开篇会先把人物代价和风险压上来。",
        candidates=candidates,
        mode="pain",
    )
    for chapter in chapters:
        for crisis in chapter.crisis[:2]:
            _append_opening_item(
                items,
                crisis,
                suffix="所以开篇会先把人物代价和风险压上来。",
                candidates=candidates,
                mode="pain",
            )
        for suspense in chapter.suspense[:1]:
            _append_opening_item(
                items,
                suspense,
                suffix="这会让读者很快意识到关系背后还有更深的现实问题。",
                candidates=candidates,
                mode="pain",
            )
    return _finalize_opening_items(items, limit=5, mode="pain")


def _build_opening_flirty_items(values: list[str], chapters: list[ChapterAnalysis]) -> list[str]:
    candidates = _opening_detail_candidates(chapters, mode="flirty")
    items = _detailize_opening_items(
        values,
        suffix="两人的边界和吸引都在这一步被挑明。",
        candidates=candidates,
        mode="flirty",
    )
    for chapter in chapters:
        for scene in chapter.scene_quotes[:2]:
            _append_opening_item(
                items,
                _opening_scene_text(scene, chapter, mode="flirty"),
                suffix="两人的边界和吸引都在这一步被挑明。",
                candidates=candidates,
                mode="flirty",
            )
        for event in chapter.plot_events[:1]:
            _append_opening_item(
                items,
                event.details or event.label,
                suffix="暧昧在这里直接变成推动关系升级的剧情动作。",
                candidates=candidates,
                mode="flirty",
            )
    return _finalize_opening_items(items, limit=5, mode="flirty")


def _build_opening_character_items(values: list[str], book: BookAnalysis, chapters: list[ChapterAnalysis]) -> list[str]:
    candidates = _opening_detail_candidates(chapters, mode="character")
    items = _detailize_opening_items(
        values,
        suffix="人设靠场景里的选择和反应立住。",
        candidates=candidates,
        mode="character",
    )
    for character in book.character_profiles[:4]:
        if not character.name.strip():
            continue
        info = character.basic_info or character.role or _first_nonempty(character.personality_traits, "核心角色")
        _append_opening_item(
            items,
            f"{character.name}在开篇就以{info}进入场景",
            suffix="人设靠场景里的选择和反应立住。",
            candidates=candidates,
            mode="character",
        )
    for chapter in chapters[:2]:
        _append_opening_item(
            items,
            chapter.summary,
            suffix="人物状态会和主线压力一起显影，所以角色辨识度会很快立住。",
            candidates=candidates,
            mode="character",
        )
    return _finalize_opening_items(items, limit=5, mode="character")


def _build_opening_dialogue_items(values: list[str], book: BookAnalysis, chapters: list[ChapterAnalysis]) -> list[str]:
    candidates = _opening_detail_candidates(chapters, mode="dialogue")
    items = _detailize_opening_items(
        values,
        suffix="一句话里同时完成划边界、立关系和抬张力。",
        candidates=candidates,
        mode="dialogue",
    )
    for chapter in chapters:
        for scene in chapter.scene_quotes[:2]:
            if scene.quote.strip():
                _append_opening_item(
                    items,
                    _opening_scene_text(scene, chapter, mode="dialogue"),
                    suffix="一句话里同时完成划边界、立关系和抬张力。",
                    candidates=candidates,
                    mode="dialogue",
                )
    if not items and book.writing_breakdown.dialogue_design.strip():
        _append_opening_item(
            items,
            book.writing_breakdown.dialogue_design,
            suffix="对白本身就在承担剧情推进功能。",
            candidates=candidates,
            mode="dialogue",
        )
    return _finalize_opening_items(items, limit=4, mode="dialogue")


def _build_opening_action_items(values: list[str], book: BookAnalysis, chapters: list[ChapterAnalysis]) -> list[str]:
    candidates = _opening_detail_candidates(chapters, mode="action")
    items = _detailize_opening_items(
        values,
        suffix="动作细节会把潜台词和权力变化直接写到读者眼前。",
        candidates=candidates,
        mode="action",
    )
    for chapter in chapters:
        for scene in chapter.scene_quotes[:2]:
            _append_opening_item(
                items,
                _opening_scene_text(scene, chapter, mode="action"),
                suffix="动作细节会把潜台词和权力变化直接写到读者眼前。",
                candidates=candidates,
                mode="action",
            )
        for event in chapter.plot_events[:1]:
            _append_opening_item(
                items,
                event.details or event.label,
                suffix="人物靠具体动作完成关系试探。",
                candidates=candidates,
                mode="action",
            )
    if not items and book.writing_breakdown.action_detail.strip():
        _append_opening_item(
            items,
            book.writing_breakdown.action_detail,
            suffix="动作细节会把潜台词和权力变化直接写到读者眼前。",
            candidates=candidates,
            mode="action",
        )
    return _finalize_opening_items(items, limit=4, mode="action")


def _detailize_opening_items(values: list[str], *, suffix: str, candidates: list[str] | None = None, mode: str = "generic") -> list[str]:
    return _finalize_opening_items(
        [_expand_opening_item(value, suffix=suffix, candidates=candidates or [], mode=mode) for value in values],
        limit=5,
        mode=mode,
    )


def _opening_detail_candidates(chapters: list[ChapterAnalysis], *, mode: str) -> list[str]:
    candidates: list[str] = []
    for chapter in chapters[:3]:
        if mode in {"flirty", "action"}:
            candidates.extend(
                _clean_delivery_sentence(_opening_scene_text(item, chapter, mode=mode))
                for item in chapter.scene_quotes[:3]
                if (item.scene or item.quote or item.purpose or chapter.summary).strip()
            )
        if mode == "dialogue":
            candidates.extend(
                _clean_delivery_sentence(_opening_scene_text(item, chapter, mode="dialogue"))
                for item in chapter.scene_quotes[:3]
                if item.quote.strip()
            )
        if mode in {"payoff", "flirty", "action", "character"}:
            candidates.extend(
                _clean_delivery_sentence(event.details or event.label)
                for event in chapter.plot_events[:3]
                if (event.details or event.label).strip()
            )
        if mode in {"payoff", "character", "action"}:
            candidates.extend(_clean_delivery_sentence(text) for text in chapter.highlights[:2] if text.strip())
        if mode in {"pain", "character"}:
            candidates.extend(_clean_delivery_sentence(text) for text in chapter.crisis[:2] if text.strip())
            candidates.extend(_clean_delivery_sentence(text) for text in chapter.suspense[:1] if text.strip())
        candidates.append(_clean_delivery_sentence(chapter.summary))
    return _unique_nonempty([candidate for candidate in candidates if candidate])


def _expand_opening_item(value: str, *, suffix: str, candidates: list[str], mode: str = "generic") -> str:
    cleaned = _clean_delivery_sentence(value)
    if not cleaned:
        return ""
    if not _opening_item_needs_expansion(cleaned):
        return _compose_opening_sentence(cleaned, suffix, mode=mode)
    replacement = _pick_opening_candidate(cleaned, candidates, mode=mode) or cleaned
    return _compose_opening_sentence(replacement, suffix, mode=mode)


def _opening_item_needs_expansion(text: str) -> bool:
    compact = len(re.sub(r"\s+", "", text))
    if _looks_cutoff(text) or text.endswith(("、", "；", "：")):
        return True
    if compact < 14:
        return True
    if compact < 24 and not re.search(r"[，；。]", text):
        return True
    if "·" in text and not re.search(r"[，；。]", text):
        return True
    if compact > 96 and any(token in text for token in ("全程张力密集", "双线并进", "本片段", "描绘", "表面是猎艳")):
        return True
    if re.search(r"(?:爽点|虐点|互动|细节|暗号|创伤|隐患|压迫|封闭)$", text):
        return True
    return any(
        token in text
        for token in ("双线并进", "结构展开", "明线", "暗线", "在开篇就以", "职业人设", "人物设定", "初见", "对视", "亮相")
    )


def _looks_cutoff(text: str) -> bool:
    cleaned = text.strip("，。；：、 ")
    if not cleaned:
        return True
    if re.search(r"(?:如|例如|比如|包括|等|vs|和|与|及)$", cleaned, flags=re.IGNORECASE):
        return True
    if re.search(r"(?:未呈|未明|未完|未获|不知|不明|未被|未能|无法|几乎|首次无|首次未)$", cleaned):
        return True
    if re.search(
        r"(?:的|其|及|与|并|而|向|对|将|把|被|让|使|在|于|从|到|里|中|上|下|前|后|内|外|时|处|图)$",
        cleaned,
    ):
        return 10 <= len(cleaned) <= 24
    return False


def _pick_opening_candidate(seed: str, candidates: list[str], *, mode: str = "generic") -> str:
    if not candidates:
        return ""
    candidates = [candidate for candidate in candidates if _opening_candidate_is_usable(candidate, mode=mode)]
    if not candidates:
        return ""
    seed_keywords = _delivery_overlap_keywords(seed)
    normalized_seed = re.sub(r"[，；。！？、“”‘’\s]", "", _strip_opening_judgement_suffix(seed))
    if normalized_seed:
        exact_scene_matches = [
            candidate
            for candidate in candidates
            if normalized_seed in re.sub(r"[，；。！？、“”‘’\s]", "", candidate)
        ]
        if exact_scene_matches:
            candidates = exact_scene_matches
    candidate_pool = candidates
    overlapping_candidates = [candidate for candidate in candidates if _delivery_overlap_score(candidate, seed_keywords) > 0]
    if overlapping_candidates:
        candidate_pool = overlapping_candidates
    scored = sorted(
        enumerate(candidate_pool),
        key=lambda item: _opening_candidate_score(item[1], seed_keywords, mode=mode),
        reverse=True,
    )
    if scored and (_opening_candidate_score(scored[0][1], seed_keywords, mode=mode) > 0 or _opening_item_needs_expansion(seed)):
        return scored[0][1]
    return ""


def _append_opening_item(items: list[str], value: str, *, suffix: str, candidates: list[str], mode: str = "generic") -> None:
    expanded = _expand_opening_item(value, suffix=suffix, candidates=candidates, mode=mode)
    if expanded:
        items.append(expanded)


def _opening_scene_text(scene: SceneQuoteItem, chapter: ChapterAnalysis, *, mode: str) -> str:
    scene_name = scene.scene.strip()
    quote = scene.quote.strip().strip("“”")
    purpose = scene.purpose.strip()
    if mode == "dialogue":
        if scene_name and quote and purpose:
            return f"在{scene_name}里，{quote}，{purpose}"
        if quote and purpose:
            return f"{quote}，{purpose}"
        if scene_name and quote:
            return f"在{scene_name}里，{quote}"
    if mode == "action":
        if scene_name and purpose:
            return f"在{scene_name}里，{purpose}"
        if scene_name and quote:
            return f"在{scene_name}里，角色借着“{quote}”前后的动作与停顿试探彼此边界"
    if mode == "flirty":
        if scene_name and quote and purpose:
            return f"在{scene_name}里，{quote}，{purpose}"
        if scene_name and quote:
            return f"在{scene_name}里，{quote}"
        if scene_name and purpose:
            return f"在{scene_name}里，{purpose}"
    return scene_name or quote or purpose or chapter.summary


def _delivery_overlap_keywords(text: str) -> list[str]:
    return _unique_nonempty(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}", text))


def _delivery_overlap_score(text: str, keywords: list[str]) -> int:
    cleaned = text.strip()
    if not cleaned:
        return 0
    score = 0
    for keyword in keywords:
        if keyword and keyword in cleaned:
            score += max(2, len(keyword))
    return score


def _opening_candidate_score(text: str, keywords: list[str], *, mode: str = "generic") -> int:
    cleaned = text.strip()
    if not cleaned:
        return 0
    score = _delivery_overlap_score(cleaned, keywords)
    score += min(len(cleaned), 90) // 10
    if re.search(r"[，；。]", cleaned):
        score += 3
    score += _opening_mode_bonus(cleaned, mode)
    if any(token in cleaned for token in ("双线并进", "结构展开", "明线", "暗线", "在开篇就以")):
        score -= 8
    if any(token in cleaned for token in ("全程张力密集", "本片段", "描绘", "表面是猎艳", "角色性向宣言")):
        score -= 8
    if len(cleaned) > 110:
        score -= 4
    if "·" in cleaned and not re.search(r"[，；。]", cleaned):
        score -= 6
    return score


def _opening_candidate_is_usable(text: str, *, mode: str) -> bool:
    cleaned = _strip_opening_judgement_suffix(_clean_delivery_sentence(text))
    compact = len(re.sub(r"\s+", "", cleaned))
    if not cleaned or _looks_cutoff(cleaned):
        return False
    if compact < 10 or compact > 130:
        return False
    if re.search(r"[（(][^）)]*$", cleaned):
        return False
    if any(token in cleaned for token in ("双线并进", "结构展开", "明线", "暗线", "全程张力密集", "本片段", "表面是猎艳")):
        return False
    if mode == "character" and any(token in cleaned for token in ("全程张力密集", "布伦赛尔冷萃")):
        return False
    return True


def _compose_opening_sentence(text: str, suffix: str, *, mode: str) -> str:
    cleaned = _strip_opening_judgement_suffix(_clean_delivery_sentence(text))
    if not cleaned:
        return ""
    if _opening_text_already_has_judgement(cleaned, mode=mode):
        return cleaned
    judgement = _build_opening_judgement_clause(cleaned, mode=mode, fallback=suffix)
    if not judgement or cleaned.endswith(judgement.rstrip("。")) or judgement.rstrip("。") in cleaned:
        return cleaned
    return f"{cleaned}，{judgement}"


def _opening_text_already_has_judgement(text: str, *, mode: str) -> bool:
    if not re.search(r"[，；。]", text):
        return False
    keyword_map = {
        "payoff": ("起局", "回报", "起跳点", "认知反差", "局面改写"),
        "pain": ("风险", "代价", "带刺", "脆弱", "伤口"),
        "flirty": ("暧昧", "欲望", "边界", "吸引", "掠食意味", "明确偏爱", "往前滑了一格"),
        "character": ("气场", "立住", "选择姿态", "判断方式", "压迫感"),
        "dialogue": ("主动权", "划界", "关系分寸", "说透"),
        "action": ("潜台词", "权力变化", "分寸改写", "动作", "停顿"),
    }
    return any(keyword in text for keyword in keyword_map.get(mode, ()))


def _build_opening_judgement_clause(text: str, *, mode: str, fallback: str) -> str:
    fallback_cleaned = fallback.strip().rstrip("。")
    keyword_clauses = {
        "payoff": [
            (("接吻", "告白", "名分"), "这一下直接把试探推到名分确认，也把开篇回报提前兑现"),
            (("亮相", "回归", "墨镜", "倚车", "扬了扬下巴"), "强势亮相先把人物气场钉住，也让后续关系和局面改写有了起跳点"),
            (("包间", "会面", "布局", "引入", "照片"), "关键人物和核心局势一起上桌，开篇直接起局"),
            (("打破", "认知", "人设"), "认知反差先一步立住，读者会立刻意识到这个人远比表面更危险"),
        ],
        "pain": [
            (("信息差", "毫无背景认知", "误判", "风险"), "信息差和失控风险先被压上台面，后续每次靠近都会天然带刺"),
            (("旧伤", "排斥", "恐惧", "脆弱", "失控"), "人物最脆弱的伤口先露出来，后续亲密因此一直带着代价"),
            (("执照", "合规", "暴露", "主线"), "主线代价提前压进关系里，开篇的危险感很快落到具体行动上"),
        ],
        "flirty": [
            (("对视", "呼吸", "靠近", "欲望", "边界"), "眼神和距离一起越线，暧昧变成实打实的推进动作"),
            (("记住了吗", "不要白不要", "接吻", "轻勾", "挑明"), "一句话或一个动作就把试探挑明，关系也被顺势往前推了一格"),
            (("墨镜", "扬了扬下巴", "倚车", "桀骜"), "强势亮相先把压迫感和兴趣一起抛出来，暧昧也就带上了掠食意味"),
            (("发丝", "挽到了耳后", "切菜"), "生活细节把锋利试探悄悄拖进家常暧昧，彼此戒备也开始松动"),
            (("性癖", "侧脸"), "一句内心失守先把欲望说破，人物吸引也从观察变成了明确偏爱"),
            (("傻了你", "就这"), "一句轻飘飘的回话把关心拐成暧昧，关系也在松弛里往前滑了一格"),
        ],
        "character": [
            (("亮相", "会面", "直面", "推门", "扬了扬下巴", "回归"), "人物在选择姿态的瞬间把位置和气场直接立住"),
            (("高压", "布局", "试探", "打量"), "这个桥段把她的判断方式和压迫感直接演出来"),
        ],
        "dialogue": [
            (("记住了吗", "不要白不要", "女朋友", "就这"), "这句对白表面轻巧，实际同时完成试探、划界和夺回主动权"),
        ],
        "action": [
            (("手指", "拽走", "换冰水", "挽到了耳后", "扬了扬下巴", "轻勾", "吻", "推"), "动作顺着身体反应把潜台词摁实，权力变化也因此变得可见"),
            (("对视", "停顿", "靠近"), "动作和停顿一起把分寸改写了，关系推进也因此显得更有压迫感"),
        ],
    }
    for keywords, clause in keyword_clauses.get(mode, []):
        if any(keyword in text for keyword in keywords):
            return clause
    generic_map = {
        "payoff": "这一步会直接把开篇爽点兑现成关系启动和局面改写",
        "pain": "开篇先把人物代价和风险一并压了上来",
        "flirty": "暧昧在这一步变成了真实推进",
        "character": "人设靠场景里的选择和反应立住",
        "dialogue": "对白在这一步把关系分寸和主动权一起说透",
        "action": "动作细节在这一步把潜台词和关系变化直接演出来",
    }
    return generic_map.get(mode, fallback_cleaned)


def _finalize_opening_items(values: list[str], *, limit: int, mode: str = "generic") -> list[str]:
    unique_items: list[str] = []
    seen_keys: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned or _needs_delivery_repair(cleaned):
            continue
        key = re.sub(r"[，；。！？、“”‘’\s]", "", _strip_opening_judgement_suffix(cleaned))
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        unique_items.append(cleaned)
    ranked = sorted(
        unique_items,
        key=lambda text: (_opening_item_priority(text, mode=mode), -unique_items.index(text)),
        reverse=True,
    )
    return ranked[:limit]


def _opening_item_priority(text: str, *, mode: str) -> int:
    cleaned = text.strip()
    if not cleaned:
        return -1
    score = min(len(cleaned), 120) // 8
    score += _opening_mode_bonus(cleaned, mode)
    if _looks_cutoff(cleaned):
        score -= 20
    if any(token in cleaned for token in ("双线并进", "结构展开", "明线", "暗线", "全程张力密集", "本片段", "描绘", "表面是猎艳")):
        score -= 20
    if len(cleaned) > 120:
        score -= 10
    return score


def _opening_mode_bonus(text: str, mode: str) -> int:
    keyword_map = {
        "payoff": ("接吻", "告白", "名分", "初见", "重逢", "对视", "亮相", "包间", "洗手间", "KTV", "引入"),
        "pain": ("风险", "危机", "代价", "隐患", "误判", "恐惧", "压迫", "失控", "旧伤", "代偿"),
        "flirty": ("接吻", "对视", "暧昧", "靠近", "试探", "边界", "呼吸", "轻勾", "挑明", "欲望"),
        "character": ("选择", "试探", "亮相", "推门", "会面", "打量", "直面", "回归", "气场"),
        "dialogue": ("“", "”", "一句", "接吻", "记住了吗", "送上门来的嘛", "女朋友"),
        "action": ("动作", "手指", "拽走", "换冰水", "推门", "扬了扬下巴", "挽到了耳后", "吻", "勾"),
    }
    penalty_map = {
        "payoff": ("两居室", "书房改造", "1.5米床", "非临时性亲密"),
        "character": ("双线并进", "结构展开", "表面是猎艳"),
    }
    score = 0
    for keyword in keyword_map.get(mode, ()):
        if keyword in text:
            score += 6
    if mode in {"flirty", "dialogue", "action"} and text.startswith("在"):
        score += 14
    if mode == "dialogue" and "“" in text:
        score += 10
    for keyword in penalty_map.get(mode, ()):
        if keyword in text:
            score -= 10
    return score


def _strip_opening_judgement_suffix(text: str) -> str:
    cleaned = text.strip().rstrip("。")
    suffix_patterns = [
        r"(?:，|；)?这一步会把开篇爽点直接落到关系启动和局面改写上$",
        r"(?:，|；)?这一步会直接把开篇爽点兑现成关系启动和局面改写$",
        r"(?:，|；)?两人的边界和吸引都在这一步被挑明$",
        r"(?:，|；)?暧昧在这里直接变成推动关系升级的剧情动作$",
        r"(?:，|；)?所以开篇会先把人物代价和风险压上来$",
        r"(?:，|；)?开篇先把人物代价和风险一并压了上来$",
        r"(?:，|；)?这会让读者很快意识到关系背后还有更深的现实问题$",
        r"(?:，|；)?人设靠场景里的选择和反应立住$",
        r"(?:，|；)?一句话里同时完成划边界、立关系和抬张力$",
        r"(?:，|；)?暧昧在这一步变成了真实推进$",
        r"(?:，|；)?对白在这一步把关系分寸和主动权一起说透$",
        r"(?:，|；)?对白本身就在承担剧情推进功能$",
        r"(?:，|；)?动作细节会把潜台词和权力变化直接写到读者眼前$",
        r"(?:，|；)?人物靠具体动作完成关系试探$",
    ]
    previous = None
    while cleaned and cleaned != previous:
        previous = cleaned
        for pattern in suffix_patterns:
            cleaned = re.sub(pattern, "", cleaned).strip("，；。 ")
    return cleaned


def _normalize_style_summary(
    book: BookAnalysis,
    chapter_analyses: list[ChapterAnalysis],
    delivery_units: list[DeliveryUnit],
) -> StyleSummary:
    style = book.style_summary.model_copy()
    representative_refs = _representative_chapter_refs(chapter_analyses, delivery_units)
    observations = [item for chapter in chapter_analyses for item in chapter.style_signals]
    if not style.narrative_pacing.strip():
        style.narrative_pacing = _pick_style_observation(
            observations,
            keywords=["节奏", "时间", "视角", "对话"],
            fallback="整体起势快，中后段通过阶段回收维持推进力。",
        )
    if not style.information_release.strip():
        style.information_release = _pick_style_observation(
            observations,
            keywords=["信息", "隐喻", "物件", "意象"],
            fallback="信息通过阶段揭露、物件回收和对话试探逐步放出。",
        )
    if not style.conflict_design.strip():
        style.conflict_design = _pick_chapter_text(
            chapter_analyses,
            attr="crisis",
            fallback="冲突会同时作用于主线推进和关系拉扯，形成双线挤压。",
        )
    if not style.emotional_leverage.strip():
        style.emotional_leverage = _pick_chapter_text(
            chapter_analyses,
            attr="highlights",
            fallback="情绪调动依赖高辨识桥段、身体细节和阶段性反转。",
        )
    if not style.characterization.strip():
        style.characterization = _pick_style_observation(
            observations,
            keywords=["身体", "动作", "视角", "叙事"],
            fallback="人物塑造主要通过动作、对话和选择完成，不靠直白说明。",
        )
    if not style.language_style.strip():
        style.language_style = _pick_style_observation(
            observations,
            keywords=["语言", "对话", "术语", "书写"],
            fallback="语言风格偏冷感克制，常用短句、动作与专业术语并置形成张力。",
        )
    if not style.hook_and_payoff.strip():
        style.hook_and_payoff = _pick_chapter_text(
            chapter_analyses,
            attr="payoff",
            fallback="开篇钩子会在中后段通过关系确认和主线清算完成回收。",
        )
    if not style.evidence_chapters:
        style.evidence_chapters = representative_refs
    return style


def _normalize_writing_breakdown(
    book: BookAnalysis,
    chapter_analyses: list[ChapterAnalysis],
    style_summary: StyleSummary,
    delivery_units: list[DeliveryUnit],
) -> WritingBreakdown:
    writing = book.writing_breakdown.model_copy()
    if not writing.writing_analysis.strip():
        writing.writing_analysis = style_summary.language_style or "通过主线推进、关系拉扯和阶段回收完成整体拆解。"
    if not writing.opening_method.strip():
        first_chapter = chapter_analyses[0] if chapter_analyses else None
        writing.opening_method = (
            _build_one_line(first_chapter) if first_chapter else "开篇方式待结合章节结果补充。"
        )
    if not writing.dialogue_design.strip():
        writing.dialogue_design = "对话主要承担试探、拉扯、关系确认和冲突升级功能。"
    if not writing.action_detail.strip():
        writing.action_detail = "关键动作会被用来承接情绪变化、权力关系和阶段回收。"
    if not writing.language_style.strip():
        writing.language_style = style_summary.language_style or "语言风格待结合完整产物补充。"
    if not writing.evidence_chapters:
        writing.evidence_chapters = list(style_summary.evidence_chapters[:7]) or _representative_chapter_refs(chapter_analyses, delivery_units)
    return writing


def _clean_character_appearance(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    if _is_weak_character_text(cleaned):
        return ""
    return cleaned


def _infer_character_appearance(
    name: str,
    chapter_analyses: list[ChapterAnalysis],
    delivery_units: list[DeliveryUnit],
) -> str:
    cleaned_name = name.strip()
    if not cleaned_name:
        return ""
    appearance_keywords = ("穿", "戴", "锁骨", "刀疤", "西装", "衬衫", "领带", "腕表", "眼", "唇", "发", "瘦", "高", "肩", "体态")
    candidates: list[str] = []
    for unit in delivery_units:
        if not any(cleaned_name in text for text in [unit.summary, *unit.highlights, *unit.payoff, *unit.climax]):
            continue
        for text in [unit.summary, *unit.highlights, *unit.payoff, *unit.climax]:
            if cleaned_name in text and any(keyword in text for keyword in appearance_keywords):
                candidates.append(_first_sentence(text))
        for item in unit.scene_quotes[:2]:
            for text in [item.scene, item.quote]:
                if cleaned_name in text and any(keyword in text for keyword in appearance_keywords):
                    candidates.append(_first_sentence(text))
    if not candidates:
        for chapter in chapter_analyses:
            if cleaned_name not in chapter.key_characters:
                continue
            for text in [chapter.summary, *chapter.highlights, *chapter.payoff, *chapter.climax]:
                if cleaned_name in text and any(keyword in text for keyword in appearance_keywords):
                    candidates.append(_first_sentence(text))
            for item in chapter.evidence[:3]:
                if cleaned_name in item.snippet and any(keyword in item.snippet for keyword in appearance_keywords):
                    candidates.append(_first_sentence(item.snippet))
    for candidate in candidates:
        normalized = _clean_character_appearance(candidate)
        if normalized:
            return normalized
    return ""


def _is_weak_character_text(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    return bool(
        re.search(
            r"(未详述|暂无明确描写|未明确描写|描写较少|外貌描写以|人物辨识度较高|核心角色|主线推动者|情绪张力核心来源)",
            cleaned,
        )
    )


def _is_weak_book_copy(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    return bool(
        re.search(
            r"(信息仍需进一步提炼|需要结合专题桥段进一步判断|待结合完整产物补充|关系进入新的推进节点|本单元完成一次清晰推进)",
            cleaned,
        )
    )


def _cp_topic_needs_template_rewrite(topic_name: str, analysis: str) -> bool:
    cleaned = analysis.strip()
    if not cleaned or _is_weak_book_copy(cleaned):
        return True
    if len(re.sub(r"\s+", "", cleaned)) < 16:
        return True
    if any(token in cleaned for token in ["这一阶段", "压力：", "回收："]):
        return True
    if re.search(r"(?i)\bvs\b|对立|拉扯|控制\s*[vV][sS]\s*依恋", cleaned):
        return True
    standard_topics = {"初期建设", "试探拉扯", "权力博弈", "身体记忆", "外部催化", "终局确认"}
    if topic_name in standard_topics and cleaned.startswith("这对的好嗑点在"):
        return True
    if topic_name in standard_topics and not any(keyword in cleaned for keyword in ["所以", "张力", "抓住", "成立"]):
        return True
    return not any(keyword in cleaned for keyword in ["为什么", "成立", "好嗑", "抓人", "张力", "真正", "所以"])


def _build_cp_topic_template(topic_name: str) -> str:
    template_map = {
        "初期建设": "开篇最有效的是先把吸引、边界和危险感同时立住，关系起点因此一下就能抓住读者。",
        "试探拉扯": "这段关系真正成立的地方，在双方越靠近越要用试探和反制守住主动权，拉扯感会一直在线。",
        "权力博弈": "这段关系最上头的地方，是高低位不断被资源、决策权和主线选择重新洗牌，亲密每推进一步，博弈就同步加深。",
        "身体记忆": "真正留下记忆点的是身体细节一次次替关系落锚，所以每次靠近都会被读者记住。",
        "外部催化": "每当外部压力压进来，这段关系就会被迫表态，所以主线冲突反而成了感情加速器。",
        "终局确认": "终局靠共同站队、承诺兑现和代价共担一起完成回收，前面的拉扯才会真正闭环。",
    }
    return template_map.get(
        topic_name,
        "这组关系的可看点来自现实压力和阶段回收持续改写关系判断，所以会比单纯梗概更抓人。",
    )


def _editorialize_cp_topic(topic: CPTopic, pair: str) -> CPTopic:
    analysis = topic.analysis.strip()
    if _cp_topic_needs_template_rewrite(topic.topic, analysis):
        analysis = _build_cp_topic_template(topic.topic)
    elif not any(keyword in analysis for keyword in ["为什么", "成立", "好嗑", "抓人", "张力", "真正"]):
        analysis = f"{pair}这组关系在{topic.topic}上的成立点，来自具体情节里的{analysis}"
    supporting = [item for item in _unique_nonempty(topic.supporting_moments) if not _is_low_signal_supporting_moment(item)]
    if len(supporting) < 2:
        supporting.extend(_default_cp_topic_moments(topic.topic))
    supporting = _prioritize_detailed_moments(
        [item for item in _unique_nonempty(supporting) if not _is_low_signal_supporting_moment(item)],
        limit=4,
    )
    if supporting and "例如" not in analysis and "比如" not in analysis:
        analysis = f"{analysis} 例如，{supporting[0]}。"
    return topic.model_copy(update={"analysis": analysis, "supporting_moments": supporting})


def _prioritize_detailed_moments(values: list[str], *, limit: int) -> list[str]:
    unique = _unique_nonempty([value for value in values if value.strip()])
    ranked = sorted(unique, key=_detailed_moment_score, reverse=True)
    return ranked[:limit]


def _detailed_moment_score(text: str) -> int:
    cleaned = text.strip()
    if not cleaned:
        return -1
    compact_length = len(re.sub(r"\s+", "", cleaned))
    punctuation_bonus = 12 if re.search(r"[，；。]", cleaned) else 0
    narrative_bonus = 8 if re.search(r"(?:在|把|让|从|到|对|与|并|却|后|时)", cleaned) else 0
    penalty = 0
    if compact_length > 110:
        penalty += 18
    if any(token in cleaned for token in ("本章双线并行", "双线并行", "双线并进", "这一阶段", "关系会从", "关系通过")):
        penalty += 20
    if any(token in cleaned for token in ("推动信任重建", "提供外部压力", "促成情感觉醒", "考验关系韧性")):
        penalty += 16
    if cleaned.count("；") >= 2:
        penalty += 18
    return compact_length + punctuation_bonus + narrative_bonus - penalty


def _default_cp_topic_analysis(topic_name: str, pair: str) -> str:
    fallback_map = {
        "初期建设": "开篇先用高辨识互动立住吸引、边界和危险感，所以关系起点一下就能抓住读者。",
        "试探拉扯": "这段最好嗑的地方在于双方都不肯先交底，越靠近越要用试探和反制守住主动权。",
        "权力博弈": "真正有张力的地方在于身份、资源和主线选择不断改写两人的高低位。",
        "身体记忆": "关系确认靠动作、触碰和身体细节反复回收，让亲密有了可感知的记忆点。",
        "外部催化": "第三方角色、家族压力和事业风险不断逼两人表态，所以感情线始终和主线冲突绑在一起推进。",
        "终局确认": "后段通过站队、承诺和共同承担代价完成闭环，让前期所有拉扯都有明确回收。",
    }
    return fallback_map.get(topic_name, f"{pair}这组关系的张力来自情感吸引、现实压力与阶段性回收的持续叠加。")


def _default_cp_topic_moments(topic_name: str) -> list[str]:
    fallback_map = {
        "初期建设": ["开篇先用高辨识初遇把吸引、边界和危险感同时立住，关系起点直接起局。", "第一次边界试探就把两人拉到必须回应的位置，后续每次靠近也都带着危险感。"],
        "试探拉扯": ["两人每次靠近都会先试探再表态，拉扯感始终落在实打实地争主动上。", "关键时刻通过反制、停顿和绕弯子把关系往前吊着推。"],
        "权力博弈": ["身份差与资源差不断改写关系高低位，所以亲密每往前一步，博弈就会同步加深。", "主线决策会直接压到亲密关系上，逼两人在资源、立场和感情之间重新站队。"],
        "身体记忆": ["动作细节会替代直白表白，把关系记忆点落到身体反应和触感回收上。", "身体触碰让每次关系确认都重新落下一枚锚点。"],
        "外部催化": ["第三方角色、家族压力和事业风险一压进来，两人就不得不提前表态。", "外部冲突每次逼近，都会把原本可以回避的关系问题推成必须正面回答的选择题。"],
        "终局确认": ["关键承诺兑现后，前文拉扯才真正完成回收，关系闭环也因此站得住。", "共同承担代价以后，这段关系才从暧昧拉扯走到明确确认。"],
    }
    return fallback_map.get(topic_name, ["关键剧情桥段把关系推到下一阶段。", "阶段性回收让前文张力真正落地。"])


def _is_low_signal_supporting_moment(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    compact = len(re.sub(r"\s+", "", cleaned))
    if compact < 12 and not re.search(r"[，；。]", cleaned):
        return True
    if compact > 180 or cleaned.count("；") >= 4:
        return True
    if compact > 120 and any(token in cleaned for token in ("双线并行", "双线并进", "高科年会晚宴夜")):
        return True
    return bool(
        re.search(
            r"(本章为后记|本章为番外|关键桥段|代表性桥段|高辨识关系桥段|阶段回收桥段|本章以|本单元|这一章|这一阶段|推动信任重建|提供外部压力|促成情感觉醒|考验关系韧性)",
            cleaned,
        )
    )


def _is_relational_payoff(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return False
    return any(keyword in cleaned for keyword in ["关系", "承诺", "站队", "共担", "确认", "闭环", "靠近", "回收", "同盟", "绑定", "求婚", "结婚", "恋人"])


def _clean_phase_label(label: str, events: list[str], index: int) -> str:
    cleaned = label.strip()
    if cleaned and "未命名" not in cleaned:
        return cleaned
    for event in events:
        candidate = _short_label(event, fallback="")
        if candidate and "未命名" not in candidate:
            return candidate
    return f"阶段{index}"


def _representative_chapter_refs(
    chapter_analyses: list[ChapterAnalysis],
    delivery_units: list[DeliveryUnit],
) -> list[str]:
    refs: list[str] = []
    if delivery_units:
        anchor_units = [delivery_units[0], delivery_units[len(delivery_units) // 2], delivery_units[-1]]
        for unit in anchor_units:
            if unit.chapter_refs:
                refs.append(unit.chapter_refs[0])
    if not refs:
        refs = [chapter.chapter_id for chapter in chapter_analyses[:3]]
    return _unique_nonempty(refs)[:5]


def _pick_style_observation(
    observations: list[StyleSignal],
    *,
    keywords: list[str],
    fallback: str,
) -> str:
    for item in observations:
        haystack = f"{item.dimension} {item.observation}"
        if any(keyword in haystack for keyword in keywords) and item.observation.strip():
            return _first_sentence(item.observation)
    for item in observations:
        if item.observation.strip():
            return _first_sentence(item.observation)
    return fallback


def _pick_chapter_text(
    chapter_analyses: list[ChapterAnalysis],
    *,
    attr: str,
    fallback: str,
) -> str:
    for chapter in chapter_analyses:
        values = getattr(chapter, attr, [])
        for value in values:
            if value.strip():
                return _first_sentence(value)
    return fallback


def _synthesize_character_profiles(
    chapter_analyses: list[ChapterAnalysis],
    delivery_units: list[DeliveryUnit],
) -> list[CharacterProfile]:
    chapter_map = {chapter.chapter_id: chapter for chapter in chapter_analyses}
    counts: dict[str, int] = {}
    for chapter in chapter_analyses:
        for name in chapter.key_characters:
            cleaned = _normalize_character_name(name)
            if cleaned:
                counts[cleaned] = counts.get(cleaned, 0) + 1
    top_names = [name for name, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:4]]
    profiles: list[CharacterProfile] = []
    for name in top_names:
        relevant_units = _units_for_character(name, delivery_units, chapter_map)
        experiences = _character_experiences(name, relevant_units)
        relationships = _character_relationships(name, chapter_analyses, top_names)
        profiles.append(
            CharacterProfile(
                name=name,
                basic_info=f"{name}是全书高频核心人物，深度参与主线推进与关键关系变化。",
                appearance="外貌描写以气质、动作与身体细节呈现，人物辨识度较高。",
                personality_traits=["主线推动者", "情绪张力核心来源", "关键关系角色"],
                major_experiences=experiences or ["主线推进中的关键角色", "关系线中的核心参与者"],
                relationships=relationships or ["与核心人物存在长期互动与关系牵引"],
            )
        )
    return profiles


def _normalize_character_name(name: str) -> str:
    cleaned = re.sub(r"[（(].*?[)）]", "", name).strip()
    cleaned = cleaned.replace("秘书", "").replace("未出场但被隐去", "").strip(" -：:")
    if len(cleaned) < 2:
        return ""
    if cleaned in {"主角", "配角", "反派"}:
        return ""
    return cleaned


def _units_for_character(
    name: str,
    delivery_units: list[DeliveryUnit],
    chapter_map: dict[str, ChapterAnalysis],
) -> list[DeliveryUnit]:
    results: list[DeliveryUnit] = []
    for unit in delivery_units:
        for chapter_id in unit.chapter_refs:
            chapter = chapter_map.get(chapter_id)
            if chapter is None:
                continue
            if name in chapter.key_characters or name in chapter.summary:
                results.append(unit)
                break
    return results[:6]


def _character_experiences(name: str, relevant_units: list[DeliveryUnit]) -> list[str]:
    experiences: list[str] = []
    for unit in relevant_units:
        candidates = [unit.summary] + unit.highlights[:1] + unit.climax[:1] + unit.payoff[:1]
        for candidate in candidates:
            if candidate.strip():
                experiences.append(_short_label(candidate, fallback=f"{name}参与关键剧情推进"))
                break
    return _unique_nonempty(experiences)[:4]


def _character_relationships(
    name: str,
    chapter_analyses: list[ChapterAnalysis],
    candidate_names: list[str],
) -> list[str]:
    counts: dict[str, int] = {}
    for chapter in chapter_analyses:
        if name not in chapter.key_characters:
            continue
        for other in chapter.key_characters:
            cleaned = _normalize_character_name(other)
            if cleaned and cleaned != name and cleaned in candidate_names:
                counts[cleaned] = counts.get(cleaned, 0) + 1
    return [f"与{other}：核心关系角色" for other, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:3]]


def _prune_low_signal_character_profiles(profiles: list[CharacterProfile]) -> list[CharacterProfile]:
    if len(profiles) <= 4:
        return profiles
    kept = list(profiles[:4])
    for profile in profiles[4:]:
        if _is_distinctive_character_profile(profile):
            kept.append(profile)
    return kept


def _is_distinctive_character_profile(profile: CharacterProfile) -> bool:
    basic_info = profile.basic_info.strip()
    generic_basic = (
        not basic_info
        or "全书高频核心人物" in basic_info
        or "深度参与主线推进与关键关系变化" in basic_info
    )
    generic_traits = not profile.personality_traits or set(profile.personality_traits).issubset({"主线推动者", "情绪张力核心来源", "关键关系角色"})
    generic_experiences = not profile.major_experiences or set(profile.major_experiences).issubset({"主线推进中的关键角色", "关系线中的核心参与者"})
    has_specific_relationship = any("核心关系角色" not in item for item in profile.relationships)
    has_specific_appearance = bool(_clean_character_appearance(profile.appearance))
    return has_specific_appearance or has_specific_relationship or not (generic_basic and generic_traits and generic_experiences)


def _base_title(title: str) -> str:
    normalized = re.sub(r"（分块\s*\d+/\d+）", "", title).strip()
    normalized = re.sub(r"^第\s*[0-9零一二三四五六七八九十百千两]+\s*[章节回卷部集篇幕]\s*", "", normalized).strip()
    return normalized


def _build_narrative_units(chapters: list[ChapterAnalysis]) -> list[NarrativeUnit]:
    units: list[NarrativeUnit] = []
    current: NarrativeUnit | None = None

    for index, chapter in enumerate(chapters):
        base_title = _base_title(chapter.title) or f"叙事单元 {index + 1}"
        previous = chapters[index - 1] if index > 0 else None

        if current is None:
            current = _start_narrative_unit(base_title, chapter)
            units.append(current)
            continue

        should_split, signal = _should_split_unit(current, previous, chapter)
        if should_split:
            if signal:
                current.boundary_signals.append(signal)
            current = _start_narrative_unit(base_title, chapter)
            units.append(current)
            continue

        current.chapters.append(chapter)

    return units


def _start_narrative_unit(base_title: str, chapter: ChapterAnalysis) -> NarrativeUnit:
    return NarrativeUnit(base_title=base_title, chapters=[chapter])


def _should_split_unit(
    current: NarrativeUnit,
    previous: ChapterAnalysis | None,
    chapter: ChapterAnalysis,
) -> tuple[bool, str | None]:
    base_title = _base_title(chapter.title) or chapter.title
    if current.base_title != base_title:
        return True, "base_title_changed"

    if previous is None:
        return False, None

    if len(current.chapters) >= 6:
        return True, "size_cap"

    relationship_changed = _relationship_signature(previous) != _relationship_signature(chapter)
    emotion_changed = previous.emotion_state.primary != chapter.emotion_state.primary

    if previous.payoff and len(current.chapters) >= 2 and (relationship_changed or emotion_changed):
        return True, "post_payoff_shift"

    if previous.climax and len(current.chapters) >= 3 and relationship_changed:
        return True, "post_climax_shift"

    if relationship_changed and len(current.chapters) >= 4:
        return True, "relationship_shift"

    if emotion_changed and len(current.chapters) >= 5:
        return True, "emotion_shift"

    return False, None


def _narrative_unit_to_delivery_unit(index: int, unit: NarrativeUnit) -> DeliveryUnit:
    chapter_refs = [chapter.chapter_id for chapter in unit.chapters]
    return DeliveryUnit(
        unit_id=f"unit-{index:03d}",
        title=_build_delivery_title(unit, index),
        base_title=unit.base_title,
        chapter_refs=chapter_refs,
        chapter_range=_chapter_range(chapter_refs),
        summary=_merge_summary(unit.chapters),
        crisis=_collect_unique_texts(chapter.crisis for chapter in unit.chapters),
        foreshadowing=_collect_unique_texts(chapter.foreshadowing for chapter in unit.chapters),
        suspense=_collect_unique_texts(chapter.suspense for chapter in unit.chapters),
        climax=_collect_unique_texts(chapter.climax for chapter in unit.chapters),
        payoff=_collect_unique_texts(chapter.payoff for chapter in unit.chapters),
        highlights=_collect_unique_texts(chapter.highlights for chapter in unit.chapters),
        beat_rhythm=_collect_unique_models(
            item
            for chapter in unit.chapters
            for item in (chapter.beat_rhythm or [_fallback_beat_rhythm(chapter)])
        ),
        scene_quotes=_collect_unique_models(
            item
            for chapter in unit.chapters
            for item in (chapter.scene_quotes or [_fallback_scene_quote(chapter)])
        ),
        relationship_progression=_collect_unique_models(
            item for chapter in unit.chapters for item in chapter.relationship_progression
        ),
        style_signals=_collect_unique_models(
            item
            for chapter in unit.chapters
            for item in (chapter.style_signals or [_fallback_style_signal(chapter)])
        ),
        evidence=[item for chapter in unit.chapters for item in chapter.evidence][:6],
    )


def _relationship_signature(chapter: ChapterAnalysis) -> str:
    if not chapter.relationship_progression:
        return ""
    item = chapter.relationship_progression[0]
    return f"{item.counterpart}|{item.stage_label}"


def _build_one_line(chapter: ChapterAnalysis) -> str:
    summary = chapter.summary.strip()
    if not summary:
        return chapter.title
    first_sentence = re.split(r"[。！？!?]\s*", summary, maxsplit=1)[0].strip()
    return first_sentence or summary[:80]


def _build_key_conflict(chapter: ChapterAnalysis) -> str:
    for candidates in (chapter.crisis, chapter.suspense, chapter.climax, chapter.payoff, chapter.highlights):
        for candidate in candidates:
            text = candidate.strip()
            if text:
                return text
    if chapter.plot_events:
        return chapter.plot_events[0].details.strip() or chapter.plot_events[0].label.strip()
    return chapter.emotion_state.trajectory.strip()


def _build_emotional_progression(chapter: ChapterAnalysis) -> str:
    if chapter.relationship_progression:
        item = chapter.relationship_progression[0]
        counterpart = item.counterpart.strip()
        stage_label = item.stage_label.strip()
        change = item.change.strip()
        parts = [part for part in [counterpart, stage_label, change] if part]
        if parts:
            return " / ".join(parts[:2]) + (f"：{parts[2]}" if len(parts) > 2 else "")
    primary = chapter.emotion_state.primary.strip()
    trajectory = chapter.emotion_state.trajectory.strip()
    if primary and trajectory:
        return f"{primary}：{trajectory}"
    return primary or trajectory


def _with_chapter_range(stage: RelationshipStage) -> RelationshipStage:
    chapter_range = _chapter_range(stage.chapter_refs)
    if stage.chapter_range == chapter_range:
        return stage
    return stage.model_copy(update={"chapter_range": chapter_range})


def _chapter_range(chapter_refs: list[str]) -> str | None:
    if not chapter_refs:
        return None
    ordered = sorted(chapter_refs, key=_chapter_sort_key)
    first_num = _chapter_number(ordered[0])
    last_num = _chapter_number(ordered[-1])
    if first_num is not None and last_num is not None:
        if first_num == last_num:
            return f"第{first_num}章"
        return f"第{first_num}-{last_num}章"
    if len(ordered) == 1:
        return ordered[0]
    return f"{ordered[0]} ~ {ordered[-1]}"


def _chapter_number(chapter_id: str) -> int | None:
    match = re.search(r"(\d+)$", chapter_id)
    if not match:
        return None
    return int(match.group(1))


def _chapter_sort_key(chapter_id: str) -> tuple[int, str]:
    number = _chapter_number(chapter_id)
    if number is not None:
        return number, chapter_id
    return 10**9, chapter_id


def _join_preview(summaries: list[str]) -> str:
    joined = " / ".join(item for item in summaries[:3] if item)
    return joined[:180]


def _merge_summary(chapters: list[ChapterAnalysis]) -> str:
    unique_lines = _collect_unique_texts([_build_one_line(chapter)] for chapter in chapters)
    return "；".join(unique_lines[:3])[:300] if unique_lines else "本单元完成一次阶段性推进。"


def _build_delivery_title(unit: NarrativeUnit, index: int) -> str:
    base_title = unit.base_title.strip() or f"叙事单元 {index}"
    if not _is_generic_delivery_title(base_title):
        return base_title

    candidates = _collect_title_candidates(unit)
    for candidate in candidates:
        compressed = _compress_title_candidate(candidate)
        if compressed:
            return compressed
    return f"叙事推进单元 {index}"


def _is_generic_delivery_title(title: str) -> bool:
    normalized = title.strip()
    return (
        not normalized
        or "分块" in normalized
        or normalized.startswith("第0章")
        or normalized in {"引子", "后记"}
        or normalized.startswith("番外")
        or normalized.startswith("叙事单元")
    )


def _collect_title_candidates(unit: NarrativeUnit) -> list[str]:
    candidates: list[str] = []
    for chapter in unit.chapters:
        candidates.extend(
            [
                chapter.summary,
                *(chapter.highlights or []),
                *(chapter.climax or []),
                *(chapter.payoff or []),
                *(chapter.crisis or []),
            ]
        )
        candidates.extend(item.scene for item in chapter.scene_quotes if item.scene.strip())
        if chapter.relationship_progression:
            first = chapter.relationship_progression[0]
            candidates.append(f"{first.counterpart} {first.stage_label} {first.change}")
    return candidates


def _compress_title_candidate(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"（分块\s*\d+/\d+）", "", text).strip()
    cleaned = re.sub(r"[“”\"'‘’]", "", cleaned)
    cleaned = re.sub(r"[A-Za-z][A-Za-z\s&\-]{2,}", "", cleaned)
    cleaned = re.sub(
        r"^(本章|本章节|本单元|这一章|该章|本部分|这一部分)(以|围绕|聚焦|主要讲述|讲述|呈现|展开)?",
        "",
        cleaned,
    )
    cleaned = re.sub(r"^(赵壹笙与卓舒清|赵壹笙和卓舒清|赵壹笙|卓舒清|齐简臻|康壹笙|康壹竽|周易)", "", cleaned).strip()
    clauses = [_trim_title_clause(item) for item in re.split(r"[；，。！？/｜]+", cleaned)]
    clauses = [item for item in clauses if item]
    if not clauses:
        return ""

    preferred = sorted(
        clauses,
        key=lambda item: (
            0 if 6 <= len(item) <= 16 else 1,
            0 if re.search(r"(重逢|试探|留宿|告白|分手|病房|退婚|婚约|晚宴|复仇|求婚|雪夜|医院|过年|谈判|对峙|崩溃)", item) else 1,
            len(item),
        ),
    )
    first = preferred[0]
    second = preferred[1] if len(preferred) > 1 else ""
    if len(first) < 5 and second:
        first = f"{first}与{second}"
    elif second and len(first) <= 8 and len(second) <= 8 and second not in first:
        first = f"{first}与{second}"
    first = re.sub(r"(为引|开场|展开|推进|切入|阶段)$", "", first).strip("，、；： ")
    if not first or len(first) < 4:
        return ""
    return first[:18]


def _repair_delivery_units(units: list[DeliveryUnit]) -> list[DeliveryUnit]:
    repaired: list[DeliveryUnit] = []
    for index, unit in enumerate(units, start=1):
        title = _repair_delivery_unit_title(unit, index)
        repaired.append(unit.model_copy(update={"title": title}))
    return repaired


def _repair_delivery_unit_title(unit: DeliveryUnit, index: int) -> str:
    current = unit.title.strip()
    if current and not _needs_delivery_title_repair(current):
        return current
    candidates = [item.scene for item in unit.scene_quotes if item.scene.strip()]
    candidates.extend(item.beat for item in unit.beat_rhythm if item.beat.strip())
    candidates.extend(unit.highlights)
    candidates.extend(unit.climax)
    candidates.extend(unit.payoff)
    candidates.extend(unit.crisis[:2])
    candidates.append(unit.summary)
    for candidate in candidates:
        compressed = _compress_title_candidate(candidate)
        if compressed and not _needs_delivery_title_repair(compressed):
            return compressed
    return f"叙事推进单元 {index}"


def _trim_title_clause(text: str) -> str:
    cleaned = text.strip("，、；： ")
    cleaned = re.sub(
        r"^(围绕|通过|借由|借助|随后|随即|同时|最终|表面|实则|并|也|又|聚焦|在|因|为|含有|包含|分两部分|双线并行|前半段|后半段)",
        "",
        cleaned,
    ).strip()
    cleaned = re.sub(r"^(的|了)", "", cleaned).strip()
    cleaned = re.sub(r"(的张力|的关系|的局面|的阶段|这一幕|这一章|这一节)$", "", cleaned).strip()
    if len(cleaned) < 4:
        return ""
    if any(token in cleaned for token in ["本章", "本单元", "章节", "分块"]):
        return ""
    return cleaned


def _repair_relationship_timeline(
    stages: list[RelationshipStage],
    delivery_units: list[DeliveryUnit],
    chapter_analyses: list[ChapterAnalysis],
) -> list[RelationshipStage]:
    repaired: list[RelationshipStage] = []
    for stage in stages:
        stage_units = _units_for_stage(stage, delivery_units)
        core_change = _repair_stage_signal(
            stage.core_change,
            stage_units,
            source="summary",
            fallback=_fallback_stage_core_change(stage.stage_label),
        )
        pressure = _repair_stage_signal(
            stage.pressure,
            stage_units,
            source="pressure",
            fallback=_fallback_stage_pressure(stage.stage_label),
        )
        payoff = _repair_stage_signal(
            stage.payoff,
            stage_units,
            source="payoff",
            fallback=_fallback_stage_payoff(stage.stage_label),
        )
        if not _is_relational_payoff(payoff):
            payoff = _fallback_stage_payoff(stage.stage_label)
        rebuilt = stage.model_copy(
            update={
                "core_change": core_change,
                "pressure": pressure,
                "payoff": payoff,
                "description": _build_synthetic_stage_description(core_change, pressure, payoff),
            }
        )
        repaired.append(_with_chapter_range(_strengthen_relationship_stage(rebuilt)))
    if repaired:
        return repaired
    dominant_pair = _resolve_primary_pair(chapter_analyses, [])
    return _build_synthetic_relationship_timeline(delivery_units, chapter_analyses, dominant_pair, target_groups=_target_stage_group_count(delivery_units))


def _units_for_stage(stage: RelationshipStage, delivery_units: list[DeliveryUnit]) -> list[DeliveryUnit]:
    refs = set(stage.chapter_refs)
    if not refs:
        return []
    return [unit for unit in delivery_units if refs.intersection(unit.chapter_refs)]


def _repair_stage_signal(text: str, units: list[DeliveryUnit], *, source: str, fallback: str) -> str:
    cleaned = text.strip()
    if _needs_delivery_repair(cleaned):
        cleaned = _extract_stage_signal(units, source=source, fallback=fallback)
    if _needs_delivery_repair(cleaned):
        return fallback
    return cleaned


def _needs_delivery_title_repair(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    if "未命名" in cleaned:
        return True
    if _is_generic_delivery_title(cleaned):
        return True
    if cleaned.startswith("以") and len(cleaned) <= 10:
        return True
    if cleaned.count("‘") != cleaned.count("’") or cleaned.count("“") != cleaned.count("”"):
        return True
    return len(cleaned) < 2


def _needs_delivery_repair(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    if _is_weak_book_copy(cleaned):
        return True
    if not re.search(r"[\u4e00-\u9fff]", cleaned):
        return True
    if cleaned.count("‘") != cleaned.count("’") or cleaned.count("“") != cleaned.count("”"):
        return True
    if len(cleaned) < 4:
        return True
    return False


def _fallback_story_line_content(
    item: StoryLineItem,
    book: BookAnalysis,
    delivery_units: list[DeliveryUnit],
    relationship_timeline: list[RelationshipStage],
) -> str:
    name = f"{item.name} {item.category}"
    if any(keyword in name for keyword in ["情感", "关系", "cp", "CP"]):
        if book.cp_analysis.summary.strip() and not _needs_delivery_repair(book.cp_analysis.summary):
            return book.cp_analysis.summary.strip()
        if relationship_timeline:
            first_stage = relationship_timeline[0].core_change.strip()
            last_payoff = relationship_timeline[-1].payoff.strip()
            return f"{first_stage}，并一路推进到{last_payoff}。"
    if any(keyword in name for keyword in ["资本", "商业", "并购", "收购"]):
        return "资本线围绕并购、股改与权力重组持续推进，并不断改写主角处境。"
    if any(keyword in name for keyword in ["家族"]):
        return "家族压力、旧情与权力博弈持续外压主线，使私人关系不断进入公共秩序。"
    if any(keyword in name for keyword in ["复仇"]):
        return "复仇线通过商业布局和旧案回收缓慢推进，并持续牵引主角的行动选择。"
    if item.key_points:
        key_points = "、".join(_unique_nonempty(item.key_points)[:2])
        if key_points:
            return f"{item.name or '这条线'}围绕{key_points}等关键推进展开。"
    for unit in delivery_units:
        summary = unit.summary.strip()
        if summary and not _needs_delivery_repair(summary):
            return _first_sentence(summary)
    return _first_sentence(book.overview) or "这条故事线围绕核心冲突持续推进。"


def _collect_unique_texts(groups: Iterable[Iterable[str]]) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            text = value.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            results.append(text)
    return results


def _collect_unique_models(items: Iterable[BeatRhythmItem | SceneQuoteItem | RelationshipProgression | StyleSignal]) -> list:
    results: list = []
    seen: set[str] = set()
    for item in items:
        key = json.dumps(item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
    return results


def _fallback_beat_rhythm(chapter: ChapterAnalysis) -> BeatRhythmItem:
    return BeatRhythmItem(
        beat=_build_one_line(chapter),
        pacing_tag="推进",
        emotion_tag=chapter.emotion_state.primary or "起伏",
        note=chapter.emotion_state.trajectory or "本单元存在明显情绪变化。",
    )


def _fallback_scene_quote(chapter: ChapterAnalysis) -> SceneQuoteItem:
    quote = chapter.evidence[0].snippet if chapter.evidence else _build_one_line(chapter)
    return SceneQuoteItem(
        scene=_build_one_line(chapter),
        quote=quote[:60],
        purpose=(chapter.highlights[0] if chapter.highlights else "提炼本章最强记忆点"),
    )


def _fallback_style_signal(chapter: ChapterAnalysis) -> StyleSignal:
    return StyleSignal(dimension="叙事节奏", observation=chapter.emotion_state.trajectory or "推进明确")


def _first_sentence(text: str) -> str:
    sentence = re.split(r"[。！？!?]\s*", text.strip(), maxsplit=1)[0].strip()
    return sentence or text.strip()


def _format_stage_progression(stage: RelationshipStage) -> str:
    chapter_range = stage.chapter_range or _chapter_range(stage.chapter_refs) or "阶段待定"
    return f"{stage.stage_label}（{chapter_range}）"


def _build_plot_card(chapter: ChapterAnalysis) -> str:
    return _build_one_line(chapter)


def _first_nonempty(values: list[str], fallback: str) -> str:
    for value in values:
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return fallback


def _short_label(text: str, *, fallback: str) -> str:
    clauses = [item.strip("，、；： ") for item in re.split(r"[；，。！？!?/｜]+", text) if item.strip("，、；： ")]
    for clause in clauses:
        if 4 <= len(clause) <= 18:
            return clause
    if clauses:
        return clauses[0][:18]
    return fallback


def _format_beat_card(item: BeatRhythmItem) -> str:
    beat = _short_label(item.beat, fallback="情节点")
    pacing = item.pacing_tag.strip() or "推进"
    emotion = item.emotion_tag.strip() or "起伏"
    note = _short_label(item.note, fallback="关系和冲突同步推进。")
    return f"{beat}｜节奏：{pacing}｜情绪：{emotion}｜{note}"


def _format_scene_card(item: SceneQuoteItem) -> str:
    scene = _short_label(item.scene, fallback="关键场面")
    quote = item.quote.strip()
    purpose = _short_label(item.purpose, fallback="提炼本章记忆点")
    if quote:
        return f"{scene}｜金句：{quote[:24]}｜作用：{purpose}"
    return f"{scene}｜作用：{purpose}"


def _format_relationship_card(item: RelationshipProgression) -> str:
    counterpart = item.counterpart.strip() or "核心关系"
    stage_label = item.stage_label.strip() or "阶段推进"
    change = item.change.strip() or "关系进入新的阶段。"
    return f"{counterpart} / {stage_label}：{change}"


def _format_style_card(item: StyleSignal) -> str:
    dimension = item.dimension.strip() or "文风信号"
    observation = item.observation.strip() or "以细节和对话共同推动情绪与冲突。"
    return f"{dimension}：{observation}"


def _split_outline_events(text: str) -> list[str]:
    parts = [item.strip("，、；： ") for item in re.split(r"[；。！？!?]+", text) if item.strip("，、；： ")]
    return parts[:4] or [text.strip()]


def _batch_system_prompt() -> str:
    return (
        "你是全书中间汇总器。"
        "请把一批章节分析结果压缩成阶段性批次摘要，保留主线、人物、关系变化、节奏信号和文风信号。"
    )


def _batch_user_prompt(title: str, index: int, batch: list[ChapterAnalysis]) -> str:
    payload = [item.model_dump(mode="json") for item in batch]
    return (
        f"书名：{title}\n"
        f"批次：{index}\n"
        "请基于以下章节分析结果，生成批次摘要：\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _book_system_prompt() -> str:
    return (
        "你是全书拆解汇总器。"
        "请基于批次摘要和章节级结果，输出固定结构化的全书分析。"
        "目标是贴近参考样稿的拆书产品稿。"
        "必须显式产出以下模块：overview、highlights_summary、selling_points_detail、audience_positioning、story_hook_layers、"
        "core_hooks、title_intro_analysis、character_profiles、cp_analysis、plot_outline、main_outline、opening_craft、"
        "relationship_timeline、writing_breakdown、style_summary、chapter_outlines。"
        "人物小传必须按人物卡输出，CP感分析必须按专题拆解，剧情大纲必须同时给出故事线层和阶段层，"
        "开篇文法分析必须独立，不要混进文笔内容总结。"
        "凡是故事线、主线大纲、情感线、CP感分析、开篇文法分析等模块，都必须先写具体剧情/桥段，再给分析判断；"
        "不要只写短语标签、空泛阶段名或‘内容待补充’之类占位。"
    )


def _book_user_prompt(
    title: str,
    batch_summaries: list[BatchSummary],
    chapter_analyses: list[ChapterAnalysis],
) -> str:
    return (
        f"书名：{title}\n"
        "请按照参考样稿模板输出全书分析，至少覆盖：综述、核心亮点总结、核心卖点、推荐定位、剧情看点分层、"
        "核心梗、作品名/简介/章节名分析、人物小传、CP感分析、剧情大纲、开篇文法分析、情感线、文笔内容总结、章节细纲总表。\n"
        "语言必须偏编辑式判断：多用短句、判断句、标签句和桥段举证句，少用泛泛总结与摘要腔。\n"
        "重点模块统一按‘剧情叙述 + 拆解判断’输出：先写发生了什么，再写为什么有效、怎样推进、造成什么变化。\n"
        "plot_outline.story_lines[*].content 不能只写‘主线/线索’，必须是完整剧情概述；"
        "plot_outline.phase_outline[*].events 不能只写‘告白/同居/做空’这类名词标签，至少要写到具体事件推进；"
        "opening_craft、relationship_timeline、cp_analysis.topics.supporting_moments 都要尽量写成一句完整剧情句。\n\n"
        "批次摘要：\n"
        f"{json.dumps([item.model_dump(mode='json') for item in batch_summaries], ensure_ascii=False, indent=2)}\n\n"
        "章节简表：\n"
        f"{json.dumps([item.model_dump(mode='json') for item in chapter_analyses], ensure_ascii=False, indent=2)}"
    )


def _book_file_user_prompt(title: str, batch_count: int, chapter_count: int) -> str:
    return (
        f"书名：{title}\n"
        f"上传文件中包含 {batch_count} 个批次摘要和 {chapter_count} 个章节分析结果。\n"
        "请仅基于上传文件内容，输出贴近参考样稿的固定结构化全书分析。"
        "必须显式覆盖核心亮点总结、核心卖点、剧情看点分层、核心梗、作品名/简介/章节名分析、人物小传、CP感分析、"
        "剧情大纲、开篇文法分析、情感线、文笔内容总结和章节细纲总表。"
        "必须单独生成 relationship_timeline、cp_analysis、plot_outline、opening_craft、writing_breakdown 和 style_summary，"
        "不要把文笔总结混进 overview。"
        "重点模块统一按‘先写具体剧情/桥段，再写分析判断’的方式生成，禁止输出短语级标签、空泛阶段名或占位话术。"
    )
