from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import os
import shutil
import subprocess
import sys
import time
import traceback


SUPPORTED_INPUT_SUFFIXES = {".txt", ".docx", ".pdf"}
STATUS_PATH = Path(".client_state/job_status.json")
SESSION_ENV = "NOVEL_AGENT_CLIENT_SESSION_ID"
WORKER_STATUS_LOG_ENV = "NOVEL_AGENT_CLIENT_WORKER_STATUS_LOG"
MONITOR_POLL_SECONDS = 2.0
HEARTBEAT_SECONDS = 10.0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in {"configure", "launch", "worker", "monitor"}:
        print("用法: python run_client.py [configure|launch|worker|monitor]")
        return 2
    action = sys.argv[1]
    bundle_root = Path(__file__).resolve().parents[1]
    try:
        if action == "configure":
            return configure(bundle_root)
        if action == "launch":
            code, session_id = launch_background(bundle_root)
            if code != 0 or not session_id:
                return code
            return monitor_progress(bundle_root, session_id=session_id)
        if action == "monitor":
            return monitor_progress(bundle_root, session_id=os.environ.get(SESSION_ENV))
        return worker(bundle_root)
    except subprocess.CalledProcessError as exc:
        return exc.returncode
    except Exception as exc:  # noqa: BLE001
        print(f"启动失败: {exc}")
        return 1


def configure(bundle_root: Path) -> int:
    env_path = ensure_env_local(bundle_root)
    print(f"请在这里填写 API Key: {env_path}")
    open_path(env_path)
    return 0


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def append_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{now_iso()}] {message}\n")


