import json
import os
from pathlib import Path

import pytest

from novel_agent.analysis.book import postprocess_book_analysis, repair_delivery_weak_slots
from novel_agent.analysis.chapter import analyze_chapter
from novel_agent.config import AppSettings, ExportFormat, Profile, ProviderName
from novel_agent.evals import build_reference_alignment_review, review_delivery_quality
from novel_agent.ingest import ingest_book
from novel_agent.pipeline import finalize_delivery, run_pipeline
from novel_agent.providers import resolve_provider
from novel_agent.runtime import build_run_context
from novel_agent.schemas import BeatRhythmItem, BookAnalysis, ChapterAnalysis, ChapterChunkExtraction, CPAnalysis, CPTopic, CharacterProfile, DeliveryUnit, EmotionState, EvalReport, InputType, OpeningCraft, PhaseOutlineItem, PlotEvent, PlotOutline, RelationshipProgression, RelationshipStage, RunManifest, RunStatsSummary, RunSummary, SceneQuoteItem, StoryHookLayers, StoryLineItem
from novel_agent.splitter import split_into_chapters
from novel_agent.utils import jsonl_dump


class _SpyBookProvider:
    name = "bailian-long"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate_structured(self, *, response_model, model, system_prompt, user_prompt, metadata=None):  # noqa: ANN001, ANN003
        from novel_agent.providers.mock import MockProvider

        self.calls.append(response_model.__name__)
        result, stats = MockProvider().generate_structured(
            response_model=response_model,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            metadata=metadata,
        )
        if response_model.__name__ == "BookAnalysis":
            stats.warnings.append("structured_provider_mode:bailian_long_fileid")
        return result, stats


class _FailingChapterProvider:
    name = "mock"

    def generate_structured(self, *, response_model, model, system_prompt, user_prompt, metadata=None):  # noqa: ANN001, ANN003
        from novel_agent.providers.mock import MockProvider

        metadata = metadata or {}
        chapter_id = metadata.get("chapter_id")
        if chapter_id is None and "chapter" in metadata:
            chapter_id = metadata["chapter"].chapter_id
        if chapter_id == "ch-0002":
            raise RuntimeError("synthetic chapter failure")
        return MockProvider().generate_structured(
            response_model=response_model,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            metadata=metadata,
        )


class _BadRequestError(RuntimeError):
    pass


class _ContentFilterFailingChapterProvider:
    name = "mock"

    def generate_structured(self, *, response_model, model, system_prompt, user_prompt, metadata=None):  # noqa: ANN001, ANN003
        from novel_agent.providers.mock import MockProvider

        metadata = metadata or {}
        chapter_id = metadata.get("chapter_id")
        if chapter_id is None and "chapter" in metadata:
            chapter_id = metadata["chapter"].chapter_id
        if chapter_id == "ch-0002":
            raise _BadRequestError("data_inspection_failed: content review blocked this chapter")
        return MockProvider().generate_structured(
            response_model=response_model,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            metadata=metadata,
        )


class _FlakyChapterProvider:
    name = "mock"

    def __init__(self) -> None:
        self.attempts: dict[str, int] = {}

    def generate_structured(self, *, response_model, model, system_prompt, user_prompt, metadata=None):  # noqa: ANN001, ANN003
        from novel_agent.providers.mock import MockProvider

        metadata = metadata or {}
        chapter_id = metadata.get("chapter_id")
        if chapter_id is None and "chapter" in metadata:
            chapter_id = metadata["chapter"].chapter_id
        if chapter_id == "ch-0002" and response_model.__name__ == "ChapterChunkExtraction":
            attempt = self.attempts.get(chapter_id, 0) + 1
            self.attempts[chapter_id] = attempt
            if attempt == 1:
                raise RuntimeError("synthetic transient chapter failure")
        return MockProvider().generate_structured(
            response_model=response_model,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            metadata=metadata,
        )


def test_pipeline_runs_with_mock_provider(tmp_path: Path) -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    settings.runs_dir = tmp_path / "runs"
    input_path = Path("tests/fixtures/sample_novel.txt")
    ctx = build_run_context(settings, str(input_path), "testrun")
    provider = resolve_provider(ProviderName.MOCK)

    outputs = run_pipeline(
        ctx=ctx,
        settings=settings,
        input_path=input_path,
        input_type=InputType.TXT,
        provider=provider,
        export_formats=[ExportFormat.MARKDOWN, ExportFormat.DOCX, ExportFormat.PDF],
        profile=Profile.MVP.value,
        force=True,
    )

    assert outputs["markdown"].exists()
    assert outputs["docx"].exists()
    assert outputs["pdf"].exists()
    assert outputs["book_analysis"].exists()
    assert outputs["eval"].exists()
    assert outputs["stage_stats"].exists()
    assert outputs["run_summary"].exists()
    assert outputs["quality_review"].exists()
    assert outputs["reference_alignment_review"].exists()
    assert outputs["delivery_integrity_review"].exists()
    assert outputs["split_diagnostics"].exists()
    book_analysis = json.loads(outputs["book_analysis"].read_text(encoding="utf-8"))
    assert len(book_analysis["chapter_outlines"]) == 5
    assert len(book_analysis["delivery_units"]) == 5
    assert all(item["key_conflict"] for item in book_analysis["chapter_outlines"])
    assert all(item["emotional_progression"] for item in book_analysis["chapter_outlines"])
    assert all(stage["chapter_range"] for stage in book_analysis["relationship_timeline"])
    markdown_text = outputs["markdown"].read_text(encoding="utf-8")
    assert "chapter_id" not in markdown_text
    assert "分块" not in markdown_text
    assert "…" not in markdown_text
    assert "待补充" not in markdown_text
    assert "## 核心亮点总结" in markdown_text
    assert "## 核心卖点" in markdown_text
    assert "## 剧情看点分层" in markdown_text
    assert "## 核心梗" in markdown_text
    assert "## 开篇文法分析" in markdown_text
    quality_review = json.loads(outputs["quality_review"].read_text(encoding="utf-8"))
    assert quality_review["status"] == "needs_optimization"
    assert quality_review["metrics"]["has_docx"] is True
    assert quality_review["metrics"]["has_pdf"] is True
    assert quality_review["metrics"]["section_order_ok"] is True
    assert quality_review["metrics"]["character_card_ok"] is True
    assert quality_review["metrics"]["relationship_stage_count"] >= 4
    assert quality_review["metrics"]["cp_topic_count"] >= 6
    assert quality_review["metrics"]["weak_placeholder_count"] == 0
    assert quality_review["metrics"]["integrity_issue_count"] >= quality_review["metrics"]["integrity_blocking_issue_count"]
    split_diagnostics = json.loads(outputs["split_diagnostics"].read_text(encoding="utf-8"))
    assert split_diagnostics["group_count"] >= 2
    delivery_integrity_review = json.loads(outputs["delivery_integrity_review"].read_text(encoding="utf-8"))
    assert delivery_integrity_review["overall_status"] in {"passed", "needs_repair", "blocked"}
    assert delivery_integrity_review["round_issue_counts"][0] >= delivery_integrity_review["round_issue_counts"][-1]
    reference_alignment_review = json.loads(outputs["reference_alignment_review"].read_text(encoding="utf-8"))
    assert reference_alignment_review["overall_status"] in {"已基本对齐", "仍需优化"}
    assert len(reference_alignment_review["dimensions"]) == 8
    assert {item["name"] for item in reference_alignment_review["dimensions"]} == {
        "结构顺序",
        "栏目独立性",
        "人物卡厚度",
        "CP专题深度",
        "剧情大纲两层结构",
        "章节细纲卡片化",
        "标题命名",
        "整体产品感",
    }
    assert not ctx.lock_path.exists()


