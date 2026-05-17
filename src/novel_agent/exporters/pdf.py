from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .report import ReportBlock


CARD_SECTION_TITLES = {
    "综述",
    "核心亮点总结",
    "核心卖点",
    "CP感分析",
    "开篇文法分析",
}
LABEL_TABLE_SECTION_TITLES = {
    "核心梗",
    "作品名/简介/章节名分析",
    "文笔内容总结",
}
MATRIX_SECTION_TITLES = {
    "推荐定位",
    "剧情看点分层",
    "情感线",
}
CHARACTER_SECTION_TITLE = "人物小传"
PLOT_SECTION_TITLE = "剧情大纲"
UNIT_SECTION_TITLE = "章节细纲"


@dataclass
class PdfTheme:
    title_font: str
    heading_font: str
    body_font: str
    ink: colors.Color = colors.HexColor("#1F2937")
    ink_soft: colors.Color = colors.HexColor("#4B5563")
    border: colors.Color = colors.HexColor("#C9D2DD")
    border_strong: colors.Color = colors.HexColor("#AAB7C6")
    accent: colors.Color = colors.HexColor("#1F4F82")
    accent_soft: colors.Color = colors.HexColor("#EAF1F8")
    paper: colors.Color = colors.white
    paper_tint: colors.Color = colors.HexColor("#F7F3EC")
    page_margin: float = 18 * mm
    section_gap: float = 3.2 * mm
    block_gap: float = 2.2 * mm
    card_padding_x: float = 7
    card_padding_y: float = 4.5
    cell_padding: float = 4.2


@dataclass
class PdfStyles:
    book_title: ParagraphStyle
    section_heading: ParagraphStyle
    card_title: ParagraphStyle
    card_body: ParagraphStyle
    card_body_small: ParagraphStyle
    label: ParagraphStyle
    value: ParagraphStyle
    matrix_header: ParagraphStyle
    matrix_cell: ParagraphStyle
    group_heading: ParagraphStyle
    sub_group_heading: ParagraphStyle
    list_item: ParagraphStyle
    section_note: ParagraphStyle


@dataclass
class PdfBulletGroup:
    title: str
    items: list[str] = field(default_factory=list)


@dataclass
class PdfCardBlock:
    title: str | None = None
    lead: list[str] = field(default_factory=list)
    rows: list[tuple[str, str]] = field(default_factory=list)
    groups: list[PdfBulletGroup] = field(default_factory=list)


@dataclass
class PdfLabelTableBlock:
    title: str | None = None
    lead: list[str] = field(default_factory=list)
    rows: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class PdfMatrixTableBlock:
    title: str | None = None
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    layout: str = "auto"


@dataclass
class PdfUnitCardBlock:
    title: str
    summary_rows: list[tuple[str, str]] = field(default_factory=list)
    groups: list[PdfBulletGroup] = field(default_factory=list)


@dataclass
class PdfSection:
    title: str
    display_title: str
    blocks: list[PdfCardBlock | PdfLabelTableBlock | PdfMatrixTableBlock | PdfUnitCardBlock] = field(default_factory=list)


@dataclass
class PdfDocument:
    title: str
    sections: list[PdfSection] = field(default_factory=list)


def export_pdf(report_blocks: list[ReportBlock], output_path: Path) -> None:
    theme = _build_theme()
    styles = _build_styles(theme)
    document = _compile_pdf_document(report_blocks)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        topMargin=theme.page_margin,
        bottomMargin=theme.page_margin,
        leftMargin=theme.page_margin,
        rightMargin=theme.page_margin,
        title=document.title,
        author="Novel Agent",
    )

    story: list = [
        Paragraph(_xml(document.title), styles.book_title),
        Spacer(1, theme.section_gap),
    ]
    for section_index, section in enumerate(document.sections):
        story.extend(_render_section(section, styles, theme, doc.width))
        if section_index != len(document.sections) - 1:
            story.append(Spacer(1, theme.section_gap))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.build(
        story,
        onFirstPage=lambda canvas, current_doc: _draw_footer(canvas, current_doc, theme),
        onLaterPages=lambda canvas, current_doc: _draw_footer(canvas, current_doc, theme),
    )


def _compile_pdf_document(report_blocks: list[ReportBlock]) -> PdfDocument:
    title = "拆书分析报告"
    sections: list[PdfSection] = []
    current_title: str | None = None
    current_blocks: list[ReportBlock] = []

    for block in report_blocks:
        if block.kind == "heading" and block.level == 1:
            title = block.text.strip() or title
            continue
        if block.kind == "heading" and block.level == 2:
            if current_title is not None:
                sections.append(_compile_pdf_section(current_title, current_blocks, len(sections)))
            current_title = block.text.strip()
            current_blocks = []
            continue
        if current_title is not None:
            current_blocks.append(block)

    if current_title is not None:
        sections.append(_compile_pdf_section(current_title, current_blocks, len(sections)))

    return PdfDocument(title=title, sections=sections)


