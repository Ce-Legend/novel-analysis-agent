from __future__ import annotations

from pathlib import Path
import zipfile

from novel_agent.client_bundle import (
    build_client_bundle,
    find_latest_input,
    find_latest_run_dir,
    load_latest_run,
    parse_run_dir_from_output,
    save_latest_run,
)


def test_find_latest_input_prefers_newest_supported_file(tmp_path: Path) -> None:
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    older = inputs_dir / "a.txt"
    newer = inputs_dir / "b.docx"
    ignored = inputs_dir / "c.md"
    older.write_text("a", encoding="utf-8")
    newer.write_text("b", encoding="utf-8")
    ignored.write_text("c", encoding="utf-8")
    older.touch()
    newer.touch()

    latest = find_latest_input(inputs_dir)

    assert latest == newer


def test_save_and_load_latest_run_roundtrip(tmp_path: Path) -> None:
    bundle_root = tmp_path
    run_dir = tmp_path / "runs" / "book" / "run-1"
    run_dir.mkdir(parents=True)

    save_latest_run(bundle_root, run_dir)

    assert load_latest_run(bundle_root) == run_dir.resolve()


def test_find_latest_run_dir_uses_existing_run_outputs(tmp_path: Path) -> None:
    older = tmp_path / "runs" / "book-a" / "run-a"
    newer = tmp_path / "runs" / "book-b" / "run-b"
    (older / "04_aggregate").mkdir(parents=True)
    (newer / "04_aggregate").mkdir(parents=True)
    (older / "04_aggregate" / "book_analysis.json").write_text("{}", encoding="utf-8")
    (newer / "04_aggregate" / "book_analysis.json").write_text("{}", encoding="utf-8")
    older.touch()
    newer.touch()

    latest = find_latest_run_dir(tmp_path / "runs")

    assert latest == newer


def test_parse_run_dir_from_output_extracts_cli_path() -> None:
    output = "foo\nRun directory: /tmp/demo\nbar\n"

    assert parse_run_dir_from_output(output) == Path("/tmp/demo")


def test_build_client_bundle_creates_launchers_and_zip(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]

    result = build_client_bundle(project_root, tmp_path, bundle_name="client-demo")

    assert result.bundle_dir.exists()
    assert result.zip_path.exists()
    assert (result.bundle_dir / "0_配置API.bat").exists()
    assert (result.bundle_dir / "1_一键开始运行.bat").exists()
    assert (result.bundle_dir / "internal" / "run_client.py").exists()
    assert (result.bundle_dir / ".env.example").exists()
    assert (result.bundle_dir / "app" / "src" / "novel_agent" / "client_bundle.py").exists()

    with zipfile.ZipFile(result.zip_path) as zf:
        names = set(zf.namelist())
    assert "client-demo/README_客户使用说明.md" in names
    assert "client-demo/1_一键开始运行.bat" in names
    assert "client-demo/internal/run_client.py" in names
    assert "client-demo/app/src/novel_agent/client_bundle.py" in names


def test_windows_bat_uses_crlf_newlines(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]

    result = build_client_bundle(project_root, tmp_path, bundle_name="client-demo-crlf")
    bat_path = result.bundle_dir / "1_一键开始运行.bat"
    data = bat_path.read_bytes()

    assert b"\r\n" in data
    assert b"@echo off\r\nchcp 936 >nul\r\nsetlocal\r\n" in data


def test_windows_launchers_use_relative_bundle_root(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]

    result = build_client_bundle(project_root, tmp_path, bundle_name="client-demo-relative")
    configure_bat = (result.bundle_dir / "0_配置API.bat").read_text(encoding="gbk")
    run_bat = (result.bundle_dir / "1_一键开始运行.bat").read_text(encoding="gbk")

    assert 'internal\\run_client.py" configure' in configure_bat
    assert 'internal\\run_client.py" launch' in run_bat


def test_windows_launchers_use_python_runner_wrapper(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]

    result = build_client_bundle(project_root, tmp_path, bundle_name="client-demo-inline")
    configure_bat = (result.bundle_dir / "0_配置API.bat").read_text(encoding="gbk")
    run_bat = (result.bundle_dir / "1_一键开始运行.bat").read_text(encoding="gbk")
    runner = (result.bundle_dir / "internal" / "run_client.py").read_text(encoding="utf-8")

    assert 'py -3.11 "%~dp0internal\\run_client.py" configure' in configure_bat
    assert 'py -3.11 "%~dp0internal\\run_client.py" launch' in run_bat
    assert "def run_all(bundle_root: Path, worker_log: Path, session_id: str) -> int:" in runner
