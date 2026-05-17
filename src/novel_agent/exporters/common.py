from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MarkdownBlock:
    kind: str
    level: int
    text: str


def parse_markdown(markdown_text: str) -> list[MarkdownBlock]:
    blocks: list[MarkdownBlock] = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("### "):
            blocks.append(MarkdownBlock(kind="heading", level=3, text=line[4:]))
            continue
        if line.startswith("## "):
            blocks.append(MarkdownBlock(kind="heading", level=2, text=line[3:]))
            continue
        if line.startswith("# "):
            blocks.append(MarkdownBlock(kind="heading", level=1, text=line[2:]))
            continue
        if line.startswith("- "):
            blocks.append(MarkdownBlock(kind="bullet", level=1, text=line[2:]))
            continue
        if line.startswith("  - "):
            blocks.append(MarkdownBlock(kind="bullet", level=2, text=line[4:]))
            continue
        blocks.append(MarkdownBlock(kind="paragraph", level=0, text=line))
    return blocks