def _compile_pdf_section(title: str, blocks: list[ReportBlock], index: int) -> PdfSection:
    numbered_title = f"{_to_chinese_section_number(index)}、{title}"
    if title in CARD_SECTION_TITLES:
        compiled_blocks = _compile_card_section(blocks)
    elif title in LABEL_TABLE_SECTION_TITLES:
        compiled_blocks = _compile_label_table_section(blocks)
    elif title in MATRIX_SECTION_TITLES:
        compiled_blocks = _compile_matrix_section(title, blocks)
    elif title == CHARACTER_SECTION_TITLE:
        compiled_blocks = _compile_character_section(blocks)
    elif title == PLOT_SECTION_TITLE:
        compiled_blocks = _compile_plot_section(blocks)
    elif title == UNIT_SECTION_TITLE:
        compiled_blocks = _compile_unit_section(blocks)
    else:
        compiled_blocks = _compile_card_section(blocks)
    return PdfSection(title=title, display_title=numbered_title, blocks=compiled_blocks)


def _compile_card_section(blocks: list[ReportBlock]) -> list[PdfCardBlock]:
    preamble, groups = _partition_by_h3(blocks)
    cards: list[PdfCardBlock] = []
    preamble_card = _blocks_to_card(None, preamble)
    if _card_has_content(preamble_card):
        cards.append(preamble_card)
    for group in groups:
        card = _blocks_to_card(group["title"], group["blocks"])
        if _card_has_content(card):
            cards.append(card)
    return cards


def _compile_label_table_section(blocks: list[ReportBlock]) -> list[PdfLabelTableBlock]:
    preamble, groups = _partition_by_h3(blocks)
    tables: list[PdfLabelTableBlock] = []
    table = _blocks_to_label_table(None, preamble)
    if _label_table_has_content(table):
        tables.append(table)
    for group in groups:
        table = _blocks_to_label_table(group["title"], group["blocks"])
        if _label_table_has_content(table):
            tables.append(table)
    return tables


def _compile_matrix_section(title: str, blocks: list[ReportBlock]) -> list[PdfMatrixTableBlock | PdfCardBlock]:
    if title == "情感线":
        matrix = _compile_relationship_matrix(blocks)
        return [matrix] if matrix.rows else _compile_card_section(blocks)
    matrix_rows = _parse_group_rows(blocks)
    if not matrix_rows:
        return _compile_card_section(blocks)
    max_items = max((len(items) for _, items in matrix_rows), default=1)
    headers = ["维度"] + [f"要点{i}" for i in range(1, max_items + 1)]
    rows = [[label, *items, *([""] * (max_items - len(items)))] for label, items in matrix_rows]
    return [PdfMatrixTableBlock(headers=headers, rows=rows, layout="group_matrix")]


def _compile_character_section(blocks: list[ReportBlock]) -> list[PdfLabelTableBlock]:
    preamble, groups = _partition_by_h3(blocks)
    tables: list[PdfLabelTableBlock] = []
    preamble_table = _blocks_to_label_table(None, preamble)
    if _label_table_has_content(preamble_table):
        tables.append(preamble_table)
    for group in groups:
        table = _blocks_to_label_table(group["title"], group["blocks"])
        if _label_table_has_content(table):
            tables.append(table)
    return tables


def _compile_plot_section(blocks: list[ReportBlock]) -> list[PdfCardBlock | PdfMatrixTableBlock]:
    preamble, groups = _partition_by_h3(blocks)
    compiled: list[PdfCardBlock | PdfMatrixTableBlock] = []
    preamble_card = _blocks_to_card(None, preamble)
    if _card_has_content(preamble_card):
        compiled.append(preamble_card)

    for group in groups:
        if group["title"] == "核心故事线-主线/副线":
            story_line_matrix = _compile_story_line_matrix(group["title"], group["blocks"])
            if story_line_matrix.rows:
                compiled.append(story_line_matrix)
                continue
        if group["title"] == "主线大纲":
            phase_cards = _compile_phase_outline_cards(group["blocks"])
            if phase_cards:
                compiled.extend(phase_cards)
                continue
        card = _blocks_to_card(group["title"], group["blocks"])
        if _card_has_content(card):
            compiled.append(card)
    return compiled


def _compile_unit_section(blocks: list[ReportBlock]) -> list[PdfUnitCardBlock | PdfCardBlock]:
    preamble, groups = _partition_by_h3(blocks)
    compiled: list[PdfUnitCardBlock | PdfCardBlock] = []
    preamble_card = _blocks_to_card(None, preamble)
    if _card_has_content(preamble_card):
        compiled.append(preamble_card)
    for group in groups:
        summary_rows: list[tuple[str, str]] = []
        detail_groups: list[PdfBulletGroup] = []
        current_group: PdfBulletGroup | None = None
        for block in group["blocks"]:
            if block.kind == "bullet" and block.style == "unit_label" and block.level == 1:
                pair = _split_label_value(block.text)
                if pair:
                    summary_rows.append(pair)
                continue
            if block.kind == "bullet" and block.style == "group_label" and block.level == 1:
                if current_group and current_group.items:
                    detail_groups.append(current_group)
                current_group = PdfBulletGroup(title=block.text.strip())
                continue
            if block.kind == "bullet" and block.level >= 2 and current_group is not None:
                current_group.items.append(block.text.strip())
        if current_group and current_group.items:
            detail_groups.append(current_group)
        if summary_rows or detail_groups:
            compiled.append(PdfUnitCardBlock(title=group["title"], summary_rows=summary_rows, groups=detail_groups))
            continue
        fallback_card = _blocks_to_card(group["title"], group["blocks"])
        if _card_has_content(fallback_card):
            compiled.append(fallback_card)
    return compiled


