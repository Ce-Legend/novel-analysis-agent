from __future__ import annotations

import json
from collections.abc import Callable

from ..config import AppSettings
from ..providers.base import LLMProvider
from ..schemas import ChapterAnalysis, ChapterChunkExtraction, ChapterRecord, StageStats
from ..utils import chunk_text


def analyze_chapter(
    chapter: ChapterRecord,
    provider: LLMProvider,
    settings: AppSettings,
    model_name: str,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> tuple[ChapterAnalysis, list[StageStats]]:
    chunks = chunk_text(chapter.raw_text, settings.pipeline.chapter_chunk_chars)
    chunk_extractions: list[ChapterChunkExtraction] = []
    stats: list[StageStats] = []

    for index, chunk in enumerate(chunks, start=1):
        if progress_callback is not None:
            progress_callback("chunk_start", index, len(chunks))
        source_ref = f"{chapter.chapter_id}:chunk-{index:02d}"
        result, chunk_stats = provider.generate_structured(
            response_model=ChapterChunkExtraction,
            model=model_name,
            system_prompt=_chapter_chunk_system_prompt(),
            user_prompt=_chapter_chunk_user_prompt(chapter.title, source_ref, chunk),
            metadata={
                "chapter_id": chapter.chapter_id,
                "source_ref": source_ref,
                "text": chunk,
            },
        )
        chunk_stats.stage_name = "chapter_chunk_extract"
        chunk_extractions.append(result)
        stats.append(chunk_stats)
        if progress_callback is not None:
            progress_callback("chunk_done", index, len(chunks))

    if len(chunk_extractions) == 1:
        merged = _chunk_to_analysis(chapter, chunk_extractions[0])
        return merged, stats

    if progress_callback is not None:
        progress_callback("merge_start", len(chunks), len(chunks))
    merged, merge_stats = provider.generate_structured(
        response_model=ChapterAnalysis,
        model=model_name,
        system_prompt=_chapter_merge_system_prompt(),
        user_prompt=_chapter_merge_user_prompt(chapter, chunk_extractions),
        metadata={
            "chapter": chapter,
            "chunk_extractions": chunk_extractions,
        },
    )
    merge_stats.stage_name = "chapter_merge"
    stats.append(merge_stats)
    if progress_callback is not None:
        progress_callback("merge_done", len(chunks), len(chunks))
    return merged, stats


def _chunk_to_analysis(chapter: ChapterRecord, extraction: ChapterChunkExtraction) -> ChapterAnalysis:
    return ChapterAnalysis(
        chapter_id=chapter.chapter_id,
        title=chapter.title,
        summary=extraction.summary,
        plot_events=extraction.plot_events,
        crisis=extraction.crisis,
        foreshadowing=extraction.foreshadowing,
        suspense=extraction.suspense,
        climax=extraction.climax,
        payoff=extraction.payoff,
        highlights=extraction.highlights,
        beat_rhythm=extraction.beat_rhythm,
        scene_quotes=extraction.scene_quotes,
        emotion_state=extraction.emotion_state,
        relationship_progression=extraction.relationship_progression,
        key_characters=extraction.key_characters,
        style_signals=extraction.style_signals,
        evidence=extraction.evidence,
    )


def _chapter_chunk_system_prompt() -> str:
    return (
        "你是一个小说拆解分析器。"
        "你的任务是把单个章节片段抽取成固定结构化结果。"
        "不要输出散文，不要省略字段。"
        "必须覆盖剧情、危机、伏笔、悬念、高潮、爽点、情节点与节奏、名场面与金句、情感推进、文风信号。"
        "情节点与节奏要包含节奏标签、情绪标签和简述。"
        "名场面与金句要优先提炼高辨识度桥段，不要只重复证据。"
        "重要结论必须用 evidence 回链到原文片段。"
    )


def _chapter_chunk_user_prompt(chapter_title: str, source_ref: str, chunk: str) -> str:
    return (
        f"章节标题：{chapter_title}\n"
        f"来源：{source_ref}\n"
        "请分析以下正文片段，抽取剧情事件、危机、伏笔、悬念、高潮、回收、爽点、情节点与节奏、名场面与金句、情绪状态、关系推进、关键人物、文笔信号，并给出证据。\n\n"
        f"{chunk}"
    )


def _chapter_merge_system_prompt() -> str:
    return (
        "你是一个章节级小说拆解整合器。"
        "给你同一章节的多个片段抽取结果后，请合并成一个完整的 ChapterAnalysis。"
        "不要丢字段，尽量消除重复。"
        "合并后仍需显式保留爽点、情节点与节奏、名场面与金句。"
        "保留最关键的 evidence。"
    )


def _chapter_merge_user_prompt(chapter: ChapterRecord, chunk_extractions: list[ChapterChunkExtraction]) -> str:
    payload = [item.model_dump(mode="json") for item in chunk_extractions]
    return (
        f"章节：{chapter.title}\n"
        f"chapter_id：{chapter.chapter_id}\n"
        "请合并以下片段抽取结果，生成单章最终结构化分析：\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
