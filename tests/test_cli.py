from pathlib import Path

from typer.testing import CliRunner

from novel_agent.cli import app
from novel_agent.runtime import RunLockError


def test_cli_rejects_active_run_lock(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    runner = CliRunner()
    input_path = tmp_path / "sample.txt"
    input_path.write_text("第一章\n测试文本", encoding="utf-8")

    class _LockedContext:
        root_dir = tmp_path / "runs" / "sample" / "same-run"
        logger = type("Logger", (), {"info": lambda *args, **kwargs: None})()

        def acquire_lock(self) -> None:
            raise RunLockError("run lock active")

        def release_lock(self) -> None:
            raise AssertionError("release_lock should not be called when acquire_lock fails")

    monkeypatch.setattr("novel_agent.cli.load_local_env", lambda: None)
    monkeypatch.setattr("novel_agent.cli.build_run_context", lambda settings, input_name, run_id: _LockedContext())

    result = runner.invoke(app, ["--input", str(input_path), "--run-id", "same-run"])

    assert result.exit_code == 1
    assert "run lock active" in result.output


def test_cli_finalize_delivery_invokes_existing_run_context(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    runner = CliRunner()
    run_dir = tmp_path / "runs" / "sample" / "same-run"
    run_dir.mkdir(parents=True, exist_ok=True)

    class _ExistingContext:
        root_dir = run_dir

    captured: dict[str, object] = {}

    monkeypatch.setattr("novel_agent.cli.load_local_env", lambda: None)
    monkeypatch.setattr("novel_agent.cli.build_existing_run_context", lambda settings, run_dir: _ExistingContext())

    def _fake_finalize_delivery(*, ctx, export_formats):  # noqa: ANN001
        captured["ctx"] = ctx
        captured["formats"] = [item.value for item in export_formats]
        return {"markdown": Path("/tmp/book_analysis.md")}

    monkeypatch.setattr("novel_agent.cli.finalize_delivery", _fake_finalize_delivery)

    result = runner.invoke(app, ["finalize-delivery", "--run-dir", str(run_dir)])

    assert result.exit_code == 0
    assert "Run directory:" in result.output
    assert captured["ctx"].root_dir == run_dir
    assert captured["formats"] == ["markdown", "docx", "pdf"]