def _compile_story_line_matrix(title: str, blocks: list[ReportBlock]) -> PdfMatrixTableBlock:
    rows: list[list[str]] = []
    current_name = ""
    current_category = ""
    current_content = ""
    current_key_points: list[str] = []
    pending_key_points: list[str] = []

    def flush_current() -> None:
        nonlocal current_name, current_category, current_content, current_key_points
        if not any([current_name, current_category, current_content]):
            return
        rows.append(
            [
                current_name or "故事线",
                current_category or "线索",
                current_content or "内容待补充。",
                "；".join(current_key_points) or "关键点待补充。",
            ]
        )
        current_name = ""
        current_category = ""
        current_content = ""
        current_key_points = []

    for block in blocks:
        if block.kind == "bullet" and block.style == "section_item" and block.level == 1:
            flush_current()
            current_name, current_category, current_content = _parse_story_line_item(block.text)
            if pending_key_points and not current_key_points:
                current_key_points = pending_key_points[:]
                pending_key_points = []
            continue
        if block.kind == "bullet" and block.style == "group_label" and block.text.strip() == "关键点":
            continue
        if block.kind == "bullet" and block.level >= 2:
            if current_name or current_content:
                current_key_points.append(block.text.strip())
            else:
                pending_key_points.append(block.text.strip())

    flush_current()
    return PdfMatrixTableBlock(
        title=title,
        headers=["名称", "分类", "内容", "关键点"],
        rows=rows,
        layout="story_line",
    )


def _compile_phase_outline_cards(blocks: list[ReportBlock]) -> list[PdfCardBlock]:
    cards: list[PdfCardBlock] = []
    current_title: str | None = None
    current_groups: list[PdfBulletGroup] = []
    current_event_title: str | None = None
    current_event_items: list[str] = []

    def flush_event() -> None:
        nonlocal current_event_title, current_event_items
        if current_event_title:
            current_groups.append(PdfBulletGroup(title=current_event_title, items=current_event_items[:] or ["对应事件说明仍需补充。"]))
        current_event_title = None
        current_event_items = []

    def flush_current() -> None:
        nonlocal current_title, current_groups
        flush_event()
        if current_title:
            cards.append(
                PdfCardBlock(
                    title=current_title,
                    groups=current_groups[:] or [PdfBulletGroup(title="事件1：阶段事件（阶段范围未明）", items=["阶段事件仍需进一步提炼。"])],
                )
            )
        current_title = None
        current_groups = []

    for block in blocks:
        if block.kind != "bullet":
            continue
        if block.level == 1:
            flush_current()
            current_title = block.text.strip()
            continue
        if block.level == 2 and current_title is not None:
            flush_event()
            current_event_title = block.text.strip()
            continue
        if block.level >= 3 and current_event_title is not None:
            current_event_items.append(block.text.strip())
    flush_current()
    return cards


def _compile_relationship_matrix(blocks: list[ReportBlock]) -> PdfMatrixTableBlock:
    rows: list[list[str]] = []
    pattern = re.compile(r"^(?P<pair>.+?)\s*/\s*(?P<stage>.+?)（(?P<chapter>.+?)）[:：](?P<content>.+)$")
    for block in blocks:
        if block.kind != "bullet" or block.level != 1:
            continue
        match = pattern.match(block.text.strip())
        if not match:
            label, value = _split_label_value(block.text) or ("关系阶段", block.text.strip())
            rows.append([label, "阶段未明", "范围未明", value])
            continue
        rows.append(
            [
                match.group("pair").strip(),
                match.group("stage").strip(),
                match.group("chapter").strip(),
                match.group("content").strip(),
            ]
        )
    return PdfMatrixTableBlock(
        headers=["角色关系", "阶段", "章节", "推进说明"],
        rows=rows,
        layout="relationship",
    )


