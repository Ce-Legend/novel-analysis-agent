from __future__ import annotations

from types import SimpleNamespace

import httpx
from pydantic import BaseModel
from openai import APITimeoutError

from novel_agent.providers.openai_provider import OpenAIProvider


class SmallPayload(BaseModel):
    ok: bool
    note: str


class _FakeResponses:
    def parse(self, **kwargs):  # noqa: ANN003
        raise RuntimeError("invalid structured output")


class _FakeChatCompletions:
    def create(self, **kwargs):  # noqa: ANN003
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true, "note": "fallback"}'))],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=5),
        )


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()
        self.chat = SimpleNamespace(completions=_FakeChatCompletions())


class _RetryOnceChatCompletions:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, **kwargs):  # noqa: ANN003
        self.calls += 1
        if self.calls == 1:
            raise APITimeoutError(request=httpx.Request("POST", "https://example.com/v1/chat/completions"))
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true, "note": "retried"}'))],
            usage=SimpleNamespace(prompt_tokens=21, completion_tokens=8),
        )


class _RetryClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()
        self.chat = SimpleNamespace(completions=_RetryOnceChatCompletions())


def test_openai_provider_falls_back_to_chat_json() -> None:
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = _FakeClient()
    provider.request_timeout = 1.0

    result, stats = provider.generate_structured(
        response_model=SmallPayload,
        model="qwen-plus",
        system_prompt="test",
        user_prompt="test",
        metadata={"case": "fallback"},
    )

    assert result.ok is True
    assert result.note == "fallback"
    assert "structured_path:chat.completions.json_object" in stats.warnings
    assert any(item.startswith("responses.parse fallback used:") for item in stats.warnings)


def test_openai_provider_retries_chat_json_after_timeout() -> None:
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = _RetryClient()
    provider.request_timeout = 1.0
    provider.aggregate_timeout = 3.0
    provider.request_retry_attempts = 2
    provider.request_retry_backoff_seconds = 0.0
    provider.prefer_chat_json = True

    result, stats = provider.generate_structured(
        response_model=SmallPayload,
        model="qwen-plus",
        system_prompt="test",
        user_prompt="test",
        metadata={"case": "retry"},
    )

    assert result.ok is True
    assert result.note == "retried"
    assert "structured_path:chat.completions.json_object" in stats.warnings
    assert "structured_provider_mode:dashscope_chat_json" in stats.warnings
    assert any(item.startswith("chat.completions.create retry 1/1") for item in stats.warnings)
