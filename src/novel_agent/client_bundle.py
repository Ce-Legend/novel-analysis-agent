from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess
import sys
import zipfile

import typer

from .config import ExportFormat, Profile, ProviderName


app = typer.Typer(add_completion=False, help="Client bundle helper commands")

SUPPORTED_INPUT_SUFFIXES = {".txt", ".docx", ".pdf"}
LATEST_RUN_FILE = Path(".client_state/latest_run.txt")


@dataclass(slots=True)
class BundleBuildResult:
    bundle_dir: Path
    zip_path: Path


def find_latest_input(inputs_dir: Path) -> Path:
    candidates = [
        path
        for path in inputs_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES
    ]
    if not candidates:
        raise FileNotFoundError(f"未在 {inputs_dir} 找到可分析小说，请放入 txt/docx/pdf 文件。")
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def find_latest_run_dir(runs_dir: Path) -> Path:
    candidates = [
        path
        for path in runs_dir.glob("*/*")
        if path.is_dir() and (path / "04_aggregate/book_analysis.json").exists()
    ]
    if not candidates:
        raise FileNotFoundError(f"未在 {runs_dir} 找到可用运行目录。")
    return max(candidates, key=lambda path: (path.stat().st_mtime, str(path)))


def save_latest_run(bundle_root: Path, run_dir: Path) -> None:
    state_path = bundle_root / LATEST_RUN_FILE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(str(run_dir.resolve()), encoding="utf-8")


def load_latest_run(bundle_root: Path) -> Path | None:
    state_path = bundle_root / LATEST_RUN_FILE
    if not state_path.exists():
        return None
    candidate = Path(state_path.read_text(encoding="utf-8").strip())
    if candidate.exists():
        return candidate
    return None


def resolve_run_dir(bundle_root: Path, explicit_run_dir: Path | None = None) -> Path:
    if explicit_run_dir is not None:
        run_dir = explicit_run_dir.resolve()
        save_latest_run(bundle_root, run_dir)
        return run_dir
    saved = load_latest_run(bundle_root)
    if saved is not None:
        return saved
    run_dir = find_latest_run_dir(bundle_root / "runs")
    save_latest_run(bundle_root, run_dir)
    return run_dir


def bundle_python_path(bundle_root: Path) -> Path:
    if os.name == "nt":
        return bundle_root / ".venv" / "Scripts" / "python.exe"
    return bundle_root / ".venv" / "bin" / "python"


def copy_env_example(bundle_root: Path) -> Path:
    env_path = bundle_root / ".env.local"
    if not env_path.exists():
        shutil.copy2(bundle_root / ".env.example", env_path)
    return env_path


def open_path(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=True)
        return
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    subprocess.run(["xdg-open", str(path)], check=True)


def parse_run_dir_from_output(output: str) -> Path | None:
    marker = "Run directory:"
    for line in output.splitlines():
        if line.startswith(marker):
            value = line.split(marker, 1)[1].strip()
            if value:
                return Path(value)
    return None