def test_finalize_delivery_rebuilds_existing_run_outputs_idempotently(tmp_path: Path) -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    settings.runs_dir = tmp_path / "runs"
    input_path = Path("tests/fixtures/sample_novel.txt")
    ctx = build_run_context(settings, str(input_path), "finalize-run")
    provider = resolve_provider(ProviderName.MOCK)

    outputs = run_pipeline(
        ctx=ctx,
        settings=settings,
        input_path=input_path,
        input_type=InputType.TXT,
        provider=provider,
        export_formats=[ExportFormat.MARKDOWN, ExportFormat.DOCX, ExportFormat.PDF],
        profile=Profile.MVP.value,
        force=True,
    )

    original_markdown = outputs["markdown"].read_text(encoding="utf-8")
    original_review = json.loads(outputs["delivery_integrity_review"].read_text(encoding="utf-8"))
    outputs["markdown"].write_text("stale", encoding="utf-8")
    (ctx.eval_dir / "delivery_integrity_review.json").unlink(missing_ok=True)
    (ctx.eval_dir / "quality_review.json").unlink(missing_ok=True)
    (ctx.eval_dir / "reference_alignment_review.json").unlink(missing_ok=True)

    finalized_outputs = finalize_delivery(
        ctx=ctx,
        export_formats=[ExportFormat.MARKDOWN, ExportFormat.DOCX, ExportFormat.PDF],
    )

    rebuilt_markdown = finalized_outputs["markdown"].read_text(encoding="utf-8")
    assert rebuilt_markdown != "stale"
    assert "待补充" not in rebuilt_markdown
    assert finalized_outputs["docx"].exists()
    assert finalized_outputs["pdf"].exists()
    assert finalized_outputs["delivery_integrity_review"].exists()
    assert finalized_outputs["quality_review"].exists()
    assert finalized_outputs["reference_alignment_review"].exists()

    second_outputs = finalize_delivery(
        ctx=ctx,
        export_formats=[ExportFormat.MARKDOWN, ExportFormat.DOCX, ExportFormat.PDF],
    )
    assert second_outputs["markdown"].read_text(encoding="utf-8") == rebuilt_markdown
    assert rebuilt_markdown == original_markdown

    delivery_integrity_review = json.loads(finalized_outputs["delivery_integrity_review"].read_text(encoding="utf-8"))
    assert delivery_integrity_review["total_issue_count"] == original_review["total_issue_count"]


def test_postprocess_backfills_relationship_timeline_and_cp_topics() -> None:
    from novel_agent.schemas import RelationshipProgression

    chapters = [
        ChapterAnalysis(
            chapter_id=f"ch-{index:04d}",
            title=f"第0章 引子（分块 {index}/8）",
            summary=summary,
            crisis=[crisis],
            highlights=[highlight],
        )
        for index, summary, crisis, highlight in [
            (
                1,
                "同学会重逢后，两人迅速进入互相试探的状态。",
                "双方都在隐藏真实动机。",
                "初见即拉满张力。",
            ),
            (
                2,
                "留宿与近距离互动让关系开始升温。",
                "靠近之后更难保持边界。",
                "身体距离率先缩短。",
            ),
            (
                3,
                "合作推进后，现实压力开始压到两人关系上。",
                "主线风险不断逼两人表态。",
                "关系与事业首次深度绑定。",
            ),
            (
                4,
                "身份与旧账被翻出，关系进入明显拉扯期。",
                "误会与控制欲同时抬头。",
                "局面迅速失衡。",
            ),
            (
                5,
                "危机爆发后，两人不得不重新确认彼此立场。",
                "外部事件逼出真实选择。",
                "首次站到同一阵线。",
            ),
            (
                6,
                "共同承担代价后，信任开始转向更深层的共谋。",
                "主线代价反噬关系。",
                "关系不再只是试探。",
            ),
            (
                7,
                "双方在危机余波里重新谈判未来边界。",
                "过去创伤仍在反复回潮。",
                "关系走向定锚前夜。",
            ),
            (
                8,
                "最终通过承诺与站队完成关系确认。",
                "终局前必须直面全部代价。",
                "关系完成闭环。",
            ),
        ]
    ]

    chapters[0].relationship_progression = [RelationshipProgression(counterpart="主角A & 主角B", stage_label="初遇试探", change="先用高辨识互动建立关系起点。")]
    chapters[1].relationship_progression = [RelationshipProgression(counterpart="主角A & 主角B", stage_label="关系升温", change="身体距离和信任感同步抬升。")]
    chapters[4].relationship_progression = [RelationshipProgression(counterpart="主角A & 主角B", stage_label="危机拉扯", change="现实压力逼迫两人重新站队。")]
    chapters[7].relationship_progression = [RelationshipProgression(counterpart="主角A & 主角B", stage_label="终局确认", change="通过承诺与共担代价完成闭环。")]

    book = BookAnalysis(title="测试书")
    processed = postprocess_book_analysis(book, chapters)

    assert 4 <= len(processed.relationship_timeline) <= 8
    assert all(stage.chapter_range for stage in processed.relationship_timeline[:4])
    assert len(processed.cp_analysis.topics) >= 6
    assert all(len(topic.supporting_moments) >= 2 for topic in processed.cp_analysis.topics[:6])
    assert all("信息仍需进一步提炼" not in topic.analysis for topic in processed.cp_analysis.topics[:6])
    assert processed.relationship_timeline[0].pair == "主角A & 主角B"


def test_postprocess_book_analysis_backfills_genre_and_rewrites_weak_cp_topics() -> None:
    chapters = [
        ChapterAnalysis(
            chapter_id=f"ch-{index:04d}",
            title=f"第{index}章",
            summary=summary,
            crisis=[crisis],
            highlights=[highlight],
            key_characters=["赵壹笙", "卓舒清", "康壹竽"],
        )
        for index, summary, crisis, highlight in [
            (
                1,
                "都市重逢局里，赵壹笙与卓舒清先用金融合作试探彼此边界。",
                "双方都不愿先交底。",
                "只和女朋友接吻把关系直接钉住。",
            ),
            (
                2,
                "金融职场博弈升温后，两人开始把情感试探带进项目合作。",
                "事业风险逼她们重新站队。",
                "身体距离先于语言确认关系。",
            ),
            (
                3,
                "百合向关系在家族压力和旧案回收里继续加码。",
                "第三方角色逼迫关系表态。",
                "共同承担代价后出现第一次明确回收。",
            ),
            (
                4,
                "终局阶段通过共同站队完成关系闭环。",
                "最终代价要求双方明牌。",
                "承诺落地后完成终局确认。",
            ),
        ]
    ]
    book = BookAnalysis(
        title="测试书",
        overview="这是一个都市情感故事，主线同时带有金融职场博弈与百合向关系推进。",
        selling_points=["都市情感张力", "金融职场高压", "百合向双强关系"],
        story_hook_layers=StoryHookLayers(
            short_term=["都市情感起局"],
            mid_term=["金融职场博弈压进关系"],
            long_term=["百合向关系完成终局回收"],
        ),
        cp_analysis=CPAnalysis(
            topics=[
                CPTopic(topic="身体记忆", analysis="控制 vs 依恋", supporting_moments=["第一次近距离试探"]),
                CPTopic(topic="外部催化", analysis="信息仍需进一步提炼。", supporting_moments=["第三方角色逼出站队", "本章为后记"]),
            ]
        ),
    )

    processed = postprocess_book_analysis(book, chapters)
    topic_map = {item.topic: item for item in processed.cp_analysis.topics}

    assert processed.title_intro_analysis.genre == "都市情感 / 金融职场 / 百合向"
    assert "身体细节" in topic_map["身体记忆"].analysis
    assert any(token in topic_map["外部催化"].analysis for token in ["外部压力", "主线冲突", "感情加速器"])
    analysis_openers = {item.analysis[:10] for item in processed.cp_analysis.topics[:6]}
    assert len(analysis_openers) >= 4
    assert 2 <= len(topic_map["身体记忆"].supporting_moments) <= 4
    assert 2 <= len(topic_map["外部催化"].supporting_moments) <= 4
    assert all("本章为后记" not in topic.supporting_moments for topic in processed.cp_analysis.topics[:6])
    assert all(
        len(moment.replace(" ", "")) >= 12 or any(punct in moment for punct in "，；。")
        for topic in processed.cp_analysis.topics[:6]
        for moment in topic.supporting_moments[:2]
    )
    assert all(stage.description.strip() for stage in processed.relationship_timeline)
    assert all("信息仍需进一步提炼" not in stage.description for stage in processed.relationship_timeline)


