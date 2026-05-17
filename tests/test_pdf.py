import re

from pypdf import PdfReader

from novel_agent.exporters.pdf import (
    PdfCardBlock,
    PdfMatrixTableBlock,
    PdfUnitCardBlock,
    _compile_pdf_document,
    export_pdf,
)
from novel_agent.exporters.report import ReportBlock


def test_pdf_layout_compiler_maps_special_sections() -> None:
    document = _compile_pdf_document(_sample_report_blocks())

    assert document.sections[0].display_title == "零、综述"
    assert document.sections[1].display_title == "一、核心亮点总结"

    positioning_section = next(section for section in document.sections if section.title == "推荐定位")
    assert isinstance(positioning_section.blocks[0], PdfMatrixTableBlock)
    assert positioning_section.blocks[0].headers[0] == "维度"

    plot_section = next(section for section in document.sections if section.title == "剧情大纲")
    assert isinstance(plot_section.blocks[0], PdfMatrixTableBlock)
    assert plot_section.blocks[0].headers == ["名称", "分类", "内容", "关键点"]
    phase_card = next(block for block in plot_section.blocks[1:] if isinstance(block, PdfCardBlock) and block.title == "【初期试探】（第1-10章）")
    assert phase_card.groups[0].title == "事件1：关系和主线同时起势（第1-4章）"
    assert phase_card.groups[0].items[0] == "商业联姻启动→项目提案抛出→朋友聚会旧情伏笔"

    relationship_section = next(section for section in document.sections if section.title == "情感线")
    assert isinstance(relationship_section.blocks[0], PdfMatrixTableBlock)
    assert relationship_section.blocks[0].headers == ["角色关系", "阶段", "章节", "推进说明"]

    unit_section = next(section for section in document.sections if section.title == "章节细纲")
    assert isinstance(unit_section.blocks[0], PdfUnitCardBlock)
    assert unit_section.blocks[0].title == "重逢试探（第1章）"