def shell_join(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def read_status(bundle_root: Path) -> dict[str, object]:
    status_path = bundle_root / STATUS_PATH
    if not status_path.exists():
        return {}
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _status_payload(
    bundle_root: Path,
    *,
    status: str,
    message: str,
    session_id: str,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    existing = read_status(bundle_root)
    payload = {
        **existing,
        "status": status,
        "message": message,
        "session_id": session_id,
        "updated_at": now_iso(),
    }
    if extra:
        payload.update(extra)
    return payload


def launch_background(bundle_root: Path) -> tuple[int, str | None]:
    logs_dir = bundle_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    launcher_log = logs_dir / f"{session_id}-launcher.log"
    worker_stdout = logs_dir / f"{session_id}-worker.log"
    worker_status_log = logs_dir / f"{session_id}-worker-status.log"
    write_status(
        bundle_root,
        _status_payload(
            bundle_root,
            status="launching",
            message="后台任务启动中",
            session_id=session_id,
            extra={
                "launcher_log": str(launcher_log),
                "worker_log": str(worker_stdout),
                "worker_status_log": str(worker_status_log),
                "stage": "launch",
            },
        ),
    )
    creationflags = 0
    stdout_handle = worker_stdout.open("w", encoding="utf-8")
    popen_kwargs: dict[str, object] = {
        "cwd": bundle_root,
        "stdout": stdout_handle,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
        "env": {
            **os.environ,
            SESSION_ENV: session_id,
            WORKER_STATUS_LOG_ENV: str(worker_status_log),
        },
    }
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        popen_kwargs["creationflags"] = creationflags
    command = [sys.executable, str(Path(__file__).resolve()), "worker"]
    append_log(launcher_log, f"bundle_root={bundle_root}")
    append_log(launcher_log, f"python={sys.executable}")
    append_log(launcher_log, f"command={shell_join(command)}")
    append_log(launcher_log, f"status_file={bundle_root / STATUS_PATH}")
    append_log(launcher_log, f"worker_log={worker_stdout}")
    append_log(launcher_log, f"worker_status_log={worker_status_log}")
    try:
        process = subprocess.Popen(command, **popen_kwargs)
    finally:
        stdout_handle.close()
    append_log(launcher_log, f"worker_pid={process.pid}")
    append_log(launcher_log, "后台 worker 已启动，启动脚本现在可以安全退出。")
    write_status(
        bundle_root,
        _status_payload(
            bundle_root,
            status="running",
            message="后台任务已启动，正在等待进度",
            session_id=session_id,
            extra={
                "launcher_log": str(launcher_log),
                "worker_log": str(worker_stdout),
                "worker_status_log": str(worker_status_log),
                "worker_pid": process.pid,
                "stage": "launch",
            },
        ),
    )
    print(f"后台任务已启动，PID={process.pid}")
    print(f"启动日志：{launcher_log}")
    print(f"后台日志：{worker_stdout}")
    print(f"状态日志：{worker_status_log}")
    print("本窗口现在显示实时进度；即使直接关闭，这个后台任务也会继续跑。")
    return 0, session_id


def monitor_progress(bundle_root: Path, *, session_id: str | None) -> int:
    print("实时进度监控已开启，关闭本窗口不会中断后台任务。")
    last_signature = ""
    idle_rounds = 0
    while True:
        status = read_status(bundle_root)
        current_session = str(status.get("session_id") or "")
        if session_id and current_session and current_session != session_id:
            if idle_rounds == 0:
                print(f"检测到新的任务会话：{current_session}")
            session_id = current_session
        message = str(status.get("message") or "等待任务写入状态...")
        phase = str(status.get("stage") or status.get("status") or "unknown")
        last_log_line = str(status.get("last_log_line") or "").strip()
        signature = "|".join(
            [
                str(status.get("status") or ""),
                phase,
                message,
                last_log_line,
                str(status.get("updated_at") or ""),
            ]
        )
        if signature != last_signature:
            print(f"[{status.get('updated_at', now_iso())}] {phase} | {message}")
            if last_log_line:
                print(f"最近进度：{last_log_line}")
            if status.get("current_log"):
                print(f"当前日志：{status['current_log']}")
            last_signature = signature
            idle_rounds = 0
        else:
            idle_rounds += 1
            if idle_rounds % int(max(HEARTBEAT_SECONDS / MONITOR_POLL_SECONDS, 1)) == 0:
                print(f"[{now_iso()}] 任务仍在运行，最近状态：{message}")
        if status.get("status") == "completed":
            print("任务完成。")
            return 0
        if status.get("status") == "failed":
            print("任务失败，请把上面显示的日志文件发我。")
            return 1
        time.sleep(MONITOR_POLL_SECONDS)


def worker(bundle_root: Path) -> int:
    session_id = os.environ.get(SESSION_ENV) or datetime.now().strftime("%Y%m%d-%H%M%S")
    worker_log = Path(os.environ.get(WORKER_STATUS_LOG_ENV, bundle_root / "logs" / f"{session_id}-worker-status.log"))
    append_log(worker_log, f"worker_started session_id={session_id}")
    append_log(worker_log, f"bundle_root={bundle_root}")
    append_log(worker_log, f"python={sys.executable}")
    append_log(worker_log, f"python_version={sys.version.split()[0]}")
    append_log(worker_log, f"platform={sys.platform}")
    try:
        return run_all(bundle_root, worker_log, session_id)
    except subprocess.CalledProcessError as exc:
        append_log(worker_log, f"命令执行失败 code={exc.returncode} command={shell_join([str(part) for part in exc.cmd])}")
        append_log(worker_log, traceback.format_exc().rstrip())
        write_status(
            bundle_root,
            {
                "status": "failed",
                "message": f"运行失败：命令退出码 {exc.returncode}",
                "session_id": session_id,
                "worker_status_log": str(worker_log),
                "failed_command": [str(part) for part in exc.cmd],
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "stage": str(read_status(bundle_root).get("stage") or "unknown"),
                "updated_at": now_iso(),
            },
        )
        print(f"运行失败，详见日志：{worker_log}")
        return exc.returncode or 1
    except Exception as exc:  # noqa: BLE001
        append_log(worker_log, f"未处理异常：{type(exc).__name__}: {exc}")
        append_log(worker_log, traceback.format_exc().rstrip())
        write_status(
            bundle_root,
            {
                "status": "failed",
                "message": f"运行失败：{exc}",
                "session_id": session_id,
                "worker_status_log": str(worker_log),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "stage": str(read_status(bundle_root).get("stage") or "unknown"),
                "updated_at": now_iso(),
            },
        )
        print(f"运行失败，详见日志：{worker_log}")
        return 1


def run_all(bundle_root: Path, worker_log: Path, session_id: str) -> int:
    append_log(worker_log, "开始检查环境与输入文件")
    write_status(
        bundle_root,
        _status_payload(
            bundle_root,
            status="running",
            message="开始检查环境与输入文件",
            session_id=session_id,
            extra={
                "worker_status_log": str(worker_log),
                "stage": "prepare",
            },
        ),
    )
    append_log(worker_log, "检查 .env.local")
    env_path = ensure_env_local(bundle_root)
    append_log(worker_log, f"env_path={env_path}")
    append_log(worker_log, "校验 API Key")
    ensure_api_key(env_path)
    append_log(worker_log, "检查并初始化虚拟环境")
    venv_python = ensure_venv(bundle_root, worker_log)
    append_log(worker_log, f"venv_python={venv_python}")
    append_log(worker_log, "选择输入文件")
    input_path = find_latest_input(bundle_root / "inputs")
    print(f"使用输入文件: {input_path}")
    append_log(worker_log, f"input_path={input_path}")
    write_status(
        bundle_root,
        _status_payload(
            bundle_root,
            status="running",
            message=f"开始分析：{input_path.name}",
            session_id=session_id,
            extra={
                "worker_status_log": str(worker_log),
                "input_path": str(input_path),
                "stage": "analyze",
            },
        ),
    )
    append_log(worker_log, "开始执行 analyze-book")
    run_dir, analyze_log = run_cli(
        bundle_root,
        venv_python,
        [
            "--input",
            str(input_path),
            "--provider",
            "openai",
            "--profile",
            "mvp",
            "--export",
            "markdown,docx,pdf",
        ],
        log_prefix="analyze",
        stage_name="analyze",
        session_id=session_id,
    )
    print(f"分析完成: {run_dir}")
    append_log(worker_log, f"analyze 完成 run_dir={run_dir}")
    append_log(worker_log, f"analyze_log={analyze_log}")
    write_status(
        bundle_root,
        _status_payload(
            bundle_root,
            status="running",
            message="分析完成，开始最终定稿",
            session_id=session_id,
            extra={
                "worker_status_log": str(worker_log),
                "run_dir": str(run_dir),
                "analyze_log": str(analyze_log),
                "current_log": str(analyze_log),
                "stage": "finalize",
            },
        ),
    )
    append_log(worker_log, "开始执行 finalize-delivery")
    finalized_run, finalize_log = run_cli(
        bundle_root,
        venv_python,
        ["finalize-delivery", "--run-dir", str(run_dir), "--export", "markdown,docx,pdf"],
        log_prefix="finalize",
        expected_run_dir=run_dir,
        stage_name="finalize",
        session_id=session_id,
    )
    print(f"定稿完成: {finalized_run}")
    append_log(worker_log, f"finalize 完成 run_dir={finalized_run}")
    append_log(worker_log, f"finalize_log={finalize_log}")
    export_dir = finalized_run / "05_export"
    print(f"结果目录: {export_dir}")
    write_status(
        bundle_root,
        _status_payload(
            bundle_root,
            status="completed",
            message="后台任务完成，已打开结果目录",
            session_id=session_id,
            extra={
                "worker_status_log": str(worker_log),
                "run_dir": str(finalized_run),
                "export_dir": str(export_dir),
                "analyze_log": str(analyze_log),
                "finalize_log": str(finalize_log),
                "current_log": str(finalize_log),
                "stage": "completed",
            },
        ),
    )
    append_log(worker_log, f"准备打开结果目录 export_dir={export_dir}")
    try:
        open_path(export_dir)
        append_log(worker_log, "结果目录已打开")
    except Exception as exc:  # noqa: BLE001
        append_log(worker_log, f"打开结果目录失败，但结果已生成：{type(exc).__name__}: {exc}")
    return 0


def ensure_env_local(bundle_root: Path) -> Path:
    env_path = bundle_root / ".env.local"
    if not env_path.exists():
        shutil.copy2(bundle_root / ".env.example", env_path)
    return env_path


def ensure_api_key(env_path: Path) -> None:
    text = env_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("DASHSCOPE_API_KEY="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value and "请填写" not in value:
                return
    raise RuntimeError("未检测到有效 DASHSCOPE_API_KEY，请先运行 0_配置API.bat 填写 .env.local。")


def write_status(bundle_root: Path, payload: dict[str, object]) -> None:
    status_path = bundle_root / STATUS_PATH
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_last_log_line(log_path: Path) -> str:
    if not log_path.exists():
        return ""
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = [line.strip() for line in fh.readlines()[-20:] if line.strip()]
    except OSError:
        return ""
    return lines[-1] if lines else ""


def ensure_venv(bundle_root: Path, worker_log: Path) -> Path:
    if sys.version_info < (3, 11):
        raise RuntimeError("当前 Python 版本低于 3.11，请先安装 Python 3.11+。")
    venv_python = bundle_root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if venv_python.exists():
        append_log(worker_log, f"检测已有虚拟环境：{venv_python}")
        check = subprocess.run(
            [str(venv_python), "-c", "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if check.returncode != 0:
            append_log(worker_log, "已有 .venv Python 版本不符合要求，删除后重建")
            shutil.rmtree(bundle_root / ".venv", ignore_errors=True)
    if not venv_python.exists():
        append_log(worker_log, "未发现 .venv，开始创建")
        run_subprocess([sys.executable, "-m", "venv", str(bundle_root / ".venv")], cwd=bundle_root, log_path=worker_log)
    run_subprocess([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], cwd=bundle_root, log_path=worker_log)
    run_subprocess([str(venv_python), "-m", "pip", "install", ".\\app" if os.name == "nt" else "./app"], cwd=bundle_root, log_path=worker_log)
    return venv_python


def find_latest_input(inputs_dir: Path) -> Path:
    candidates = [
        path
        for path in inputs_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES
    ]
    if not candidates:
        raise RuntimeError(f"未在 {inputs_dir} 找到小说文件，请放入 txt/docx/pdf。")
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def find_latest_run_dir(runs_dir: Path) -> Path:
    candidates = [
        path
        for path in runs_dir.glob("*/*")
        if path.is_dir() and (path / "04_aggregate" / "book_analysis.json").exists()
    ]
    if not candidates:
        raise RuntimeError(f"未在 {runs_dir} 找到可用运行目录。")
    return max(candidates, key=lambda path: (path.stat().st_mtime, str(path)))


def run_cli(
    bundle_root: Path,
    venv_python: Path,
    args: list[str],
    *,
    log_prefix: str,
    expected_run_dir: Path | None = None,
    stage_name: str,
    session_id: str,
) -> tuple[Path, Path]:
    command = [str(venv_python), "-m", "novel_agent.cli", *args]
    logs_dir = bundle_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{log_prefix}.log"
    print(f"执行中，日志文件: {log_path}")
    write_status(
        bundle_root,
        _status_payload(
            bundle_root,
            status="running",
            message=f"{stage_name} 已启动",
            session_id=session_id,
            extra={
                "stage": stage_name,
                "current_log": str(log_path),
                f"{stage_name}_log": str(log_path),
            },
        ),
    )
    with log_path.open("w", encoding="utf-8") as fh:
        fh.write(f"[{now_iso()}] command={shell_join(command)}\n")
        fh.write(f"[{now_iso()}] cwd={bundle_root}\n")
        process = subprocess.Popen(
            command,
            cwd=bundle_root,
            stdout=fh,
            stderr=subprocess.STDOUT,
        )
        last_heartbeat_at = time.monotonic()
        last_log_line = ""
        while True:
            try:
                return_code = process.wait(timeout=1)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() - last_heartbeat_at >= HEARTBEAT_SECONDS:
                    current_last_log_line = read_last_log_line(log_path)
                    if current_last_log_line != last_log_line and current_last_log_line:
                        last_log_line = current_last_log_line
                    write_status(
                        bundle_root,
                        _status_payload(
                            bundle_root,
                            status="running",
                            message=f"{stage_name} 进行中",
                            session_id=session_id,
                            extra={
                                "stage": stage_name,
                                "current_log": str(log_path),
                                "last_log_line": last_log_line,
                                f"{stage_name}_log": str(log_path),
                            },
                        ),
                    )
                    last_heartbeat_at = time.monotonic()
                continue
            except KeyboardInterrupt:
                print("检测到控制台中断信号，已忽略，任务继续运行中...")
                continue
        fh.write(f"[{now_iso()}] return_code={return_code}\n")
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, command)
    if expected_run_dir is not None:
        run_dir = expected_run_dir
    else:
        run_dir = find_latest_run_dir(bundle_root / "runs")
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{now_iso()}] resolved_run_dir={run_dir}\n")
    write_status(
        bundle_root,
        _status_payload(
            bundle_root,
            status="running",
            message=f"{stage_name} 完成",
            session_id=session_id,
            extra={
                "stage": stage_name,
                "current_log": str(log_path),
                "last_log_line": read_last_log_line(log_path),
                f"{stage_name}_log": str(log_path),
            },
        ),
    )
    return run_dir, log_path


def run_subprocess(command: list[str], *, cwd: Path, log_path: Path) -> None:
    append_log(log_path, f"执行命令：{shell_join(command)}")
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{now_iso()}] ---- subprocess output begin ----\n")
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            stdout=fh,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        fh.write(f"[{now_iso()}] ---- subprocess output end (code={completed.returncode}) ----\n")
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(completed.returncode, command)
    append_log(log_path, "命令执行完成")


def open_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=True)
        return
    subprocess.run(["xdg-open", str(path)], check=True)


if __name__ == "__main__":
    raise SystemExit(main())
