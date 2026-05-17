from __future__ import annotations

import json
import os
from time import perf_counter
from time import sleep
from typing import Any

from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError

from ..schemas import StageStats
from ..utils import resolve_api_key
from .base import LLMProvider, T


class OpenAIProvider(LLMProvider):
    name = "openai"
    retryable_exceptions = (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or resolve_api_key("OPENAI_API_KEY", "DASHSCOPE_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY or DASHSCOPE_API_KEY is required for the openai provider")
        base_url = resolve_api_key("NOVEL_AGENT_OPENAI_BASE_URL", "OPENAI_BASE_URL")
        client_kwargs: dict[str, str | int] = {"api_key": key, "max_retries": 0}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = OpenAI(**client_kwargs)
        self.request_timeout = float(os.getenv("NOVEL_AGENT_LLM_TIMEOUT_SECONDS", "60"))
        self.aggregate_timeout = float(os.getenv("NOVEL_AGENT_BOOK_AGGREGATE_TIMEOUT_SECONDS", "180"))
        self.request_retry_attempts = int(os.getenv("NOVEL_AGENT_PROVIDER_RETRY_ATTEMPTS", "3"))
        self.request_retry_backoff_seconds = float(os.getenv("NOVEL_AGENT_PROVIDER_RETRY_BACKOFF_SECONDS", "2"))
        self.base_url = base_url or ""
        self.prefer_chat_json = "dashscope.aliyuncs.com" in self.base_url

    def generate_structured(
        self,
        *,
        response_model: type[T],
        model: str,
        system_prompt: str,
        user_prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[T, StageStats]:
        retry_warnings: list[str] = []
        if getattr(self, "prefer_chat_json", False):
            parsed, stats = self._fallback_generate_structured(
                response_model=response_model,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                metadata=metadata,
                retry_warnings=retry_warnings,
            )
            stats.warnings.extend(retry_warnings)
            stats.warnings.append("structured_provider_mode:dashscope_chat_json")
            return parsed, stats

        started = perf_counter()
        timeout = self._timeout_for_response_model(response_model)
        try:
            response = self._call_with_retries(
                lambda: self.client.responses.parse(
                    model=model,
                    instructions=system_prompt,
                    input=user_prompt,
                    text_format=response_model,
                    temperature=0.2,
                    truncation="auto",
                    prompt_cache_key=f"novel-agent:{response_model.__name__}:{model}",
                    metadata={k: str(v) for k, v in (metadata or {}).items() if isinstance(v, (str, int, float))},
                    timeout=timeout,
                ),
                action_label="responses.parse",
                warnings=retry_warnings,
            )
            elapsed_ms = int((perf_counter() - started) * 1000)
            parsed = response.output_parsed
            if parsed is None:
                raise RuntimeError("OpenAI response did not return parsed structured output")
            usage = getattr(response, "usage", None)
            stats = StageStats(
                stage_name="llm",
                model=model,
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                latency_ms=elapsed_ms,
                warnings=list(retry_warnings),
            )
            stats.warnings.append("structured_path:responses.parse")
            return parsed, stats
        except Exception as exc:
            parsed, stats = self._fallback_generate_structured(
                response_model=response_model,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                metadata=metadata,
                retry_warnings=retry_warnings,
            )
            stats.warnings.extend(retry_warnings)
            stats.warnings.append(f"responses.parse fallback used: {type(exc).__name__}")
            return parsed, stats

    def _fallback_generate_structured(
        self,
        *,
        response_model: type[T],
        model: str,
        system_prompt: str,
        user_prompt: str,
        metadata: dict[str, Any] | None = None,
        retry_warnings: list[str] | None = None,
    ) -> tuple[T, StageStats]:
        schema_json = json.dumps(response_model.model_json_schema(), ensure_ascii=False, indent=2)
        fallback_system = (
            f"{system_prompt}\n\n"
            "你必须只输出合法 JSON，不要输出任何额外说明、前言、Markdown 代码块或自然语言解释。"
            "JSON 必须严格满足给定 schema。"
        )
        fallback_user = (
            "请根据以下 JSON Schema 输出结果。\n"
            "只能输出一个 JSON 对象。\n\n"
            f"JSON Schema:\n{schema_json}\n\n"
            f"任务输入:\n{user_prompt}"
        )
        started = perf_counter()
        timeout = self._timeout_for_response_model(response_model)
        local_retry_warnings = retry_warnings if retry_warnings is not None else []
        response = self._call_with_retries(
            lambda: self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": fallback_system},
                    {"role": "user", "content": fallback_user},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                metadata={k: str(v) for k, v in (metadata or {}).items() if isinstance(v, (str, int, float))},
                timeout=timeout,
            ),
            action_label="chat.completions.create",
            warnings=local_retry_warnings,
        )
        elapsed_ms = int((perf_counter() - started) * 1000)
        content = response.choices[0].message.content or "{}"
        parsed = response_model.model_validate_json(content)
        usage = getattr(response, "usage", None)
        stats = StageStats(
            stage_name="llm",
            model=model,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=elapsed_ms,
            warnings=["structured_path:chat.completions.json_object"],
        )
        return parsed, stats

    def _timeout_for_response_model(self, response_model: type[T]) -> float:
        base = getattr(self, "request_timeout", 60.0)
        if response_model.__name__ in {"BookAnalysis", "BatchSummary"}:
            return max(base * 2, getattr(self, "aggregate_timeout", base * 2))
        if response_model.__name__ == "ChapterAnalysis":
            return base * 2
        return base

    def _call_with_retries(self, func: Any, *, action_label: str, warnings: list[str]) -> Any:
        max_attempts = max(int(getattr(self, "request_retry_attempts", 3)), 1)
        backoff_seconds = max(float(getattr(self, "request_retry_backoff_seconds", 2.0)), 0.0)
        for attempt in range(1, max_attempts + 1):
            try:
                return func()
            except self.retryable_exceptions as exc:
                if attempt >= max_attempts:
                    raise
                warnings.append(f"{action_label} retry {attempt}/{max_attempts - 1}: {type(exc).__name__}")
                sleep(backoff_seconds * attempt)
        raise RuntimeError(f"{action_label} retry loop exhausted unexpectedly")
