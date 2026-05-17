from __future__ import annotations

import re

from .config import AppSettings
from .schemas import ChapterRecord, IngestedBook
from .utils import chunk_text, estimate_tokens


CHAPTER_PATTERNS = [
    re.compile(r"^\s*第\s*[0-9零一二三四五六七八九十百千两]+\s*[章节回卷部集篇幕].*$"),
    re.compile(r"^\s*(序章|楔子|序幕|番外|后记|尾声).*$"),
]


def split_into_chapters(book: IngestedBook, settings: AppSettings) -> list[ChapterRecord]:
    lines = book.normalized_text.splitlines()
    chapters: list[tuple[str, list[str]]] = []
    current_title = "第0章 引子"
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if _looks_like_chapter_heading(stripped):
            if current_lines:
                chapters.append((current_title, current_lines))
            current_title = stripped
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        chapters.append((current_title, current_lines))

    if len(chapters) <= 1:
        return _fallback_chunks(book, settings)

    records: list[ChapterRecord] = []
    for index, (title, body_lines) in enumerate(chapters, start=1):
        text = "\n".join(body_lines).strip()
        warnings: list[str] = []
        if not text:
            warnings.append("Empty chapter after split")
        if len(text) > settings.pipeline.fallback_chunk_chars * 3:
            warnings.append("Chapter is very long and may produce multiple analysis chunks")
        records.append(
            ChapterRecord(
                chapter_id=f"ch-{index:04d}",
                title=title,
                order=index,
                raw_text=text,
                token_count=estimate_tokens(text),
                split_warnings=warnings,
            )
        )
    return _degrade_sparse_huge_chapters(records, settings)


def _looks_like_chapter_heading(line: str) -> bool:
    if not line:
        return False
    return any(pattern.match(line) for pattern in CHAPTER_PATTERNS)


def _fallback_chunks(book: IngestedBook, settings: AppSettings) -> list[ChapterRecord]:
    chunks = chunk_text(book.normalized_text, settings.pipeline.fallback_chunk_chars)
    records: list[ChapterRecord] = []
    for index, chunk in enumerate(chunks, start=1):
        records.append(
            ChapterRecord(
                chapter_id=f"chunk-{index:04d}",
                title=f"未识别章节 {index}",
                order=index,
                raw_text=chunk,
                token_count=estimate_tokens(chunk),
                split_warnings=["Chapter heading not detected; used fallback chunking"],
            )
        )
    return records


def _degrade_sparse_huge_chapters(records: list[ChapterRecord], settings: AppSettings) -> list[ChapterRecord]:
    if len(records) > 3:
        return records

    oversized_threshold = settings.pipeline.fallback_chunk_chars * 8
    if not any(len(record.raw_text) > oversized_threshold for record in records):
        return records

    degraded: list[ChapterRecord] = []
    order = 1
    for record in records:
        if len(record.raw_text) <= oversized_threshold:
            degraded.append(record.model_copy(update={"chapter_id": f"ch-{order:04d}", "order": order}))
            order += 1
            continue

        chunks = chunk_text(record.raw_text, settings.pipeline.fallback_chunk_chars)
        total = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            warnings = list(record.split_warnings)
            warnings.append("Sparse heading detection; oversized chapter was split into fallback chunks")
            degraded.append(
                ChapterRecord(
                    chapter_id=f"ch-{order:04d}",
                    title=f"{record.title}（分块 {index}/{total}）",
                    order=order,
                    raw_text=chunk,
                    token_count=estimate_tokens(chunk),
                    split_warnings=warnings,
                )
            )
            order += 1
    return degraded