def _blocks_to_card(title: str | None, blocks: list[ReportBlock]) -> PdfCardBlock:
    lead: list[str] = []
    rows: list[tuple[str, str]] = []
    groups: list[PdfBulletGroup] = []
    current_group: PdfBulletGroup | None = None

    def flush_group() -> None:
        nonlocal current_group
        if current_group and current_group.items:
            groups.append(current_group)
        current_group = None

    for block in blocks:
        if block.kind == "paragraph":
            flush_group()
            lead.append(block.text.strip())
            continue
        if block.kind != "bullet":
            continue
        if block.style == "group_label" and block.level == 1:
            flush_group()
            current_group = PdfBulletGroup(title=block.text.strip())
            continue
        if block.level >= 2 and current_group is not None:
            current_group.items.append(block.text.strip())
            continue
        flush_group()
        pair = _split_label_value(block.text)
        if pair:
            rows.append(pair)
        else:
            lead.append(block.text.strip())

    flush_group()
    return PdfCardBlock(title=title, lead=lead, rows=rows, groups=groups)


def _blocks_to_label_table(title: str | None, blocks: list[ReportBlock]) -> PdfLabelTableBlock:
    lead: list[str] = []
    rows: list[tuple[str, str]] = []
    for block in blocks:
        if block.kind == "paragraph":
            lead.append(block.text.strip())
            continue
        if block.kind != "bullet":
            continue
        if block.style == "group_label" and block.level == 1:
            continue
        if block.level >= 2:
            continue
        pair = _split_label_value(block.text)
        if pair:
            rows.append(pair)
        else:
            lead.append(block.text.strip())

    for label, items in _parse_group_rows(blocks):
        rows.append((label, "；".join(items)))

    rows = _dedupe_rows(rows)
    return PdfLabelTableBlock(title=title, lead=lead, rows=rows)


def _parse_group_rows(blocks: list[ReportBlock]) -> list[tuple[str, list[str]]]:
    rows: list[tuple[str, list[str]]] = []
    current_label: str | None = None
    current_items: list[str] = []

    def flush_current() -> None:
        nonlocal current_label, current_items
        if current_label:
            rows.append((current_label, current_items[:] or ["待补充。"]))
        current_label = None
        current_items = []

    for block in blocks:
        if block.kind == "bullet" and block.style == "group_label" and block.level == 1:
            flush_current()
            current_label = block.text.strip()
            continue
        if block.kind == "bullet" and block.level >= 2 and current_label is not None:
            current_items.append(block.text.strip())
            continue
        if block.kind == "bullet" and block.level == 1 and block.style == "section_item":
            pair = _split_label_value(block.text)
            if pair:
                rows.append((pair[0], [pair[1]]))

    flush_current()
    return _dedupe_group_rows(rows)


def _partition_by_h3(blocks: list[ReportBlock]) -> tuple[list[ReportBlock], list[dict[str, str | list[ReportBlock]]]]:
    preamble: list[ReportBlock] = []
    groups: list[dict[str, str | list[ReportBlock]]] = []
    current_title: str | None = None
    current_blocks: list[ReportBlock] = []

    for block in blocks:
        if block.kind == "heading" and block.level == 3:
            if current_title is None:
                if current_blocks:
                    preamble.extend(current_blocks)
            else:
                groups.append({"title": current_title, "blocks": current_blocks[:]})
            current_title = block.text.strip()
            current_blocks = []
            continue
        current_blocks.append(block)

    if current_title is None:
        preamble.extend(current_blocks)
    else:
        groups.append({"title": current_title, "blocks": current_blocks[:]})

    return preamble, groups


def _render_section(section: PdfSection, styles: PdfStyles, theme: PdfTheme, width: float) -> list:
    heading = _render_section_heading(section.display_title, styles, theme, width)
    if not section.blocks:
        return [heading]

    flowables: list = []
    first_block_flowables = _render_layout_block(section.blocks[0], styles, theme, width)
    if _should_keep_heading_with_first_block(section.blocks[0]):
        flowables.append(KeepTogether([heading, Spacer(1, theme.block_gap), *first_block_flowables]))
    else:
        flowables.append(heading)
        flowables.append(Spacer(1, theme.block_gap))
        flowables.extend(first_block_flowables)
    for index, block in enumerate(section.blocks[1:], start=1):
        flowables.append(Spacer(1, theme.block_gap))
        flowables.extend(_render_layout_block(block, styles, theme, width))
    return flowables


def _render_layout_block(
    block: PdfCardBlock | PdfLabelTableBlock | PdfMatrixTableBlock | PdfUnitCardBlock,
    styles: PdfStyles,
    theme: PdfTheme,
    width: float,
) -> list:
    if isinstance(block, PdfUnitCardBlock):
        return _render_unit_card(block, styles, theme, width)
    if isinstance(block, PdfMatrixTableBlock):
        return _render_matrix_table_blocks(block, styles, theme, width)
    if isinstance(block, PdfLabelTableBlock):
        return [_wrap_keep_together(_render_label_table_block(block, styles, theme, width), keep=False)]
    if _should_render_card_groups_loose(block):
        return _render_loose_group_card(block, styles, theme, width)
    return [_wrap_keep_together(_render_card_block(block, styles, theme, width), keep=False)]


