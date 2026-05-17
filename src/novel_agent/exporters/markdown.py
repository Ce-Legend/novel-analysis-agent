from __future__ import annotations

from .report import ReportBlock, render_report_markdown


def render_markdown(report_blocks: list[ReportBlock]) -> str:
    return render_report_markdown(report_blocks)