def test_postprocess_backfills_character_profiles_and_style_evidence() -> None:
    from novel_agent.schemas import RelationshipProgression, StyleSignal

    chapters = [
        ChapterAnalysis(
            chapter_id=f"ch-{index:04d}",
            title=f"第0章 引子（分块 {index}/6）",
            summary=summary,
            crisis=[crisis],
            highlights=[highlight],
            key_characters=characters,
            relationship_progression=progression,
            style_signals=style_signals,
        )
        for index, summary, crisis, highlight, characters, progression, style_signals in [
            (
                1,
                "赵壹笙与卓舒清初遇，关系迅速进入试探。",
                "双方都在隐藏真实动机。",
                "初见就有高辨识张力。",
                ["赵壹笙", "卓舒清", "齐简臻"],
                [RelationshipProgression(counterpart="赵壹笙 & 卓舒清", stage_label="试探启动", change="先建立吸引与边界。")],
                [StyleSignal(dimension="对话节奏", observation="短句交锋推动关系和冲突同步起势。")],
            ),
            (
                2,
                "两人继续靠近，关系进入明显升温。",
                "主线压力开始压到关系上。",
                "身体距离先一步缩短。",
                ["赵壹笙", "卓舒清", "康壹竽"],
                [RelationshipProgression(counterpart="赵壹笙 & 卓舒清", stage_label="关系升温", change="亲密和信任同步加码。")],
                [StyleSignal(dimension="身体叙事", observation="动作和触感替代直白表白。")],
            ),
            (
                3,
                "康壹竽进入主线，推动姐妹线与主关系线并进。",
                "家族压力开始成形。",
                "姐妹同盟正式入场。",
                ["赵壹笙", "康壹竽", "卓舒清"],
                [RelationshipProgression(counterpart="赵壹笙 & 卓舒清", stage_label="战略共谋", change="情感与主线决策开始绑定。")],
                [StyleSignal(dimension="信息投喂", observation="信息通过阶段揭露和物件回收逐步放出。")],
            ),
            (
                4,
                "危机爆发后，赵壹笙与卓舒清必须重新站队。",
                "关系受到现实阻力强压。",
                "关系进入高压拉扯。",
                ["赵壹笙", "卓舒清", "方新箬"],
                [RelationshipProgression(counterpart="赵壹笙 & 卓舒清", stage_label="危机拉扯", change="现实代价逼迫关系重估。")],
                [StyleSignal(dimension="冲突推进", observation="冲突同时作用于主线推进和关系拉扯。")],
            ),
            (
                5,
                "创伤被摊开后，关系进入更深绑定。",
                "过往伤口开始反噬。",
                "关系转向创伤共担。",
                ["赵壹笙", "卓舒清", "齐简臻"],
                [RelationshipProgression(counterpart="赵壹笙 & 卓舒清", stage_label="创伤共担", change="双方开始共担代价。")],
                [StyleSignal(dimension="人物塑造", observation="人物通过动作、选择和沉默被塑造出来。")],
            ),
            (
                6,
                "终局通过承诺和站队完成关系确认。",
                "最终代价要求双方做出明确选择。",
                "关系闭环完成。",
                ["赵壹笙", "卓舒清", "康壹竽"],
                [RelationshipProgression(counterpart="赵壹笙 & 卓舒清", stage_label="终局确认", change="通过承诺与共担完成关系闭环。")],
                [StyleSignal(dimension="语言风格", observation="语言偏冷感克制，但关键句会在回收节点突然加重。")],
            ),
        ]
    ]

    processed = postprocess_book_analysis(BookAnalysis(title="测试书"), chapters)

    assert len(processed.character_profiles) >= 4
    assert all(profile.basic_info for profile in processed.character_profiles[:4])
    assert all(profile.relationships for profile in processed.character_profiles[:4])
    assert processed.style_summary.evidence_chapters
    assert processed.writing_breakdown.evidence_chapters
    assert processed.style_summary.narrative_pacing
    assert processed.style_summary.language_style


def test_postprocess_book_analysis_prunes_low_signal_extra_character_profiles() -> None:
    chapters = [
        ChapterAnalysis(
            chapter_id="ch-0001",
            title="第1章",
            summary="赵壹笙与卓舒清重逢，康壹竽与齐简臻分别从姐妹线和共谋线切入主线。",
            key_characters=["赵壹笙", "卓舒清", "康壹竽", "齐简臻", "方新箬"],
        )
    ]
    book = BookAnalysis(
        title="测试书",
        character_profiles=[
            CharacterProfile(name="赵壹笙", basic_info="角色1", personality_traits=["冷静"], major_experiences=["事件1"], relationships=["与卓舒清：恋人"]),
            CharacterProfile(name="卓舒清", basic_info="角色2", personality_traits=["敏锐"], major_experiences=["事件2"], relationships=["与赵壹笙：恋人"]),
            CharacterProfile(name="康壹竽", basic_info="角色3", personality_traits=["果断"], major_experiences=["事件3"], relationships=["与赵壹笙：姐妹"]),
            CharacterProfile(name="齐简臻", basic_info="角色4", personality_traits=["理性"], major_experiences=["事件4"], relationships=["与赵壹笙：共谋者"]),
            CharacterProfile(name="方新箬", basic_info="方新箬是全书高频核心人物，深度参与主线推进与关键关系变化。", personality_traits=["主线推动者", "情绪张力核心来源", "关键关系角色"], major_experiences=["主线推进中的关键角色"], relationships=["与卓舒清：核心关系角色"]),
        ],
    )

    processed = postprocess_book_analysis(book, chapters)

    assert [item.name for item in processed.character_profiles] == ["赵壹笙", "卓舒清", "康壹竽", "齐简臻"]


def test_quality_reviews_count_weak_placeholders_by_dimension() -> None:
    rendered_report = """# 测试书

## 作品名/简介/章节名分析

- 类型：信息仍需进一步提炼。

## 人物小传

### 康壹竽
- 外貌特点：信息仍需进一步提炼。

### 齐简臻
- 外貌特点：信息仍需进一步提炼。

## CP感分析

### 身体记忆

信息仍需进一步提炼。

### 外部催化

信息仍需进一步提炼。

## 文笔内容总结

- 写法分析：信息仍需进一步提炼。
"""
    book = BookAnalysis(
        title="测试书",
        character_profiles=[
            CharacterProfile(name="康壹竽", basic_info="角色A", appearance="信息仍需进一步提炼。", personality_traits=["果断"], major_experiences=["事件A"], relationships=["关系A"]),
            CharacterProfile(name="齐简臻", basic_info="角色B", appearance="信息仍需进一步提炼。", personality_traits=["敏锐"], major_experiences=["事件B"], relationships=["关系B"]),
        ],
        cp_analysis=CPAnalysis(
            summary="主 CP 总结。",
            topics=[
                CPTopic(topic="身体记忆", analysis="信息仍需进一步提炼。", supporting_moments=["桥段1", "桥段2"]),
                CPTopic(topic="外部催化", analysis="信息仍需进一步提炼。", supporting_moments=["桥段3", "桥段4"]),
                CPTopic(topic="初期建设", analysis="这对的好嗑点在试探与错位吸引，所以开篇就成立。", supporting_moments=["桥段5", "桥段6"]),
                CPTopic(topic="试探拉扯", analysis="这对的好嗑点在双方都不肯先交底，所以推进会一直吊着读者。", supporting_moments=["桥段7", "桥段8"]),
                CPTopic(topic="权力博弈", analysis="这对的好嗑点在高低位不断互换，所以亲密与博弈并行。", supporting_moments=["桥段9", "桥段10"]),
                CPTopic(topic="终局确认", analysis="这对的好嗑点在共同承担代价，所以前文拉扯全部回收。", supporting_moments=["桥段11", "桥段12"]),
            ],
        ),
    )
    eval_report = EvalReport(
        expected_chapters=1,
        total_chapters=1,
        analyzed_chapters=1,
        failed_chapters=0,
        schema_valid=True,
        evidence_coverage_ratio=1.0,
        required_sections_present=[],
    )

    quality_review = review_delivery_quality(
        book,
        [],
        eval_report,
        exported_formats=["markdown", "docx", "pdf"],
        rendered_report=rendered_report,
    )
    reference_review = build_reference_alignment_review(book, [], rendered_report=rendered_report)
    dims = {item.name: item for item in reference_review.dimensions}

    assert quality_review.status == "needs_optimization"
    assert quality_review.metrics["weak_placeholder_count"] == 6
    assert quality_review.metrics["weak_character_line_count"] == 2
    assert quality_review.metrics["weak_cp_line_count"] == 2
    assert dims["人物卡厚度"].remaining_issue_count == 2
    assert dims["CP专题深度"].remaining_issue_count == 2
    assert dims["整体产品感"].remaining_issue_count == 6