def _render_matrix_table_blocks(
    block: PdfMatrixTableBlock,
    styles: PdfStyles,
    theme: PdfTheme,
    width: float,
) -> list:
    flowables: list = []
    for index, chunk in enumerate(_split_matrix_table_block(block), start=1):
        if index > 1:
            flowables.append(Spacer(1, theme.block_gap))
        flowables.append(_wrap_keep_together(_render_matrix_table(chunk, styles, theme, width), keep=_should_keep_table_block(chunk)))
    return flowables


def _split_matrix_table_block(block: PdfMatrixTableBlock) -> list[PdfMatrixTableBlock]:
    max_rows = _matrix_chunk_row_limit(block)
    if len(block.rows) <= max_rows:
        return [block]
    chunks: list[PdfMatrixTableBlock] = []
    for index in range(0, len(block.rows), max_rows):
        rows = block.rows[index : index + max_rows]
        title = block.title if index == 0 else (f"{block.title}（续）" if block.title else None)
        chunks.append(PdfMatrixTableBlock(title=title, headers=block.headers[:], rows=rows, layout=block.layout))
    return chunks


def _matrix_chunk_row_limit(block: PdfMatrixTableBlock) -> int:
    if block.layout == "relationship":
        return 3
    if block.layout == "story_line":
        return 3
    return 6


def _render_section_heading(title: str, styles: PdfStyles, theme: PdfTheme, width: float) -> Table:
    table = Table(
        [[Paragraph(_xml(title), styles.section_heading)]],
        colWidths=[width],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), theme.paper_tint),
                ("LINEBEFORE", (0, 0), (0, -1), 3, theme.accent),
                ("BOX", (0, 0), (-1, -1), 0.7, theme.border),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _render_card_block(block: PdfCardBlock, styles: PdfStyles, theme: PdfTheme, width: float) -> Table:
    content: list = _build_block_content(
        lead=block.lead,
        rows=block.rows,
        groups=block.groups,
        styles=styles,
        theme=theme,
        width=width - 2 * theme.card_padding_x,
    )
    return _build_card_table(block.title, content, styles, theme, width)


def _render_label_table_block(block: PdfLabelTableBlock, styles: PdfStyles, theme: PdfTheme, width: float) -> Table:
    content: list = []
    for paragraph in block.lead:
        content.append(Paragraph(_xml(paragraph), styles.card_body))
        content.append(Spacer(1, 1.5 * mm))
    if block.rows:
        content.append(_build_label_value_table(block.rows, styles, theme, width - 2 * theme.card_padding_x))
    if content and isinstance(content[-1], Spacer):
        content.pop()
    return _build_card_table(block.title, content, styles, theme, width)


def _render_matrix_table(block: PdfMatrixTableBlock, styles: PdfStyles, theme: PdfTheme, width: float) -> Table:
    column_count = max(len(block.headers), 1)
    rows = [block.headers] + [row + [""] * (column_count - len(row)) for row in block.rows]
    data = []
    for row_index, row in enumerate(rows):
        style = styles.matrix_header if row_index == 0 else styles.matrix_cell
        data.append([Paragraph(_xml(cell), style) for cell in row])
    table = Table(
        data,
        colWidths=_resolve_matrix_col_widths(block, width),
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), theme.accent_soft),
                ("TEXTCOLOR", (0, 0), (-1, 0), theme.accent),
                ("GRID", (0, 0), (-1, -1), 0.6, theme.border),
                ("BOX", (0, 0), (-1, -1), 0.8, theme.border_strong),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), theme.cell_padding),
                ("RIGHTPADDING", (0, 0), (-1, -1), theme.cell_padding),
                ("TOPPADDING", (0, 0), (-1, -1), theme.cell_padding - 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), theme.cell_padding - 1),
            ]
        )
    )
    for row_index in range(1, len(rows)):
        if row_index % 2 == 0:
            table.setStyle(TableStyle([("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F9FBFD"))]))
    content: list = []
    if block.title:
        content.append(Paragraph(_xml(block.title), styles.card_title))
        content.append(Spacer(1, 1.6 * mm))
    content.append(table)
    return _build_card_table(None, content, styles, theme, width)


def _render_unit_card(block: PdfUnitCardBlock, styles: PdfStyles, theme: PdfTheme, width: float) -> list:
    content: list = [_build_card_title_bar(block.title, styles, theme, width)]
    if block.summary_rows:
        content.append(Spacer(1, 1.6 * mm))
        content.append(_build_label_value_table(block.summary_rows, styles, theme, width))
    for group_index, group in enumerate(block.groups, start=1):
        if content:
            content.append(Spacer(1, 1.6 * mm))
        content.append(_build_sub_group_bar(f"{group_index}. {group.title}", styles, theme, width))
        content.append(Spacer(1, 1.2 * mm))
        for item_index, item in enumerate(group.items, start=1):
            if group.title == "情感推进":
                label, detail = _split_relationship_progress_item(item)
                if label and detail:
                    content.append(Paragraph(f"{item_index}. {_relationship_label_xml(label)}", styles.list_item))
                    content.append(Paragraph(_xml(detail), styles.card_body_small))
                    continue
            content.append(Paragraph(_xml(f"{item_index}. {item}"), styles.list_item))
    return content