def _run_with_log(bundle_root: Path, command: list[str], log_prefix: str) -> tuple[int, str]:
    logs_dir = bundle_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{log_prefix}.log"
    process = subprocess.Popen(
        command,
        cwd=bundle_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    lines: list[str] = []
    assert process.stdout is not None
    with log_path.open("w", encoding="utf-8") as fh:
        for line in process.stdout:
            print(line, end="")
            fh.write(line)
            lines.append(line)
    return_code = process.wait()
    return return_code, "".join(lines)


def _run_bundle_cli(bundle_root: Path, args: list[str], *, log_prefix: str) -> Path:
    python_path = bundle_python_path(bundle_root)
    if not python_path.exists():
        raise FileNotFoundError("未找到 .venv Python，请先运行 1_环境初始化。")
    command = [str(python_path), "-m", "novel_agent.cli", *args]
    return_code, output = _run_with_log(bundle_root, command, log_prefix)
    if return_code != 0:
        raise typer.Exit(code=return_code)
    run_dir = parse_run_dir_from_output(output)
    if run_dir is None:
        run_dir = find_latest_run_dir(bundle_root / "runs")
    save_latest_run(bundle_root, run_dir)
    return run_dir


@app.command("configure-api")
def configure_api_command(
    bundle_root: Path = typer.Option(Path("."), "--bundle-root", file_okay=False, dir_okay=True, resolve_path=True),
) -> None:
    env_path = copy_env_example(bundle_root)
    typer.echo(f"配置文件：{env_path}")
    open_path(env_path)


@app.command("analyze")
def analyze_command(
    bundle_root: Path = typer.Option(Path("."), "--bundle-root", file_okay=False, dir_okay=True, resolve_path=True),
    input_path: Path | None = typer.Option(None, "--input", exists=True, file_okay=True, dir_okay=False, readable=True),
    provider: ProviderName = typer.Option(ProviderName.OPENAI, "--provider"),
    profile: Profile = typer.Option(Profile.MVP, "--profile"),
    export: str = typer.Option("markdown,docx,pdf", "--export"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    env_path = copy_env_example(bundle_root)
    chosen_input = input_path.resolve() if input_path is not None else find_latest_input(bundle_root / "inputs")
    typer.echo(f"使用输入文件：{chosen_input}")
    typer.echo(f"环境配置：{env_path}")
    run_dir = _run_bundle_cli(
        bundle_root,
        [
            "--input",
            str(chosen_input),
            "--provider",
            provider.value,
            "--profile",
            profile.value,
            "--export",
            export,
            *(["--force"] if force else []),
        ],
        log_prefix="analyze",
    )
    typer.echo(f"分析完成：{run_dir}")


@app.command("finalize")
def finalize_command(
    bundle_root: Path = typer.Option(Path("."), "--bundle-root", file_okay=False, dir_okay=True, resolve_path=True),
    run_dir: Path | None = typer.Option(None, "--run-dir", exists=False),
    export: str = typer.Option("markdown,docx,pdf", "--export"),
) -> None:
    chosen_run = resolve_run_dir(bundle_root, run_dir)
    typer.echo(f"使用运行目录：{chosen_run}")
    finalized_run = _run_bundle_cli(
        bundle_root,
        ["finalize-delivery", "--run-dir", str(chosen_run), "--export", export],
        log_prefix="finalize",
    )
    typer.echo(f"定稿完成：{finalized_run}")


@app.command("open-results")
def open_results_command(
    bundle_root: Path = typer.Option(Path("."), "--bundle-root", file_okay=False, dir_okay=True, resolve_path=True),
    run_dir: Path | None = typer.Option(None, "--run-dir", exists=False),
) -> None:
    chosen_run = resolve_run_dir(bundle_root, run_dir)
    export_dir = chosen_run / "05_export"
    if not export_dir.exists():
        raise FileNotFoundError(f"未找到结果目录：{export_dir}")
    save_latest_run(bundle_root, chosen_run)
    typer.echo(f"打开结果目录：{export_dir}")
    open_path(export_dir)


@app.command("run-all")
def run_all_command(
    bundle_root: Path = typer.Option(Path("."), "--bundle-root", file_okay=False, dir_okay=True, resolve_path=True),
    input_path: Path | None = typer.Option(None, "--input", exists=True, file_okay=True, dir_okay=False, readable=True),
    provider: ProviderName = typer.Option(ProviderName.OPENAI, "--provider"),
    profile: Profile = typer.Option(Profile.MVP, "--profile"),
    export: str = typer.Option("markdown,docx,pdf", "--export"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    chosen_input = input_path.resolve() if input_path is not None else find_latest_input(bundle_root / "inputs")
    typer.echo(f"使用输入文件：{chosen_input}")
    analyze_run = _run_bundle_cli(
        bundle_root,
        [
            "--input",
            str(chosen_input),
            "--provider",
            provider.value,
            "--profile",
            profile.value,
            "--export",
            export,
            *(["--force"] if force else []),
        ],
        log_prefix="analyze",
    )
    typer.echo(f"分析完成：{analyze_run}")
    finalized_run = _run_bundle_cli(
        bundle_root,
        ["finalize-delivery", "--run-dir", str(analyze_run), "--export", export],
        log_prefix="finalize",
    )
    typer.echo(f"定稿完成：{finalized_run}")
    export_dir = finalized_run / "05_export"
    if export_dir.exists():
        typer.echo(f"结果目录：{export_dir}")
        open_path(export_dir)


def build_client_bundle(project_root: Path, output_dir: Path, *, bundle_name: str | None = None) -> BundleBuildResult:
    bundle_name = bundle_name or f"小说拆解智能体-客户交付包-{datetime.now():%Y%m%d}"
    bundle_dir = output_dir / bundle_name
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    app_dir = bundle_dir / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    internal_dir = bundle_dir / "internal"
    internal_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(project_root / "pyproject.toml", app_dir / "pyproject.toml")
    shutil.copy2(project_root / "README.md", app_dir / "README.md")
    shutil.copy2(project_root / "scripts" / "client_bundle_runner.py", internal_dir / "run_client.py")
    shutil.copytree(
        project_root / "src",
        app_dir / "src",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )

    for relative_dir in ["inputs", "runs", "logs", ".client_state"]:
        target = bundle_dir / relative_dir
        target.mkdir(parents=True, exist_ok=True)
        (target / ".keep").write_text("", encoding="utf-8")

    (bundle_dir / ".env.example").write_text(_env_example_text(), encoding="utf-8")
    (bundle_dir / "README_客户使用说明.md").write_text(_client_readme_text(), encoding="utf-8")

    launcher_texts = {
        "0_配置API.bat": _windows_python_launcher_bat("configure"),
        "1_一键开始运行.bat": _windows_python_launcher_bat("launch"),
    }
    for filename, content in launcher_texts.items():
        path = bundle_dir / filename
        encoding = "gbk" if path.suffix == ".bat" else "utf-8"
        newline = "\r\n" if path.suffix == ".bat" else "\n"
        with path.open("w", encoding=encoding, newline=newline) as fh:
            fh.write(content)

    zip_path = output_dir / f"{bundle_name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(bundle_dir.rglob("*")):
            zf.write(path, bundle_dir.name + "/" + str(path.relative_to(bundle_dir)))
    return BundleBuildResult(bundle_dir=bundle_dir, zip_path=zip_path)


def _env_example_text() -> str:
    return """DASHSCOPE_API_KEY=\"请填写你的百炼 Key\"
NOVEL_AGENT_OPENAI_BASE_URL=\"https://dashscope.aliyuncs.com/compatible-mode/v1\"
NOVEL_AGENT_CHAPTER_MODEL=\"qwen-plus\"
NOVEL_AGENT_BOOK_PROVIDER=\"bailian-long\"
NOVEL_AGENT_BOOK_MODEL=\"qwen-long\"
NOVEL_AGENT_JUDGE_MODEL=\"qwen-flash\"
NOVEL_AGENT_LLM_TIMEOUT_SECONDS=\"60\"
"""


def _client_readme_text() -> str:
    return """# 小说拆解智能体客户交付包

## 你只需要做 3 步
1. 双击 `0_配置API`，填写 `.env.local`
2. 把小说文件放进 `inputs/`
3. 双击 `1_一键开始运行`

## 支持输入
- txt
- docx
- pdf

## 正式结果目录
- `runs/<书名>/<run_id>/05_export`

这里会生成：
- `book_analysis.md`
- `book_analysis.docx`
- `book_analysis.pdf`

## 质检目录
- `runs/<书名>/<run_id>/06_eval`

重点看：
- `delivery_integrity_review.json`
- `quality_review.json`
- `reference_alignment_review.json`

## 首次初始化说明
- Windows：会优先尝试使用本机 Python；如果没装，会尝试用 `winget` 安装 Python 3.11
- macOS：会优先尝试使用本机 `python3`；如果没装，会尝试用 `brew` 安装，或打开 Python 官网下载页
- 首次初始化需要联网安装依赖

## 注意
- 请不要把真实 API Key 发给别人
- 真实 API Key 填在本地 `.env.local`，`.env.example` 只做模板
- 正式交付只认 `05_export`
- `1_一键开始运行` 会先后台启动任务，再在当前窗口持续显示实时进度
- 就算把这个进度窗口关掉，后台任务也会继续跑，不靠这个窗口保活
- 当前进度看 `.client_state/job_status.json`
- 启动日志看 `logs/*-launcher.log`
- 后台主输出看 `logs/*-worker.log`
- 详细阶段日志与异常堆栈看 `logs/*-worker-status.log`
- 分析/定稿原始命令输出看 `logs/*-analyze.log` 和 `logs/*-finalize.log`
"""


def _windows_python_launcher_bat(action: str) -> str:
    return f"""@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"

py -3.11 -c "import sys" >nul 2>nul
if not errorlevel 1 goto run_py311

python -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,11) else 1)" >nul 2>nul
if not errorlevel 1 goto run_python

echo 未检测到 Python 3.11+，正在尝试通过 winget 安装 Python 3.11...
winget --version >nul 2>nul
if errorlevel 1 (
  echo 当前机器没有 winget，请先安装 Python 3.11：
  echo https://www.python.org/downloads/windows/
  start "" "https://www.python.org/downloads/windows/"
  pause
  exit /b 1
)
winget install -e --id Python.Python.3.11
py -3.11 -c "import sys" >nul 2>nul
if not errorlevel 1 goto run_py311
echo Python 3.11 安装后仍未检测到，请重新打开此脚本再试。
pause
exit /b 1

:run_py311
py -3.11 "%~dp0internal\\run_client.py" {action}
goto end

:run_python
python "%~dp0internal\\run_client.py" {action}

:end
if errorlevel 1 pause
"""




if __name__ == "__main__":
    app()
