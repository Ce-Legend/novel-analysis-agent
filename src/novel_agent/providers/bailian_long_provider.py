from __future__ import annotations

import json
import os
from pathlib import Path
from time import perf_counter, sleep
from typing import Any

from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError

from ..schemas import BookAnalysis, StageStats
from ..utils import resolve_api_key
from .base import LLMProvider, T


class BailianLongProvider(LLMProvider):
    name = "bailian-long"
    retryable_exceptions = (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or resolve_api_key("DASHSCOPE_API_KEY", "OPENAI_API_KEY")
        if not key:
            raise RuntimeError("DASHSCOPE_API_KEY or OPENAI_API_KEY is required for the bailian-long provider")

        base_url = (
            resolve_api_key("NOVEL_AGENT_OPENAI_BASE_URL", "OPENAI_BASE_URL")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.client = OpenAI(api_key=key, base_url=base_url, max_retries=0)
        self.request_timeout = float(os.getenv("NOVEL_AGENT_LLM_TIMEOUT_SECONDS", "60"))
        self.file_poll_interval = float(os.getenv("NOVEL_AGENT_FILE_POLL_INTERVAL_SECONDS", "2"))
        self.file_poll_timeout = float(os.getenv("NOVEL_AGENT_FILE_POLL_TIMEOUT_SECONDS", "120"))
        self.aggregate_timeout = float(os.getenv("NOVEL_AGENT_BOOK_AGGREGATE_TIMEOUT_SECONDS", "180"))
        self.request_retry_attempts = int(os.getenv("NOVEL_AGENT_PROVIDER_RETRY_ATTEMPTS", "3"))
        self.request_retry_backoff_seconds = float(os.getenv("NOVEL_AGENT_PROVIDER_RETRY_BACKOFF_SECONDS", "2"))

    def generate_structured(
        self,
        *,
        response_model: type[T],
        model: str,
        system_prompt: str,
        user_prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[T, StageStats]:
        if response_model is not BookAnalysis:
            raise ValueError("bailian-long provider currently only supports BookAnalysis aggregation")

        payload = metadata or {}
        source_path = Path(str(payload.get("aggregate_input_path", ""))).expanduser()
        if not source_path.exists():
            raise FileNotFoundError("aggregate_input_path is required for bailian-long aggregation")

        upload_metadata_path = payload.get("aggregate_upload_metadata_path")
        started = perf_counter()
        retry_warnings: list[str] = []
        uploaded_file = self._call_with_retries(
            lambda: self.client.files.create(
                file=source_path,
                purpose="file-extract",
                timeout=self.request_timeout,
            ),
            action_label="files.create",
            warnings=retry_warnings,
        )
        file_id = getattr(uploaded_file, "id", None)
        if not file_id:
            raise RuntimeError("Bailian file upload did not return a file id")

        upload_status = getattr(uploaded_file, "status", None) or "uploaded"
        deleted = False
        warnings = ["structured_path:bailian-long.chat.completions.fileid_json_object", *retry_warnings]
        try:
            upload_status = self._wait_for_processed(file_id, upload_status)
            response = self._call_with_retries(
                lambda: self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": self._schema_prompt(system_prompt, response_model)},
                        {"role": "system", "content": f"fileid://{file_id}"},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    metadata={k: str(v) for k, v in payload.items() if isinstance(v, (str, int, float))},
                    timeout=max(self.request_timeout * 2, self.aggregate_timeout),
                ),
                action_label="chat.completions.create",
                warnings=warnings,
            )
            elapsed_ms = int((perf_counter() - started) * 1000)
            content = response.choices[0].message.content or "{}"
            parsed = response_model.model_validate_json(content)
            usage = getattr(response, "usage", None)
            warnings.extend(
                [
                    "structured_provider_mode:bailian_long_fileid",
                    f"uploaded_file_status:{upload_status}",
                ]
            )
            stats = StageStats(
                stage_name="llm",
                model=model,
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                latency_ms=elapsed_ms,
                warnings=warnings,
            )
            return parsed, stats
        finally:
            delete_error: str | None = None
            try:
                self.client.files.delete(file_id, timeout=self.request_timeout)
                deleted = True
            except Exception as exc:  # pragma: no cover - best effort cleanup
                delete_error = f"{type(exc).__name__}: {exc}"
            if upload_metadata_path:
                Path(upload_metadata_path).write_text(
                    json.dumps(
                        {
                            "provider": self.name,
                            "model": model,
                            "source_path": str(source_path),
                            "file_id": file_id,
                            "upload_status": upload_status,
                            "deleted": deleted,
                            "delete_error": delete_error,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

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

    def _schema_prompt(self, system_prompt: str, response_model: type[T]) -> str:
        schema_json = json.dumps(response_model.model_json_schema(), ensure_ascii=False, indent=2)
        return (
            f"{system_prompt}\n\n"
            "你必须只输出合法 JSON，不要输出任何额外说明、前言、Markdown 代码块或自然语言解释。"
            "JSON 必须严格满足给定 schema。\n\n"
            f"JSON Schema:\n{schema_json}"
        )

    def _wait_for_processed(self, file_id: str, initial_status: str) -> str:
        status = initial_status
        deadline = perf_counter() + self.file_poll_timeout
        while perf_counter() < deadline:
            if status == "processed":
                return status
            if status in {"error", "failed"}:
                raise RuntimeError(f"Bailian uploaded file entered terminal status: {status}")
            sleep(self.file_poll_interval)
            retrieved = self.client.files.retrieve(file_id, timeout=self.request_timeout)
            status = getattr(retrieved, "status", None) or status
        raise TimeoutError(f"Bailian uploaded file was not processed within {self.file_poll_timeout} seconds")
