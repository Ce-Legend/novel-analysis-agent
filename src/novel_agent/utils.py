from __future__ import annotations

from pathlib import Path
import json
import math
import os
import re
from typing import Iterable, TypeVar

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback path
    load_dotenv = None

try:
    import tiktoken
except ImportError:  # pragma: no cover - fallback path
    tiktoken = None


T = TypeVar("T")


def load_local_env(filename: str = ".env.local") -> bool:
    if load_dotenv is None:
        return False
    path = Path(filename)
    if not path.exists():
        return False
    return bool(load_dotenv(dotenv_path=path, override=False))


def resolve_api_key(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def detect_input_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return "txt"
    if suffix == ".docx":
        return "docx"
    if suffix == ".pdf":
        return "pdf"
    raise ValueError(f"Unsupported input type: {suffix}")


def read_text_with_fallback(path: Path) -> str:
    encodings = ["utf-8", "utf-8-sig", "gb18030", "gbk", "big5"]
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u3000", " ")
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def estimate_tokens(text: str, model: str = "gpt-5-mini") -> int:
    if tiktoken is None:
        return max(1, math.ceil(len(text) / 3))
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def chunk_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        addition = len(paragraph) + (2 if current else 0)
        if current and current_len + addition > max_chars:
            chunks.append("\n\n".join(current))
            current = [paragraph]
            current_len = len(paragraph)
        else:
            current.append(paragraph)
            current_len += addition
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def batched(items: list[T], size: int) -> Iterable[list[T]]:
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def jsonl_dump(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def jsonl_append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def jsonl_upsert(path: Path, row: dict, *, key_field: str) -> None:
    existing = jsonl_load(path) if path.exists() else []
    deduped: list[dict] = []
    seen = set()
    row_key = row.get(key_field)
    for item in reversed(existing):
        item_key = item.get(key_field)
        if item_key == row_key:
            continue
        if item_key in seen:
            continue
        deduped.append(item)
        if item_key is not None:
            seen.add(item_key)
    deduped.reverse()
    deduped.append(row)
    jsonl_dump(path, deduped)


def jsonl_load(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
