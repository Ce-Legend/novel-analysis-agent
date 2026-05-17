from pathlib import Path

from novel_agent.analysis.chapter import analyze_chapter
from novel_agent.config import AppSettings, Profile, ProviderName
from novel_agent.ingest import ingest_book
from novel_agent.providers import resolve_provider
from novel_agent.schemas import InputType
from novel_agent.splitter import split_into_chapters


class _CountingProvider:
    name = "mock"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._provider = resolve_provider(ProviderName.MOCK)

    def generate_structured(self, *, response_model, model, system_prompt, user_prompt, metadata=None):  # noqa: ANN001, ANN003
        self.calls.append(response_model.__name__)
        return self._provider.generate_structured(
            response_model=response_model,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            metadata=metadata,
        )


def test_analyze_chapter_skips_merge_for_single_chunk() -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    input_path = Path("tests/fixtures/sample_novel.txt")
    ingested = ingest_book(input_path, InputType.TXT, settings)
    chapters = split_into_chapters(ingested, settings)
    provider = _CountingProvider()

    analysis, stats = analyze_chapter(
        chapter=chapters[0],
        provider=provider,
        settings=settings,
        model_name=settings.model_settings.chapter_model,
    )

    assert analysis.chapter_id == chapters[0].chapter_id
    assert provider.calls == ["ChapterChunkExtraction"]
    assert len(stats) == 1
    assert stats[0].stage_name == "chapter_chunk_extract"
