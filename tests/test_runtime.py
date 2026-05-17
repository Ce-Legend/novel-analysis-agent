import json
import os
from pathlib import Path

import pytest

from novel_agent.config import AppSettings, Profile
from novel_agent.runtime import RunLockError, build_run_context


def test_run_context_rejects_active_foreign_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    settings.runs_dir = tmp_path / "runs"
    ctx = build_run_context(settings, "sample.txt", "locked-run")
    ctx.lock_path.write_text(json.dumps({"pid": 424242, "run_id": ctx.run_id}), encoding="utf-8")
    monkeypatch.setattr("novel_agent.runtime._pid_is_running", lambda pid: pid == 424242)

    with pytest.raises(RunLockError):
        ctx.acquire_lock()


def test_run_context_replaces_stale_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    settings.runs_dir = tmp_path / "runs"
    ctx = build_run_context(settings, "sample.txt", "stale-run")
    ctx.lock_path.write_text(json.dumps({"pid": 424242, "run_id": ctx.run_id}), encoding="utf-8")
    monkeypatch.setattr("novel_agent.runtime._pid_is_running", lambda pid: False)

    ctx.acquire_lock()

    payload = json.loads(ctx.lock_path.read_text(encoding="utf-8"))
    assert payload["pid"] == os.getpid()
    assert payload["run_id"] == ctx.run_id

    ctx.release_lock()
    assert not ctx.lock_path.exists()
