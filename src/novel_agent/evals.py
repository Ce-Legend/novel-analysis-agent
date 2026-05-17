from __future__ import annotations

import re

from .exporters.report import DELIVERY_SECTION_ORDER
from .schemas import (
    BookAnalysis,
    ChapterAnalysis,
    ChapterFailureRecord,
    DeliveryIntegrityReview,
    EvalReport,
    QualityReview,
    ReferenceAlignmentDimensionReview,
    ReferenceAlignmentReview,
)


REQUIRED_BOOK_FIELDS = [
    "overview",
    "highlights_summary",
    "selling_points_detail",
    "selling_points",
    "audience_positioning",
    "story_hook_layers",
    "title_intro_analysis",
    "character_profiles",
    "cp_analysis",
    "plot_outline",
    "opening_craft",
    "main_outline",
    "delivery_units",
    "relationship_timeline",
    "writing_breakdown",
    "style_summary",
]


def _is_content_filter_failure(failure: ChapterFailureRecord) -> bool:
    error_type = (failure.error_type or "").lower()
    error_message = (failure.error_message or "").lower()
    if "data_inspection_failed" in error_message:
        return True
    if "inappropriate content" in error_message:
        return True
    return error_type == "badrequesterror" and "content" in error_message


def evaluate_run(
    book: BookAnalysis,
    chapters: list[ChapterAnalysis],
    exported_formats: list[str],
    *,
    expected_chapters: int | None = None,
    failures: list[ChapterFailureRecord] | None = None,
) -> EvalReport:
    total_chapters = len(chapters)
    analyzed_chapters = len([chapter for chapter in chapters if chapter.summary.strip()])
    with_evidence = len([chapter for chapter in chapters if chapter.evidence])
    failure_rows = failures or []
    content_filter_failures = [failure for failure in failure_rows if _is_content_filter_failure(failure)]
    other_failures = [failure for failure in failure_rows if not _is_content_filter_failure(failure)]
    warnings: list[str] = []
    if total_chapters == 0:
        warnings.append("No chapters were analyzed")
    if expected_chapters is not None and total_chapters < expected_chapters:
        warnings.append(f"Only {total_chapters}/{expected_chapters} chapters were analyzed successfully")
    if failure_rows:
        warnings.append(f"{len(failure_rows)} chapters failed during analysis")
    if not {"docx", "pdf"}.issubset(set(exported_formats)):
        warnings.append("Final delivery is missing docx or pdf export")
    if not book.relationship_timeline:
        warnings.append("Relationship timeline is empty")
    if not book.style_summary.evidence_chapters and not book.writing_breakdown.evidence_chapters:
        warnings.append("Writing summary has no evidence chapters")
    if not book.delivery_units:
        warnings.append("Delivery units are empty")

    present = [field for field in REQUIRED_BOOK_FIELDS if _field_present(book, field)]
    return EvalReport(
        expected_chapters=expected_chapters or total_chapters,
        total_chapters=total_chapters,
        analyzed_chapters=analyzed_chapters,
        failed_chapters=len(failure_rows),
        content_filter_failed_chapters=len(content_filter_failures),
        other_failed_chapters=len(other_failures),
        schema_valid=True,
        evidence_coverage_ratio=(with_evidence / total_chapters) if total_chapters else 0.0,
        required_sections_present=present,
        warnings=warnings,
    )