def _render_loose_group_card(block: PdfCardBlock, styles: PdfStyles, theme: PdfTheme, width: float) -> list:
    content: list = []
    if block.title:
        content.append(_build_card_title_bar(block.title, styles, theme, width))
        content.append(Spacer(1, 1.5 * mm))
    for lead in block.lead:
        content.append(Paragraph(_xml(lead), styles.card_body))
        content.append(Spacer(1, 1.2 * mm))
    if block.rows:
        content.append(_build_label_value_table(block.rows, styles, theme, width))
        content.append(Spacer(1, 1.5 * mm))
    for group_index, group in enumerate(block.groups, start=1):
        content.append(_build_sub_group_bar(f"{group_index}. {group.title}", styles, theme, width))
        content.append(Spacer(1, 1.1 * mm))
        for item_index, item in enumerate(group.items, start=1):
            content.append(Paragraph(_xml(f"{item_index}. {item}"), styles.list_item))
        if group_index != len(block.groups):
            content.append(Spacer(1, 1.5 * mm))
    if content and isinstance(content[-1], Spacer):
        content.pop()
    return content


def _build_card_title_bar(title: str, styles: PdfStyles, theme: PdfTheme, width: float) -> Table:
    table = Table([[Paragraph(_xml(title), styles.card_title)]], colWidths=[width], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.8, theme.border_strong),
                ("BACKGROUND", (0, 0), (-1, -1), theme.accent_soft),
                ("LEFTPADDING", (0, 0), (-1, -1), theme.card_padding_x),
                ("RIGHTPADDING", (0, 0), (-1, -1), theme.card_padding_x),
                ("TOPPADDING", (0, 0), (-1, -1), theme.card_padding_y),
                ("BOTTOMPADDING", (0, 0), (-1, -1), theme.card_padding_y),
            ]
        )
    )
    return table


def _build_card_table(title: str | None, content: list, styles: PdfStyles, theme: PdfTheme, width: float) -> Table:
    rows = []
    if title:
        rows.append([Paragraph(_xml(title), styles.card_title)])
    rows.append([content or [Paragraph(_xml("信息暂未提炼完整。"), styles.card_body)]])
    table = Table(rows, colWidths=[width], splitByRow=1, hAlign="LEFT")
    style_commands = [
        ("BOX", (0, 0), (-1, -1), 0.8, theme.border_strong),
        ("BACKGROUND", (0, 0), (-1, -1), theme.paper),
        ("LEFTPADDING", (0, 0), (-1, -1), theme.card_padding_x),
        ("RIGHTPADDING", (0, 0), (-1, -1), theme.card_padding_x),
        ("TOPPADDING", (0, 0), (-1, -1), theme.card_padding_y),
        ("BOTTOMPADDING", (0, 0), (-1, -1), theme.card_padding_y),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    if title:
        style_commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), theme.accent_soft),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, theme.border),
            ]
        )
    table.setStyle(TableStyle(style_commands))
    return table


def _build_block_content(
    *,
    lead: list[str],
    rows: list[tuple[str, str]],
    groups: list[PdfBulletGroup],
    styles: PdfStyles,
    theme: PdfTheme,
    width: float,
) -> list:
    content: list = []
    for paragraph in lead:
        content.append(Paragraph(_xml(paragraph), styles.card_body))
        content.append(Spacer(1, 1.5 * mm))
    if rows:
        content.append(_build_label_value_table(rows, styles, theme, width))
    for group_index, group in enumerate(groups, start=1):
        if content:
            content.append(Spacer(1, 1.5 * mm))
        content.append(_build_sub_group_bar(f"{group_index}. {group.title}", styles, theme, width))
        content.append(Spacer(1, 1.1 * mm))
        for item_index, item in enumerate(group.items, start=1):
            content.append(Paragraph(_xml(f"{item_index}. {item}"), styles.list_item))
    if content and isinstance(content[-1], Spacer):
        content.pop()
    return content


def _build_label_value_table(
    rows: list[tuple[str, str]],
    styles: PdfStyles,
    theme: PdfTheme,
    width: float,
) -> Table:
    data = [[Paragraph(_xml(label), styles.label), Paragraph(_xml(value), styles.value)] for label, value in rows]
    label_width = 28 * mm
    table = Table(data, colWidths=[label_width, max(width - label_width, 40 * mm)], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.45, theme.border),
                ("BOX", (0, 0), (-1, -1), 0.6, theme.border_strong),
                ("BACKGROUND", (0, 0), (0, -1), theme.paper_tint),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), theme.cell_padding),
                ("RIGHTPADDING", (0, 0), (-1, -1), theme.cell_padding),
                ("TOPPADDING", (0, 0), (-1, -1), theme.cell_padding - 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), theme.cell_padding - 1),
            ]
        )
    )
    for row_index in range(len(rows)):
        if row_index % 2 == 1:
            table.setStyle(TableStyle([("BACKGROUND", (1, row_index), (1, row_index), colors.HexColor("#FCFDFE"))]))
    return table


