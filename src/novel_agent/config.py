from __future__ import annotations

from enum import StrEnum
from pathlib import Path
import os

from pydantic import BaseModel, ConfigDict, Field


class Profile(StrEnum):
    MVP = "mvp"
    SCALE = "scale"


class ProviderName(StrEnum):
    AUTO = "auto"
    MOCK = "mock"
    OPENAI = "openai"
    BAILIAN_LONG = "bailian-long"


class ExportFormat(StrEnum):
    MARKDOWN = "markdown"
    DOCX = "docx"
    PDF = "pdf"


class ModelSettings(BaseModel):
    chapter_model: str = "gpt-5-mini"
    book_model: str = "gpt-5-mini"
    judge_model: str = "gpt-5-mini"


class PipelineSettings(BaseModel):
    chapter_chunk_chars: int = 8000
    fallback_chunk_chars: int = 12000
    aggregate_batch_size: int = 20
    min_pdf_text_chars: int = 500
    low_ocr_confidence: float = 75.0
    max_retries: int = 3
    llm_timeout_seconds: int = 30


class AppSettings(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    runs_dir: Path = Path("runs")
    model_settings: ModelSettings = Field(default_factory=ModelSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    book_provider: ProviderName | None = None

    @classmethod
    def for_profile(cls, profile: Profile) -> "AppSettings":
        book_provider = _provider_from_env("NOVEL_AGENT_BOOK_PROVIDER")
        if profile == Profile.SCALE:
            return cls(
                model_settings=ModelSettings(
                    chapter_model=os.getenv("NOVEL_AGENT_CHAPTER_MODEL", "gpt-5-mini"),
                    book_model=os.getenv("NOVEL_AGENT_BOOK_MODEL", "gpt-5-mini"),
                    judge_model=os.getenv("NOVEL_AGENT_JUDGE_MODEL", "gpt-5-mini"),
                ),
                pipeline=PipelineSettings(
                    chapter_chunk_chars=6000,
                    fallback_chunk_chars=9000,
                    aggregate_batch_size=12,
                ),
                book_provider=book_provider,
            )
        return cls(
            model_settings=ModelSettings(
                chapter_model=os.getenv("NOVEL_AGENT_CHAPTER_MODEL", "gpt-5-mini"),
                book_model=os.getenv("NOVEL_AGENT_BOOK_MODEL", "gpt-5-mini"),
                judge_model=os.getenv("NOVEL_AGENT_JUDGE_MODEL", "gpt-5-mini"),
            ),
            book_provider=book_provider,
        )


def _provider_from_env(name: str) -> ProviderName | None:
    value = os.getenv(name)
    if not value:
        return None
    return ProviderName(value)
