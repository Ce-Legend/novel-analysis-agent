from __future__ import annotations

import json
from pathlib import Path
import importlib.util


def _load_runner_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "client_bundle_runner.py"
    spec = importlib.util.spec_from_file_location("client_bundle_runner", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_run_cli_ignores_keyboard_interrupt(monkeypatch, tmp_path: Path, capsys) -> None:
    runner = _load_runner_module()
    bundle_root = tmp_path
    (bundle_root / "logs").mkdir(parents=True, exist_ok=True)
    run_dir = bundle_root / "runs" / "book" / "run-1"
    (run_dir / "04_aggregate").mkdir(parents=True, exist_ok=True)
    (run_dir / "04_aggregate" / "book_analysis.json").write_text("{}", encoding="utf-8")

    class _FakeProcess:
        def __init__(self) -> None:
            self.calls = 0

        def wait(self, timeout=None):  # noqa: ANN001
            self.calls += 1
            if self.calls == 1:
                raise KeyboardInterrupt
            return 0

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())

    result, log_path = runner.run_cli(
        bundle_root,
        Path("python"),
        ["--input", "demo.txt"],
        log_prefix="analyze",
        stage_name="analyze",
        session_id="session-1",
    )

    assert result == run_dir
    assert log_path.exists()
    assert "command=" in log_path.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    assert "检测到控制台中断信号" in captured.out


def test_launch_background_writes_status_and_logs(monkeypatch, tmp_path: Path) -> None:
    runner = _load_runner_module()
    bundle_root = tmp_path
    captured: dict[str, object] = {}

    class _FakeProcess:
        pid = 4321

    def _fake_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakeProcess()

    monkeypatch.setattr(runner.subprocess, "Popen", _fake_popen)

    result, session_id = runner.launch_background(bundle_root)

    assert result == 0
    assert session_id
    status = json.loads((bundle_root / ".client_state" / "job_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "running"
    assert status["session_id"] == session_id
    assert Path(status["launcher_log"]).exists()
    assert status["worker_log"].endswith("-worker.log")
    assert status["worker_status_log"].endswith("-worker-status.log")
    assert captured["args"][0][-1] == "worker"


def test_worker_failure_updates_status_and_traceback(tmp_path: Path) -> None:
    runner = _load_runner_module()
    bundle_root = tmp_path
    (bundle_root / ".env.example").write_text('DASHSCOPE_API_KEY="请填写你的百炼 Key"\n', encoding="utf-8")

    exit_code = runner.worker(bundle_root)

    assert exit_code == 1
    status = json.loads((bundle_root / ".client_state" / "job_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["error_type"] == "RuntimeError"
    log_path = Path(status["worker_status_log"])
    assert log_path.exists()
    log_text = log_path.read_text(encoding="utf-8")
    assert "未处理异常" in log_text
    assert "RuntimeError" in log_text


def test_monitor_progress_exits_on_completed_status(tmp_path: Path, capsys) -> None:
    runner = _load_runner_module()
    bundle_root = tmp_path
    runner.write_status(
        bundle_root,
        {
            "status": "completed",
            "message": "后台任务完成",
            "session_id": "session-1",
            "stage": "completed",
            "updated_at": "2026-04-14T23:10:00",
        },
    )

    exit_code = runner.monitor_progress(bundle_root, session_id="session-1")

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "后台任务完成" in captured.out
    assert "任务完成" in captured.out