def review_delivery_quality(
    book: BookAnalysis,
    chapters: list[ChapterAnalysis],
    eval_report: EvalReport,
    *,
    exported_formats: list[str],
    rendered_report: str,
    degraded_split_chapters: int = 0,
    split_group_count: int | None = None,
    delivery_integrity_review: DeliveryIntegrityReview | None = None,
) -> QualityReview:
    covered_items: list[str] = []
    quality_gaps: list[str] = []
    high_risks: list[str] = []
    weak_placeholder_lines = _collect_weak_placeholder_lines(rendered_report)
    weak_character_lines = _find_matching_lines(
        _extract_section_text(rendered_report, "人物小传"),
        [r"外貌特点：(?:信息仍需进一步提炼。?|未详述|暂无明确描写|未明确描写|描写较少)"],
    )
    weak_cp_lines = _find_matching_lines(
        _extract_section_text(rendered_report, "CP感分析"),
        [r"信息仍需进一步提炼"],
    )
    weak_unnamed_count = _count_matches(rendered_report, r"未命名条目")

    generic_scene_fallback_count = _count_matches(
        rendered_report,
        r"(关键场面｜(?:作用：(?:提炼本章最强记忆点|强化本段记忆点)|金句：)|提炼本章最强记忆点)",
    )
    weak_character_copy_count = len(weak_character_lines)
    truncated_tail_count = _count_matches(
        rendered_report,
        r"( / 关系变化：;|实为测试亲(?:密层级)?$|[；：]\s*$|[‘“][^’”\n]{0,16}$|[A-Za-z]{3,}”$)",
    )

    export_set = set(exported_formats)
    has_final_exports = {"docx", "pdf"}.issubset(export_set)
    if has_final_exports:
        covered_items.append("已生成最终 Docx/PDF 成品")
    else:
        quality_gaps.append("缺少最终 Docx/PDF 成品")

    section_order_ok = _section_order_matches_template(rendered_report)
    if section_order_ok:
        covered_items.append("顶层模块顺序已对齐样稿模板")
    else:
        quality_gaps.append("顶层模块顺序仍未对齐样稿模板")

    report_has_internal_markers = bool(
        re.search(
            r"(chapter_id\s*[:：]|未识别章节|分块\s*\d+/\d+|ch-\d{4}|"
            r"待补充|关系进入新的推进节点|本单元完成一次清晰推进|细节、动作和对话共同服务张力|"
            r"为引子分块|\d+/\d+分块|"
            r"narrative voice|narrative perspective|metaphor usage|dialogue rhythm|"
            r"lexical register shift|sensory layering|strategic entanglement|shadow antagonist|"
            r"controlled detachment|residual leverage|external validation|identity-based recalibration|"
            r"\b(?:details|detail|list|stage|physical|identity|trust)\b|(?:→|->|➡)|[（(][^）)\n]{0,40}(?:\n|$))",
            rendered_report,
            flags=re.IGNORECASE,
        )
    )
    if report_has_internal_markers:
        quality_gaps.append("最终报告仍暴露技术切块或内部字段")
    else:
        covered_items.append("最终报告未暴露技术字段")

    sample_sections_ok = all(
        section in _extract_top_level_sections(rendered_report)
        for section in ["剧情看点分层", "核心梗", "开篇文法分析"]
    )
    if sample_sections_ok:
        covered_items.append("样稿关键独立章节已存在")
    else:
        quality_gaps.append("剧情看点分层/核心梗/开篇文法分析仍未全部独立成章")

    if book.main_outline and all(item.description.strip() for item in book.main_outline):
        covered_items.append("主线大纲可读")
    else:
        quality_gaps.append("主线大纲不足或可读性弱")

    plot_outline_ok = bool(book.plot_outline.story_lines) and bool(book.plot_outline.phase_outline)
    if plot_outline_ok:
        covered_items.append("剧情大纲已具备故事线层和阶段层")
    else:
        quality_gaps.append("剧情大纲仍缺故事线层或阶段层")

    delivery_units_ok = bool(book.delivery_units) and all(
        unit.title.strip()
        and unit.summary.strip()
        and "分块" not in unit.title
        and len(unit.title.strip()) <= 24
        and not re.search(r"(本章|本单元|章节)", unit.title)
        for unit in book.delivery_units
    )
    if delivery_units_ok:
        covered_items.append("章节细纲已切换为交付单元")
    else:
        quality_gaps.append("章节细纲仍未完成交付单元重组")

    relationship_has_stages = 4 <= len(book.relationship_timeline) <= 8
    relationship_has_ranges = all(stage.chapter_range for stage in book.relationship_timeline)
    relationship_has_descriptions = all(stage.description.strip() for stage in book.relationship_timeline)
    if relationship_has_stages and relationship_has_ranges and relationship_has_descriptions:
        covered_items.append("情感线阶段表达基本满足")
    else:
        quality_gaps.append("情感线阶段不足或缺少章节锚点")

    cp_analysis_ok = (
        book.cp_analysis.summary.strip()
        and bool(book.cp_analysis.topics)
        and len(book.cp_analysis.topics) >= 6
    )
    if cp_analysis_ok:
        covered_items.append("CP感分析已独立成章")
    else:
        quality_gaps.append("CP感分析缺失或内容过空")

    writing_breakdown_ok = all(
        [
            book.writing_breakdown.writing_analysis.strip(),
            book.writing_breakdown.opening_method.strip(),
            book.writing_breakdown.dialogue_design.strip(),
            book.writing_breakdown.action_detail.strip(),
            (book.writing_breakdown.language_style or book.style_summary.language_style).strip(),
        ]
    )
    style_summary_ok = all(
        [
            book.style_summary.narrative_pacing.strip(),
            book.style_summary.information_release.strip(),
            book.style_summary.conflict_design.strip(),
            book.style_summary.emotional_leverage.strip(),
            book.style_summary.characterization.strip(),
            (book.style_summary.language_style or book.writing_breakdown.language_style).strip(),
            book.style_summary.hook_and_payoff.strip(),
        ]
    )
    if writing_breakdown_ok and style_summary_ok:
        covered_items.append("文笔内容总结具备拆解维度")
    else:
        quality_gaps.append("文笔内容总结偏空或缺少拆解维度")

    audience_positioning_ok = any(
        [
            bool(book.audience_positioning.comps),
            bool(book.audience_positioning.reader_profile),
            bool(book.audience_positioning.marketing_keywords),
            bool(book.audience_positioning.short_term_hooks),
            bool(book.audience_positioning.mid_term_hooks),
            bool(book.audience_positioning.long_term_hooks),
        ]
    )
    story_hook_layers_ok = any(
        [
            bool(book.story_hook_layers.short_term),
            bool(book.story_hook_layers.mid_term),
            bool(book.story_hook_layers.long_term),
        ]
    )
    title_intro_ok = all(
        [
            book.title_intro_analysis.title_analysis.strip(),
            book.title_intro_analysis.core_hook.strip(),
            book.title_intro_analysis.genre.strip(),
            book.title_intro_analysis.intro_analysis.strip(),
        ]
    )
    if audience_positioning_ok and title_intro_ok and story_hook_layers_ok:
        covered_items.append("推荐定位、剧情看点分层与作品名/简介分析已覆盖")
    else:
        quality_gaps.append("推荐定位、剧情看点分层或作品名/简介分析覆盖不足")

    highlights_ok = bool(book.highlights_summary)
    selling_detail_ok = bool(book.selling_points_detail)
    if highlights_ok and selling_detail_ok:
        covered_items.append("核心亮点总结与核心卖点已拆分")
    else:
        quality_gaps.append("核心亮点总结与核心卖点仍未完全拆分")

    required_character_count = 4 if len(chapters) >= 12 else 2
    character_card_ok = len(book.character_profiles) >= required_character_count and all(
        profile.basic_info.strip()
        and bool(profile.personality_traits or profile.traits)
        and bool(profile.major_experiences or ([profile.arc] if profile.arc.strip() else []))
        and bool(profile.relationships)
        for profile in book.character_profiles[:required_character_count]
    )
    if character_card_ok and weak_character_copy_count == 0:
        covered_items.append("人物小传已达到人物卡结构")
    else:
        quality_gaps.append("人物小传仍未达到人物卡结构")

    chapter_outline_card_ok = bool(book.delivery_units) and not re.search(
        r"(from\s+.+?\bto\b|关系从试探靠近推进到新的阶段|这一单元以细节和对话共同推动情绪与冲突|"
        r"关系在这一单元完成一次清晰升级|本单元围绕关键剧情点完成一次节奏推进|细节与对话共同抬升情绪张力|"
        r"待补充|关系进入新的推进节点|本单元完成一次清晰推进|细节、动作和对话共同服务张力|"
        r"为引子分块|\d+/\d+分块|…|"
        r"\b(?:details|detail|list|stage|physical|identity|trust)\b|(?:→|->|➡)|[（(][^）)\n]{0,40}(?:\n|$)|"
        r"关键场面｜(?:作用：(?:提炼本章最强记忆点|强化本段记忆点)|金句：)|"
        r" / 关系变化：;|外貌特点：未详述|实为测试亲(?:密层级)?)",
        rendered_report,
        flags=re.IGNORECASE,
    )
    if chapter_outline_card_ok:
        covered_items.append("章节细纲已基本卡片化")
    else:
        quality_gaps.append("章节细纲仍残留摘要腔或分析腔")

    if generic_scene_fallback_count > 0:
        quality_gaps.append("名场面与金句仍残留泛化占位条目")
    if weak_character_copy_count > 0:
        quality_gaps.append("人物卡仍残留弱字段占位")
    if truncated_tail_count > 0:
        quality_gaps.append("最终章纲仍残留截断摘要句")
    if weak_placeholder_lines:
        quality_gaps.append("最终成品仍残留弱占位文案")

    integrity_total = 0
    integrity_blocking = 0
    if delivery_integrity_review is not None:
        integrity_total = delivery_integrity_review.total_issue_count
        integrity_blocking = delivery_integrity_review.blocking_issue_count
        if integrity_total == 0:
            covered_items.append("成品完整性巡检已通过")
        else:
            quality_gaps.append("成品完整性巡检仍发现残句/脏字段/版式风险")
        if integrity_blocking > 0:
            high_risks.append(f"成品完整性巡检仍有 {integrity_blocking} 个阻断项")

    chapter_outline_ratio = (len(book.chapter_outlines) / len(chapters)) if chapters else 0.0
    delivery_unit_count = len(book.delivery_units)

    if eval_report.other_failed_chapters > 0:
        high_risks.append(f"存在 {eval_report.other_failed_chapters} 个非内容审核失败章节，交付链路非全成功")
    elif eval_report.content_filter_failed_chapters > 0:
        quality_gaps.append(f"存在 {eval_report.content_filter_failed_chapters} 个内容审核失败章节，成品为部分交付")
    if eval_report.evidence_coverage_ratio < 0.8:
        high_risks.append("章节证据覆盖率偏低，整书汇总结论的可追溯性不足")
    if degraded_split_chapters > 0 and delivery_unit_count == len(chapters):
        quality_gaps.append("切章仍高度依赖原始分析单元，交付重组收益有限")
    elif degraded_split_chapters > 0 and delivery_unit_count < len(chapters):
        covered_items.append("技术分块已被交付单元重组部分吸收")

    module_coverage_ok = all(
        [
            book.overview.strip(),
            bool(book.selling_points),
            audience_positioning_ok,
            title_intro_ok,
            story_hook_layers_ok,
            bool(book.character_profiles),
            cp_analysis_ok,
            plot_outline_ok,
            bool(book.opening_craft.core_payoffs),
            bool(book.main_outline),
            bool(book.delivery_units),
            bool(book.relationship_timeline),
            writing_breakdown_ok,
        ]
    )
    if module_coverage_ok:
        covered_items.append("最终交付模块矩阵基础齐全")
    else:
        quality_gaps.append("最终交付模块矩阵仍有缺口")

    status = "deliverable"
    if high_risks:
        status = "high_risk"
    elif quality_gaps:
        status = "needs_optimization"

    return QualityReview(
        status=status,
        covered_items=covered_items,
        quality_gaps=quality_gaps,
        high_risks=high_risks,
        metrics={
            "chapter_count": len(chapters),
            "chapter_outline_count": len(book.chapter_outlines),
            "chapter_outline_ratio": round(chapter_outline_ratio, 4) if chapters else 0.0,
            "delivery_unit_count": delivery_unit_count,
            "relationship_stage_count": len(book.relationship_timeline),
            "cp_topic_count": len(book.cp_analysis.topics),
            "style_evidence_count": len(book.style_summary.evidence_chapters),
            "writing_evidence_count": len(book.writing_breakdown.evidence_chapters),
            "degraded_split_chapters": degraded_split_chapters,
            "split_group_count": split_group_count or 0,
            "failed_chapters": eval_report.failed_chapters,
            "content_filter_failed_chapters": eval_report.content_filter_failed_chapters,
            "other_failed_chapters": eval_report.other_failed_chapters,
            "evidence_coverage_ratio": round(eval_report.evidence_coverage_ratio, 4),
            "has_docx": "docx" in export_set,
            "has_pdf": "pdf" in export_set,
            "report_has_internal_markers": report_has_internal_markers,
            "section_order_ok": section_order_ok,
            "sample_sections_ok": sample_sections_ok,
            "character_card_ok": character_card_ok,
            "plot_outline_ok": plot_outline_ok,
            "chapter_outline_card_ok": chapter_outline_card_ok,
            "generic_scene_fallback_count": generic_scene_fallback_count,
            "weak_character_copy_count": weak_character_copy_count,
            "truncated_tail_count": truncated_tail_count,
            "weak_placeholder_count": len(weak_placeholder_lines),
            "weak_character_line_count": len(weak_character_lines),
            "weak_cp_line_count": len(weak_cp_lines),
            "weak_unnamed_count": weak_unnamed_count,
            "integrity_issue_count": integrity_total,
            "integrity_blocking_issue_count": integrity_blocking,
        },
    )