def test_export_pdf_smoke(tmp_path) -> None:
    output_path = tmp_path / "book_analysis.pdf"

    export_pdf(_sample_report_blocks(), output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0

    reader = PdfReader(str(output_path))
    extracted = "".join(page.extract_text() or "" for page in reader.pages)
    normalized = re.sub(r"\s+", "", extracted)

    assert "零、综述" in normalized
    assert "一、核心亮点总结" in normalized
    assert "【初期试探】（第1-10章）" in normalized
    assert "事件1：关系和主线同时起势（第1-4章）" in normalized
    assert "商业联姻启动→项目提案抛出→朋友聚会旧情伏笔" in normalized
    assert "推进：两人开始把旧伤和当前计划一起摊开" in normalized
    assert "节奏：紧凑" in normalized
    assert "情绪：戒备观望" in normalized
    assert "quick" not in normalized
    assert "guarded" not in normalized
    assert "情绪：情绪变化" not in normalized
    assert "情绪：+" not in normalized
    assert "节奏：推进" not in normalized


def test_pdf_story_line_matrix_skips_orphan_key_points_placeholder() -> None:
    blocks = [
        ReportBlock(kind="heading", level=1, text="测试书", style="book_title"),
        ReportBlock(kind="heading", level=2, text="剧情大纲", style="section_heading"),
        ReportBlock(kind="heading", level=3, text="核心故事线-主线/副线", style="group_heading"),
        ReportBlock(kind="bullet", level=1, text="关键点", style="group_label"),
        ReportBlock(kind="bullet", level=2, text="洗手间告白", style="group_detail"),
        ReportBlock(kind="bullet", level=1, text="情感主线｜核心线索:赵壹笙在KTV洗手间直球告白接吻，把关系直接推到名分确认。", style="section_item"),
        ReportBlock(kind="bullet", level=1, text="关键点", style="group_label"),
        ReportBlock(kind="bullet", level=2, text="留宿升温", style="group_detail"),
    ]

    document = _compile_pdf_document(blocks)
    plot_section = next(section for section in document.sections if section.title == "剧情大纲")
    matrix = next(block for block in plot_section.blocks if isinstance(block, PdfMatrixTableBlock))

    assert len(matrix.rows) == 1
    assert matrix.rows[0][0] == "情感主线"
    assert matrix.rows[0][2] != "内容待补充。"
    assert "名分确认" in matrix.rows[0][2]


def test_export_pdf_splits_long_relationship_matrix_across_chunks(tmp_path) -> None:
    output_path = tmp_path / "long_relationship.pdf"
    blocks = [
        ReportBlock(kind="heading", level=1, text="测试书", style="book_title"),
        ReportBlock(kind="heading", level=2, text="情感线", style="section_heading"),
    ]
    for index in range(1, 7):
        blocks.append(
            ReportBlock(
                kind="bullet",
                level=1,
                text=(
                    f"赵壹笙 & 卓舒清 / 阶段{index}（第{index}-{index + 1}章）："
                    f"推进：第{index}阶段里两人把旧伤、利益和站队放到同一张桌面上谈清楚，关系明显变厚；"
                    f"压力：外部局势和内部创伤同时抬升，逼得她们不能再回到试探姿态；"
                    f"回收：第{index}阶段最终都会落到共同承担和关系确认。"
                ),
                style="section_item",
            )
        )

    export_pdf(blocks, output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def _sample_report_blocks() -> list[ReportBlock]:
    return [
        ReportBlock(kind="heading", level=1, text="测试书", style="book_title"),
        ReportBlock(kind="heading", level=2, text="综述", style="section_heading"),
        ReportBlock(kind="paragraph", level=0, text="这是一个关于重逢、试探和关系升级的故事。", style="body"),
        ReportBlock(kind="paragraph", level=0, text="整体成品感来自情感线和主线推进同时抬升。", style="body"),
        ReportBlock(kind="heading", level=2, text="核心亮点总结", style="section_heading"),
        ReportBlock(kind="heading", level=3, text="双强关系", style="group_heading"),
        ReportBlock(kind="paragraph", level=0, text="双方一开始就把吸引、边界和危险感同时立住。", style="body"),
        ReportBlock(kind="heading", level=2, text="推荐定位", style="section_heading"),
        ReportBlock(kind="bullet", level=1, text="对标作品", style="group_label"),
        ReportBlock(kind="bullet", level=2, text="对标作品A", style="group_detail"),
        ReportBlock(kind="bullet", level=2, text="对标作品B", style="group_detail"),
        ReportBlock(kind="bullet", level=1, text="读者画像", style="group_label"),
        ReportBlock(kind="bullet", level=2, text="偏好高张力关系推进的读者", style="group_detail"),
        ReportBlock(kind="bullet", level=2, text="偏好双强拉扯的读者", style="group_detail"),
        ReportBlock(kind="heading", level=2, text="剧情大纲", style="section_heading"),
        ReportBlock(kind="heading", level=3, text="核心故事线-主线/副线", style="group_heading"),
        ReportBlock(kind="bullet", level=1, text="情感主线｜核心线索：两人从重逢试探走到关系绑定", style="section_item"),
        ReportBlock(kind="bullet", level=1, text="关键点", style="group_label"),
        ReportBlock(kind="bullet", level=2, text="重逢对峙", style="group_detail"),
        ReportBlock(kind="bullet", level=2, text="名分确认", style="group_detail"),
        ReportBlock(kind="heading", level=3, text="主线大纲", style="group_heading"),
        ReportBlock(kind="bullet", level=1, text="【初期试探】（第1-10章）", style="section_item"),
        ReportBlock(kind="bullet", level=2, text="事件1：关系和主线同时起势（第1-4章）", style="group_detail"),
        ReportBlock(kind="bullet", level=3, text="商业联姻启动→项目提案抛出→朋友聚会旧情伏笔", style="group_detail"),
        ReportBlock(kind="bullet", level=2, text="事件2：名分确认把试探推进到公开层面（第5-10章）", style="group_detail"),
        ReportBlock(kind="bullet", level=3, text="KTV告白接吻→同居试探→职场重逢压迫", style="group_detail"),
        ReportBlock(kind="bullet", level=1, text="【中段升级】（第11-30章）", style="section_item"),
        ReportBlock(kind="bullet", level=2, text="事件1：现实利益和亲密关系开始绑定（第11-20章）", style="group_detail"),
        ReportBlock(kind="bullet", level=3, text="健康崩坏→姐妹介入→家族博弈升压", style="group_detail"),
        ReportBlock(kind="bullet", level=2, text="事件2：旧账与新合作一起把关系推高（第21-30章）", style="group_detail"),
        ReportBlock(kind="bullet", level=3, text="信任危机→关系重估→共谋升级", style="group_detail"),
        ReportBlock(kind="heading", level=2, text="情感线", style="section_heading"),
        ReportBlock(
            kind="bullet",
            level=1,
            text="赵壹笙 & 卓舒清 / 创伤共担（第51-52章）：推进：两人开始把旧伤和当前计划一起摊开，还第一次在现实风险面前互相承认脆弱；压力：家族旧账和现实风险同时加码，逼得她们不能再靠暧昧回避；回收：信任从口头安慰转向共同承担。",
            style="section_item",
        ),
        ReportBlock(kind="heading", level=2, text="章节细纲", style="section_heading"),
        ReportBlock(kind="heading", level=3, text="重逢试探（第1章）", style="unit_heading"),
        ReportBlock(kind="bullet", level=1, text="剧情：两人在高压场合重逢并完成第一轮试探。", style="unit_label"),
        ReportBlock(kind="bullet", level=1, text="危机：双方都在隐藏真实目的。", style="unit_label"),
        ReportBlock(kind="bullet", level=1, text="伏笔：旧关系和后续合作都被提前埋下。", style="unit_label"),
        ReportBlock(kind="bullet", level=1, text="悬念：她到底是来赴约还是来设局。", style="unit_label"),
        ReportBlock(kind="bullet", level=1, text="高潮：洗手间里确认关系边界。", style="unit_label"),
        ReportBlock(kind="bullet", level=1, text="爽点：第一次名分确认让关系立住。", style="unit_label"),
        ReportBlock(kind="bullet", level=1, text="情节点与节奏", style="group_label"),
        ReportBlock(kind="bullet", level=2, text="情节点：重逢对峙｜节奏：紧凑｜情绪：戒备观望｜作用：开场即完成一轮高压交锋，并把旧账、吸引和现实风险同时推到台面上。", style="unit_detail"),
        ReportBlock(kind="bullet", level=1, text="名场面与金句", style="group_label"),
        ReportBlock(kind="bullet", level=2, text="洗手间近距离试探｜金句：我只和女朋友接吻。", style="unit_detail"),
        ReportBlock(kind="bullet", level=1, text="情感推进", style="group_label"),
        ReportBlock(kind="bullet", level=2, text="赵壹笙 / 初遇试探：关系从互相打量推进到名分确认，还把原本可撤回的暧昧逼成了必须回应的站位。", style="unit_detail"),
        ReportBlock(kind="bullet", level=1, text="文风信号", style="group_label"),
        ReportBlock(kind="bullet", level=2, text="对话节奏：短句快速来回，直接抬高拉扯感。", style="unit_detail"),
    ]
