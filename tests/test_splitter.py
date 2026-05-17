from pathlib import Path

from novel_agent.config import AppSettings, Profile
from novel_agent.ingest import ingest_book
from novel_agent.schemas import IngestedBook, InputType
from novel_agent.splitter import split_into_chapters


def test_splitter_detects_chapters() -> None:
    path = Path("tests/fixtures/sample_novel.txt")
    settings = AppSettings.for_profile(Profile.MVP)
    ingested = ingest_book(path, InputType.TXT, settings)
    chapters = split_into_chapters(ingested, settings)
    assert len(chapters) >= 4
    assert chapters[0].title
    assert chapters[1].chapter_id.startswith("ch-")


def test_splitter_degrades_sparse_huge_chapters() -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    huge_body = ("这一段是正文。\n\n" * 20000).strip()
    book = IngestedBook(
        book_id="sparse-book",
        title="Sparse Book",
        input_path="sparse.txt",
        input_type=InputType.TXT,
        normalized_text=f"引子\n{huge_body}\n\n番外：补充\n收尾\n\n后记\n结束",
    )

    chapters = split_into_chapters(book, settings)

    assert len(chapters) > 3
    assert any("分块" in chapter.title for chapter in chapters)
    assert any(
        "Sparse heading detection; oversized chapter was split into fallback chunks" in warning
        for chapter in chapters
        for warning in chapter.split_warnings
    )