def build_reference_alignment_review(
    book: BookAnalysis,
    chapters: list[ChapterAnalysis],
    *,
    rendered_report: str,
) -> ReferenceAlignmentReview:
    sections = _extract_top_level_sections(rendered_report)
    dims: list[ReferenceAlignmentDimensionReview] = []
    character_section = _extract_section_text(rendered_report, "人物小传")
    cp_section = _extract_section_text(rendered_report, "CP感分析")
    weak_placeholder_lines = _collect_weak_placeholder_lines(rendered_report)
    weak_character_lines = _find_matching_lines(
        character_section,
        [r"外貌特点：(?:信息仍需进一步提炼。?|未详述|暂无明确描写|未明确描写|描写较少)"],
    )
    weak_cp_lines = _find_matching_lines(cp_section, [r"信息仍需进一步提炼"])

    structure_ok = sections[: len(DELIVERY_SECTION_ORDER)] == DELIVERY_SECTION_ORDER
    dims.append(
        _dimension_review(
            "结构顺序",
            "达标" if structure_ok else "不达标",
            evidence_lines=_find_lines(rendered_report, ["## 综述", "## 章节细纲", "## 文笔内容总结"]),
            top_examples=[] if structure_ok else ["顶层顺序未完全命中目标模板"],
            recommendation="保持 14 个顶层模块顺序不变。",
        )
    )

    section_independent_ok = (
        "剧情看点分层" in sections
        and "核心梗" in sections
        and "开篇文法分析" in sections
        and len(book.cp_analysis.topics) >= 6
        and bool(book.plot_outline.story_lines)
        and bool(book.plot_outline.phase_outline)
    )
    dims.append(
        _dimension_review(
            "栏目独立性",
            "达标" if section_independent_ok else "接近",
            evidence_lines=_find_lines(rendered_report, ["## 剧情看点分层", "## 核心梗", "## 开篇文法分析", "## CP感分析"]),
            top_examples=[] if section_independent_ok else ["关键专题已存在，但部分栏目内容仍偏弱。"],
            recommendation="继续保持专题独立成章，不再混写。",
        )
    )

    weak_character_copy_count = len(weak_character_lines)
    character_core_ok = len(book.character_profiles) >= (4 if len(chapters) >= 12 else 2) and all(
        profile.basic_info.strip()
        and bool(profile.personality_traits or profile.traits)
        and bool(profile.major_experiences or ([profile.arc] if profile.arc.strip() else []))
        and bool(profile.relationships)
        for profile in book.character_profiles[: (4 if len(chapters) >= 12 else 2)]
    )
    character_status = "达标" if character_core_ok and weak_character_copy_count == 0 else "接近"
    dims.append(
        _dimension_review(
            "人物卡厚度",
            character_status,
            evidence_lines=_find_lines(rendered_report, ["## 人物小传", "基本信息：", "人物关系"]),
            top_examples=weak_character_lines[:3],
            recommendation="缺失外貌信息时直接省略，不要输出弱占位。",
            remaining_issue_count=weak_character_copy_count,
        )
    )

    cp_topic_count = len(book.cp_analysis.topics)
    weak_cp_topics = len(weak_cp_lines)
    cp_status = "达标" if cp_topic_count >= 6 and weak_cp_topics == 0 else "接近"
    dims.append(
        _dimension_review(
            "CP专题深度",
            cp_status,
            evidence_lines=_find_lines(rendered_report, ["## CP感分析", "### 初期建设", "### 终局确认"]),
            top_examples=weak_cp_lines[:3],
            recommendation="每节保持‘一句判断 + 为什么成立 + 2-4 个桥段’。",
            remaining_issue_count=weak_cp_topics,
        )
    )

    plot_status = "达标" if bool(book.plot_outline.story_lines) and bool(book.plot_outline.phase_outline) else "接近"
    dims.append(
        _dimension_review(
            "剧情大纲两层结构",
            plot_status,
            evidence_lines=_find_lines(rendered_report, ["### 核心故事线-主线/副线", "### 主线大纲"]),
            top_examples=[],
            recommendation="继续维持故事线层和阶段层双层结构。",
        )
    )

    chapter_card_issue_lines = _find_matching_lines(
        rendered_report,
        [
            r"关键场面｜(?:作用：(?:提炼本章最强记忆点|强化本段记忆点)|金句：)",
            r" / 关系变化：;",
            r"实为测试亲(?:密层级)?",
            r"### 未命名条目",
        ],
    )
    chapter_card_status = "达标" if not chapter_card_issue_lines else "不达标"
    dims.append(
        _dimension_review(
            "章节细纲卡片化",
            chapter_card_status,
            evidence_lines=_find_lines(rendered_report, ["## 章节细纲"]),
            top_examples=chapter_card_issue_lines[:5],
            recommendation="继续清掉半截句、泛化场面和弱标签。",
            remaining_issue_count=len(chapter_card_issue_lines),
        )
    )

    title_issues = [
        unit.title
        for unit in book.delivery_units
        if "分块" in unit.title or re.search(r"(本章|本单元|章节)", unit.title) or len(unit.title.strip()) > 24
    ]
    title_status = "达标" if not title_issues else "接近"
    dims.append(
        _dimension_review(
            "标题命名",
            title_status,
            evidence_lines=_find_lines(rendered_report, [r"^### .+（第"], regex=True),
            top_examples=title_issues[:5],
            recommendation="标题继续保持‘事件 + 关系/冲突’式短标题。",
            remaining_issue_count=len(title_issues),
        )
    )

    product_gap_count = len(weak_placeholder_lines)
    product_status = "达标" if product_gap_count == 0 else ("接近" if product_gap_count <= 3 else "不达标")
    dims.append(
        _dimension_review(
            "整体产品感",
            product_status,
            evidence_lines=_find_lines(rendered_report, ["## 章节细纲", "## CP感分析", "## 人物小传"]),
            top_examples=weak_placeholder_lines[:5],
            recommendation="正式成品里不要落任何弱占位文案，宁可省略也不要保留 placeholder。",
            remaining_issue_count=product_gap_count,
        )
    )

    status_counts = {
        "达标": sum(1 for item in dims if item.status == "达标"),
        "接近": sum(1 for item in dims if item.status == "接近"),
        "不达标": sum(1 for item in dims if item.status == "不达标"),
    }
    overall_status = "已基本对齐" if status_counts["达标"] >= 6 and status_counts["不达标"] == 0 else "仍需优化"
    return ReferenceAlignmentReview(
        overall_status=overall_status,
        summary=f"人工对表结果：{status_counts['达标']} 项达标，{status_counts['接近']} 项接近，{status_counts['不达标']} 项不达标。",
        dimensions=dims,
        metrics=status_counts,
    )


