from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import hashlib
import json
import logging
import os
import re
import uuid

from .config import AppSettings
from .schemas import RunManifest


class RunLockError(RuntimeError):
    pass


def slugify(value: str) -> str:
    slug = re.sub(r"[^\w\-]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-_")
    if slug:
        return slug[:80]
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"book-{digest}"


@dataclass
class RunContext:
    settings: AppSettings
    book_id: str
    run_id: str
    root_dir: Path
    logger: logging.Logger

    @property
    def ingest_dir(self) -> Path:
        return self.root_dir / "01_ingest"

    @property
    def split_dir(self) -> Path:
        return self.root_dir / "02_split"

    @property
    def chapter_dir(self) -> Path:
        return self.root_dir / "03_chapter_analysis"

    @property
    def aggregate_dir(self) -> Path:
        return self.root_dir / "04_aggregate"

    @property
    def export_dir(self) -> Path:
        return self.root_dir / "05_export"

    @property
    def eval_dir(self) -> Path:
        return self.root_dir / "06_eval"

    @property
    def lock_path(self) -> Path:
        return self.root_dir / ".run.lock"

    def ensure_dirs(self) -> None:
        for path in [
            self.root_dir,
            self.ingest_dir,
            self.split_dir,
            self.chapter_dir,
            self.aggregate_dir,
            self.export_dir,
            self.eval_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def acquire_lock(self) -> None:
        payload = {
            "pid": os.getpid(),
            "run_id": self.run_id,
            "book_id": self.book_id,
            "acquired_at": datetime.utcnow().isoformat(),
        }

        while True:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                existing = _read_lock_payload(self.lock_path)
                existing_pid = existing.get("pid")
                if isinstance(existing_pid, int) and _pid_is_running(existing_pid) and existing_pid != os.getpid():
                    raise RunLockError(
                        f"run_id '{self.run_id}' is already active under pid {existing_pid}. "
                        f"Refusing concurrent execution for {self.root_dir}."
                    )
                self.lock_path.unlink(missing_ok=True)
                continue
            else:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
                return

    def release_lock(self) -> None:
        existing = _read_lock_payload(self.lock_path)
        if existing.get("pid") not in {None, os.getpid()}:
            return
        self.lock_path.unlink(missing_ok=True)


def setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger(f"novel_agent.{log_path.parent.name}.{log_path.stem}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


def build_run_context(settings: AppSettings, input_name: str, run_id: str | None = None) -> RunContext:
    book_id = slugify(Path(input_name).stem)
    actual_run_id = run_id or datetime.utcnow().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    root_dir = settings.runs_dir / book_id / actual_run_id
    root_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logger(root_dir / "run.log")
    ctx = RunContext(settings=settings, book_id=book_id, run_id=actual_run_id, root_dir=root_dir, logger=logger)
    ctx.ensure_dirs()
    return ctx


def build_existing_run_context(settings: AppSettings, run_dir: Path) -> RunContext:
    root_dir = run_dir.resolve()
    if not root_dir.exists() or not root_dir.is_dir():
        raise FileNotFoundError(f"Run directory does not exist: {root_dir}")
    book_id = root_dir.parent.name
    run_id = root_dir.name
    logger = setup_logger(root_dir / "run.log")
    ctx = RunContext(settings=settings, book_id=book_id, run_id=run_id, root_dir=root_dir, logger=logger)
    ctx.ensure_dirs()
    return ctx


def write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(path: Path, manifest: RunManifest) -> None:
    write_json(path, manifest.model_dump(mode="json"))


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_lock_payload(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
