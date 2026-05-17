from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from openai import APIConnectionError

from novel_agent.providers.bailian_long_provider import BailianLongProvider
from novel_agent.schemas import BookAnalysis


class _FakeFiles:
    def __init__(self) -> None:
        self.deleted_ids: list[str] = []

    def create(self, **kwargs):  # noqa: ANN003
        return SimpleNamespace(id="file-123", status="processed")

    def retrieve(self, file_id: str, **kwargs):  # noqa: ANN003
        return SimpleNamespace(id=file_id, status="processed")

    def delete(self, file_id: str, **kwargs):  # noqa: ANN003
        self.deleted_ids.append(file_id)
        return SimpleNamespace(id=file_id, deleted=True)


class _FakeChatCompletions:
    def __init__(self, fail_first: bool = False) -> None:
        self.last_timeout = None
        self.fail_first = fail_first
        self.calls = 0

    def create(self, **kwargs):  # noqa: ANN003
        self.calls += 1
        self.last_timeout = kwargs.get("timeout")
        if self.fail_first and self.calls == 1:
            raise APIConnectionError(request=SimpleNamespace(method="POST", url="https://example.com"))
        payload = {
            "title": "测试书",
            "overview": "全书概述",
            "selling_points": ["卖点"],
            "positioning": ["定位"],
            "core_hooks": ["钩子"],
            "character_profiles": [],
            "main_outline": [],
            "chapter_outlines": [],
            "emotion_observations": ["情绪观察"],
            "relationship_timeline": [],
            "style_summary": {
                "narrative_pacing": "节奏稳定",
                "information_release": "信息投喂清晰",
                "conflict_design": "冲突推进明确",
                "emotional_leverage": "情绪调动自然",
                "characterization": "人物塑造有层次",
                "language_style": "语言平实",
                "hook_and_payoff": "钩子与回收完整",
                "evidence_chapters": [],
            },
            "chapter_evidence_index": {},
        }
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload, ensure_ascii=False)))],
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=60),
        )


class _FakeClient:
    def __init__(self, *, fail_first_chat: bool = False) -> None:
        self.files = _FakeFiles()
        self.chat = SimpleNamespace(completions=_FakeChatCompletions(fail_first=fail_first_chat))


def test_bailian_long_provider_uploads_file_and_returns_book_analysis(tmp_path: Path) -> None:
    source_path = tmp_path / "aggregate.json"
    source_path.write_text('{"hello": "world"}', encoding="utf-8")
    upload_meta_path = tmp_path / "upload.json"

    provider = BailianLongProvider.__new__(BailianLongProvider)
    provider.client = _FakeClient()
    provider.request_timeout = 1.0
    provider.aggregate_timeout = 180.0
    provider.file_poll_interval = 0.01
    provider.file_poll_timeout = 0.1
    provider.request_retry_attempts = 3
    provider.request_retry_backoff_seconds = 0.0

    result, stats = provider.generate_structured(
        response_model=BookAnalysis,
        model="qwen-long",
        system_prompt="test",
        user_prompt="请输出全书分析",
        metadata={
            "aggregate_input_path": str(source_path),
            "aggregate_upload_metadata_path": str(upload_meta_path),
        },
    )

    assert result.title == "测试书"
    assert "structured_provider_mode:bailian_long_fileid" in stats.warnings
    assert upload_meta_path.exists()
    upload_meta = json.loads(upload_meta_path.read_text(encoding="utf-8"))
    assert upload_meta["file_id"] == "file-123"
    assert upload_meta["deleted"] is True
    assert provider.client.chat.completions.last_timeout == 180.0


def test_bailian_long_provider_retries_final_merge_once(tmp_path: Path) -> None:
    source_path = tmp_path / "aggregate.json"
    source_path.write_text('{"hello": "world"}', encoding="utf-8")

    provider = BailianLongProvider.__new__(BailianLongProvider)
    provider.client = _FakeClient(fail_first_chat=True)
    provider.request_timeout = 1.0
    provider.aggregate_timeout = 180.0
    provider.file_poll_interval = 0.01
    provider.file_poll_timeout = 0.1
    provider.request_retry_attempts = 3
    provider.request_retry_backoff_seconds = 0.0

    result, stats = provider.generate_structured(
        response_model=BookAnalysis,
        model="qwen-long",
        system_prompt="test",
        user_prompt="请输出全书分析",
        metadata={"aggregate_input_path": str(source_path)},
    )

    assert result.title == "测试书"
    assert provider.client.chat.completions.calls == 2
    assert any(item.startswith("chat.completions.create retry 1/2: APIConnectionError") for item in stats.warnings)


def test_bailian_long_provider_coerces_outline_scalar_fields(tmp_path: Path) -> None:
    source_path = tmp_path / "aggregate.json"
    source_path.write_text('{"hello": "world"}', encoding="utf-8")

    provider = BailianLongProvider.__new__(BailianLongProvider)
    provider.client = _FakeClient()
    provider.request_timeout = 1.0
    provider.aggregate_timeout = 180.0
    provider.file_poll_interval = 0.01
    provider.file_poll_timeout = 0.1
    provider.request_retry_attempts = 3
    provider.request_retry_backoff_seconds = 0.0

    payload = {
        "title": "测试书",
        "overview": "全书概述",
        "character_profiles": [],
        "main_outline": [],
        "chapter_outlines": [
            {
                "chapter_id": "ch-0001",
                "title": "第1章",
                "one_line": "开局重逢",
                "key_conflict": "关系试探",
                "emotional_progression": "先试探后升级",
                "plot": "主线启动",
                "crisis": "身份暴露风险",
                "foreshadowing": ["旧日关系", "后续并购"],
                "suspense": ["她到底站哪边"],
                "climax": "第一次正面交锋",
                "payoff": "张力立住",
                "beats": [],
                "signature_scenes": [],
                "relationship_progress": [],
                "style_signals": [],
            }
        ],
        "emotion_observations": [],
        "relationship_timeline": [],
        "style_summary": {},
        "chapter_evidence_index": {},
    }
    provider.client.chat.completions.create = lambda **kwargs: SimpleNamespace(  # noqa: ANN003
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload, ensure_ascii=False)))],
        usage=SimpleNamespace(prompt_tokens=120, completion_tokens=60),
    )

    result, _stats = provider.generate_structured(  # noqa: F841
        response_model=BookAnalysis,
        model="qwen-long",
        system_prompt="test",
        user_prompt="请输出全书分析",
        metadata={"aggregate_input_path": str(source_path)},
    )

    assert result.chapter_outlines[0].foreshadowing == "旧日关系；后续并购"
    assert result.chapter_outlines[0].suspense == "她到底站哪边"
