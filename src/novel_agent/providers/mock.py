from __future__ import annotations

from typing import Any

from ..schemas import (
    AudiencePositioning,
    BatchSummary,
    CPTopic,
    BookAnalysis,
    ChapterAnalysis,
    ChapterChunkExtraction,
    ChapterRecord,
    CharacterProfile,
    CPAnalysis,
    HighlightSummaryItem,
    EmotionState,
    EvidenceItem,
    BeatRhythmItem,
    OpeningCraft,
    OutlineBeat,
    PhaseOutlineItem,
    PlotEvent,
    PlotOutline,
    RelationshipProgression,
    RelationshipStage,
    SceneQuoteItem,
    SellingPointItem,
    StageStats,
    StoryHookLayers,
    StoryLineItem,
    StyleSignal,
    StyleSummary,
    TitleIntroAnalysis,
    WritingBreakdown,
)
from .base import LLMProvider, T


class MockProvider(LLMProvider):
    name = "mock"

    def generate_structured(
        self,
        *,
        response_model: type[T],
        model: str,
        system_prompt: str,
        user_prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[T, StageStats]:
        payload = metadata or {}
        result = self._build_mock_response(response_model, payload)
        stats = StageStats(stage_name="llm", model=model, input_tokens=0, output_tokens=0)
        stats.warnings.append("structured_path:mock")
        return result, stats

    def _build_mock_response(self, response_model: type[T], metadata: dict[str, Any]) -> T:
        if response_model is ChapterChunkExtraction:
            chapter_id = metadata["chapter_id"]
            source_ref = metadata["source_ref"]
            text = metadata["text"]
            summary = text.split("\n")[0][:120] or "本段主要推动剧情"
            event_label = "关系推进" if any(word in text for word in ["认识", "告白", "喜欢", "结婚"]) else "剧情推进"
            relationship_stage = "刚认识" if "认识" in text else "关系拉近" if "喜欢" in text or "告白" in text else "关系变化"
            payload = ChapterChunkExtraction(
                chapter_id=chapter_id,
                source_ref=source_ref,
                summary=summary,
                plot_events=[PlotEvent(label=event_label, details=summary)],
                crisis=["存在阻碍或压力"] if any(word in text for word in ["危机", "追杀", "威胁", "压力"]) else [],
                foreshadowing=["埋下后续伏笔"] if "伏笔" in text else [],
                suspense=["留下问题等待揭示"] if "?" in text or "？" in text else [],
                climax=["本段情绪或事件达到高点"] if any(word in text for word in ["终于", "突然", "爆发", "决定"]) else [],
                payoff=["阶段性回收前文信息"] if "回收" in text else [],
                highlights=["关系或剧情在本段形成读者期待的爽点"],
                beat_rhythm=[
                    BeatRhythmItem(
                        beat="关键互动或事件推进",
                        pacing_tag="推进",
                        emotion_tag="期待",
                        note="本段完成一次可感知的剧情推进",
                    )
                ],
                scene_quotes=[
                    SceneQuoteItem(
                        scene="代表性桥段",
                        quote=text[:30],
                        purpose="提炼本段最易被记住的片段",
                    )
                ],
                emotion_state=EmotionState(
                    primary="紧张" if any(word in text for word in ["危机", "威胁", "冲突"]) else "推进",
                    secondary=["心动"] if any(word in text for word in ["喜欢", "牵手", "拥抱"]) else [],
                    trajectory="上升",
                ),
                relationship_progression=[
                    RelationshipProgression(
                        counterpart="主 CP",
                        stage_label=relationship_stage,
                        change="本段关系发生阶段性变化",
                    )
                ],
                key_characters=["主角A", "主角B"],
                style_signals=[StyleSignal(dimension="节奏", observation="事件推进明确")],
                evidence=[
                    EvidenceItem(
                        chapter_id=chapter_id,
                        source_ref=source_ref,
                        snippet=text[:80],
                        note="mock evidence",
                    )
                ],
            )
            return payload  # type: ignore[return-value]

        if response_model is ChapterAnalysis:
            chapter: ChapterRecord = metadata["chapter"]
            chunks: list[ChapterChunkExtraction] = metadata["chunk_extractions"]
            evidence = [item for chunk in chunks for item in chunk.evidence][:5]
            analysis = ChapterAnalysis(
                chapter_id=chapter.chapter_id,
                title=chapter.title,
                summary="；".join(chunk.summary for chunk in chunks[:2])[:300] or "本章完成一次阶段性推进",
                plot_events=[event for chunk in chunks for event in chunk.plot_events][:6],
                crisis=_unique([item for chunk in chunks for item in chunk.crisis]),
                foreshadowing=_unique([item for chunk in chunks for item in chunk.foreshadowing]),
                suspense=_unique([item for chunk in chunks for item in chunk.suspense]),
                climax=_unique([item for chunk in chunks for item in chunk.climax]),
                payoff=_unique([item for chunk in chunks for item in chunk.payoff]),
                highlights=_unique([item for chunk in chunks for item in chunk.highlights]),
                beat_rhythm=[item for chunk in chunks for item in chunk.beat_rhythm][:6],
                scene_quotes=[item for chunk in chunks for item in chunk.scene_quotes][:6],
                emotion_state=chunks[-1].emotion_state,
                relationship_progression=[item for chunk in chunks for item in chunk.relationship_progression][:5],
                key_characters=_unique([name for chunk in chunks for name in chunk.key_characters]),
                style_signals=[signal for chunk in chunks for signal in chunk.style_signals][:5],
                evidence=evidence,
            )
            return analysis  # type: ignore[return-value]

        if response_model is BatchSummary:
            label = metadata["batch_label"]
            chapters: list[ChapterAnalysis] = metadata["chapter_analyses"]
            batch = BatchSummary(
                batch_label=label,
                overview=f"{label} 聚合了 {len(chapters)} 章内容",
                outline_beats=[
                    OutlineBeat(
                        label=f"阶段 {index + 1}",
                        chapter_refs=[chapter.chapter_id],
                        description=chapter.summary[:80],
                    )
                    for index, chapter in enumerate(chapters[:5])
                ],
                relationship_stages=[
                    RelationshipStage(
                        pair="主 CP",
                        stage_label=chapter.relationship_progression[0].stage_label if chapter.relationship_progression else "关系推进",
                        chapter_refs=[chapter.chapter_id],
                        description=chapter.summary[:80],
                    )
                    for chapter in chapters[:5]
                ],
                style_signals=[StyleSignal(dimension="节奏", observation="整体推进稳定")],
                key_characters=_unique([name for chapter in chapters for name in chapter.key_characters]),
            )
            return batch  # type: ignore[return-value]

        if response_model is BookAnalysis:
            title = metadata["title"]
            chapters: list[ChapterAnalysis] = metadata["chapter_analyses"]
            batches: list[BatchSummary] = metadata["batch_summaries"]
            book = BookAnalysis(
                title=title,
                overview=f"{title} 的 V1 mock 全书概览，已基于 {len(chapters)} 章生成。",
                selling_points=["双线推进明确", "关系发展清晰", "阶段性冲突稳定"],
                highlights_summary=[
                    HighlightSummaryItem(title="双线关系起势快", detail="开篇快速抛出关系张力和现实压力，能立刻抓住读者。"),
                    HighlightSummaryItem(title="冲突与情感并行", detail="主线冲突和情感推进同步展开，不会出现明显断层。"),
                ],
                selling_points_detail=[
                    SellingPointItem(category="情感向", detail="关系推进与阶段回收清楚，具备持续追读感。"),
                    SellingPointItem(category="题材向", detail="主线冲突与人物关系互相抬升，结构稳定。"),
                ],
                positioning=["面向拆书内部操作", "适合后续导出为标准文档"],
                core_hooks=["主线推进", "关系变化", "冲突升级"],
                story_hook_layers=StoryHookLayers(
                    short_term=["开篇关系迅速建立", "初始冲突立即抛出"],
                    mid_term=["关系拉扯与主线同步升级", "关键危机推动阶段变化"],
                    long_term=["主线与情感线阶段回收", "结尾完成长期钩子闭环"],
                ),
                audience_positioning=AudiencePositioning(
                    comps=["样稿对标 A", "样稿对标 B"],
                    reader_profile=["偏好关系推进与拆书结构的读者"],
                    marketing_keywords=["情感线", "章节细纲", "主线推进"],
                    short_term_hooks=["开篇关系建立迅速"],
                    mid_term_hooks=["冲突与情感拉扯同步升级"],
                    long_term_hooks=["主线与情感线完成阶段性回收"],
                ),
                title_intro_analysis=TitleIntroAnalysis(
                    title_analysis=f"{title} 的标题直接指向核心关系与故事钩子",
                    core_hook="关系推进与主线冲突交叉发力",
                    genre="现代言情 / 关系成长",
                    intro_analysis="简介会优先交代人物关系、初始危机与长期看点。",
                    chapter_name_analysis="章节名以阶段推进和关系节点为主，便于拆书汇总。",
                ),
                character_profiles=[
                    CharacterProfile(
                        name="主角A",
                        role="核心主角",
                        traits=["行动推进"],
                        arc="逐步推动主线",
                        basic_info="关键行动方，承担主要推进任务。",
                        appearance="外在标识鲜明，便于读者快速记忆。",
                        personality_traits=["执行力强", "目标明确", "情绪克制"],
                        major_experiences=["开篇率先推动剧情", "中段承接主线危机", "后段完成阶段回收"],
                        relationships=["与主角B形成核心关系张力", "与外部阻力保持持续对冲"],
                    ),
                    CharacterProfile(
                        name="主角B",
                        role="核心主角",
                        traits=["关系回应"],
                        arc="逐步与主角A形成配合",
                        basic_info="核心关系对象，承担情感与主线的双重回应。",
                        appearance="气质鲜明，具有角色辨识度。",
                        personality_traits=["观察敏锐", "回应克制", "阶段性失控"],
                        major_experiences=["前期维持距离", "中期进入拉扯", "后期形成关系承诺"],
                        relationships=["与主角A形成长期拉扯", "被阶段性危机催化关系变化"],
                    ),
                ],
                cp_analysis=CPAnalysis(
                    summary="主 CP 以合作到承诺的关系推进形成稳定拉扯。",
                    topics=[
                        CPTopic(topic="初期建设", analysis="开篇用快速互动建立关系起点。", supporting_moments=["初遇即形成高辨识互动"]),
                        CPTopic(topic="矛盾与拉扯", analysis="关系推进始终伴随现实阻力和情绪克制。", supporting_moments=["关键对峙后关系反而升温"]),
                        CPTopic(topic="第三方催化", analysis="外部压力不断迫使两人直面关系。", supporting_moments=["阶段性危机带来合作升级"]),
                        CPTopic(topic="身体记忆", analysis="动作和场景承担情感确认功能。", supporting_moments=["高辨识场面成为关系锚点"]),
                        CPTopic(topic="细节线索", analysis="物件、台词和回收形成持续牵引。", supporting_moments=["关键台词重复回收"]),
                        CPTopic(topic="终极爆发", analysis="后段通过承诺或站队完成关系闭环。", supporting_moments=["主线与情感线同时回收"]),
                    ],
                    relationship_tension=["现实压力驱动合作关系", "情感表达滞后于行动兑现"],
                    stage_progression=["试探阶段", "合作阶段", "承诺阶段"],
                    catalyst_roles=["家族压力", "阶段性危机", "关键表态"],
                    emotional_hooks=["关系升温清晰", "冲突与回收节奏明确"],
                ),
                main_outline=[beat for batch in batches for beat in batch.outline_beats][:10],
                plot_outline=PlotOutline(
                    story_lines=[
                        StoryLineItem(
                            name="主线关系推进",
                            category="主线",
                            content="主角关系与主线冲突同步展开。",
                            key_points=["关系建立", "冲突升级", "阶段回收"],
                        ),
                        StoryLineItem(
                            name="外部压力线",
                            category="副线",
                            content="现实阻力不断逼出人物真实选择。",
                            key_points=["外部危机", "同盟形成", "阶段性清算"],
                        ),
                    ],
                    phase_outline=[
                        PhaseOutlineItem(phase="起", chapter_range="第1-2章", events=["开篇建立关系与初始冲突"]),
                        PhaseOutlineItem(phase="承", chapter_range="第3-4章", events=["关系与主线同步升级"]),
                        PhaseOutlineItem(phase="转", chapter_range="第5章", events=["关键危机推动阶段变化"]),
                        PhaseOutlineItem(phase="合", chapter_range="第5章", events=["完成阶段回收与关系确认"]),
                    ],
                ),
                opening_craft=OpeningCraft(
                    core_payoffs=["开篇快速抛出强互动", "高辨识桥段迅速建立记忆点"],
                    core_pain_points=["现实压力伴随关系建立同步压下"],
                    flirty_moments=["用对话和动作制造第一轮拉扯", "关键场景完成关系升级"],
                    character_building=["人物通过选择和反应建立性格", "角色功能清楚可识别"],
                    dialogue_design=["对话承担试探、确认与拉扯功能"],
                    action_details=["动作细节直接服务情绪与权力变化"],
                ),
                chapter_outlines=[
                    {
                        "chapter_id": chapter.chapter_id,
                        "title": chapter.title,
                        "one_line": chapter.summary[:80],
                        "plot": chapter.summary[:80],
                        "crisis": (chapter.crisis[0] if chapter.crisis else "阶段阻力待补充"),
                        "foreshadowing": (chapter.foreshadowing[0] if chapter.foreshadowing else "伏笔待补充"),
                        "suspense": (chapter.suspense[0] if chapter.suspense else "悬念待补充"),
                        "climax": (chapter.climax[0] if chapter.climax else "高潮待补充"),
                        "payoff": (chapter.highlights[0] if chapter.highlights else "爽点待补充"),
                    }
                    for chapter in chapters
                ],
                emotion_observations=[chapter.emotion_state.primary for chapter in chapters[:10]],
                relationship_timeline=[
                    RelationshipStage(
                        pair="主 CP",
                        stage_label=chapter.relationship_progression[0].stage_label if chapter.relationship_progression else "阶段推进",
                        chapter_refs=[chapter.chapter_id],
                        description=chapter.summary[:80],
                    )
                    for chapter in chapters[:8]
                ],
                writing_breakdown=WritingBreakdown(
                    writing_analysis="通过关系推进与主线冲突交替铺开叙事。",
                    opening_method="开篇优先抛出人物关系和现实压力。",
                    dialogue_design="对话承担试探、拉扯与关系确认功能。",
                    action_detail="关键动作服务情绪变化和关系推进。",
                    language_style="语言直接，强调拆解颗粒度与阶段回收。",
                    evidence_chapters=[chapter.chapter_id for chapter in chapters[:5]],
                ),
                style_summary=StyleSummary(
                    narrative_pacing="章节推进清楚，信息密度中等",
                    information_release="通过逐章推进释放主要信息",
                    conflict_design="冲突主要由章节事件驱动",
                    emotional_leverage="关系线与主线交替推进",
                    characterization="通过事件与互动呈现角色变化",
                    language_style="以直接叙述和关键节点为主",
                    hook_and_payoff="每章保留推进点，便于后续汇总",
                    evidence_chapters=[chapter.chapter_id for chapter in chapters[:5]],
                ),
                chapter_evidence_index={
                    chapter.chapter_id: [item.snippet for item in chapter.evidence[:2]]
                    for chapter in chapters
                },
            )
            return book  # type: ignore[return-value]

        raise ValueError(f"Mock provider does not support {response_model.__name__}")


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