def _build_sub_group_bar(title: str, styles: PdfStyles, theme: PdfTheme, width: float) -> Table:
    table = Table([[Paragraph(_xml(title), styles.sub_group_heading)]], colWidths=[width], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F8FC")),
                ("LINEBEFORE", (0, 0), (0, -1), 2.2, theme.accent),
                ("BOX", (0, 0), (-1, -1), 0.45, theme.border),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 4.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
            ]
        )
    )
    return table


def _resolve_matrix_col_widths(block: PdfMatrixTableBlock, width: float) -> list[float]:
    column_count = max(len(block.headers), 1)
    if block.layout == "story_line" and column_count == 4:
        widths = [26 * mm, 22 * mm, 78 * mm]
        widths.append(max(width - sum(widths), 32 * mm))
        return widths
    if block.layout == "relationship" and column_count == 4:
        widths = [30 * mm, 18 * mm, 20 * mm]
        widths.append(max(width - sum(widths), 40 * mm))
        return widths
    if column_count == 2:
        first = 30 * mm
        return [first, max(width - first, 50 * mm)]
    if column_count == 3:
        first = 26 * mm
        second = 30 * mm
        return [first, second, max(width - first - second, 60 * mm)]
    first = 24 * mm
    remaining = max(width - first, 60 * mm)
    other = remaining / max(column_count - 1, 1)
    return [first] + [other] * (column_count - 1)


def _wrap_keep_together(flowable, *, keep: bool):
    if keep:
        return KeepTogether([flowable])
    return flowable


def _should_keep_heading_with_first_block(
    block: PdfCardBlock | PdfLabelTableBlock | PdfMatrixTableBlock | PdfUnitCardBlock,
) -> bool:
    if isinstance(block, PdfCardBlock) and _should_render_card_groups_loose(block):
        return False
    return isinstance(block, (PdfCardBlock, PdfLabelTableBlock))


def _should_keep_table_block(block: PdfMatrixTableBlock) -> bool:
    return block.layout == "relationship"


def _should_render_card_groups_loose(block: PdfCardBlock) -> bool:
    return not block.title and not block.rows and len(block.groups) >= 2


def _build_theme() -> PdfTheme:
    heading_font = _register_font(
        "NovelHeading",
        ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/STHeiti Light.ttc"],
        fallback="STSong-Light",
    )
    body_font = _register_font(
        "NovelBody",
        ["/System/Library/Fonts/Supplemental/Songti.ttc", "/System/Library/Fonts/STHeiti Light.ttc"],
        fallback="STSong-Light",
    )
    title_font = heading_font
    return PdfTheme(title_font=title_font, heading_font=heading_font, body_font=body_font)


def _build_styles(theme: PdfTheme) -> PdfStyles:
    base = getSampleStyleSheet()
    return PdfStyles(
        book_title=ParagraphStyle(
            "BookTitle",
            parent=base["Title"],
            fontName=theme.title_font,
            fontSize=22,
            leading=28,
            alignment=TA_CENTER,
            textColor=theme.ink,
            spaceAfter=0,
        ),
        section_heading=ParagraphStyle(
            "SectionHeading",
            parent=base["Heading1"],
            fontName=theme.heading_font,
            fontSize=15,
            leading=20,
            alignment=TA_LEFT,
            textColor=theme.ink,
            spaceAfter=0,
            spaceBefore=0,
        ),
        card_title=ParagraphStyle(
            "CardTitle",
            parent=base["Heading2"],
            fontName=theme.heading_font,
            fontSize=12.2,
            leading=16,
            textColor=theme.accent,
            spaceAfter=0,
            spaceBefore=0,
        ),
        card_body=ParagraphStyle(
            "CardBody",
            parent=base["BodyText"],
            fontName=theme.body_font,
            fontSize=10.2,
            leading=15.3,
            textColor=theme.ink,
            spaceAfter=0,
            spaceBefore=0,
        ),
        card_body_small=ParagraphStyle(
            "CardBodySmall",
            parent=base["BodyText"],
            fontName=theme.body_font,
            fontSize=9.4,
            leading=13.4,
            textColor=theme.ink,
            spaceAfter=0,
            spaceBefore=0,
        ),
        label=ParagraphStyle(
            "Label",
            parent=base["BodyText"],
            fontName=theme.heading_font,
            fontSize=9.8,
            leading=13.8,
            textColor=theme.ink,
            spaceAfter=0,
            spaceBefore=0,
        ),
        value=ParagraphStyle(
            "Value",
            parent=base["BodyText"],
            fontName=theme.body_font,
            fontSize=9.8,
            leading=14.2,
            textColor=theme.ink,
            spaceAfter=0,
            spaceBefore=0,
        ),
        matrix_header=ParagraphStyle(
            "MatrixHeader",
            parent=base["BodyText"],
            fontName=theme.heading_font,
            fontSize=9.6,
            leading=13.2,
            textColor=theme.accent,
            spaceAfter=0,
            spaceBefore=0,
        ),
        matrix_cell=ParagraphStyle(
            "MatrixCell",
            parent=base["BodyText"],
            fontName=theme.body_font,
            fontSize=9.3,
            leading=13.2,
            textColor=theme.ink,
            spaceAfter=0,
            spaceBefore=0,
        ),
        group_heading=ParagraphStyle(
            "GroupHeading",
            parent=base["BodyText"],
            fontName=theme.heading_font,
            fontSize=10.1,
            leading=14.2,
            textColor=theme.accent,
            spaceAfter=0,
            spaceBefore=0,
        ),
        sub_group_heading=ParagraphStyle(
            "SubGroupHeading",
            parent=base["BodyText"],
            fontName=theme.heading_font,
            fontSize=9.8,
            leading=13.6,
            textColor=theme.accent,
            spaceAfter=0,
            spaceBefore=0,
        ),
        list_item=ParagraphStyle(
            "ListItem",
            parent=base["BodyText"],
            fontName=theme.body_font,
            fontSize=9.6,
            leading=13.8,
            textColor=theme.ink,
            leftIndent=10,
            firstLineIndent=-8,
            bulletIndent=0,
            spaceAfter=0,
            spaceBefore=0,
        ),
        section_note=ParagraphStyle(
            "SectionNote",
            parent=base["BodyText"],
            fontName=theme.body_font,
            fontSize=8.8,
            leading=12,
            textColor=theme.ink_soft,
            alignment=TA_CENTER,
            spaceAfter=0,
            spaceBefore=0,
        ),
    )