def _field_present(book: BookAnalysis, field_name: str) -> bool:
    value = getattr(book, field_name)
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    if field_name == "audience_positioning":
        return any(
            [
                bool(book.audience_positioning.comps),
                bool(book.audience_positioning.reader_profile),
                bool(book.audience_positioning.marketing_keywords),
                bool(book.audience_positioning.short_term_hooks),
                bool(book.audience_positioning.mid_term_hooks),
                bool(book.audience_positioning.long_term_hooks),
            ]
        )
    if field_name == "story_hook_layers":
        return any(
            [
                bool(book.story_hook_layers.short_term),
                bool(book.story_hook_layers.mid_term),
                bool(book.story_hook_layers.long_term),
            ]
        )
    if field_name == "title_intro_analysis":
        return all(
            [
                bool(book.title_intro_analysis.title_analysis.strip()),
                bool(book.title_intro_analysis.core_hook.strip()),
                bool(book.title_intro_analysis.genre.strip()),
                bool(book.title_intro_analysis.intro_analysis.strip()),
            ]
        )
    if field_name == "cp_analysis":
        return bool(book.cp_analysis.summary.strip()) and len(book.cp_analysis.topics) >= 3
    if field_name == "plot_outline":
        return bool(book.plot_outline.story_lines) and bool(book.plot_outline.phase_outline)
    if field_name == "opening_craft":
        return any(
            [
                bool(book.opening_craft.core_payoffs),
                bool(book.opening_craft.core_pain_points),
                bool(book.opening_craft.flirty_moments),
            ]
        )
    if field_name == "writing_breakdown":
        return any(
            [
                bool(book.writing_breakdown.writing_analysis.strip()),
                bool(book.writing_breakdown.opening_method.strip()),
                bool(book.writing_breakdown.dialogue_design.strip()),
                bool(book.writing_breakdown.action_detail.strip()),
            ]
        )
    if field_name == "style_summary":
        return bool(book.style_summary.narrative_pacing.strip())
    return bool(value)