def test_pipeline_resumes_from_partial_chapter_analysis(tmp_path: Path) -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    settings.runs_dir = tmp_path / "runs"
    input_path = Path("tests/fixtures/sample_novel.txt")
    ctx = build_run_context(settings, str(input_path), "resume-run")
    provider = resolve_provider(ProviderName.MOCK)

    ingested = ingest_book(input_path, InputType.TXT, settings)
    normalized_path = ctx.ingest_dir / "normalized.txt"
    normalized_path.write_text(ingested.normalized_text, encoding="utf-8")
    manifest = RunManifest(
        run_id=ctx.run_id,
        book_id=ctx.book_id,
        input_path=str(input_path),
        input_type=InputType.TXT,
        profile=Profile.MVP.value,
        provider=provider.name,
        export_formats=["markdown"],
    )
    (ctx.ingest_dir / "manifest.json").write_text(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")

    chapters = split_into_chapters(ingested, settings)
    jsonl_dump(ctx.split_dir / "chapters.jsonl", [chapter.model_dump(mode="json") for chapter in chapters])

    first_analysis, _ = analyze_chapter(
        chapter=chapters[0],
        provider=provider,
        settings=settings,
        model_name=settings.model_settings.chapter_model,
    )
    jsonl_dump(
        ctx.chapter_dir / "chapter_analysis.jsonl",
        [
            first_analysis.model_dump(mode="json"),
            first_analysis.model_dump(mode="json"),
        ],
    )
    stale_book = {"title": "stale", "overview": "stale-overview"}
    (ctx.aggregate_dir / "book_analysis.json").write_text(json.dumps(stale_book, ensure_ascii=False), encoding="utf-8")

    outputs = run_pipeline(
        ctx=ctx,
        settings=settings,
        input_path=input_path,
        input_type=InputType.TXT,
        provider=provider,
        export_formats=[ExportFormat.MARKDOWN],
        profile=Profile.MVP.value,
        force=False,
    )

    rows = [json.loads(line) for line in (ctx.chapter_dir / "chapter_analysis.jsonl").read_text(encoding="utf-8").strip().splitlines()]
    assert len(rows) == len(chapters)
    assert len({row["chapter_id"] for row in rows}) == len(chapters)
    assert outputs["book_analysis"].exists()
    assert outputs["markdown"].exists()
    assert outputs["stage_stats"].exists()
    assert outputs["run_summary"].exists()
    assert outputs["quality_review"].exists()
    assert outputs["reference_alignment_review"].exists()

    refreshed_book = json.loads(outputs["book_analysis"].read_text(encoding="utf-8"))
    assert refreshed_book["overview"] != "stale-overview"

    stage_stats = json.loads(outputs["stage_stats"].read_text(encoding="utf-8"))
    assert stage_stats["total_calls"] > 0
    assert "aggregate_book" in stage_stats["stages"]
    run_summary = json.loads(outputs["run_summary"].read_text(encoding="utf-8"))
    assert run_summary["completed_chapters"] == len(chapters)
    assert run_summary["failed_chapters"] == 0


def test_pipeline_can_split_book_provider_from_chapter_provider(tmp_path: Path, monkeypatch) -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    settings.runs_dir = tmp_path / "runs"
    settings.book_provider = ProviderName.BAILIAN_LONG
    settings.model_settings.book_model = "qwen-long"
    input_path = Path("tests/fixtures/sample_novel.txt")
    ctx = build_run_context(settings, str(input_path), "book-provider-split")
    chapter_provider = resolve_provider(ProviderName.MOCK)
    spy_provider = _SpyBookProvider()

    monkeypatch.setattr("novel_agent.pipeline.resolve_book_provider", lambda default_provider, configured_name: spy_provider)

    outputs = run_pipeline(
        ctx=ctx,
        settings=settings,
        input_path=input_path,
        input_type=InputType.TXT,
        provider=chapter_provider,
        export_formats=[ExportFormat.MARKDOWN],
        profile=Profile.MVP.value,
        force=True,
    )

    assert outputs["book_analysis"].exists()
    assert spy_provider.calls == ["BookAnalysis"]
    upload_input = ctx.aggregate_dir / "qwen_long_book_input.json"
    assert upload_input.exists()
    assert outputs["quality_review"].exists()
    assert outputs["reference_alignment_review"].exists()


def test_pipeline_run_summary_records_failed_chapters_without_blocking_delivery(tmp_path: Path, monkeypatch) -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    settings.runs_dir = tmp_path / "runs"
    settings.book_provider = ProviderName.BAILIAN_LONG
    settings.model_settings.book_model = "qwen-long"
    input_path = Path("tests/fixtures/sample_novel.txt")
    ctx = build_run_context(settings, str(input_path), "failure-summary")
    chapter_provider = _FailingChapterProvider()
    spy_provider = _SpyBookProvider()

    monkeypatch.setattr("novel_agent.pipeline.resolve_book_provider", lambda default_provider, configured_name: spy_provider)

    outputs = run_pipeline(
        ctx=ctx,
        settings=settings,
        input_path=input_path,
        input_type=InputType.TXT,
        provider=chapter_provider,
        export_formats=[ExportFormat.MARKDOWN],
        profile=Profile.MVP.value,
        force=True,
    )

    run_summary = json.loads((ctx.eval_dir / "run_summary.json").read_text(encoding="utf-8"))
    chapter_status = json.loads((ctx.chapter_dir / "chapter_status.json").read_text(encoding="utf-8"))
    eval_report = json.loads(outputs["eval"].read_text(encoding="utf-8"))
    quality_review = json.loads(outputs["quality_review"].read_text(encoding="utf-8"))

    assert run_summary["total_chapters"] == 5
    assert run_summary["completed_chapters"] == 4
    assert run_summary["failed_chapters"] == 1
    assert run_summary["latest_failed_chapter_id"] == "ch-0002"
    assert run_summary["current_stage"] == "completed_with_failures"
    assert chapter_status["failed_chapters"] == 1
    assert chapter_status["current_stage"] == "completed_with_failures"
    assert eval_report["failed_chapters"] == 1
    assert quality_review["status"] == "high_risk"
    assert outputs["book_analysis"].exists()
    assert outputs["markdown"].exists()


def test_pipeline_treats_content_filter_failures_as_allowed_risk(tmp_path: Path, monkeypatch) -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    settings.runs_dir = tmp_path / "runs"
    settings.book_provider = ProviderName.BAILIAN_LONG
    settings.model_settings.book_model = "qwen-long"
    input_path = Path("tests/fixtures/sample_novel.txt")
    ctx = build_run_context(settings, str(input_path), "content-filter-failure")
    chapter_provider = _ContentFilterFailingChapterProvider()
    spy_provider = _SpyBookProvider()

    monkeypatch.setattr("novel_agent.pipeline.resolve_book_provider", lambda default_provider, configured_name: spy_provider)

    outputs = run_pipeline(
        ctx=ctx,
        settings=settings,
        input_path=input_path,
        input_type=InputType.TXT,
        provider=chapter_provider,
        export_formats=[ExportFormat.MARKDOWN],
        profile=Profile.MVP.value,
        force=True,
    )

    eval_report = json.loads(outputs["eval"].read_text(encoding="utf-8"))
    quality_review = json.loads(outputs["quality_review"].read_text(encoding="utf-8"))

    assert eval_report["failed_chapters"] == 1
    assert eval_report["content_filter_failed_chapters"] == 1
    assert eval_report["other_failed_chapters"] == 0
    assert quality_review["metrics"]["failed_chapters"] == 1
    assert quality_review["metrics"]["content_filter_failed_chapters"] == 1
    assert quality_review["metrics"]["other_failed_chapters"] == 0
    assert quality_review["status"] == "needs_optimization"
    assert not any("非内容审核失败章节" in item for item in quality_review["high_risks"])


def test_finalize_delivery_allows_failed_chapters_when_outputs_are_partial(tmp_path: Path, monkeypatch) -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    settings.runs_dir = tmp_path / "runs"
    settings.book_provider = ProviderName.BAILIAN_LONG
    settings.model_settings.book_model = "qwen-long"
    input_path = Path("tests/fixtures/sample_novel.txt")
    ctx = build_run_context(settings, str(input_path), "finalize-with-failures")
    chapter_provider = _FailingChapterProvider()
    spy_provider = _SpyBookProvider()

    monkeypatch.setattr("novel_agent.pipeline.resolve_book_provider", lambda default_provider, configured_name: spy_provider)

    outputs = run_pipeline(
        ctx=ctx,
        settings=settings,
        input_path=input_path,
        input_type=InputType.TXT,
        provider=chapter_provider,
        export_formats=[ExportFormat.MARKDOWN],
        profile=Profile.MVP.value,
        force=True,
    )

    outputs["markdown"].write_text("stale", encoding="utf-8")
    (ctx.eval_dir / "delivery_integrity_review.json").unlink(missing_ok=True)
    (ctx.eval_dir / "quality_review.json").unlink(missing_ok=True)
    (ctx.eval_dir / "reference_alignment_review.json").unlink(missing_ok=True)

    finalized_outputs = finalize_delivery(
        ctx=ctx,
        export_formats=[ExportFormat.MARKDOWN, ExportFormat.DOCX, ExportFormat.PDF],
    )

    rebuilt_markdown = finalized_outputs["markdown"].read_text(encoding="utf-8")
    eval_report = json.loads(finalized_outputs["eval"].read_text(encoding="utf-8"))

    assert rebuilt_markdown != "stale"
    assert finalized_outputs["docx"].exists()
    assert finalized_outputs["pdf"].exists()
    assert eval_report["failed_chapters"] == 1


def test_pipeline_retries_failed_chapter_before_aggregate(tmp_path: Path, monkeypatch) -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    settings.runs_dir = tmp_path / "runs"
    settings.book_provider = ProviderName.BAILIAN_LONG
    settings.model_settings.book_model = "qwen-long"
    input_path = Path("tests/fixtures/sample_novel.txt")
    ctx = build_run_context(settings, str(input_path), "retry-chapter")
    chapter_provider = _FlakyChapterProvider()
    spy_provider = _SpyBookProvider()

    monkeypatch.setattr("novel_agent.pipeline.resolve_book_provider", lambda default_provider, configured_name: spy_provider)

    outputs = run_pipeline(
        ctx=ctx,
        settings=settings,
        input_path=input_path,
        input_type=InputType.TXT,
        provider=chapter_provider,
        export_formats=[ExportFormat.MARKDOWN],
        profile=Profile.MVP.value,
        force=True,
    )

    run_summary = json.loads(outputs["run_summary"].read_text(encoding="utf-8"))
    assert chapter_provider.attempts["ch-0002"] == 2
    assert run_summary["failed_chapters"] == 0
    assert outputs["book_analysis"].exists()


def test_schema_normalization_backfills_evidence_snippet() -> None:
    extraction = ChapterChunkExtraction.model_validate(
        {
            "chapter_id": "ch-0001",
            "source_ref": "ch-0001:chunk-01",
            "summary": "测试",
            "evidence": [
                {
                    "chapter_id": "ch-0001",
                    "source_ref": "ch-0001:chunk-01",
                    "anchor": "心跳意象反复出现",
                    "note": "用于建立身体记忆",
                }
            ],
        }
    )

    assert extraction.evidence[0].snippet == "心跳意象反复出现"


def test_repair_delivery_weak_slots_cleans_titles_and_stage_payoff() -> None:
    chapters = [
        ChapterAnalysis(
            chapter_id="ch-0057",
            title="番外：过年搞事（分块 31/49）",
            summary="卓舒清回邺城与父亲摊牌，赵壹笙正式见家长。",
            highlights=["见家长流程正式开启"],
            payoff=["关系获得家族系统的正式接纳"],
            scene_quotes=[SceneQuoteItem(scene="见家长开场白", quote="叔叔您好，我是赵壹笙。", purpose="仪式化接纳")],
        ),
        ChapterAnalysis(
            chapter_id="ch-0058",
            title="番外：过年搞事（分块 32/49）",
            summary="两人在生活细节中完成更深层的关系确认。",
            crisis=["旧伤回潮让两人必须面对更深层的脆弱"],
            payoff=["共同承担成为关系新锚点"],
        ),
    ]
    book = BookAnalysis(
        delivery_units=[
            DeliveryUnit(
                unit_id="unit-029",
                title="以‘叔叔您好",
                chapter_refs=["ch-0057", "ch-0058"],
                chapter_range="第57-58章",
                summary="卓舒清回邺城与父亲摊牌，赵壹笙正式见家长。",
                scene_quotes=[SceneQuoteItem(scene="见家长开场白", quote="叔叔您好，我是赵壹笙。", purpose="仪式化接纳")],
                payoff=["关系获得家族系统的正式接纳"],
            )
        ],
        relationship_timeline=[
            RelationshipStage(
                pair="赵壹笙 & 卓舒清",
                stage_label="创伤共担",
                chapter_refs=["ch-0057", "ch-0058"],
                chapter_range="第57-58章",
                core_change="信息仍需进一步提炼。",
                pressure="信息仍需进一步提炼。",
                payoff="‘姐姐踩我’与‘阿清",
                description="信息仍需进一步提炼。",
            )
        ],
        plot_outline=PlotOutline(
            story_lines=[
                StoryLineItem(name="情感主线", category="核心线索", content="信息仍需进一步提炼。", key_points=["见家长", "共同承担"])
            ]
        ),
        cp_analysis=CPAnalysis(summary="两人的关系从试探靠近一路推进到共同承担。"),
    )

    repaired = repair_delivery_weak_slots(book, chapters)

    assert repaired.delivery_units[0].title == "见家长开场白"
    assert "信息仍需进一步提炼" not in repaired.relationship_timeline[0].description
    assert repaired.relationship_timeline[0].payoff
    assert "信息仍需进一步提炼" not in repaired.relationship_timeline[0].payoff
    assert "共同承担" in repaired.plot_outline.story_lines[0].content


def test_quality_review_downgrades_split_risk_when_semantic_groups_are_sufficient(tmp_path: Path, monkeypatch) -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    settings.runs_dir = tmp_path / "runs"
    settings.book_provider = ProviderName.BAILIAN_LONG
    settings.model_settings.book_model = "qwen-long"
    input_path = Path("tests/fixtures/sample_novel.txt")
    ctx = build_run_context(settings, str(input_path), "semantic-groups")
    chapter_provider = resolve_provider(ProviderName.MOCK)
    spy_provider = _SpyBookProvider()

    monkeypatch.setattr("novel_agent.pipeline.resolve_book_provider", lambda default_provider, configured_name: spy_provider)

    outputs = run_pipeline(
        ctx=ctx,
        settings=settings,
        input_path=input_path,
        input_type=InputType.TXT,
        provider=chapter_provider,
        export_formats=[ExportFormat.MARKDOWN],
        profile=Profile.MVP.value,
        force=True,
    )

    quality_review = json.loads(outputs["quality_review"].read_text(encoding="utf-8"))
    assert quality_review["status"] == "needs_optimization"
    assert "chapter_outline_ratio" in quality_review["metrics"]
    assert quality_review["metrics"]["has_docx"] is False
    assert quality_review["metrics"]["has_pdf"] is False


def test_postprocess_detailizes_story_lines_opening_craft_and_phase_outline() -> None:
    chapters = [
        ChapterAnalysis(
            chapter_id="ch-0001",
            title="第1章 同学会重逢",
            summary="赵壹笙在同学会公开挑明旧账，又在KTV洗手间对卓舒清直球告白接吻，把关系一下推到名分确认。",
            plot_events=[
                PlotEvent(label="同学会重逢", details="赵壹笙在同学会上主动点破旧账，把卓舒清重新拉回自己的视线中心。"),
                PlotEvent(label="洗手间告白", details="两人在KTV洗手间直球告白接吻，关系从互相打量直接推进到名分确认。"),
            ],
            crisis=["赵壹笙在高压工作和旧伤阴影里硬撑，情感靠近会直接碰到她最脆弱的地方。"],
            highlights=["洗手间告白接吻让开篇爽点立刻落地。"],
            beat_rhythm=[
                BeatRhythmItem(
                    beat="公开对峙",
                    pacing_tag="fast",
                    emotion_tag="testing",
                    note="赵壹笙借公开场合迫使卓舒清回应，让旧账、吸引和现实风险同时上桌。",
                )
            ],
            relationship_progression=[
                RelationshipProgression(
                    counterpart="赵壹笙 & 卓舒清",
                    stage_label="试探启动",
                    change="重逢让两人重新正视旧伤与吸引，关系从冷置状态回到高压拉扯。",
                )
            ],
            scene_quotes=[
                SceneQuoteItem(
                    scene="KTV洗手间告白",
                    quote="我只和女朋友接吻。",
                    purpose="一句话里同时完成划边界、立关系和抬张力。",
                )
            ],
        ),
        ChapterAnalysis(
            chapter_id="ch-0002",
            title="第2章 留宿升温",
            summary="卓舒清把赵壹笙带回住处，留宿、照料和清晨互动把试探推成贴身暧昧，也让生活空间开始互相渗透。",
            plot_events=[
                PlotEvent(label="留宿试探", details="卓舒清默许赵壹笙留宿，照料、近距离对视和衣物细节把关系推向更亲密的位置。"),
            ],
            crisis=["两人越靠近，越难继续把这段关系当成可撤回的策略动作。"],
            highlights=["生活空间被打开以后，关系不再只是口头暧昧。"],
            relationship_progression=[
                RelationshipProgression(
                    counterpart="赵壹笙 & 卓舒清",
                    stage_label="关系升温",
                    change="两人从高压试探转向生活化嵌入，关系第一次出现可持续的亲密日常。",
                )
            ],
        ),
    ]
    book = BookAnalysis(
        title="细化测试书",
        overview="赵壹笙与卓舒清在主线压力下，从试探靠近一路推进到共同站队。",
        cp_analysis=CPAnalysis(summary=""),
        plot_outline=PlotOutline(
            story_lines=[StoryLineItem(name="情感主线", category="核心线索", content="线索", key_points=["洗手间告白"])],
            phase_outline=[PhaseOutlineItem(phase="起", chapter_range="第1-2章", events=["告白"])],
        ),
        opening_craft=OpeningCraft(
            core_payoffs=["KTV告白接吻"],
            core_pain_points=["健康隐患"],
            flirty_moments=["洗手间告白"],
            character_building=["赵壹笙：高压精英"],
            dialogue_design=["我只和女朋友接吻"],
            action_details=["尾指轻勾"],
        ),
    )

    processed = postprocess_book_analysis(book, chapters)

    assert "洗手间" in processed.plot_outline.story_lines[0].content
    assert "名分确认" in processed.plot_outline.story_lines[0].content
    assert "：" in processed.plot_outline.phase_outline[0].events[0]
    assert "KTV洗手间" in processed.plot_outline.phase_outline[0].events[0] or "关系" in processed.plot_outline.phase_outline[0].events[0]
    assert processed.opening_craft.core_payoffs
    assert "KTV洗手间" in processed.opening_craft.core_payoffs[0]
    assert "名分确认" in processed.opening_craft.core_payoffs[0]
    assert any(token in processed.opening_craft.core_payoffs[0] for token in ["名分确认", "开篇回报", "关系启动", "直接起局"])
    assert processed.opening_craft.core_pain_points
    assert any(
        "赵壹笙在高压工作和旧伤阴影里硬撑" in item or "两人越靠近，越难继续把这段关系当成可撤回的策略动作" in item
        for item in processed.opening_craft.core_pain_points
    )
    assert processed.opening_craft.dialogue_design
    assert "我只和女朋友接吻" in processed.opening_craft.dialogue_design[0] or "对白" in processed.opening_craft.dialogue_design[0]
    assert any(token in processed.opening_craft.dialogue_design[0] for token in ["试探", "主动权", "划界", "关系分寸"])


def test_postprocess_synthesizes_non_relationship_story_lines_from_key_points() -> None:
    chapters = [
        ChapterAnalysis(
            chapter_id="ch-0001",
            title="第1章 董事会试探",
            summary="高科项目刚启动，赵壹笙先把股改、融资与董事会站队摆上桌面。",
        )
    ]
    book = BookAnalysis(
        title="资本线细化测试书",
        plot_outline=PlotOutline(
            story_lines=[
                StoryLineItem(
                    name="资本主线",
                    category="并行线索",
                    content="高科无限的股改并购、海外扩张与权力重组",
                    key_points=["梅肯兹裁员13%", "景致资本注资", "法人变更"],
                )
            ]
        ),
    )

    processed = postprocess_book_analysis(book, chapters)

    assert "梅肯兹裁员13%" in processed.plot_outline.story_lines[0].content
    assert "景致资本注资" in processed.plot_outline.story_lines[0].content
    assert "资本博弈" in processed.plot_outline.story_lines[0].content


def test_postprocess_opening_craft_dedupes_repeated_judgement_suffixes() -> None:
    chapters = [
        ChapterAnalysis(
            chapter_id="ch-0001",
            title="第1章 初见",
            summary="赵壹笙与齐简臻在咖啡厅包间会面，正式把卓舒清引入高科主线。",
            plot_events=[
                PlotEvent(label="包间会面", details="赵壹笙与齐简臻在咖啡厅包间会面，正式把卓舒清引入高科主线。"),
            ],
            crisis=["赵壹笙对卓舒清毫无背景认知，却已被迫把她纳入既定布局。"],
            scene_quotes=[SceneQuoteItem(scene="咖啡厅包间·初见", quote="送上门来的嘛，不要白不要。", purpose="一句话里同时完成划边界、立关系和抬张力。")],
        )
    ]
    book = BookAnalysis(
        title="开篇去重测试书",
        opening_craft=OpeningCraft(
            core_payoffs=["包间会面，这一步会直接把开篇爽点兑现成关系启动和局面改写。"],
            core_pain_points=["信息差风险，所以开篇会先把人物代价和风险压上来。"],
            flirty_moments=["咖啡厅包间·初见，两人的边界和吸引都在这一步被挑明。"],
            character_building=["赵壹笙在开篇就以女性，约30岁，高科无限创始人兼CEO进入场景。"],
            dialogue_design=["送上门来的嘛，不要白不要，一句话里同时完成划边界、立关系和抬张力。"],
            action_details=["包间会面，动作细节会把潜台词和权力变化直接写到读者眼前。"],
        ),
    )

    processed = postprocess_book_analysis(book, chapters)

    assert "这一步会直接把开篇爽点兑现成关系启动和局面改写" not in processed.opening_craft.core_payoffs[0]
    assert "所以开篇会先把人物代价和风险压上来" not in processed.opening_craft.core_pain_points[0]
    assert "两人的边界和吸引都在这一步被挑明" not in processed.opening_craft.flirty_moments[0]
    assert "一句话里同时完成划边界、立关系和抬张力" not in processed.opening_craft.dialogue_design[0]
    assert any(token in processed.opening_craft.dialogue_design[0] for token in ["主动权", "划界", "关系分寸"])


def test_postprocess_opening_craft_rewrites_scene_labels_into_plot_sentences() -> None:
    chapters = [
        ChapterAnalysis(
            chapter_id="ch-0001",
            title="第1章 初见",
            summary="赵壹笙与齐简臻在咖啡厅包间会面，随后在KTV洗手间把试探推进成带名分意味的接吻。",
            plot_events=[
                PlotEvent(label="包间会面", details="赵壹笙与齐简臻在咖啡厅包间会面，先把卓舒清拉进高科主线，再把关系危险感一起抬高。"),
            ],
            scene_quotes=[
                SceneQuoteItem(
                    scene="KTV洗手间告白",
                    quote="我只和女朋友接吻。",
                    purpose="一句话里同时完成划边界、立关系和抬张力。",
                ),
                SceneQuoteItem(
                    scene="咖啡厅包间·初见",
                    quote="送上门来的嘛，不要白不要。",
                    purpose="以玩笑先抬高欲望，再把主动权留在自己手里。",
                ),
            ],
        )
    ]
    book = BookAnalysis(
        title="开篇场景标签改写测试书",
        opening_craft=OpeningCraft(
            flirty_moments=["咖啡厅包间·初见"],
            dialogue_design=["送上门来的嘛，不要白不要。"],
            action_details=["KTV洗手间告白"],
        ),
    )

    processed = postprocess_book_analysis(book, chapters)

    assert processed.opening_craft.flirty_moments
    assert processed.opening_craft.dialogue_design
    assert processed.opening_craft.action_details
    assert any(item.startswith("在") for item in processed.opening_craft.flirty_moments)
    assert any("咖啡厅包间·初见" in item for item in processed.opening_craft.flirty_moments)
    assert any("送上门来的嘛，不要白不要" in item for item in processed.opening_craft.dialogue_design)
    assert "KTV洗手间告白，动作细节会把潜台词" not in processed.opening_craft.action_details[0]


def test_postprocess_opening_craft_prioritizes_early_high_impact_hooks_over_later_domestic_details() -> None:
    chapters = [
        ChapterAnalysis(
            chapter_id="ch-0001",
            title="第1章 告白接吻",
            summary="赵壹笙在KTV洗手间对卓舒清直球告白接吻，把关系一下推到名分确认。",
            plot_events=[
                PlotEvent(label="洗手间告白", details="两人在KTV洗手间直球告白接吻，关系从互相打量直接推进到名分确认。"),
            ],
            scene_quotes=[
                SceneQuoteItem(scene="KTV洗手间告白", quote="我只和女朋友接吻。", purpose="一句话里同时完成划边界、立关系和抬张力。"),
            ],
            highlights=["洗手间告白接吻让开篇爽点立刻落地。"],
        ),
        ChapterAnalysis(
            chapter_id="ch-0002",
            title="第2章 密码门对视",
            summary="卓舒清开门输入密码，又让赵壹笙记住门锁，关系开始往危险试探推进。",
            plot_events=[
                PlotEvent(label="密码门对视", details="卓舒清一边输入密码一边让赵壹笙记住门锁，把引狼入室的暧昧推成主导权试探。"),
            ],
        ),
        ChapterAnalysis(
            chapter_id="ch-0003",
            title="第3章 宵夜留宿",
            summary="赵壹笙邀卓舒清到家里吃宵夜，递拖鞋、问喜好，生活空间开始互相渗透。",
            plot_events=[
                PlotEvent(label="宵夜留宿", details="赵壹笙邀卓舒清至其两居室家中吃宵夜，递拖鞋、问喜好的细节暗示关系进阶；书房改造、1.5米床等空间叙事强化非临时性亲密。"),
            ],
        ),
    ]
    processed = postprocess_book_analysis(BookAnalysis(title="开篇排序测试书"), chapters)

    assert processed.opening_craft.core_payoffs
    assert "KTV洗手间" in processed.opening_craft.core_payoffs[0] or "名分确认" in processed.opening_craft.core_payoffs[0]
    assert "两居室" not in processed.opening_craft.core_payoffs[0]


def test_pipeline_run_summary_keeps_cumulative_seed_on_resume(tmp_path: Path) -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    settings.runs_dir = tmp_path / "runs"
    input_path = Path("tests/fixtures/sample_novel.txt")
    ctx = build_run_context(settings, str(input_path), "resume-seed")
    provider = resolve_provider(ProviderName.MOCK)

    ingested = ingest_book(input_path, InputType.TXT, settings)
    normalized_path = ctx.ingest_dir / "normalized.txt"
    normalized_path.write_text(ingested.normalized_text, encoding="utf-8")
    manifest = RunManifest(
        run_id=ctx.run_id,
        book_id=ctx.book_id,
        input_path=str(input_path),
        input_type=InputType.TXT,
        profile=Profile.MVP.value,
        provider=provider.name,
        export_formats=["markdown"],
    )
    (ctx.ingest_dir / "manifest.json").write_text(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")

    chapters = split_into_chapters(ingested, settings)
    jsonl_dump(ctx.split_dir / "chapters.jsonl", [chapter.model_dump(mode="json") for chapter in chapters])
    first_analysis, _ = analyze_chapter(
        chapter=chapters[0],
        provider=provider,
        settings=settings,
        model_name=settings.model_settings.chapter_model,
    )
    jsonl_dump(ctx.chapter_dir / "chapter_analysis.jsonl", [first_analysis.model_dump(mode="json")])
    previous_summary = RunSummary(
        run_id=ctx.run_id,
        book_id=ctx.book_id,
        input_path=str(input_path),
        provider=provider.name,
        book_provider=provider.name,
        chapter_model=settings.model_settings.chapter_model,
        book_model=settings.model_settings.book_model,
        total_chapters=len(chapters),
        completed_chapters=1,
        failed_chapters=0,
        total_calls=7,
        total_input_tokens=777,
        total_output_tokens=333,
        total_latency_ms=2222,
        estimated_cost_cny=1.2345,
        current_stage="chapter-analyze",
    )
    (ctx.eval_dir / "run_summary.json").write_text(
        json.dumps(previous_summary.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )
    previous_stage_stats = RunStatsSummary(
        total_calls=7,
        total_input_tokens=777,
        total_output_tokens=333,
        total_latency_ms=2222,
        stages={"chapter_chunk_extract": 2, "chapter_merge": 1},
    )
    (ctx.eval_dir / "stage_stats.json").write_text(
        json.dumps(previous_stage_stats.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )

    outputs = run_pipeline(
        ctx=ctx,
        settings=settings,
        input_path=input_path,
        input_type=InputType.TXT,
        provider=provider,
        export_formats=[ExportFormat.MARKDOWN],
        profile=Profile.MVP.value,
        force=False,
    )

    run_summary = json.loads(outputs["run_summary"].read_text(encoding="utf-8"))
    stage_stats = json.loads(outputs["stage_stats"].read_text(encoding="utf-8"))
    assert run_summary["completed_chapters"] == len(chapters)
    assert run_summary["total_calls"] >= 7
    assert run_summary["total_input_tokens"] >= 777
    assert stage_stats["total_calls"] >= 7
    assert stage_stats["total_input_tokens"] >= 777


def test_pipeline_rejects_concurrent_same_run_id(tmp_path: Path, monkeypatch) -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    settings.runs_dir = tmp_path / "runs"
    input_path = Path("tests/fixtures/sample_novel.txt")
    ctx = build_run_context(settings, str(input_path), "locked-run")
    provider = resolve_provider(ProviderName.MOCK)
    monkeypatch.setattr("novel_agent.runtime._pid_is_running", lambda pid: True)

    lock_path = ctx.lock_path
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps({"pid": os.getpid() + 1000, "host": "test-host", "run_id": ctx.run_id}, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="already active"):
        run_pipeline(
            ctx=ctx,
            settings=settings,
            input_path=input_path,
            input_type=InputType.TXT,
            provider=provider,
            export_formats=[ExportFormat.MARKDOWN],
            profile=Profile.MVP.value,
            force=False,
        )


def test_pipeline_skips_chapter_if_already_completed_mid_run(tmp_path: Path, monkeypatch) -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    settings.runs_dir = tmp_path / "runs"
    input_path = Path("tests/fixtures/sample_novel.txt")
    ctx = build_run_context(settings, str(input_path), "mid-run-skip")
    provider = resolve_provider(ProviderName.MOCK)

    ingested = ingest_book(input_path, InputType.TXT, settings)
    normalized_path = ctx.ingest_dir / "normalized.txt"
    normalized_path.write_text(ingested.normalized_text, encoding="utf-8")
    manifest = RunManifest(
        run_id=ctx.run_id,
        book_id=ctx.book_id,
        input_path=str(input_path),
        input_type=InputType.TXT,
        profile=Profile.MVP.value,
        provider=provider.name,
        export_formats=["markdown"],
    )
    (ctx.ingest_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )

    chapters = split_into_chapters(ingested, settings)
    jsonl_dump(ctx.split_dir / "chapters.jsonl", [chapter.model_dump(mode="json") for chapter in chapters])

    called_ids: list[str] = []
    injected = False
    original_analyze_chapter = analyze_chapter

    def fake_analyze_chapter(*, chapter, provider, settings, model_name, progress_callback=None):  # noqa: ANN001, ANN003
        nonlocal injected
        called_ids.append(chapter.chapter_id)
        analysis, stats = original_analyze_chapter(
            chapter=chapter,
            provider=provider,
            settings=settings,
            model_name=model_name,
            progress_callback=progress_callback,
        )
        if chapter.chapter_id == chapters[0].chapter_id and not injected:
            injected = True
            injected_analysis, _ = original_analyze_chapter(
                chapter=chapters[1],
                provider=provider,
                settings=settings,
                model_name=model_name,
            )
            jsonl_dump(ctx.chapter_dir / "chapter_analysis.jsonl", [injected_analysis.model_dump(mode="json")])
        return analysis, stats

    monkeypatch.setattr("novel_agent.pipeline.analyze_chapter", fake_analyze_chapter)

    outputs = run_pipeline(
        ctx=ctx,
        settings=settings,
        input_path=input_path,
        input_type=InputType.TXT,
        provider=provider,
        export_formats=[ExportFormat.MARKDOWN],
        profile=Profile.MVP.value,
        force=False,
    )

    assert chapters[0].chapter_id in called_ids
    assert chapters[1].chapter_id not in called_ids
    rows = [
        json.loads(line)
        for line in (ctx.chapter_dir / "chapter_analysis.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len({row["chapter_id"] for row in rows}) == len(chapters)
    assert outputs["run_summary"].exists()


def test_pipeline_sorts_persisted_chapter_truth_before_aggregate(tmp_path: Path) -> None:
    settings = AppSettings.for_profile(Profile.MVP)
    settings.runs_dir = tmp_path / "runs"
    input_path = Path("tests/fixtures/sample_novel.txt")
    ctx = build_run_context(settings, str(input_path), "sorted-truth")
    provider = resolve_provider(ProviderName.MOCK)

    ingested = ingest_book(input_path, InputType.TXT, settings)
    normalized_path = ctx.ingest_dir / "normalized.txt"
    normalized_path.write_text(ingested.normalized_text, encoding="utf-8")
    manifest = RunManifest(
        run_id=ctx.run_id,
        book_id=ctx.book_id,
        input_path=str(input_path),
        input_type=InputType.TXT,
        profile=Profile.MVP.value,
        provider=provider.name,
        export_formats=["markdown"],
    )
    (ctx.ingest_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )

    chapters = split_into_chapters(ingested, settings)
    jsonl_dump(ctx.split_dir / "chapters.jsonl", [chapter.model_dump(mode="json") for chapter in chapters])
    analyses = [
        analyze_chapter(
            chapter=chapter,
            provider=provider,
            settings=settings,
            model_name=settings.model_settings.chapter_model,
        )[0].model_dump(mode="json")
        for chapter in chapters
    ]
    jsonl_dump(ctx.chapter_dir / "chapter_analysis.jsonl", list(reversed(analyses)))

    outputs = run_pipeline(
        ctx=ctx,
        settings=settings,
        input_path=input_path,
        input_type=InputType.TXT,
        provider=provider,
        export_formats=[ExportFormat.MARKDOWN],
        profile=Profile.MVP.value,
        force=False,
    )

    book_analysis = json.loads(outputs["book_analysis"].read_text(encoding="utf-8"))
    outline_ids = [item["chapter_id"] for item in book_analysis["chapter_outlines"]]
    assert outline_ids == [chapter.chapter_id for chapter in chapters]


def test_postprocess_book_analysis_builds_delivery_units_without_split_markers() -> None:
    chapters = [
        ChapterAnalysis(
            chapter_id="ch-0001",
            title="第一章 开局（分块 1/3）",
            summary="主角第一次见面并建立初步合作。",
            crisis=["现实压力逼近"],
            emotion_state=EmotionState(primary="紧张", trajectory="升温"),
        ),
        ChapterAnalysis(
            chapter_id="ch-0002",
            title="第一章 开局（分块 2/3）",
            summary="两人继续试探并确认合作条件。",
            suspense=["合作是否能维持"],
            emotion_state=EmotionState(primary="紧张", trajectory="持续推进"),
        ),
        ChapterAnalysis(
            chapter_id="ch-0003",
            title="第一章 开局（分块 3/3）",
            summary="阶段关系达成一致并进入下一步。",
            payoff=["前文试探得到阶段回收"],
            emotion_state=EmotionState(primary="紧张", trajectory="回收"),
        ),
    ]
    book = postprocess_book_analysis(BookAnalysis(title="测试书", overview="测试综述"), chapters)

    assert len(book.delivery_units) == 1
    assert book.delivery_units[0].title == "开局"
    assert book.delivery_units[0].chapter_range == "第1-3章"
    assert "分块" not in book.delivery_units[0].title


def test_postprocess_book_analysis_cleans_unnamed_plot_outline_phase_labels() -> None:
    chapters = [
        ChapterAnalysis(
            chapter_id="ch-0001",
            title="第一章 开局（分块 1/2）",
            summary="庭院烧烤与FaceTime互动推动关系升温。",
            crisis=["现实风险开始抬头。"],
        ),
        ChapterAnalysis(
            chapter_id="ch-0002",
            title="第一章 开局（分块 2/2）",
            summary="膝前凝视允诺给时间，让关系进入更深阶段。",
            climax=["关系在对视和允诺里完成回收。"],
        ),
    ]
    book = BookAnalysis(
        title="测试书",
        overview="围绕主线冲突与关系变化展开。",
        plot_outline={
            "story_lines": [],
            "phase_outline": [
                {
                    "phase": "未命名条目",
                    "chapter_range": "第1-2章",
                    "events": ["庭院烧烤与FaceTime互动", "膝前凝视允诺给时间"],
                }
            ],
        },
    )

    processed = postprocess_book_analysis(book, chapters)

    assert processed.plot_outline.phase_outline
    assert all("未命名" not in item.phase for item in processed.plot_outline.phase_outline)