def _draw_footer(canvas, doc, theme: PdfTheme) -> None:  # noqa: ANN001
    canvas.saveState()
    canvas.setStrokeColor(theme.border)
    canvas.setLineWidth(0.4)
    canvas.line(doc.leftMargin, 12 * mm, A4[0] - doc.rightMargin, 12 * mm)
    canvas.setFont(theme.body_font, 9)
    canvas.setFillColor(theme.ink_soft)
    canvas.drawCentredString(A4[0] / 2, 8 * mm, f"{doc.page}")
    canvas.restoreState()


def _register_font(alias: str, candidates: list[str], *, fallback: str) -> str:
    try:
        pdfmetrics.getFont(alias)
        return alias
    except KeyError:
        pass

    for candidate in candidates:
        path = Path(candidate)
        if not path.exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont(alias, str(path)))
            return alias
        except Exception:
            continue

    try:
        pdfmetrics.getFont(fallback)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(fallback))
    return fallback


def _split_label_value(text: str) -> tuple[str, str] | None:
    raw = text.strip()
    if not raw:
        return None
    if "：" in raw:
        label, value = raw.split("：", 1)
        return label.strip(), value.strip()
    if ":" in raw:
        label, value = raw.split(":", 1)
        return label.strip(), value.strip()
    return None


def _split_relationship_progress_item(text: str) -> tuple[str, str]:
    match = re.match(r"^(?P<label>.+?\s/\s.+?)[:：](?P<detail>.+)$", text.strip())
    if not match:
        return "", ""
    return match.group("label").strip(), match.group("detail").strip()


def _relationship_label_xml(label: str) -> str:
    safe_label = escape(label).replace(" / ", "&nbsp;/&nbsp;")
    return safe_label


def _parse_story_line_item(text: str) -> tuple[str, str, str]:
    match = re.match(r"^(?P<left>.+?)[：:](?P<content>.+)$", text.strip())
    if match:
        left = match.group("left")
        content = match.group("content")
    else:
        left = text.strip()
        content = ""
    name, _, category = left.partition("｜")
    if not category:
        category = "线索"
    return name.strip(), category.strip(), content.strip()


def _dedupe_rows(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[tuple[str, str]] = []
    for row in rows:
        normalized = (row[0].strip(), row[1].strip())
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _dedupe_group_rows(rows: list[tuple[str, list[str]]]) -> list[tuple[str, list[str]]]:
    merged: dict[str, list[str]] = {}
    for label, items in rows:
        bucket = merged.setdefault(label, [])
        for item in items:
            stripped = item.strip()
            if stripped and stripped not in bucket:
                bucket.append(stripped)
    return [(label, items) for label, items in merged.items()]


def _card_has_content(card: PdfCardBlock) -> bool:
    return bool(card.title or card.lead or card.rows or any(group.items for group in card.groups))


def _label_table_has_content(table: PdfLabelTableBlock) -> bool:
    return bool(table.title or table.lead or table.rows)


def _xml(text: str) -> str:
    return escape(text.strip()).replace("\n", "<br/>")


def _to_chinese_section_number(index: int) -> str:
    numerals = "零一二三四五六七八九"
    if index < 10:
        return numerals[index]
    if index == 10:
        return "十"
    if index < 20:
        return f"十{numerals[index - 10]}"
    tens, ones = divmod(index, 10)
    if ones == 0:
        return f"{numerals[tens]}十"
    return f"{numerals[tens]}十{numerals[ones]}"