def _extract_top_level_sections(rendered_report: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"^##\s+(.+)$", rendered_report, flags=re.MULTILINE)]


def _extract_section_text(rendered_report: str, section_name: str) -> str:
    pattern = rf"^##\s+{re.escape(section_name)}\s*$"
    match = re.search(pattern, rendered_report, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+.+$", rendered_report[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(rendered_report)
    return rendered_report[start:end]


def _section_order_matches_template(rendered_report: str) -> bool:
    sections = _extract_top_level_sections(rendered_report)
    return sections[: len(DELIVERY_SECTION_ORDER)] == DELIVERY_SECTION_ORDER


def _count_matches(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, flags=re.IGNORECASE | re.MULTILINE))


def _collect_weak_placeholder_lines(rendered_report: str) -> list[str]:
    return _find_matching_lines(
        rendered_report,
        [
            r"信息仍需进一步提炼",
            r"未命名条目",
            r"外貌特点：(?:未详述|暂无明确描写|未明确描写|描写较少)",
        ],
    )


def _find_matching_lines(text: str, patterns: list[str]) -> list[str]:
    lines = text.splitlines()
    results: list[str] = []
    for line in lines:
        for pattern in patterns:
            if re.search(pattern, line, flags=re.IGNORECASE):
                results.append(line.strip())
                break
    return results


def _find_lines(text: str, patterns: list[str], *, regex: bool = False) -> list[int]:
    line_numbers: list[int] = []
    for index, line in enumerate(text.splitlines(), start=1):
        for pattern in patterns:
            matched = re.search(pattern, line) if regex else pattern in line
            if matched:
                line_numbers.append(index)
                break
    return line_numbers[:8]


def _dimension_review(
    name: str,
    status: str,
    *,
    evidence_lines: list[int],
    top_examples: list[str],
    recommendation: str,
    remaining_issue_count: int = 0,
) -> ReferenceAlignmentDimensionReview:
    return ReferenceAlignmentDimensionReview(
        name=name,
        status=status,
        evidence_lines=evidence_lines,
        remaining_issue_count=remaining_issue_count,
        top_examples=top_examples[:5],
        recommendation=recommendation,
    )


def _has_editorial_cp_judgment(text: str) -> bool:
    return any(keyword in text for keyword in ["为什么", "成立", "好嗑", "抓人", "真正", "张力"])
