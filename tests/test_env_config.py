import os
from pathlib import Path

from novel_agent.config import ProviderName
from novel_agent.providers import resolve_provider
from novel_agent.utils import load_local_env


def test_load_local_env_reads_dotenv_file(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text('DASHSCOPE_API_KEY="test-key"\n', encoding="utf-8")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        loaded = load_local_env()
    finally:
        os.chdir(cwd)

    assert loaded is True
    assert os.getenv("DASHSCOPE_API_KEY") == "test-key"


def test_resolve_provider_uses_dashscope_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("NOVEL_AGENT_OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    provider = resolve_provider(ProviderName.AUTO)

    assert provider.name == "openai"


def test_app_settings_reads_book_provider_from_env(monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_AGENT_BOOK_PROVIDER", "bailian-long")

    from novel_agent.config import AppSettings, Profile

    settings = AppSettings.for_profile(Profile.MVP)

    assert settings.book_provider == ProviderName.BAILIAN_LONG
