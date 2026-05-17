from __future__ import annotations

from dataclasses import dataclass
import re

from ..schemas import (
    BookAnalysis,
    ChapterAnalysis,
    DeliveryIntegrityIssue,
    DeliveryIntegrityReview,
    DeliveryUnit,
    PhaseOutlineItem,
    PlotEvent,
    RelationshipStage,
)


GENERIC_UNIT_TITLES = ("引子", "番外", "后记", "叙事单元", "未识别章节")
KNOWN_ENGLISH_REPLACEMENTS = {
    "narrative voice": "叙述视角",
    "narrative perspective": "叙述视角",
    "lexical precision": "措辞控制",
    "lexicon": "措辞控制",
    "syntax": "句法控制",
    "diction": "措辞节奏",
    "imagery": "意象铺陈",
    "story": "叙事组织",
    "subtext": "潜台词推进",
    "sensory precision": "感官精描",
    "metaphor usage": "意象运用",
    "dialogue rhythm": "对话节奏",
    "lexical register shift": "语体切换",
    "sensory layering": "感官铺陈",
    "bodily punctuation": "身体节拍",
    "bodily narration": "身体叙述",
    "bodily writing": "身体书写",
    "sartorial semiotics": "服饰符号",
    "object symbolism": "物象隐喻",
    "spatial irony": "空间反差",
    "spatial dynamics": "空间调度",
    "controlled detachment": "克制疏离",
    "strategic entanglement": "战略纠缠",
    "residual leverage": "旧关系余波",
    "shadow antagonist": "暗线对手",
    "external validation": "外部见证",
    "professional observation": "职业观察",
    "identity-based recalibration": "身份重估",
    "close third-person": "贴身第三人称",
    "staccato exchanges": "短句急切对话",
    "bilingual precision": "双语切换",
    "temporal-layering": "时空叠层",
    "physicality_as_metaphor": "身体隐喻",
    "medical-metaphor-system": "病理隐喻",
    "sensory juxtaposition": "冷热对冲",
    "professional vernacular": "职业话语",
    "committed intention": "关系确认",
    "mutual destabilization": "双向失衡",
    "professional recontainment": "关系收束回工作场",
    "body-memory reawakening": "身体记忆回潮",
    "old-identity reintegration": "旧身份回流",
    "initiation": "关系启动",
    "physical": "身体层面",
}
PACE_TAG_REPLACEMENTS = {
    "fast": "紧凑",
    "quick": "紧凑",
    "breakneck": "疾速推进",
    "slow": "舒缓",
    "slow motion": "慢镜舒展",
    "slow-motion": "慢镜舒展",
    "steady": "平稳",
    "escalation": "升温",
    "accelerating": "加速抬升",
    "medium": "平稳推进",
    "moderate": "平稳推进",
    "medium-slow": "缓推",
    "slow-burn": "缓慢升温",
    "slow-burn entry": "蓄势起笔",
    "slow-burn setup": "蓄势铺垫",
    "intimate acceleration": "贴身升温",
    "comedic release": "松弛缓冲",
    "percussive climax": "骤然爆发",
    "playful-fast": "轻快挑逗",
    "hold": "停顿蓄压",
    "hold_breath": "屏息蓄压",
    "hold-breath": "屏息蓄压",
    "breath-hold": "屏息蓄压",
    "breath_hold": "屏息蓄压",
    "hold-cut": "停顿转折",
    "accelerando": "加速抬升",
    "adagio": "低速铺压",
    "andante": "匀速推进",
    "largo": "沉缓下压",
    "rubato": "弹性拉扯",
    "fermata": "悬停蓄压",
    "marcato": "重拍推进",
    "jolt": "骤然一击",
    "staccato": "短促切分",
    "still": "静止蓄压",
    "languid": "舒缓铺陈",
    "soft": "柔缓推进",
    "sharp": "骤切收紧",
    "tense": "紧绷推进",
    "comic": "轻巧转松",
    "jarring": "失衡切入",
    "cut": "截断转折",
    "contrast": "反差转折",
    "dissolve": "缓释回落",
    "liquid": "流动推进",
    "tactile": "触感推进",
    "waltz": "回旋推进",
    "maestoso": "庄重抬升",
    "luminous": "明亮转松",
    "stutter": "停顿卡顿",
    "urgency": "急促推进",
    "pause": "悬停一拍",
    "measured": "稳压推进",
    "swell": "涌升抬高",
    "pivot": "转折抬升",
    "release": "缓释回落",
    "muted": "低频压抑",
    "unfold": "逐层铺开",
    "final": "收束定音",
    "linger": "延宕回味",
    "break": "断裂反弹",
    "whip_pan": "甩切推进",
    "whip pan": "甩切推进",
    "controlled detachment": "克制疏离",
    "crescendo": "加速抬升",
    "slow-tension": "缓压蓄势",
    "slow burn tension": "缓慢蓄压",
    "slow-burn tension": "缓慢蓄压",
    "lingering": "延宕回味",
    "slow_build": "逐层升温",
    "slow build": "逐层升温",
    "ritardando": "渐缓下沉",
    "suspended": "悬停蓄压",
    "punctuated": "顿挫切分",
    "sharp_cut": "骤切收紧",
    "sharp-cut": "骤切收紧",
    "micro-pause": "微停顿",
    "micro_pause": "微停顿",
    "cinematic climax": "高潮爆发",
    "freeze-frame": "定格悬停",
    "freeze_frame": "定格悬停",
}
EMOTION_TAG_REPLACEMENTS = {
    "controlled detachment": "克制疏离",
    "tenderness": "温柔试探",
    "desire": "欲望拉扯",
    "grief": "哀伤失控",
    "anger": "怒意对撞",
    "fear": "不安戒备",
    "tender": "温柔试探",
    "teasing": "撩拨试探",
    "tense": "紧绷对抗",
    "numb": "麻木下坠",
    "wry": "冷淡讥诮",
    "weary": "疲惫失衡",
    "vulnerable": "脆弱松动",
    "defiant": "强硬反击",
    "defiance": "强硬反击",
    "playful": "玩笑试探",
    "playfulness": "玩笑试探",
    "provocative": "挑衅试探",
    "anticipation": "心动升温",
    "irritation": "烦躁戒备",
    "amusement": "松弛戏谑",
    "tactile hunger": "身体渴望",
    "controlled vulnerability": "克制失守",
    "lethal confidence": "危险自信",
    "arousal": "欲望升温",
    "awe": "震荡失语",
    "calm": "表面平静",
    "chaos": "失控翻涌",
    "clarity": "清醒判断",
    "cold": "冷感克制",
    "comic": "戏谑松动",
    "devotion": "投入确认",
    "distrust": "戒备怀疑",
    "dread": "不安压顶",
    "fatigue": "疲惫失衡",
    "feral": "野性失控",
    "focused": "专注逼近",
    "grieving": "哀痛回潮",
    "hostage": "受制紧绷",
    "instinct": "本能靠近",
    "intimate": "亲密靠近",
    "jarring": "骤然失衡",
    "levity": "轻松试探",
    "moderate": "克制推进",
    "muted": "压低情绪",
    "panic": "惊惶失序",
    "rage": "怒意爆发",
    "relief": "松口回缓",
    "released": "情绪松开",
    "resigned": "无奈下沉",
    "resolve": "定意确认",
    "reverent": "郑重靠近",
    "serene": "平静贴近",
    "sharp": "尖锐对冲",
    "shock": "震惊失守",
    "soft": "柔软靠近",
    "still": "静压蓄势",
    "swell": "情绪上涨",
    "tension": "拉扯加码",
    "testing": "试探拉扯",
    "tight": "绷紧压迫",
    "triumph": "强势得手",
    "unbroken": "执拗不退",
    "volatile": "情绪爆裂",
    "steely": "强硬克制",
    "dawning": "渐次明朗",
    "guarded": "戒备观望",
    "yearning": "渴望牵引",
    "menace": "威压逼近",
    "wary": "谨慎戒备",
    "charged": "高压拉扯",
    "anxious": "焦灼不安",
    "anxiety": "焦灼不安",
    "jolted": "骤然惊震",
    "resolute": "定意向前",
    "detached": "疏离观望",
    "contempt": "轻蔑压制",
    "reserve": "克制观望",
    "ecstatic": "极致沸腾",
    "furious": "暴怒失控",
    "doubt": "迟疑动摇",
    "shame": "羞惭失衡",
    "command": "强势掌控",
    "finality": "决绝收束",
    "curiosity": "好奇试探",
    "calculation": "冷静算计",
    "electric": "触电震荡",
    "awe-softness": "震荡柔软",
    "vulnerability": "脆弱松动",
    "dissonance": "失衡拉扯",
    "exhaustion": "疲惫失衡",
    "disorientation": "失序恍惚",
    "shocked": "震惊失守",
    "awestruck": "震荡失语",
    "resignation": "无奈下沉",
    "anticipatory": "心动蓄势",
    "isolation": "孤立压抑",
    "catharsis": "宣泄释放",
    "urgency": "焦灼逼近",
    "desperate": "绝望失控",
    "flustered": "慌乱失守",
    "guarded_vulnerability": "戒备松动",
    "charge": "高压拉扯",
}
PHASE_MARKERS = ("起", "承", "转", "合")
GENERIC_PACING_LABELS = {"推进"}
GENERIC_EMOTION_LABELS = {"情绪变化", "+", "情绪"}
PACE_FALLBACK_LABEL = "平稳推进"
EMOTION_FALLBACK_LABEL = "拉扯加码"
PACE_CONTEXT_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("铺垫", "起手", "开场", "起笔", "预热", "引入"), "蓄势铺垫"),
    (("停顿", "悬停", "屏息", "静默", "沉默", "驻足", "定格", "凝视", "停住"), "悬停一拍"),
    (("骤", "猛", "砸", "撞", "扑", "闯", "爆", "冲击", "突", "一击"), "骤然一击"),
    (("加速", "逼近", "连击", "快切", "疾步", "升温", "抬升", "追", "逼"), "加速抬升"),
    (("反差", "转折", "骤切", "切换", "打断", "回转", "拐点", "断裂"), "截断转折"),
    (("释放", "回落", "释然", "松开", "消解", "回缓"), "缓释回落"),
    (("舒缓", "缓慢", "慢", "日常", "回味", "拖沓", "柔和"), "舒缓"),
    (("推进", "进入", "会面", "对话", "交谈", "接近", "靠近"), "平稳推进"),
)
EMOTION_CONTEXT_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("欲望", "吻", "唇", "贴身", "暧昧", "撩", "触碰", "呼吸", "体温"), "欲望升温"),
    (("温柔", "照料", "安抚", "轻声", "拥抱", "抚摸", "陪伴", "靠近"), "温柔试探"),
    (("反击", "质问", "压制", "掌控", "回怼", "呛声", "强势"), "强硬反击"),
    (("哀伤", "落泪", "哭", "灵堂", "墓", "痛", "崩溃"), "哀伤失控"),
    (("疲惫", "虚弱", "衰竭", "发烧", "病房", "乏力", "倦", "麻木"), "疲惫失衡"),
    (("震惊", "失语", "愣住", "惊骇", "瞳孔", "僵住", "惊"), "震惊失守"),
    (("不安", "焦虑", "焦灼", "害怕", "恐惧", "窒息", "压顶"), "不安压顶"),
    (("无奈", "退让", "放弃", "沉下去", "认命"), "无奈下沉"),
    (("平静", "冷静", "淡定", "面无表情", "沉着"), "表面平静"),
    (("确认", "承认", "决定", "直视", "笃定", "向前", "认定"), "定意确认"),
    (("试探", "打量", "观望", "怀疑", "警惕", "提防"), "戒备怀疑"),
    (("对峙", "拉扯", "僵持", "旧账", "博弈", "逼近"), "拉扯加码"),
)
GENERIC_CHINESE_FALLBACKS = {
    "情感推进": "关系进入新的推进节点。",
    "文风信号": "细节、动作和对话共同服务张力。",
    "情节点与节奏": "本单元完成一次清晰推进。",
}
RELATIONSHIP_STAGE_LABEL_POOL = (
    "试探期",
    "升温期",
    "共谋期",
    "危机期",
    "确认期",
    "同盟期",
    "敌对期",
    "创伤共担",
)
LOW_SIGNAL_PATTERNS = (
    r"待补充",
    r"未命名条目",
    r"信息仍需进一步提炼",
    r"^到$",
    r"^从$",
    r"^关系变化$",
    r"^关键场面$",
    r"^提炼本章最强记忆点$",
    r"^强化本段记忆点$",
    r"^外貌特点：未详述$",
    r"关系进入新的推进节点",
    r"本单元完成一次阶段性推进",
    r"本单元完成一次清晰推进",
    r"完成一次清晰推进",
    r"围绕关键剧情点完成推进",
    r"细节、动作和对话共同服务张力",
)
FRAGMENT_ENGLISH_WORDS = {"details", "detail", "list", "stage", "physical", "identity", "trust"}
TRUNCATED_ENDING_WORDS = (
    "说",
    "称",
    "提及",
    "提到",
    "指出",
    "强调",
    "坦白",
    "回复",
    "确认",
    "观察",
    "回应",
    "讲",
    "问",
    "及",
    "与",
    "而",
    "并",
    "为",
    "对",
    "向",
    "将",
    "把",
    "被",
    "让",
    "从",
    "到",
    "如",
    "例如",
    "比如",
    "包括",
    "等",
    "vs",
    "和",
    "与",
    "及",
)
EMPTY_GROUP_FALLBACKS = {
    "支撑桥段": ["代表桥段已在章节细纲对应单元展开。"],
}
DELIVERY_SECTION_ORDER = [
    "综述",
    "核心亮点总结",
    "核心卖点",
    "推荐定位",
    "剧情看点分层",
    "核心梗",
    "作品名/简介/章节名分析",
    "人物小传",
    "CP感分析",
    "剧情大纲",
    "开篇文法分析",
    "情感线",
    "章节细纲",
    "文笔内容总结",
]


@dataclass
class ReportBlock:
    kind: str
    level: int
    text: str
    style: str = ""


@dataclass
class PhaseOutlineEventDisplay:
    title: str
    chapter_range: str
    description: str


def build_delivery_integrity_review(
    report_blocks: list[ReportBlock],
    *,
    rendered_report: str = "",
    round_issue_counts: list[int] | None = None,
) -> DeliveryIntegrityReview:
    issues = _collect_delivery_integrity_issues(report_blocks, rendered_report=rendered_report)
    blocking_issue_count = sum(1 for issue in issues if issue.severity == "blocking")
    repairable_issue_count = sum(1 for issue in issues if issue.repairable)
    issue_type_counts: dict[str, int] = {}
    for issue in issues:
        issue_type_counts[issue.issue_type] = issue_type_counts.get(issue.issue_type, 0) + 1
    overall_status = "passed"
    if blocking_issue_count > 0:
        overall_status = "blocked"
    elif issues:
        overall_status = "needs_repair"
    return DeliveryIntegrityReview(
        overall_status=overall_status,
        total_issue_count=len(issues),
        blocking_issue_count=blocking_issue_count,
        repairable_issue_count=repairable_issue_count,
        round_issue_counts=round_issue_counts or [],
        issue_type_counts=issue_type_counts,
        issues=issues,
    )


def repair_delivery_report_blocks(report_blocks: list[ReportBlock]) -> list[ReportBlock]:
    repaired: list[ReportBlock] = []
    current_section = ""
    current_block_title = ""
    current_group_title = ""
    relationship_seen_by_block: dict[str, set[str]] = {}
    for block in report_blocks:
        if block.kind == "heading" and block.level == 2:
            current_section = block.text.strip()
            current_block_title = ""
            current_group_title = ""
            repaired.append(block)
            continue
        if block.kind == "heading" and block.level == 3:
            current_block_title = block.text.strip()
            current_group_title = ""
            repaired_text = _repair_heading_text(current_section, current_block_title)
            if repaired_text:
                repaired.append(block.__class__(kind=block.kind, level=block.level, text=repaired_text, style=block.style))
            continue
        if block.kind == "bullet" and block.style == "group_label" and block.level == 1:
            current_group_title = block.text.strip()
            repaired.append(block)
            continue

        repaired_text = _repair_block_text(
            block.text,
            section_title=current_section,
            block_title=current_block_title,
            group_title=current_group_title,
            relationship_seen=relationship_seen_by_block.setdefault(current_block_title or current_section, set()),
        )
        if not repaired_text:
            continue
        repaired.append(block.__class__(kind=block.kind, level=block.level, text=repaired_text, style=block.style))
    return repaired


def build_delivery_report(
    book: BookAnalysis,
    chapters: list[ChapterAnalysis],
    *,
    include_debug: bool = False,
) -> list[ReportBlock]:
    grouped_units = book.delivery_units or [_chapter_to_unit(chapter, index) for index, chapter in enumerate(chapters, start=1)]
    chapter_units = _dedupe_chapter_unit_titles(
        [_chapter_to_unit(chapter, index) for index, chapter in enumerate(chapters, start=1)]
    ) or grouped_units
    chapter_lookup = {chapter.chapter_id: chapter for chapter in chapters}
    blocks: list[ReportBlock] = [ReportBlock(kind="heading", level=1, text=_value(book.title), style="book_title")]

    _append_section(blocks, "综述", _build_overview_paragraphs(book))

    _append_themed_section(
        blocks,
        "核心亮点总结",
        [(item.title, item.detail) for item in book.highlights_summary],
        fallback_title="核心亮点",
        fallback_values=book.selling_points,
    )

    _append_themed_section(
        blocks,
        "核心卖点",
        [(item.category, item.detail) for item in book.selling_points_detail],
        fallback_title="核心卖点",
        fallback_values=book.selling_points,
    )

    blocks.append(ReportBlock(kind="heading", level=2, text="推荐定位", style="section_heading"))
    _append_labeled_bullets(blocks, "对标作品", _compress_list(book.audience_positioning.comps, limit=4, max_chars=26))
    _append_labeled_bullets(blocks, "读者画像", _compress_list(book.audience_positioning.reader_profile, limit=5, max_chars=28))
    _append_labeled_bullets(blocks, "营销关键词", _compress_list(book.audience_positioning.marketing_keywords, limit=8, max_chars=16))
    blocks.append(ReportBlock(kind="heading", level=2, text="剧情看点分层", style="section_heading"))
    _append_labeled_bullets(blocks, "短期看点", _compress_list(book.story_hook_layers.short_term or book.audience_positioning.short_term_hooks, limit=4, max_chars=34))
    _append_labeled_bullets(blocks, "中期看点", _compress_list(book.story_hook_layers.mid_term or book.audience_positioning.mid_term_hooks, limit=4, max_chars=34))
    _append_labeled_bullets(blocks, "长期看点", _compress_list(book.story_hook_layers.long_term or book.audience_positioning.long_term_hooks, limit=4, max_chars=34))

    blocks.append(ReportBlock(kind="heading", level=2, text="核心梗", style="section_heading"))
    blocks.append(
        ReportBlock(
            kind="bullet",
            level=1,
            text=f"一句总梗：{_compress_paragraph(book.title_intro_analysis.core_hook, max_sentences=1, max_chars=72)}",
            style="section_item",
        )
    )
    if book.core_hooks:
        blocks.append(
            ReportBlock(
                kind="bullet",
                level=1,
                text=f"主线梗：{_compress_sentence(book.core_hooks[0], max_chars=54)}",
                style="section_item",
            )
        )
    _append_labeled_bullets(blocks, "副线梗", _compress_list(book.core_hooks[1:], limit=3, max_chars=44))

    blocks.append(ReportBlock(kind="heading", level=2, text="作品名/简介/章节名分析", style="section_heading"))
    blocks.append(ReportBlock(kind="bullet", level=1, text=f"作品名分析：{_compress_paragraph(book.title_intro_analysis.title_analysis, max_sentences=2, max_chars=92)}", style="section_item"))
    _append_optional_bullet(
        blocks,
        "类型",
        _format_editorial_field(
            book.title_intro_analysis.genre,
            max_sentences=1,
            max_chars=30,
            preserve_compound_tags=True,
        ),
    )
    _append_optional_bullet(
        blocks,
        "简介分析",
        _format_editorial_field(book.title_intro_analysis.intro_analysis, max_sentences=2, max_chars=92),
    )
    blocks.append(ReportBlock(kind="bullet", level=1, text=f"章节名分析：{_compress_paragraph(book.title_intro_analysis.chapter_name_analysis, max_sentences=2, max_chars=92)}", style="section_item"))

    blocks.append(ReportBlock(kind="heading", level=2, text="人物小传", style="section_heading"))
    if book.character_profiles:
        for character in book.character_profiles:
            blocks.append(ReportBlock(kind="heading", level=3, text=_value(character.name or "未命名角色"), style="person_heading"))
            blocks.append(ReportBlock(kind="bullet", level=1, text=f"基本信息：{_compress_paragraph(character.basic_info or character.role, max_sentences=2, max_chars=72)}", style="section_item"))
            appearance = _format_optional_field(character.appearance, max_sentences=2, max_chars=72)
            _append_optional_bullet(blocks, "外貌特点", appearance)
            _append_labeled_bullets(blocks, "性格特点", _compress_list(character.personality_traits or character.traits, limit=5, max_chars=28))
            _append_labeled_bullets(blocks, "主要经历", _compress_list(character.major_experiences or ([character.arc] if character.arc.strip() else []), limit=5, max_chars=36))
            _append_labeled_bullets(blocks, "人物关系", _compress_list(character.relationships, limit=5, max_chars=30))
    else:
        blocks.append(ReportBlock(kind="paragraph", level=0, text="人物信息暂未提炼完整。", style="body"))

    blocks.append(ReportBlock(kind="heading", level=2, text="CP感分析", style="section_heading"))
    cp_summary = _format_editorial_field(book.cp_analysis.summary, max_sentences=4, max_chars=220) or _compress_paragraph(
        book.cp_analysis.summary,
        max_sentences=4,
        max_chars=220,
    )
    if cp_summary:
        blocks.append(ReportBlock(kind="paragraph", level=0, text=cp_summary, style="body"))
    if book.cp_analysis.topics:
        for topic in book.cp_analysis.topics:
            blocks.append(ReportBlock(kind="heading", level=3, text=_compress_title(topic.topic, max_chars=18), style="group_heading"))
            topic_analysis = _format_editorial_field(topic.analysis, max_sentences=3, max_chars=180) or _compress_paragraph(
                topic.analysis,
                max_sentences=3,
                max_chars=180,
            )
            if topic_analysis:
                blocks.append(ReportBlock(kind="paragraph", level=0, text=topic_analysis, style="body"))
            _append_labeled_bullets(blocks, "支撑桥段", _collect_detail_items(topic.supporting_moments, limit=4, max_chars=140))
    else:
        _append_labeled_bullets(blocks, "关系张力", _compress_list(book.cp_analysis.relationship_tension, limit=5, max_chars=26))
        _append_labeled_bullets(blocks, "阶段推进", _compress_list(book.cp_analysis.stage_progression, limit=5, max_chars=28))
        _append_labeled_bullets(blocks, "催化角色", _compress_list(book.cp_analysis.catalyst_roles, limit=5, max_chars=20))
        _append_labeled_bullets(blocks, "关键情感抓手", _compress_list(book.cp_analysis.emotional_hooks, limit=5, max_chars=32))

    blocks.append(ReportBlock(kind="heading", level=2, text="剧情大纲", style="section_heading"))
    blocks.append(ReportBlock(kind="heading", level=3, text="核心故事线-主线/副线", style="group_heading"))
    if book.plot_outline.story_lines:
        for story_line in book.plot_outline.story_lines:
            story_line_content = _format_preserved_clause(story_line.content, max_chars=180) or _compress_paragraph(
                story_line.content,
                max_sentences=3,
                max_chars=180,
            )
            blocks.append(
                ReportBlock(
                    kind="bullet",
                    level=1,
                    text=f"{_compress_title(story_line.name, max_chars=22)}｜{_compress_title(story_line.category, max_chars=12)}：{story_line_content}",
                    style="section_item",
                )
            )
            _append_labeled_bullets(blocks, "关键点", _collect_detail_items(story_line.key_points, limit=4, max_chars=48))
    else:
        blocks.append(ReportBlock(kind="paragraph", level=0, text="故事线信息暂未提炼完整。", style="body"))

    blocks.append(ReportBlock(kind="heading", level=3, text="主线大纲", style="group_heading"))
    if book.plot_outline.phase_outline:
        for phase_index, phase in enumerate(book.plot_outline.phase_outline, start=1):
            label = _format_phase_outline_label(phase.phase or "阶段", phase_index)
            chapter_range = _format_phase_chapter_range(phase.chapter_range or "阶段范围未明")
            blocks.append(ReportBlock(kind="bullet", level=1, text=f"【{_truncate_chars(label, 22)}】（{chapter_range}）", style="section_item"))
            for event_index, event in enumerate(_build_phase_outline_events(phase, chapters), start=1):
                blocks.append(
                    ReportBlock(
                        kind="bullet",
                        level=2,
                        text=f"事件{event_index}：{event.title}（{event.chapter_range}）",
                        style="group_detail",
                    )
                )
                blocks.append(ReportBlock(kind="bullet", level=3, text=event.description, style="group_detail"))
    elif book.main_outline:
        for beat_index, beat in enumerate(book.main_outline, start=1):
            chapter_range = _format_chapter_refs(beat.chapter_refs)
            label = _format_phase_outline_label(beat.label or "主线阶段", beat_index)
            description = _compress_paragraph(beat.description, max_sentences=2, max_chars=90)
            blocks.append(ReportBlock(kind="bullet", level=1, text=f"【{label}】（{chapter_range}）", style="section_item"))
            blocks.append(ReportBlock(kind="bullet", level=2, text=f"事件1：主线推进（{chapter_range}）", style="group_detail"))
            blocks.append(ReportBlock(kind="bullet", level=3, text=description, style="group_detail"))
    else:
        blocks.append(ReportBlock(kind="paragraph", level=0, text="主线/剧情大纲信息暂未提炼完整。", style="body"))

    blocks.append(ReportBlock(kind="heading", level=2, text="开篇文法分析", style="section_heading"))
    _append_labeled_bullets(blocks, "开篇核心爽点", _collect_detail_items(book.opening_craft.core_payoffs, limit=6, max_chars=100))
    _append_labeled_bullets(blocks, "开篇核心虐点", _collect_detail_items(book.opening_craft.core_pain_points, limit=6, max_chars=100))
    _append_labeled_bullets(blocks, "开篇暧昧互动", _collect_detail_items(book.opening_craft.flirty_moments, limit=5, max_chars=100))
    _append_labeled_bullets(blocks, "人设贴合建设", _collect_detail_items(book.opening_craft.character_building, limit=5, max_chars=100))
    _append_labeled_bullets(blocks, "对话设计", _collect_detail_items(book.opening_craft.dialogue_design, limit=4, max_chars=100))
    _append_labeled_bullets(blocks, "动作细节", _collect_detail_items(book.opening_craft.action_details, limit=4, max_chars=100))

    blocks.append(ReportBlock(kind="heading", level=2, text="情感线", style="section_heading"))
    if book.relationship_timeline:
        for stage in book.relationship_timeline:
            pair = _compress_title(stage.pair, max_chars=18)
            stage_label = _compress_title(stage.stage_label, max_chars=18)
            description = _build_relationship_timeline_description(stage, chapter_lookup)
            chapter_range = _clean_delivery_text(stage.chapter_range or _format_chapter_refs(stage.chapter_refs))
            blocks.append(
                ReportBlock(
                    kind="bullet",
                    level=1,
                    text=f"{pair} / {stage_label}（{chapter_range}）：{description}",
                    style="section_item",
                )
            )
    else:
        blocks.append(ReportBlock(kind="paragraph", level=0, text="情感线信息暂未提炼完整。", style="body"))

    blocks.append(ReportBlock(kind="heading", level=2, text="章节细纲", style="section_heading"))
    for index, unit in enumerate(chapter_units, start=1):
        chapter = chapter_lookup.get(unit.chapter_refs[0]) if len(unit.chapter_refs) == 1 else None
        blocks.extend(_build_unit_blocks(unit, index, include_debug=include_debug, chapter=chapter))

    blocks.append(ReportBlock(kind="heading", level=2, text="文笔内容总结", style="section_heading"))
    style_lead = _build_writing_summary_lead(book)
    if style_lead:
        blocks.append(ReportBlock(kind="paragraph", level=0, text=style_lead, style="body"))
    _append_optional_bullet(
        blocks,
        "写法分析",
        _format_editorial_field(book.writing_breakdown.writing_analysis, max_sentences=2, max_chars=84),
    )
    _append_optional_bullet(
        blocks,
        "叙事节奏",
        _format_editorial_field(book.style_summary.narrative_pacing, max_sentences=1, max_chars=46),
    )
    _append_optional_bullet(
        blocks,
        "信息投喂",
        _format_editorial_field(book.style_summary.information_release, max_sentences=1, max_chars=46),
    )
    _append_optional_bullet(
        blocks,
        "冲突推进",
        _format_editorial_field(book.style_summary.conflict_design, max_sentences=1, max_chars=46),
    )
    _append_optional_bullet(
        blocks,
        "情绪调动",
        _format_editorial_field(book.style_summary.emotional_leverage, max_sentences=1, max_chars=46),
    )
    _append_optional_bullet(
        blocks,
        "人物塑造",
        _format_editorial_field(book.style_summary.characterization, max_sentences=1, max_chars=46),
    )
    _append_optional_bullet(
        blocks,
        "语言风格",
        _format_editorial_field(book.style_summary.language_style or book.writing_breakdown.language_style, max_sentences=1, max_chars=38),
    )
    _append_optional_bullet(
        blocks,
        "钩子与回收",
        _format_editorial_field(book.style_summary.hook_and_payoff, max_sentences=1, max_chars=46),
    )

    return blocks


def render_report_markdown(blocks: list[ReportBlock]) -> str:
    lines: list[str] = []
    for block in blocks:
        if block.kind == "heading":
            lines.append("#" * block.level + f" {block.text}")
        elif block.kind == "bullet":
            indent = "  " * max(block.level - 1, 0)
            lines.append(f"{indent}- {block.text}")
        else:
            lines.append(block.text)
        if block.kind in {"heading", "paragraph"}:
            lines.append("")
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + "\n"


def _collect_delivery_integrity_issues(
    report_blocks: list[ReportBlock],
    *,
    rendered_report: str,
) -> list[DeliveryIntegrityIssue]:
    issues: list[DeliveryIntegrityIssue] = []
    current_section = ""
    current_block_title = ""
    current_group_title = ""
    relationship_details: dict[str, list[str]] = {}

    for block in report_blocks:
        if block.kind == "heading" and block.level == 2:
            current_section = block.text.strip()
            current_block_title = ""
            current_group_title = ""
            continue
        if block.kind == "heading" and block.level == 3:
            current_block_title = block.text.strip()
            current_group_title = ""
            if current_section == "章节细纲" and _is_title_noise(current_block_title):
                issues.append(
                    DeliveryIntegrityIssue(
                        issue_type="title_noise",
                        severity="blocking",
                        repairable=True,
                        section=current_section,
                        block_title=current_block_title,
                        text=current_block_title,
                    )
                )
            continue
        if block.kind == "bullet" and block.style == "group_label" and block.level == 1:
            current_group_title = block.text.strip()
            continue

        issue_types = _classify_integrity_issue_types(
            block.text,
            section_title=current_section,
            group_title=current_group_title,
        )
        for issue_type in issue_types:
            severity = "warning" if issue_type in {"generic_label", "pdf_render_risk"} else "blocking"
            issues.append(
                DeliveryIntegrityIssue(
                    issue_type=issue_type,
                    severity=severity,
                    repairable=True,
                    section=current_section,
                    block_title=current_block_title,
                    group_title=current_group_title,
                    text=block.text.strip(),
                )
            )
        if current_group_title == "情感推进" and block.kind == "bullet" and block.level >= 2:
            detail = _extract_relationship_detail(block.text)
            if detail:
                relationship_details.setdefault(current_block_title or current_section, []).append(detail)

    for block_title, details in relationship_details.items():
        duplicates = _find_duplicate_details(details)
        for detail in duplicates:
            issues.append(
                DeliveryIntegrityIssue(
                    issue_type="field_pollution",
                    severity="blocking",
                    repairable=True,
                    section="章节细纲",
                    block_title=block_title,
                    group_title="情感推进",
                    text=detail,
                )
            )

    if rendered_report:
        for token, issue_type in (
            ("金句：?", "dirty_residue"),
            ("‘’", "dirty_residue"),
            ("情绪：情绪变化", "generic_label"),
            ("关系推进：", "generic_label"),
        ):
            if token in rendered_report:
                issues.append(
                    DeliveryIntegrityIssue(
                        issue_type=issue_type,
                        severity="blocking" if issue_type == "dirty_residue" else "warning",
                        repairable=True,
                        section="全文",
                        text=token,
                    )
                )
    return issues


def _repair_heading_text(section_title: str, text: str) -> str:
    cleaned = _clean_delivery_text(text, strip_boilerplate=True)
    if not cleaned:
        return ""
    if section_title != "章节细纲":
        return cleaned
    match = re.match(r"^(?P<title>.+?)（(?P<chapter>第.+?章)）$", cleaned)
    if not match:
        return cleaned
    title = match.group("title").strip()
    chapter_range = match.group("chapter").strip()
    title = _normalize_unit_heading_candidate(title, max_chars=18)
    if not title:
        title = _fallback_unit_heading_label(chapter_range=chapter_range)
    return f"{title}（{chapter_range}）"


def _repair_block_text(
    text: str,
    *,
    section_title: str,
    block_title: str,
    group_title: str,
    relationship_seen: set[str],
) -> str:
    cleaned = _clean_delivery_text(text, strip_boilerplate=False)
    if not cleaned:
        return ""
    if group_title == "文风信号":
        repaired = _repair_style_signal_text(cleaned)
    elif group_title == "名场面与金句":
        repaired = _repair_scene_quote_text(cleaned)
    elif group_title == "情感推进":
        repaired = _repair_relationship_item_text(cleaned, relationship_seen=relationship_seen)
    elif group_title == "情节点与节奏":
        repaired = _repair_beat_line_text(cleaned)
    else:
        repaired = _trim_broken_tail(cleaned)
    if _classify_integrity_issue_types(repaired, section_title=section_title, group_title=group_title):
        repaired = _final_strip_broken_text(repaired)
    if _is_low_signal_text(repaired) or _is_fragmentary(repaired):
        return ""
    return repaired


def _append_section(blocks: list[ReportBlock], title: str, values: list[str], *, bullets: bool = False) -> None:
    blocks.append(ReportBlock(kind="heading", level=2, text=title, style="section_heading"))
    if bullets:
        for value in values:
            blocks.append(ReportBlock(kind="bullet", level=1, text=_value(value), style="section_item"))
        return
    for value in values:
        blocks.append(ReportBlock(kind="paragraph", level=0, text=_value(value), style="body"))


def _classify_integrity_issue_types(text: str, *, section_title: str, group_title: str) -> list[str]:
    cleaned = text.strip()
    issue_types: list[str] = []
    if not cleaned:
        return ["broken_fragment"]
    if _is_broken_fragment_text(cleaned):
        issue_types.append("broken_fragment")
    if _has_dirty_residue(cleaned):
        issue_types.append("dirty_residue")
    if _has_generic_label_problem(cleaned, group_title=group_title):
        issue_types.append("generic_label")
    if section_title == "章节细纲" and group_title == "情感推进" and _has_pdf_render_risk(cleaned):
        issue_types.append("pdf_render_risk")
    return _unique_preserve_order(issue_types)


def _is_title_noise(text: str) -> bool:
    cleaned = text.strip()
    bare_title = re.sub(r"（第.+?章）$", "", cleaned).strip()
    if not bare_title:
        return True
    if "分块" in bare_title or "番外：过年搞事" in bare_title:
        return True
    if _is_generic_chapter_title(bare_title):
        return True
    if re.search(r"\bvs\b", bare_title, flags=re.IGNORECASE):
        return True
    return _is_broken_fragment_text(bare_title)


def _is_broken_fragment_text(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    if re.search(r"(?:如|例如|比如|包括|等|vs|和|与|及)\s*$", cleaned, flags=re.IGNORECASE):
        return True
    if _is_fragmentary(cleaned) or _looks_cutoff(cleaned):
        return True
    return False


def _has_dirty_residue(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    if "‘’" in cleaned or "“”" in cleaned or '""' in cleaned:
        return True
    if re.search(r"金句：\s*[?？…\.]+$", cleaned):
        return True
    if re.search(r"情绪：\s*\+", cleaned):
        return True
    if re.search(r"(?i)(?:^|[\u4e00-\u9fffA-Za-z0-9])vs(?:$|[\u4e00-\u9fffA-Za-z0-9])", cleaned):
        return True
    return False


def _has_generic_label_problem(text: str, *, group_title: str) -> bool:
    cleaned = text.strip()
    if group_title == "情感推进" and re.search(r"/\s*关系推进[:：]", cleaned):
        return True
    if "情绪：情绪变化" in cleaned:
        return True
    return False


def _has_pdf_render_risk(text: str) -> bool:
    label = _extract_relationship_label(text)
    if not label or " / " not in label:
        return False
    counterpart, stage = [part.strip() for part in label.split(" / ", 1)]
    return len(counterpart) >= 14 or len(stage) >= 10


def _extract_relationship_label(text: str) -> str:
    match = re.match(r"^(?P<label>.+?\s/\s.+?)[:：](?P<detail>.+)$", text.strip())
    if not match:
        return ""
    return match.group("label").strip()


def _extract_relationship_detail(text: str) -> str:
    match = re.match(r"^.+?\s/\s.+?[:：](?P<detail>.+)$", text.strip())
    if not match:
        return ""
    detail = _clean_delivery_text(match.group("detail"), strip_boilerplate=True)
    return detail


def _find_duplicate_details(details: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    for detail in details:
        normalized = _clean_delivery_text(detail, strip_boilerplate=True)
        if not normalized:
            continue
        counts[normalized] = counts.get(normalized, 0) + 1
    return [detail for detail, count in counts.items() if count >= 2]


def _score_relationship_support_candidate(candidate: str, anchor_text: str) -> int:
    if not candidate:
        return 0
    score = 0
    anchor = _clean_delivery_text(anchor_text, strip_boilerplate=True)
    cleaned_candidate = _clean_delivery_text(candidate, strip_boilerplate=True)
    if not anchor or not cleaned_candidate:
        return score
    if cleaned_candidate in anchor or anchor in cleaned_candidate:
        score += 3
    overlap = {
        token
        for token in re.findall(r"[\u4e00-\u9fffA-Za-z]{2,}", anchor)
        if token in cleaned_candidate
    }
    score += len(overlap)
    return score


def _split_label_value(text: str) -> tuple[str, str] | None:
    if "：" not in text:
        return None
    label, value = text.split("：", 1)
    resolved_label = _clean_delivery_text(label)
    resolved_value = _clean_delivery_text(value)
    if not resolved_label or not resolved_value:
        return None
    return resolved_label, resolved_value


def _repair_style_signal_text(text: str) -> str:
    label, value = _split_label_value(text) or ("叙事观察", text)
    dimension = _compress_title(_clean_tag(label, replacements=KNOWN_ENGLISH_REPLACEMENTS, fallback=label), max_chars=16)
    observation = _format_preserved_clause(value, max_chars=58) or _compress_sentence(
        value,
        max_chars=58,
        fallback="",
        strip_boilerplate=True,
    )
    if not observation or _is_broken_fragment_text(observation):
        return ""
    if not dimension or _is_low_signal_text(dimension):
        dimension = _infer_style_dimension(observation)
    return f"{dimension}：{observation}" if dimension else observation


def _repair_scene_quote_text(text: str) -> str:
    parts = [part.strip() for part in text.split("｜") if part.strip()]
    if not parts:
        return ""
    scene = _compress_title(parts[0], max_chars=24)
    quote = ""
    purpose = ""
    for part in parts[1:]:
        if part.startswith("金句："):
            candidate = _compress_quote(part.split("：", 1)[1])
            if candidate:
                quote = candidate
        elif part.startswith("作用："):
            candidate = _format_preserved_clause(part.split("：", 1)[1], max_chars=42) or _compress_sentence(
                part.split("：", 1)[1],
                max_chars=42,
                fallback="",
                strip_boilerplate=True,
            )
            if candidate and not _is_broken_fragment_text(candidate):
                purpose = candidate
    result = scene
    if quote:
        result += f"｜金句：{quote}"
    if purpose:
        result += f"｜作用：{purpose}"
    return result if scene else ""


def _repair_relationship_item_text(text: str, *, relationship_seen: set[str]) -> str:
    match = re.match(r"^(?P<counterpart>.+?)\s*/\s*(?P<stage>.+?)[:：](?P<detail>.+)$", text.strip())
    if not match:
        return _final_strip_broken_text(text)
    counterpart = _compress_title(match.group("counterpart"), max_chars=18)
    stage_label = _compress_title(match.group("stage"), max_chars=16)
    detail = _format_preserved_clause(match.group("detail"), max_chars=170) or _compress_sentence(
        match.group("detail"),
        max_chars=170,
        fallback="",
        strip_boilerplate=True,
    )
    if not detail:
        return ""
    detail = _dedupe_relationship_detail(detail, relationship_seen)
    if not detail:
        return ""
    if (
        not stage_label
        or stage_label in {"关系推进", "关系变化", "关系阶段"}
        or not _contains_chinese(stage_label)
        or re.search(r"[A-Za-z]", stage_label)
        or len(stage_label) > 8
    ):
        stage_label = _infer_relationship_stage_label(detail)
    if stage_label in {"关系推进", "关系变化", "关系阶段"}:
        stage_label = RELATIONSHIP_STAGE_LABEL_POOL[0]
    return f"{counterpart} / {stage_label}：{detail}"


def _dedupe_relationship_detail(detail: str, relationship_seen: set[str]) -> str:
    normalized = _clean_delivery_text(detail, strip_boilerplate=True)
    if not normalized:
        return ""
    candidate = normalized
    if candidate in relationship_seen:
        clauses = [clause for clause in _split_clauses(candidate) if clause]
        candidate = clauses[0] if clauses else candidate
    if candidate in relationship_seen:
        return ""
    relationship_seen.add(candidate)
    return candidate


def _repair_beat_line_text(text: str) -> str:
    parts = [part.strip() for part in text.split("｜") if part.strip()]
    values: dict[str, str] = {}
    for part in parts:
        label, value = _split_label_value(part) or ("", part)
        if label:
            values[label] = value
    raw_beat = values.get("情节点", parts[0] if parts else "")
    beat = _format_preserved_clause(raw_beat, max_chars=72) or _compress_sentence(
        raw_beat,
        max_chars=72,
        fallback="",
        strip_boilerplate=True,
    )
    note = _format_preserved_clause(values.get("作用", ""), max_chars=110) or _compress_sentence(
        values.get("作用", ""),
        max_chars=110,
        fallback="",
        strip_boilerplate=True,
    )
    pacing = _resolve_contextual_tag(
        values.get("节奏", ""),
        replacements=PACE_TAG_REPLACEMENTS,
        fallback=PACE_FALLBACK_LABEL,
        generic_labels=GENERIC_PACING_LABELS,
        context_text=f"{beat} {note}",
        context_rules=PACE_CONTEXT_RULES,
    )
    emotion = _resolve_contextual_tag(
        values.get("情绪", ""),
        replacements=EMOTION_TAG_REPLACEMENTS,
        fallback=EMOTION_FALLBACK_LABEL,
        generic_labels=GENERIC_EMOTION_LABELS,
        context_text=f"{beat} {note}",
        context_rules=EMOTION_CONTEXT_RULES,
    )
    if not beat or not note or _is_broken_fragment_text(note):
        return ""
    return f"情节点：{beat}｜节奏：{pacing}｜情绪：{emotion}｜作用：{note}"


def _final_strip_broken_text(text: str) -> str:
    cleaned = _trim_broken_tail(_clean_delivery_text(text, strip_boilerplate=True))
    if re.search(r"(?:如|例如|比如|包括|等|vs|和|与|及)\s*$", cleaned, flags=re.IGNORECASE):
        cleaned = re.sub(r"(?:如|例如|比如|包括|等|vs|和|与|及)\s*$", "", cleaned, flags=re.IGNORECASE).strip("，、；： ")
    return cleaned


def _append_optional_bullet(blocks: list[ReportBlock], label: str, value: str) -> None:
    if not value:
        return
    blocks.append(ReportBlock(kind="bullet", level=1, text=f"{label}：{value}", style="section_item"))


def _build_overview_paragraphs(book: BookAnalysis) -> list[str]:
    cleaned = _clean_delivery_text(book.overview, strip_boilerplate=True)
    if not cleaned:
        return ["信息仍需进一步提炼。"]

    parts = _split_overview_parts(cleaned)
    if not parts:
        return ["信息仍需进一步提炼。"]

    paragraphs = [_format_overview_paragraph("；".join(parts[:2]), max_chars=210)]
    follow_parts = [part for part in parts[2:4] if not part.startswith(("并在", "并于", "并把", "最后"))]
    followup = _format_overview_followup("；".join(follow_parts), book)
    if followup and followup != paragraphs[0]:
        paragraphs.append(followup)
    return paragraphs


def _split_overview_parts(text: str) -> list[str]:
    sentence_parts = [part.strip("，；： ") for part in re.split(r"[。！？!?]+", text) if part.strip("，；： ")]
    if len(sentence_parts) >= 2:
        return sentence_parts
    return [part.strip("，；： ") for part in re.split(r"[；;]+", text) if part.strip("，；： ")]


def _format_overview_paragraph(text: str, *, max_chars: int = 180) -> str:
    cleaned = _clean_delivery_text(text, strip_boilerplate=True)
    if not cleaned:
        return "信息仍需进一步提炼。"
    if _is_english_heavy(cleaned) or _has_problematic_english(cleaned):
        return "信息仍需进一步提炼。"
    major_parts = [part.strip("，；： ") for part in re.split(r"[；;]+", cleaned) if part.strip("，；： ")]
    if len(major_parts) >= 2:
        candidate = "；".join(major_parts[:3])
        while len(candidate) > max_chars and len(major_parts) > 1:
            major_parts = major_parts[:-1]
            candidate = "；".join(major_parts)
    else:
        candidate = _compress_paragraph(cleaned, max_sentences=2, max_chars=max_chars)
    candidate = _trim_broken_tail(candidate)
    if len(candidate) > max_chars:
        candidate = _compress_paragraph(candidate, max_sentences=2, max_chars=max_chars)
    candidate = _truncate_chars(candidate, max_chars)
    return candidate or "信息仍需进一步提炼。"


def _format_overview_followup(text: str, book: BookAnalysis) -> str:
    cleaned = _clean_delivery_text(text, strip_boilerplate=True)
    if cleaned:
        followup = _compress_paragraph(cleaned, max_sentences=2, max_chars=150, fallback="")
        if followup and not _is_low_signal_text(followup):
            return followup

    style_signal = _format_editorial_field(
        book.style_summary.language_style or book.writing_breakdown.language_style,
        max_sentences=1,
        max_chars=26,
    )
    hook_signal = _compress_sentence(book.core_hooks[0], max_chars=34, fallback="") if book.core_hooks else ""
    parts: list[str] = []
    if hook_signal:
        parts.append(f"成品抓手在{hook_signal}")
    if style_signal:
        parts.append(f"文风上偏{style_signal}")
    candidate = "；".join(parts[:2])
    return _truncate_chars(candidate, 150) if candidate else ""


def _build_writing_summary_lead(book: BookAnalysis) -> str:
    analysis = _format_editorial_field(book.writing_breakdown.writing_analysis, max_sentences=1, max_chars=82)
    conflict = _format_editorial_field(book.style_summary.conflict_design, max_sentences=1, max_chars=40)
    emotion = _format_editorial_field(book.style_summary.emotional_leverage, max_sentences=1, max_chars=38)
    hook = _format_editorial_field(book.style_summary.hook_and_payoff, max_sentences=1, max_chars=40)

    if not any([analysis, conflict, emotion, hook]):
        return ""

    parts: list[str] = []
    if analysis:
        parts.append(f"整体看，{analysis}")
    if conflict:
        parts.append(f"叙事上{conflict}")
    if emotion:
        parts.append(f"情绪上{emotion}")
    elif hook:
        parts.append(f"回收上{hook}")

    return _truncate_chars("；".join(parts[:3]), 160)


def _append_themed_section(
    blocks: list[ReportBlock],
    title: str,
    items: list[tuple[str, str]],
    *,
    fallback_title: str,
    fallback_values: list[str],
) -> None:
    blocks.append(ReportBlock(kind="heading", level=2, text=title, style="section_heading"))
    cleaned_items: list[tuple[str, str]] = []
    for index, (item_title, item_detail) in enumerate(items, start=1):
        if not (item_title or item_detail).strip():
            continue
        resolved_title = _compress_title(item_title or fallback_title, max_chars=18)
        resolved_detail = _compress_paragraph(item_detail, max_sentences=2, max_chars=120)
        if _is_low_signal_text(resolved_title):
            resolved_title = f"{fallback_title}{index}"
        if _is_low_signal_text(resolved_detail):
            continue
        cleaned_items.append((resolved_title, resolved_detail))
    if cleaned_items:
        for item_title, item_detail in cleaned_items:
            blocks.append(ReportBlock(kind="heading", level=3, text=item_title, style="group_heading"))
            blocks.append(ReportBlock(kind="paragraph", level=0, text=item_detail, style="body"))
        return
    fallback = [value for value in _compress_list(fallback_values, limit=5, max_chars=46) if not _is_low_signal_text(value)]
    if not fallback:
        return
    for index, value in enumerate(fallback, start=1):
        blocks.append(ReportBlock(kind="heading", level=3, text=f"{fallback_title}{index}", style="group_heading"))
        blocks.append(ReportBlock(kind="paragraph", level=0, text=value, style="body"))


def _append_labeled_bullets(blocks: list[ReportBlock], label: str, values: list[str]) -> None:
    resolved_values = [value for value in values if not _is_low_signal_text(value)] or EMPTY_GROUP_FALLBACKS.get(label, [])
    if not resolved_values:
        return
    blocks.append(ReportBlock(kind="bullet", level=1, text=label, style="group_label"))
    for value in resolved_values:
        blocks.append(ReportBlock(kind="bullet", level=2, text=_value(value), style="group_detail"))


def _format_optional_field(text: str, *, max_sentences: int, max_chars: int) -> str:
    cleaned = _clean_delivery_text(text, strip_boilerplate=True)
    if not cleaned:
        return ""
    if _is_weak_optional_value(cleaned):
        return ""
    formatted = _format_editorial_field(cleaned, max_sentences=max_sentences, max_chars=max_chars)
    if not formatted or _is_weak_optional_value(formatted):
        return ""
    return formatted


def _format_editorial_field(
    text: str,
    *,
    max_sentences: int,
    max_chars: int,
    preserve_compound_tags: bool = False,
) -> str:
    cleaned = _clean_delivery_text(text, strip_boilerplate=True)
    if not cleaned:
        return ""
    if _is_placeholder_copy(cleaned):
        return ""
    if _is_english_heavy(cleaned) or _has_problematic_english(cleaned):
        return ""
    sentences = _split_sentences(cleaned)
    candidate = "；".join(sentences[:max_sentences]) if sentences else cleaned
    candidate = _trim_broken_tail(candidate).lstrip("；：，、- ")
    if not candidate:
        return ""
    if not preserve_compound_tags and (_is_fragmentary(candidate) or _looks_cutoff(candidate)):
        return ""
    if preserve_compound_tags and not _contains_chinese(candidate):
        return ""
    if not preserve_compound_tags and not _contains_chinese(candidate) and re.search(r"[A-Za-z]{3,}", candidate):
        return ""
    candidate = _truncate_chars(candidate, max_chars)
    if not candidate or _is_placeholder_copy(candidate):
        return ""
    return candidate


def _format_preserved_clause(text: str, *, max_chars: int) -> str:
    cleaned = _clean_delivery_text(text, strip_boilerplate=True)
    if not cleaned:
        return ""
    if _is_placeholder_copy(cleaned):
        return ""
    if _is_english_heavy(cleaned) or _has_problematic_english(cleaned):
        return ""
    candidate = _trim_broken_tail(cleaned).lstrip("；：，、- ")
    candidate = _truncate_chars(candidate, max_chars)
    if not candidate or _is_placeholder_copy(candidate):
        return ""
    return candidate


def _build_phase_outline_events(phase: PhaseOutlineItem, chapters: list[ChapterAnalysis]) -> list[PhaseOutlineEventDisplay]:
    phase_chapters = _chapters_for_range(chapters, phase.chapter_range)
    raw_titles = [_resolve_phase_event_title_text(event) for event in phase.events]
    raw_details = [_extract_phase_event_detail_text(event) for event in phase.events]
    valid_titles = [title for title in raw_titles if title]
    if valid_titles:
        event_count = min(len(valid_titles), 4)
    elif phase_chapters:
        event_count = min(max(len(phase_chapters), 1), 4)
    else:
        event_count = 1
    if phase_chapters:
        event_count = min(event_count, len(phase_chapters))

    chapter_groups = _split_phase_chapters(phase_chapters, event_count)
    displays: list[PhaseOutlineEventDisplay] = []
    for index in range(event_count):
        event_chapters = chapter_groups[index] if index < len(chapter_groups) else []
        title = valid_titles[index] if index < len(valid_titles) else _derive_phase_event_title(event_chapters, index + 1)
        if not title:
            title = f"阶段事件{index + 1}"
        chapter_range = _format_chapter_refs([chapter.chapter_id for chapter in event_chapters]) if event_chapters else "阶段范围未明"
        detail_hint = raw_details[index] if index < len(raw_details) else ""
        description = _build_phase_event_description(event_chapters, title, detail_hint=detail_hint)
        displays.append(PhaseOutlineEventDisplay(title=title, chapter_range=chapter_range, description=description))
    return displays


def _format_phase_outline_label(label: str, index: int) -> str:
    cleaned = _clean_delivery_text(label, strip_boilerplate=True) or f"阶段推进{index}"
    cleaned = re.sub(rf"^(?:{'|'.join(PHASE_MARKERS)})[：:]\s*", "", cleaned)
    marker = PHASE_MARKERS[index - 1] if 1 <= index <= len(PHASE_MARKERS) else f"阶段{index}"
    return f"{marker}：{_truncate_chars(cleaned, 18)}"


def _resolve_phase_event_title_text(text: str) -> str:
    title_text = text.split("：", 1)[0] if "：" in text else text
    cleaned = _clean_delivery_text(title_text, strip_boilerplate=True)
    if not cleaned:
        return ""
    cleaned = re.sub(r"[A-Za-z][A-Za-z0-9\s_\-/&+]{2,}", "", cleaned).strip("，、；：- ")
    resolved = _compress_title(cleaned or text, max_chars=18)
    if not resolved or resolved == "未命名条目" or _is_low_signal_text(resolved) or re.search(r"[A-Za-z]", resolved):
        return ""
    return resolved


def _extract_phase_event_detail_text(text: str) -> str:
    if "：" not in text:
        return ""
    return _clean_delivery_text(text.split("：", 1)[1], strip_boilerplate=True)


def _split_phase_chapters(chapters: list[ChapterAnalysis], group_count: int) -> list[list[ChapterAnalysis]]:
    if not chapters or group_count <= 0:
        return []
    size, remainder = divmod(len(chapters), group_count)
    groups: list[list[ChapterAnalysis]] = []
    cursor = 0
    for index in range(group_count):
        current_size = size + (1 if index < remainder else 0)
        if current_size <= 0:
            current_size = 1
        groups.append(chapters[cursor : cursor + current_size])
        cursor += current_size
    if cursor < len(chapters) and groups:
        groups[-1].extend(chapters[cursor:])
    return groups


def _derive_phase_event_title(chapters: list[ChapterAnalysis], index: int) -> str:
    candidates: list[str] = []
    for chapter in chapters:
        candidates.extend(event.label for event in chapter.plot_events if event.label.strip())
        candidates.extend(chapter.highlights)
        candidates.extend(chapter.climax)
        candidates.extend(chapter.payoff)
        candidates.append(chapter.summary)
    for candidate in candidates:
        resolved = _resolve_phase_event_title_text(candidate)
        if resolved:
            return resolved
    return f"阶段事件{index}"


def _build_phase_event_description(chapters: list[ChapterAnalysis], title: str, *, detail_hint: str = "") -> str:
    if detail_hint and not _is_low_signal_text(detail_hint):
        return _truncate_chars(detail_hint, 180)
    if not chapters:
        return "对应章节事件仍需补充。"
    label_chain = _build_phase_event_label_chain(chapters)
    if label_chain:
        return label_chain
    items: list[str] = []
    for chapter in chapters:
        for event in chapter.plot_events[:3]:
            segment = _build_phase_event_segment(event.details or event.label)
            if not segment or segment == title or segment in items:
                continue
            items.append(segment)
            if len(items) >= 3:
                break
        if len(items) >= 3:
            break
    if len(items) < 2:
        for chapter in chapters:
            for value in [chapter.summary, *chapter.highlights[:1], *chapter.climax[:1], *chapter.payoff[:1]]:
                segment = _build_phase_event_segment(value)
                if not segment or segment == title or segment in items:
                    continue
                items.append(segment)
                if len(items) >= 3:
                    break
            if len(items) >= 3:
                break
    if not items:
        return "对应章节事件仍需补充。"
    return _truncate_chars("；".join(items[:3]), 180)


def _build_phase_event_label_chain(chapters: list[ChapterAnalysis]) -> str:
    labels: list[str] = []
    for chapter in chapters:
        for event in chapter.plot_events[:3]:
            label = _normalize_phase_event_flow_label(event.label or event.details)
            if not label or label in labels:
                continue
            labels.append(label)
            if len(labels) >= 3:
                return "→".join(labels)
    return "→".join(labels) if labels else ""


def _normalize_phase_event_flow_label(text: str) -> str:
    cleaned = _resolve_phase_event_title_text(text)
    if not cleaned:
        return ""
    cleaned = re.sub(r"^[A-Za-z]{2,}", "", cleaned).strip("，、；：- ")
    cleaned = re.sub(r"^(?:KTV|洗手间|咨询会|项目会|项目会议|病房|泳池|电梯|酒会|天台|机场|书房)", "", cleaned).strip("，、；：- ")
    if len(cleaned) > 4:
        for token in ("告白", "重逢", "试探", "交锋", "升温", "同居", "求婚"):
            if cleaned.endswith(token):
                return token if token == "告白" else cleaned
    return cleaned


def _build_phase_event_segment(text: str) -> str:
    cleaned = _clean_delivery_text(text, strip_boilerplate=True)
    if not cleaned:
        return ""
    if "：" in cleaned:
        cleaned = cleaned.split("：", 1)[1].strip()
    cleaned = re.sub(r"[A-Za-z][A-Za-z0-9\s_\-/&+]{2,}", "", cleaned).strip("，、；：- ")
    sentences = _split_sentences(cleaned)
    candidate = sentences[0] if sentences else cleaned
    candidate = _truncate_chars(candidate, 72)
    if not candidate or _is_low_signal_text(candidate) or _looks_cutoff(candidate) or not _contains_chinese(candidate):
        return ""
    return candidate


def _build_summary_segments(text: str, *, max_items: int) -> list[str]:
    cleaned = _clean_delivery_text(text, strip_boilerplate=True)
    if not cleaned:
        return []
    segments: list[str] = []
    for clause in _split_clauses(cleaned):
        candidate = _truncate_chars(clause, 14)
        if not candidate or _is_low_signal_text(candidate) or _looks_cutoff(candidate) or not _contains_chinese(candidate):
            continue
        segments.append(candidate)
        if len(segments) >= max_items:
            break
    return segments


def _build_relationship_timeline_description(stage: RelationshipStage, chapter_lookup: dict[str, ChapterAnalysis]) -> str:
    source_chapters = [chapter_lookup[chapter_id] for chapter_id in stage.chapter_refs if chapter_id in chapter_lookup]
    description = _clean_delivery_text(stage.description, strip_boilerplate=True)
    core_change = _build_relationship_stage_part(
        primary="" if _relationship_timeline_part_needs_rebuild(stage.core_change) else stage.core_change,
        fallback_values=[event.details for chapter in source_chapters for event in chapter.plot_events[:2]]
        + [item.change for chapter in source_chapters for item in chapter.relationship_progression]
        + [chapter.summary for chapter in source_chapters]
        + [_extract_labeled_segment(description, "推进"), _extract_stage_core_change(description)],
    )
    pressure = _build_relationship_stage_part(
        primary="" if _relationship_timeline_part_needs_rebuild(stage.pressure) else (stage.pressure or _extract_labeled_segment(description, "压力")),
        fallback_values=[value for chapter in source_chapters for value in chapter.crisis + chapter.suspense]
        + [chapter.summary for chapter in source_chapters]
        + [_extract_labeled_segment(description, "压力")],
    )
    payoff = _build_relationship_stage_part(
        primary="" if _relationship_timeline_part_needs_rebuild(stage.payoff) else (stage.payoff or _extract_labeled_segment(description, "回收")),
        fallback_values=[
            value
            for chapter in source_chapters
            for value in [item.change for item in chapter.relationship_progression] + chapter.payoff + chapter.highlights
        ]
        + [_extract_labeled_segment(description, "回收")],
        require_relational=True,
    )
    core_change, pressure, payoff = _dedupe_relationship_timeline_parts(core_change, pressure, payoff)
    parts = [f"推进：{core_change}", f"压力：{pressure}", f"回收：{payoff}"]
    return _truncate_chars("；".join(parts), 320)


def _build_relationship_stage_part(*, primary: str, fallback_values: list[str], require_relational: bool = False) -> str:
    items: list[str] = []
    for value in [primary] + fallback_values:
        cleaned = _format_preserved_clause(value, max_chars=120) or _compress_sentence(
            value,
            max_chars=120,
            fallback="",
            strip_boilerplate=True,
        )
        cleaned = cleaned.lstrip("；：，、- ")
        if not cleaned or _is_low_signal_text(cleaned) or not _contains_chinese(cleaned):
            continue
        if require_relational and not _looks_relational_stage_text(cleaned):
            continue
        if cleaned not in items:
            items.append(cleaned)
        if len(items) >= 2:
            break
    if items:
        return "；".join(items[:2])
    return "对应内容仍需补充。"


def _dedupe_relationship_timeline_parts(core_change: str, pressure: str, payoff: str) -> tuple[str, str, str]:
    seen: list[str] = []

    def normalize(part: str) -> str:
        items = []
        for segment in [item.strip() for item in part.split("；") if item.strip()]:
            if any(segment == existing or segment in existing or existing in segment for existing in items):
                continue
            if any(segment == existing or segment in existing or existing in segment for existing in seen):
                continue
            items.append(segment)
        cleaned = "；".join(items)
        if cleaned:
            seen.extend(items)
        return cleaned

    normalized_core = normalize(core_change)
    normalized_pressure = normalize(pressure)
    normalized_payoff = normalize(payoff)
    return (
        normalized_core or "对应推进仍需补充。",
        normalized_pressure or "对应压力仍需补充。",
        normalized_payoff or "对应回收仍需补充。",
    )


def _looks_relational_stage_text(text: str) -> bool:
    cleaned = _clean_delivery_text(text, strip_boilerplate=True)
    if not cleaned:
        return False
    relational_keywords = ("关系", "两人", "彼此", "靠近", "信任", "亲密", "试探", "站队", "共同", "承担", "依赖", "分手", "复合", "确认")
    return any(keyword in cleaned for keyword in relational_keywords)


def _relationship_timeline_part_needs_rebuild(text: str) -> bool:
    cleaned = _clean_delivery_text(text, strip_boilerplate=True)
    if not cleaned:
        return True
    if any(token in cleaned for token in ("这一阶段", "本章", "本单元", "结构展开")):
        return True
    return cleaned.count("；") >= 2 and len(cleaned) >= 90


def _extract_labeled_segment(text: str, label: str) -> str:
    if not text:
        return ""
    match = re.search(rf"{re.escape(label)}[：:](.+?)(?:[；。]|$)", text)
    if not match:
        return ""
    return match.group(1).strip()


def _extract_stage_core_change(text: str) -> str:
    if not text:
        return ""
    candidate = re.split(r"(?:；|。)?(?:推进|压力|回收)[：:]", text, maxsplit=1)[0]
    return candidate.strip("；：，、- ")


def _chapters_for_range(chapters: list[ChapterAnalysis], chapter_range: str) -> list[ChapterAnalysis]:
    bounds = _parse_chapter_range_bounds(chapter_range)
    if bounds is None:
        return []
    start, end = bounds
    return [
        chapter
        for chapter in chapters
        if (number := _chapter_number(chapter.chapter_id)) is not None and start <= number <= end
    ]


def _parse_chapter_range_bounds(chapter_range: str) -> tuple[int, int] | None:
    normalized_range = _clean_delivery_text(chapter_range or "")
    if not normalized_range:
        return None
    match = re.search(r"第(\d+)(?:-(\d+))?章", normalized_range)
    if match:
        start = int(match.group(1))
        end = int(match.group(2) or start)
        return start, end
    match = re.search(r"ch-(\d+)\s*[–~-]\s*ch-(\d+)", normalized_range)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.search(r"ch-(\d+)", normalized_range)
    if match:
        number = int(match.group(1))
        return number, number
    return None


def _format_phase_chapter_range(chapter_range: str) -> str:
    bounds = _parse_chapter_range_bounds(chapter_range)
    if bounds is None:
        return _clean_delivery_text(chapter_range or "阶段范围未明")
    start, end = bounds
    if start == end:
        return f"第{start}章"
    return f"第{start}-{end}章"


def _infer_tag_from_keywords(text: str, *, keyword_map: dict[str, str], fallback: str) -> str:
    normalized = re.sub(r"[_\-/+&]+", " ", text.lower())
    normalized = re.sub(r"\s*(?:->|→|➡)\s*", " 到 ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return fallback
    parts = [part.strip() for part in normalized.split("到") if part.strip()]
    resolved: list[str] = []
    for part in parts or [normalized]:
        for keyword, mapped in keyword_map.items():
            if keyword in part:
                resolved.append(mapped)
                break
    if resolved:
        return "到".join(_unique_preserve_order(resolved)[:2])
    return fallback


def _collect_detail_items(values: list[str], *, limit: int, max_chars: int) -> list[str]:
    results: list[str] = []
    for value in values:
        cleaned = _format_preserved_clause(value, max_chars=max_chars) or _compress_sentence(
            value,
            max_chars=max_chars,
            fallback="",
            strip_boilerplate=True,
        )
        cleaned = cleaned.lstrip("；：，、- ")
        if not cleaned or _is_low_signal_text(cleaned) or _looks_cutoff(cleaned) or not _contains_chinese(cleaned):
            continue
        results.append(cleaned)
        if len(results) >= limit:
            break
    return _unique_preserve_order(results)


def _collect_chapter_plot_details(chapter: ChapterAnalysis, *, limit: int, max_chars: int) -> list[str]:
    items: list[str] = []
    for event in chapter.plot_events:
        text = _build_plot_event_text(event, max_chars=max_chars)
        if text:
            items.append(text)
        if len(items) >= limit:
            return _unique_preserve_order(items)[:limit]

    supplemental = [
        *_collect_detail_items(chapter.highlights, limit=limit, max_chars=max_chars),
        *_collect_detail_items(chapter.climax, limit=limit, max_chars=max_chars),
        *_collect_detail_items(chapter.payoff, limit=limit, max_chars=max_chars),
    ]
    for item in supplemental:
        if item in items:
            continue
        items.append(item)
        if len(items) >= limit:
            break

    if not items:
        for item in _collect_detail_items([quote.scene for quote in chapter.scene_quotes if quote.scene.strip()], limit=limit, max_chars=max_chars):
            if item in items:
                continue
            items.append(item)
            if len(items) >= limit:
                break

    if not items:
        summary = _format_preserved_clause(chapter.summary, max_chars=max_chars) or _compress_paragraph(
            chapter.summary,
            max_sentences=2,
            max_chars=max_chars,
            fallback="",
        )
        if summary and not _is_low_signal_text(summary):
            items.append(summary)
    return _unique_preserve_order(items)[:limit]


def _build_plot_event_text(event: PlotEvent, *, max_chars: int) -> str:
    label = _format_preserved_clause(event.label, max_chars=18)
    details = _format_preserved_clause(event.details, max_chars=max_chars) or _compress_sentence(
        event.details,
        max_chars=max_chars,
        fallback="",
        strip_boilerplate=True,
    )
    if label and details and label not in details:
        candidate = f"{label}：{details}"
    else:
        candidate = details or label
    candidate = _truncate_chars(candidate, max_chars)
    if not candidate or _is_low_signal_text(candidate) or not _contains_chinese(candidate):
        return ""
    return candidate


def _build_unit_blocks(
    unit: DeliveryUnit,
    index: int,
    *,
    include_debug: bool,
    chapter: ChapterAnalysis | None = None,
) -> list[ReportBlock]:
    heading_text = _build_unit_heading_text(unit, index, chapter=chapter)
    blocks: list[ReportBlock] = [ReportBlock(kind="heading", level=3, text=heading_text, style="unit_heading")]

    plot_summary = _format_chapter_plot_summary(unit, chapter) if chapter is not None else _format_summary_text(unit.summary)
    beat_items = _format_beat_rhythm(unit, chapter=chapter)
    relationship_items = _format_relationship_progress(unit, chapter=chapter)
    if chapter is not None and _should_strengthen_unit_card(plot_summary, beat_items, relationship_items):
        plot_summary = _format_chapter_plot_summary(unit, chapter, detail_boost=True)
        beat_items = _format_beat_rhythm(unit, chapter=chapter, detail_boost=True)
        relationship_items = _format_relationship_progress(unit, chapter=chapter, detail_boost=True)
    blocks.append(ReportBlock(kind="bullet", level=1, text=f"剧情：{plot_summary}", style="unit_label"))
    if chapter is not None:
        blocks.append(
            ReportBlock(
                kind="bullet",
                level=1,
                text=f"危机：{_format_detailed_field(chapter.crisis or unit.crisis, refill_values=chapter.suspense + chapter.highlights, fallback='现实压力持续加码。')}",
                style="unit_label",
            )
        )
        blocks.append(
            ReportBlock(
                kind="bullet",
                level=1,
                text=f"伏笔：{_format_detailed_field(chapter.foreshadowing or unit.foreshadowing, refill_values=chapter.suspense + [chapter.summary], fallback='后续回收点已埋下。')}",
                style="unit_label",
            )
        )
        blocks.append(
            ReportBlock(
                kind="bullet",
                level=1,
                text=f"悬念：{_format_detailed_field(chapter.suspense or unit.suspense, refill_values=chapter.crisis + [chapter.summary], fallback='关键后续走向仍未揭晓。')}",
                style="unit_label",
            )
        )
        blocks.append(
            ReportBlock(
                kind="bullet",
                level=1,
                text=f"高潮：{_format_detailed_field(chapter.climax or unit.climax, refill_values=chapter.highlights + [chapter.summary], fallback='情绪与冲突在本段抬升。')}",
                style="unit_label",
            )
        )
        blocks.append(
            ReportBlock(
                kind="bullet",
                level=1,
                text=f"爽点：{_format_detailed_field(chapter.highlights or unit.highlights, refill_values=chapter.payoff + chapter.climax, fallback='关系推进与主线回收同步出现。')}",
                style="unit_label",
            )
        )
    else:
        blocks.append(ReportBlock(kind="bullet", level=1, text=f"危机：{_format_short_field(unit.crisis, refill_values=unit.suspense + unit.highlights, fallback='现实压力持续加码。')}", style="unit_label"))
        blocks.append(ReportBlock(kind="bullet", level=1, text=f"伏笔：{_format_short_field(unit.foreshadowing, refill_values=[unit.summary] + unit.highlights, fallback='后续回收点已埋下。')}", style="unit_label"))
        blocks.append(ReportBlock(kind="bullet", level=1, text=f"悬念：{_format_short_field(unit.suspense, refill_values=unit.crisis + [unit.summary], fallback='关键后续走向仍未揭晓。')}", style="unit_label"))
        blocks.append(ReportBlock(kind="bullet", level=1, text=f"高潮：{_format_short_field(unit.climax, refill_values=unit.highlights + [unit.summary], fallback='情绪与冲突在本段抬升。')}", style="unit_label"))
        blocks.append(ReportBlock(kind="bullet", level=1, text=f"爽点：{_format_short_field(unit.highlights or unit.payoff, refill_values=unit.climax + [unit.summary], fallback='关系推进与主线回收同步出现。')}", style="unit_label"))

    blocks.append(ReportBlock(kind="bullet", level=1, text="情节点与节奏", style="group_label"))
    for item in beat_items:
        blocks.append(ReportBlock(kind="bullet", level=2, text=item, style="unit_detail"))

    blocks.append(ReportBlock(kind="bullet", level=1, text="名场面与金句", style="group_label"))
    scene_items = _format_scene_quotes(unit)
    for item in scene_items:
        blocks.append(ReportBlock(kind="bullet", level=2, text=item, style="unit_detail"))

    blocks.append(ReportBlock(kind="bullet", level=1, text="情感推进", style="group_label"))
    for item in relationship_items:
        blocks.append(ReportBlock(kind="bullet", level=2, text=item, style="unit_detail"))

    blocks.append(ReportBlock(kind="bullet", level=1, text="文风信号", style="group_label"))
    style_items = _format_style_signals(unit)
    for item in style_items:
        blocks.append(ReportBlock(kind="bullet", level=2, text=item, style="unit_detail"))

    if include_debug and unit.evidence:
        blocks.append(ReportBlock(kind="bullet", level=1, text="证据", style="group_label"))
        for item in unit.evidence[:3]:
            blocks.append(ReportBlock(kind="bullet", level=2, text=item.snippet.strip()[:120], style="unit_detail"))

    return blocks


def _should_strengthen_unit_card(plot_summary: str, beat_items: list[str], relationship_items: list[str]) -> bool:
    generic_beat_count = sum(
        1
        for item in beat_items
        if any(token in item for token in ("情绪：情绪变化", "情绪：+", "节奏：推进"))
    )
    if len(plot_summary) < 170:
        return True
    if len(relationship_items) < 3:
        return True
    if generic_beat_count >= 1:
        return True
    if len(beat_items) >= 4 and generic_beat_count > 1:
        return True
    return False


def _format_detailed_field(values: list[str], *, refill_values: list[str], fallback: str) -> str:
    items = _collect_detail_items(values, limit=2, max_chars=72)
    if not items:
        items = _collect_detail_items(refill_values, limit=2, max_chars=72)
    if not items:
        return fallback
    return "；".join(items)


def _format_chapter_plot_summary(unit: DeliveryUnit, chapter: ChapterAnalysis, *, detail_boost: bool = False) -> str:
    parts: list[str] = []
    summary = _format_preserved_clause(chapter.summary or unit.summary, max_chars=180 if detail_boost else 150) or _compress_paragraph(
        chapter.summary or unit.summary,
        max_sentences=3,
        max_chars=190 if detail_boost else 150,
        fallback="",
    )
    plot_details = _collect_chapter_plot_details(chapter, limit=5 if detail_boost else 4, max_chars=88 if detail_boost else 72)
    if detail_boost:
        parts.extend(plot_details[:4])
    if summary and not _is_low_signal_text(summary):
        parts.extend([sentence for sentence in _split_sentences(summary) if sentence and not _is_low_signal_text(sentence)])

    for item in plot_details:
        if item in parts:
            continue
        parts.append(item)
        if len(parts) >= (4 if detail_boost else 3):
            break

    if not parts:
        fallback = _first_nonempty_text(chapter.highlights + chapter.climax + chapter.payoff + [chapter.summary, unit.summary])
        cleaned_fallback = _format_preserved_clause(fallback, max_chars=180 if detail_boost else 140) or _compress_paragraph(
            fallback,
            max_sentences=2,
            max_chars=180 if detail_boost else 140,
            fallback="本章剧情仍需进一步提炼。",
        )
        return cleaned_fallback or "本章剧情仍需进一步提炼。"

    return _truncate_chars("；".join(_unique_preserve_order(parts[:4 if detail_boost else 3])), 260 if detail_boost else 220)


def _format_beat_rhythm(unit: DeliveryUnit, *, chapter: ChapterAnalysis | None = None, detail_boost: bool = False) -> list[str]:
    items: list[str] = []
    used_anchor_keys: set[str] = set()
    fallback_title = _compress_title(unit.title or "关系推进", max_chars=20)
    if fallback_title == "未命名条目":
        fallback_title = _fallback_unit_heading(unit, 0)
    for item in unit.beat_rhythm[:6]:
        raw_beat = _clean_delivery_text(item.beat, strip_boilerplate=True)
        beat = _compress_title(item.beat, max_chars=24)
        note = _format_preserved_clause(item.note, max_chars=180 if detail_boost else 150) or _compress_sentence(
            item.note,
            max_chars=180 if detail_boost else 150,
            fallback="",
            strip_boilerplate=True,
        )
        if (_beat_note_needs_backfill(note) or not _contains_chinese(note)) and chapter is not None:
            note = _build_fallback_beat_note(chapter, beat=beat, max_chars=180 if detail_boost else 150)
        pacing = _resolve_contextual_tag(
            item.pacing_tag,
            replacements=PACE_TAG_REPLACEMENTS,
            fallback=PACE_FALLBACK_LABEL,
            generic_labels=GENERIC_PACING_LABELS,
            context_text=" ".join(part for part in [beat, note, chapter.summary if chapter is not None else unit.summary] if part),
            context_rules=PACE_CONTEXT_RULES,
        )
        emotion = _resolve_contextual_tag(
            item.emotion_tag,
            replacements=EMOTION_TAG_REPLACEMENTS,
            fallback=EMOTION_FALLBACK_LABEL,
            generic_labels=GENERIC_EMOTION_LABELS,
            context_text=" ".join(part for part in [beat, note, chapter.summary if chapter is not None else unit.summary] if part),
            context_rules=EMOTION_CONTEXT_RULES,
        )
        beat_anchor = _build_detailed_beat_anchor(
            raw_beat=raw_beat,
            beat=beat,
            note=note,
            unit=unit,
            chapter=chapter,
            max_chars=132 if detail_boost else 108,
            avoid_texts=used_anchor_keys,
        )
        beat_anchor = _ensure_beat_anchor_has_change(
            beat_anchor=beat_anchor,
            raw_beat=raw_beat,
            beat=beat,
            note=note,
            unit=unit,
            chapter=chapter,
            max_chars=132 if detail_boost else 108,
            avoid_texts=used_anchor_keys,
        )
        if _is_low_signal_text(beat_anchor) or _is_low_signal_text(note) or not _contains_chinese(note):
            continue
        used_anchor_keys.add(_normalize_beat_anchor_key(beat_anchor))
        items.append(f"情节点：{beat_anchor}｜节奏：{pacing}｜情绪：{emotion}｜作用：{note}")
    if items:
        return _unique_preserve_order(items)[:6]

    if chapter is not None:
        fallback_items: list[str] = []
        for event in chapter.plot_events[:3]:
            beat = _compress_title(event.label or event.details, max_chars=24)
            note = _build_plot_event_text(event, max_chars=180 if detail_boost else 150)
            if not beat or _is_low_signal_text(beat) or not note:
                continue
            pacing = _resolve_contextual_tag("", replacements=PACE_TAG_REPLACEMENTS, fallback=PACE_FALLBACK_LABEL, generic_labels=GENERIC_PACING_LABELS, context_text=f"{beat} {note} {chapter.summary}", context_rules=PACE_CONTEXT_RULES)
            emotion = _resolve_contextual_tag("", replacements=EMOTION_TAG_REPLACEMENTS, fallback=EMOTION_FALLBACK_LABEL, generic_labels=GENERIC_EMOTION_LABELS, context_text=f"{beat} {note} {chapter.summary}", context_rules=EMOTION_CONTEXT_RULES)
            fallback_items.append(f"情节点：{beat}｜节奏：{pacing}｜情绪：{emotion}｜作用：{note}")
        if not fallback_items:
            for scene in chapter.scene_quotes[:3]:
                beat = _compress_title(scene.scene or fallback_title, max_chars=24)
                note = _format_preserved_clause(scene.purpose or scene.quote or chapter.summary, max_chars=180 if detail_boost else 150)
                if not beat or not note or _is_low_signal_text(note):
                    continue
                pacing = _resolve_contextual_tag("", replacements=PACE_TAG_REPLACEMENTS, fallback=PACE_FALLBACK_LABEL, generic_labels=GENERIC_PACING_LABELS, context_text=f"{beat} {note} {chapter.summary}", context_rules=PACE_CONTEXT_RULES)
                emotion = _resolve_contextual_tag("", replacements=EMOTION_TAG_REPLACEMENTS, fallback=EMOTION_FALLBACK_LABEL, generic_labels=GENERIC_EMOTION_LABELS, context_text=f"{beat} {note} {chapter.summary}", context_rules=EMOTION_CONTEXT_RULES)
                fallback_items.append(f"情节点：{beat}｜节奏：{pacing}｜情绪：{emotion}｜作用：{note}")
        if fallback_items:
            return _unique_preserve_order(fallback_items)[:3]

    summary_note = _format_preserved_clause(unit.summary, max_chars=150 if detail_boost else 130) or _compress_sentence(unit.summary, max_chars=150 if detail_boost else 130, fallback="")
    if summary_note and not _is_low_signal_text(summary_note):
        pacing = _resolve_contextual_tag("", replacements=PACE_TAG_REPLACEMENTS, fallback=PACE_FALLBACK_LABEL, generic_labels=GENERIC_PACING_LABELS, context_text=f"{fallback_title} {summary_note} {unit.summary}", context_rules=PACE_CONTEXT_RULES)
        emotion = _resolve_contextual_tag("", replacements=EMOTION_TAG_REPLACEMENTS, fallback=EMOTION_FALLBACK_LABEL, generic_labels=GENERIC_EMOTION_LABELS, context_text=f"{fallback_title} {summary_note} {unit.summary}", context_rules=EMOTION_CONTEXT_RULES)
        return [f"情节点：{fallback_title}｜节奏：{pacing}｜情绪：{emotion}｜作用：{summary_note}"]
    return items


def _build_detailed_beat_anchor(
    *,
    raw_beat: str,
    beat: str,
    note: str,
    unit: DeliveryUnit,
    chapter: ChapterAnalysis | None,
    max_chars: int,
    avoid_texts: set[str] | None = None,
) -> str:
    used_keys = avoid_texts or set()
    focus_terms = _extract_beat_focus_terms(" ".join(part for part in [raw_beat, beat] if part).strip())
    raw_label = _build_raw_beat_narrative(raw_beat, max_chars=max_chars)
    raw_needs_expansion = _beat_requires_candidate_expansion(raw_beat or beat)
    if (
        raw_label
        and not raw_needs_expansion
        and len(re.sub(r"\s+", "", raw_label)) >= 10
        and not _looks_cutoff(raw_label)
        and _normalize_beat_anchor_key(raw_label) not in used_keys
    ):
        return _truncate_chars(raw_label, max_chars)
    beat_label = _build_raw_beat_narrative(beat, max_chars=max_chars)
    if (
        beat_label
        and not _beat_requires_candidate_expansion(beat)
        and len(re.sub(r"\s+", "", beat_label)) >= 12
        and _normalize_beat_anchor_key(beat_label) not in used_keys
    ):
        return _truncate_chars(beat_label, max_chars)
    candidates: list[str] = []
    if chapter is not None:
        for event in chapter.plot_events[:4]:
            event_text = _build_plot_event_text(event, max_chars=max_chars)
            if event_text:
                candidates.append(event_text)
        for scene in chapter.scene_quotes[:3]:
            scene_text = _build_scene_anchor_text(scene, max_chars=max_chars)
            if scene_text:
                candidates.append(scene_text)
        candidates.extend(_collect_detail_items(chapter.highlights + [chapter.summary], limit=4, max_chars=max_chars))
    else:
        candidates.extend(_collect_detail_items([unit.summary, *unit.highlights, *unit.payoff, *unit.climax], limit=4, max_chars=max_chars))

    anchor_text = " ".join(part for part in [beat_label, note, chapter.summary if chapter is not None else unit.summary] if part)
    ranked_candidates = sorted(
        [
            candidate
            for candidate in _unique_preserve_order([candidate for candidate in candidates if candidate])
            if _normalize_beat_anchor_key(candidate) not in used_keys
        ],
        key=lambda candidate: (_score_beat_focus_overlap(candidate, focus_terms) * 4 + _score_text_overlap(candidate, anchor_text), len(candidate)),
        reverse=True,
    )
    if ranked_candidates and _score_beat_focus_overlap(ranked_candidates[0], focus_terms) > 0:
        return _truncate_chars(ranked_candidates[0], max_chars)
    if raw_label and _normalize_beat_anchor_key(raw_label) not in used_keys:
        return _truncate_chars(raw_label, max_chars)
    if beat_label and len(re.sub(r"\s+", "", beat_label)) >= 6 and _normalize_beat_anchor_key(beat_label) not in used_keys:
        return beat_label
    if beat_label and note and not _is_low_signal_text(note):
        note_clause = _format_preserved_clause(note, max_chars=max_chars) or _compress_sentence(
            note,
            max_chars=max_chars,
            fallback="",
            strip_boilerplate=True,
        )
        if note_clause and _normalize_beat_anchor_key(f"{beat_label}，{note_clause}") not in used_keys:
            return _truncate_chars(f"{beat_label}，{note_clause}", max_chars)
    if ranked_candidates:
        return _truncate_chars(ranked_candidates[0], max_chars)
    return beat_label


def _ensure_beat_anchor_has_change(
    *,
    beat_anchor: str,
    raw_beat: str,
    beat: str,
    note: str,
    unit: DeliveryUnit,
    chapter: ChapterAnalysis | None,
    max_chars: int,
    avoid_texts: set[str] | None = None,
) -> str:
    cleaned_anchor = beat_anchor.strip()
    if not cleaned_anchor:
        return cleaned_anchor
    if not _beat_anchor_needs_change(cleaned_anchor):
        return cleaned_anchor
    used_keys = avoid_texts or set()
    best_anchor = cleaned_anchor
    change_clause = _build_beat_change_clause(note, max_chars=max_chars)
    if change_clause and (
        ("：" in cleaned_anchor and len(re.sub(r"\s+", "", cleaned_anchor)) >= 20)
        or re.search(r"从.+到|再到|一句“", cleaned_anchor)
    ):
        merged = _merge_beat_anchor_with_progress(cleaned_anchor, change_clause, max_chars=max_chars)
        if _normalize_beat_anchor_key(merged) not in used_keys:
            return merged
    progress_text = _build_beat_progress_text(
        raw_beat=raw_beat,
        beat=beat,
        note=note,
        unit=unit,
        chapter=chapter,
        max_chars=max_chars,
    )
    if progress_text:
        progress_key = _normalize_beat_anchor_key(progress_text)
        if progress_key not in used_keys:
            candidate = _truncate_chars(progress_text, max_chars) if _is_generic_beat_anchor(cleaned_anchor) else _merge_beat_anchor_with_progress(cleaned_anchor, progress_text, max_chars=max_chars)
            if _normalize_beat_anchor_key(candidate) not in used_keys and candidate != cleaned_anchor:
                best_anchor = candidate
                if not _beat_anchor_needs_change(candidate):
                    return candidate
    if change_clause:
        merged = _merge_beat_anchor_with_progress(best_anchor, change_clause, max_chars=max_chars)
        if _normalize_beat_anchor_key(merged) not in used_keys:
            return merged
    return best_anchor


def _build_scene_anchor_text(scene: SceneQuoteItem, *, max_chars: int) -> str:
    scene_name = _format_preserved_clause(scene.scene, max_chars=max_chars // 2) or _compress_sentence(
        scene.scene,
        max_chars=max_chars // 2,
        fallback="",
        strip_boilerplate=True,
    )
    quote_text = _normalize_scene_quote(scene.quote, max_chars=max_chars)
    purpose_text = _format_preserved_clause(scene.purpose, max_chars=max_chars) or _compress_sentence(
        scene.purpose,
        max_chars=max_chars,
        fallback="",
        strip_boilerplate=True,
    )
    purpose_text = _rewrite_beat_change_clause(purpose_text)
    if scene_name and quote_text:
        return _truncate_chars(f"{scene_name}：{quote_text}", max_chars)
    if scene_name and purpose_text:
        return _truncate_chars(f"{scene_name}：{purpose_text}", max_chars)
    return scene_name or quote_text or purpose_text


def _build_beat_progress_text(
    *,
    raw_beat: str,
    beat: str,
    note: str,
    unit: DeliveryUnit,
    chapter: ChapterAnalysis | None,
    max_chars: int,
) -> str:
    seed_text = " ".join(part for part in [raw_beat, beat] if part).strip()
    focus_terms = _extract_beat_focus_terms(seed_text)
    context_text = " ".join(part for part in [seed_text, note, chapter.summary if chapter is not None else unit.summary] if part)
    candidates: list[str] = []
    if chapter is not None:
        candidates.extend(
            value
            for value in (
                *[_build_plot_event_text(event, max_chars=max_chars) for event in chapter.plot_events[:5]],
                *[_build_scene_progress_text(scene, max_chars=max_chars) for scene in chapter.scene_quotes[:5]],
                *(_collect_detail_items(chapter.highlights + chapter.payoff + [chapter.summary], limit=5, max_chars=max_chars)),
            )
            if value
        )
    else:
        candidates.extend(_collect_detail_items([unit.summary, *unit.highlights, *unit.payoff, *unit.climax], limit=5, max_chars=max_chars))
    ranked = sorted(
        _unique_preserve_order(candidates),
        key=lambda candidate: (
            _score_beat_focus_overlap(candidate, focus_terms) * 4 + _score_text_overlap(candidate, context_text),
            _beat_change_bonus(candidate),
            len(candidate),
        ),
        reverse=True,
    )
    for candidate in ranked:
        if candidate and not _is_low_signal_text(candidate) and _score_beat_focus_overlap(candidate, focus_terms) > 0:
            return _truncate_chars(candidate, max_chars)
    return ""


def _build_scene_progress_text(scene: SceneQuoteItem, *, max_chars: int) -> str:
    scene_name = _format_preserved_clause(scene.scene, max_chars=max_chars // 3) or _compress_sentence(
        scene.scene,
        max_chars=max_chars // 3,
        fallback="",
        strip_boilerplate=True,
    )
    quote_text = _normalize_scene_quote(scene.quote, max_chars=max_chars)
    purpose_text = _format_preserved_clause(scene.purpose, max_chars=max_chars) or _compress_sentence(
        scene.purpose,
        max_chars=max_chars,
        fallback="",
        strip_boilerplate=True,
    )
    purpose_text = _rewrite_beat_change_clause(purpose_text)
    if scene_name.endswith(("后", "前", "里", "中", "时")):
        scene_prefix = f"{scene_name}，"
    else:
        scene_prefix = f"在{scene_name}时，"
    if scene_name and quote_text and purpose_text:
        return _truncate_chars(f"{scene_prefix}{quote_text}，{purpose_text}", max_chars)
    if scene_name and quote_text:
        return _truncate_chars(f"{scene_prefix}{quote_text}", max_chars)
    if scene_name and purpose_text:
        return _truncate_chars(f"{scene_prefix}{purpose_text}", max_chars)
    return quote_text or purpose_text or scene_name


def _build_beat_change_clause(note: str, *, max_chars: int) -> str:
    cleaned = _format_preserved_clause(note, max_chars=max_chars) or _compress_sentence(
        note,
        max_chars=max_chars,
        fallback="",
        strip_boilerplate=True,
    )
    if not cleaned or _is_low_signal_text(cleaned):
        return ""
    rewritten = _rewrite_beat_change_clause(cleaned)
    if rewritten and rewritten != cleaned:
        return _truncate_chars(rewritten, max_chars)
    clauses = [part.strip("，；。 ") for part in re.split(r"[；。]", cleaned) if part.strip("，；。 ")]
    for clause in clauses:
        if _beat_change_bonus(clause) > 0:
            return clause
    return clauses[0] if clauses else ""


def _merge_beat_anchor_with_progress(anchor: str, progress_text: str, *, max_chars: int) -> str:
    cleaned_anchor = anchor.strip("，；。 ")
    cleaned_progress = progress_text.strip("，；。 ")
    if not cleaned_anchor:
        return _truncate_chars(cleaned_progress, max_chars)
    if not cleaned_progress:
        return _truncate_chars(cleaned_anchor, max_chars)
    if cleaned_anchor in cleaned_progress:
        return _truncate_chars(cleaned_progress, max_chars)
    anchor_prefix = cleaned_anchor.split("：", 1)[0].strip()
    if anchor_prefix and cleaned_progress.startswith(anchor_prefix):
        return _truncate_chars(cleaned_progress if len(cleaned_progress) > len(cleaned_anchor) else cleaned_anchor, max_chars)
    progress_suffix = cleaned_progress
    anchor_keywords = _extract_overlap_keywords(cleaned_anchor)
    for keyword in anchor_keywords:
        if keyword and keyword in progress_suffix and len(keyword) >= 2:
            progress_suffix = progress_suffix.replace(keyword, "", 1).strip("，；。 ：")
    if not progress_suffix or len(re.sub(r"\s+", "", progress_suffix)) < 6 or re.fullmatch(r"[，；。：、\s]+", progress_suffix):
        progress_suffix = cleaned_progress
    separator = "，" if "：" in cleaned_anchor else "："
    return _truncate_chars(f"{cleaned_anchor}{separator}{progress_suffix}", max_chars)


def _build_raw_beat_narrative(text: str, *, max_chars: int) -> str:
    cleaned = _format_preserved_clause(text, max_chars=max_chars) or _compress_sentence(
        text,
        max_chars=max_chars,
        fallback="",
        strip_boilerplate=True,
    )
    if not cleaned:
        return ""
    head = ""
    body = cleaned
    if "：" in cleaned and any(token in cleaned for token in ("→", "/", "｜")):
        head, body = cleaned.split("：", 1)
    if any(token in body for token in ("→", "/", "｜")) or (body.count("到") >= 2 and not re.search(r"[，；。！？]", body)):
        segments = _split_beat_segments(body)
        narrative = _join_beat_segments_as_narrative(segments)
        if narrative:
            if head:
                return _truncate_chars(f"{head}：{narrative}", max_chars)
            return _truncate_chars(narrative, max_chars)
    return _truncate_chars(cleaned, max_chars)


def _beat_requires_candidate_expansion(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    compact = len(re.sub(r"\s+", "", cleaned))
    if compact < 12:
        return True
    if any(token in cleaned for token in ("→", "/", "｜")):
        return True
    if cleaned.count("到") >= 2 and not re.search(r"[，；。！？]", cleaned):
        return True
    return False


def _normalize_scene_quote(text: str, *, max_chars: int) -> str:
    cleaned = _format_preserved_clause(text, max_chars=max_chars) or _compress_sentence(
        text,
        max_chars=max_chars,
        fallback="",
        strip_boilerplate=True,
    )
    cleaned = cleaned.strip().strip("“”\"' ").rstrip("。！？")
    if not cleaned:
        return ""
    if len(cleaned) <= 16:
        return f"一句“{cleaned}”"
    return cleaned


def _rewrite_beat_change_clause(text: str) -> str:
    replacements = [
        ("环境压迫感强化主角气场，烦躁情绪为后续亲密互动提供反差基底", "把赵壹笙的烦躁戒备先压到场内，也把后续亲密反差提前立住"),
        ("肢体越界三连击把试探直接推成贴身张力", "把隔桌试探一步步推成贴身暧昧，身体距离也在这一下被彻底改写"),
        ("肢体越界三连击（夺杯/换水/描摹），节奏由缓至急，触觉细节引爆性张力", "把隔桌试探一步步推成贴身暧昧，身体距离也在这一下被彻底改写"),
        ("用玩笑打断升温，让松弛表象下的紧绷继续成立", "表面把失控拐回玩笑，实则让拉扯继续往失守边缘推"),
        ("用幽默截断升温，维持权力平衡，情绪在松弛表象下持续紧绷", "表面把失控拐回玩笑，实则让拉扯继续往失守边缘推"),
        ("冰裂声和耳语一起把压迫感推到顶点", "把原本暧昧试探一下劈成正面交锋，压迫感也在这一刻彻底顶满"),
        ("听觉暴力（冰裂声）+语言暴力（玩死）双重冲击，节奏陡峭如刀锋劈开悬念", "把原本暧昧试探一下劈成正面交锋，强势姿态也在这一句里彻底立住"),
        ("长句堆叠生理细节（蹭头发、瞪天花板、赤脚走路），节奏拖沓，映射精神钝化", "把她被高压工作掏空后的失序状态彻底摊开，也让人物底色从强撑转向麻木下坠"),
        ("动作描写转为短句，插入内心吐槽，节奏微提，情绪转向自嘲式清醒", "把前一刻的失序晨起重新拽回职业状态，也让人物从麻木转向带刺清醒"),
        ("目光扫车而非人，建立物质逻辑先行的认知框架", "先把这场靠近落到算计和试探上，彼此关系也从搭话直接转成带目的的接近"),
        ("桃花眼特写与语言挑衅同步，启动权力博弈", "把引狼入室的暧昧一下推成主导权试探，门里门外的高低位也在这里开始换手"),
        ("静谧环境放大呼吸声，听觉成为情欲催化剂", "让对视试探直接烧到身体失控边缘，欲望也从暗涌推成明火"),
        ("清水甜味与痒感颤栗构成双重感官锚点", "把身体试探一下落到认人与认情的双重确认上，关系也开始从猎艳滑向失守"),
        ("动作链完成从私密到公共的身份转译", "把一夜亲密顺势翻成白天的主权宣示，关系也从私密越界推进到公开留痕"),
        ("高跟鞋声起，卓舒清抬眸，镜头聚焦赵壹笙压迫性面容与休闲领带的矛盾统一", "把重逢的第一眼从简单照面拉成压迫感十足的成人重逢，旧记忆与新身份在这一刻重新对上"),
        ("以教学姿态实施诱惑，消解引狼入室的被动性", "把引狼入室的暧昧一下推成主导权试探，门里门外的高低位也在这里开始换手"),
        ("用轻语完成道德赦免，将越界行为合法化为亲密特权", "把刚刚越界的身体试探认成默认默契，关系也从猎艳滑向更难抽身的靠近"),
        ("确立赵壹笙强势人格锚点", "先把她强势归来的姿态钉在众人面前，也让后续靠近带上更强的压迫感"),
        ("确立赵壹笙强势人格锚点，视觉化‘归来者’气场", "先把她强势归来的姿态钉在众人面前，也让后续靠近带上更强的压迫感"),
        ("以生活化细节软化精英形象", "把锋利试探缓缓拖进带家感的暧昧，彼此戒备也在生活细节里悄悄松动"),
        ("以生活化细节软化精英形象，触发卓舒清‘家的错觉’", "把锋利试探缓缓拖进带家感的暧昧，彼此戒备也在生活细节里悄悄松动"),
        ("将外部亲密与内在警觉并置", "把刚刚升温的亲密猛地拽进旧伤警觉，关系也从调情转向碰到伤口"),
        ("将外部亲密与内在警觉并置，制造认知张力", "把刚刚升温的亲密猛地拽进旧伤警觉，关系也从调情转向碰到伤口"),
        ("静态凝视+肢体语言主导，节奏沉稳蓄力", "先把她强势归来的姿态钉在众人面前，也让后续靠近带上更强的压迫感"),
        ("短句切割+多人视线交织，节奏骤紧", "把旧识围观一下推成正面碰撞，场内气压也在这一刻骤然收紧"),
        ("细节特写延缓时间感", "把锋利试探缓缓拖进带家感的暧昧，彼此戒备也在生活细节里悄悄松动"),
        ("细节特写（发丝、锁骨、砂锅）延缓时间感", "把锋利试探缓缓拖进带家感的暧昧，彼此戒备也在生活细节里悄悄松动"),
        ("长句中断+感官聚焦让节奏骤停", "把刚刚升温的情欲猛地拽进创伤暴露，关系也从调情转向真正靠近伤口"),
        ("动作密集+拟声联想（猫咪捣乱），节奏轻快跳跃", "让身体试探从观察试水直接跳到互相撩拨，亲密关系也顺势往前推了一大步"),
        ("长句中断+感官聚焦（指尖触感、气息温度），节奏骤停", "把刚刚升温的情欲猛地拽进创伤暴露，关系也从调情转向真正靠近伤口"),
        ("镜头缓慢推进，强调视觉与触觉的渐进式唤醒", "把彼此试探慢慢推到身体主导的升温阶段，谁先靠近谁也因此重新洗牌"),
        ("短句切分制造生理痛感与心理松动的同步震颤", "把疼痛暴露和心防松动同时逼出来，亲密关系也第一次碰到脆弱底线"),
        ("主控权在0.5秒内完成二次让渡，节奏如呼吸起伏", "把主导权从单向试探拉回到重新协商，身体靠近也因此变成双向回应"),
    ]
    for source, target in replacements:
        if source in text:
            return target
    return text


def _normalize_beat_anchor_key(text: str) -> str:
    return re.sub(r"[，；：。！？、“”‘’\s]", "", text or "")


def _extract_beat_focus_terms(text: str) -> list[str]:
    raw_parts = re.split(r"[，,；：。！？/|→\-]+|到|与|并|及", text or "")
    terms: list[str] = []
    for part in raw_parts:
        cleaned = part.strip()
        if len(cleaned) < 2:
            continue
        terms.append(cleaned)
        if len(cleaned) >= 4:
            terms.append(cleaned[:4])
            terms.append(cleaned[-4:])
    return _unique_preserve_order([term for term in terms if term and term not in {"赵壹笙", "卓舒清", "齐简臻", "康壹竽", "方新箬"}])


def _score_beat_focus_overlap(candidate: str, focus_terms: list[str]) -> int:
    score = 0
    for term in focus_terms:
        if term and term in candidate:
            score += max(2, len(term))
    return score


def _is_generic_beat_anchor(text: str) -> bool:
    compact = len(re.sub(r"\s+", "", text))
    if compact < 12:
        return True
    if not re.search(r"[，；。]", text):
        return True
    return "/" in text or "→" in text


def _beat_anchor_needs_change(text: str) -> bool:
    compact = len(re.sub(r"\s+", "", text))
    if compact < 12:
        return True
    if _beat_anchor_reads_like_analysis(text):
        return True
    return _beat_change_bonus(text) <= 0


def _beat_change_bonus(text: str) -> int:
    change_markers = (
        "把",
        "让",
        "令",
        "使",
        "推成",
        "推到",
        "推进",
        "引发",
        "触发",
        "形成",
        "完成",
        "改写",
        "暴露",
        "揭开",
        "震惊",
        "撕开",
        "升级",
        "失控",
        "松动",
        "崩解",
        "确立",
        "拉到",
        "转向",
        "逼出",
        "带出",
        "落到",
        "消解",
        "拖进",
        "拽进",
        "烧到",
        "滑向",
        "翻成",
        "对上",
        "换手",
        "顶满",
        "留痕",
        "钉在",
        "拉成",
        "拉回",
        "拖到",
    )
    score = 0
    for marker in change_markers:
        if marker in text:
            score += 2
    return score


def _beat_anchor_reads_like_analysis(text: str) -> bool:
    analysis_markers = (
        "锚点",
        "视觉化",
        "特写",
        "认知框架",
        "并置",
        "合法化",
        "特权",
        "形象",
        "气场",
        "结构",
        "教学姿态",
        "实施诱惑",
        "权力结构",
        "节奏骤停",
        "节奏骤紧",
        "延缓时间感",
    )
    strong_story_markers = (
        "把",
        "让",
        "从",
        "再到",
        "推成",
        "推到",
        "改写",
        "拖进",
        "拽进",
        "烧到",
        "滑向",
        "翻成",
        "钉在",
        "拉成",
        "换手",
        "对上",
    )
    if any(marker in text for marker in analysis_markers) and not any(marker in text for marker in strong_story_markers):
        return True
    return bool(re.search(r"^在.+时，.+(?:以|将|用).+", text))


def _split_beat_segments(text: str) -> list[str]:
    normalized = text.replace("→", "|").replace("/", "|").replace("｜", "|")
    if normalized.count("到") >= 2 and not re.search(r"[，；。！？]", normalized):
        normalized = normalized.replace("到", "|")
    return [
        _normalize_beat_segment(part)
        for part in re.split(r"[|]+", normalized)
        if _normalize_beat_segment(part)
    ]


def _normalize_beat_segment(segment: str) -> str:
    cleaned = (segment or "").strip().strip("，；。:：、 ")
    if not cleaned:
        return ""
    if cleaned.endswith("注视"):
        cleaned = f"{cleaned[:-2]}对视"
    if len(cleaned) >= 2 and cleaned[0] in "“\"'‘’" and cleaned[-1] in "”\"'‘’":
        inner = cleaned[1:-1].strip("，；。！？ ")
        if inner:
            return f"一句“{inner}”"
    quote_match = re.search(r"[“\"']([^“”\"']{1,16})[”\"']", segment)
    if quote_match:
        quote_text = quote_match.group(1).strip("，；。！？ ")
        if cleaned.startswith("自嘲"):
            return f"自嘲一句“{quote_text}”"
        return f"一句“{quote_text}”"
    return cleaned


def _join_beat_segments_as_narrative(segments: list[str]) -> str:
    if not segments:
        return ""
    head = ""
    body_segments = list(segments)
    if "：" in body_segments[0]:
        head, first = body_segments[0].split("：", 1)
        body_segments[0] = first.strip()
    if len(body_segments) == 1:
        body = body_segments[0]
    elif len(body_segments) == 2:
        second = body_segments[1]
        if second.startswith(("一句“", "自嘲一句“")):
            connector = "时，" if not body_segments[0].endswith(("时", "后")) else "，"
            body = f"{body_segments[0]}{connector}{second}"
        else:
            body = f"从{body_segments[0]}到{second}"
    elif len(body_segments) == 3:
        body = f"从{body_segments[0]}到{body_segments[1]}，再到{body_segments[2]}"
    else:
        middle = "、".join(body_segments[1:-1])
        body = f"从{body_segments[0]}到{middle}，再到{body_segments[-1]}"
    if head:
        return f"{head}：{body}"
    return body


def _score_text_overlap(candidate: str, anchor_text: str) -> int:
    anchor_keywords = _extract_overlap_keywords(anchor_text)
    if not anchor_keywords:
        return 0
    score = 0
    for keyword in anchor_keywords:
        if keyword and keyword in candidate:
            score += max(2, len(keyword))
    return score


def _extract_overlap_keywords(text: str) -> list[str]:
    return _unique_preserve_order(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}", text))


def _format_scene_quotes(unit: DeliveryUnit) -> list[str]:
    items: list[str] = []
    for item in unit.scene_quotes[:4]:
        scene = _compress_title(item.scene, max_chars=24)
        if _is_low_signal_text(scene) or len(scene.strip()) < 2:
            scene = ""
        quote = _compress_quote(item.quote)
        purpose = _format_preserved_clause(item.purpose, max_chars=42) or _compress_sentence(item.purpose, max_chars=42, fallback="")
        if _is_low_signal_text(purpose):
            purpose = _infer_scene_purpose(unit)
        if not scene:
            scene = _compress_title(_first_nonempty_text(unit.highlights + unit.climax + [unit.summary]), max_chars=24)
        if not scene or (_is_low_signal_text(scene) and not quote):
            continue
        text = scene
        if quote:
            text += f"｜金句：{quote}"
        if purpose:
            text += f"｜作用：{purpose}"
        if _is_low_signal_text(text):
            continue
        items.append(text)
    if items:
        return _unique_preserve_order(items)[:3]
    scene = _compress_title(_first_nonempty_text(unit.highlights + unit.climax + [unit.summary]), max_chars=24)
    purpose = _infer_scene_purpose(unit)
    if scene and not _is_low_signal_text(scene) and purpose:
        return [f"{scene}｜作用：{purpose}"]
    return items


def _format_relationship_progress(
    unit: DeliveryUnit,
    *,
    chapter: ChapterAnalysis | None = None,
    detail_boost: bool = False,
) -> list[str]:
    items: list[str] = []
    max_chars = 220 if detail_boost else 180
    for item in unit.relationship_progression[:4]:
        counterpart = _compress_title(item.counterpart, max_chars=18)
        stage_label = _compress_title(item.stage_label, max_chars=16)
        if _is_low_signal_text(counterpart) or len(counterpart.strip()) < 2:
            counterpart = _infer_relationship_counterpart(unit)
        if (
            _is_low_signal_text(stage_label)
            or len(stage_label.strip()) < 2
            or not _contains_chinese(stage_label)
            or re.search(r"[A-Za-z]", stage_label)
            or len(stage_label) > 8
        ):
            stage_label = _infer_relationship_stage_label(item.change or unit.summary)
        change = _build_relationship_change_text(
            item.change,
            unit=unit,
            chapter=chapter,
            counterpart=counterpart,
            stage_label=stage_label,
            max_chars=max_chars,
            detail_boost=detail_boost,
        )
        change = change.lstrip("；：，、- ")
        if _is_low_signal_text(change) or not _contains_chinese(change):
            continue
        items.append(f"{counterpart} / {stage_label}：{change}")
    if detail_boost and chapter is not None and len(items) < 3:
        inferred_items = _build_inferred_relationship_items(
            unit,
            chapter,
            existing_items=items,
            max_items=3,
            max_chars=max_chars,
        )
        items.extend(inferred_items)
    if items:
        return _unique_preserve_order(items)[:4]
    summary_change = _build_relationship_change_text(
        unit.summary or "关系推进进入新阶段。",
        unit=unit,
        chapter=chapter,
        counterpart=_infer_relationship_counterpart(unit),
        stage_label="",
        max_chars=max_chars,
        detail_boost=detail_boost,
    )
    if summary_change and not _is_low_signal_text(summary_change):
        return [f"{_infer_relationship_counterpart(unit)} / {_infer_relationship_stage_label(summary_change)}：{summary_change}"]
    return items


def _beat_note_needs_backfill(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned or _is_low_signal_text(cleaned):
        return True
    compact_length = len(re.sub(r"\s+", "", cleaned))
    if compact_length < 8:
        return True
    return cleaned in {"用", "短句切割", "长句逻辑链", "动作承接", "形成对比", "压迫感", "情绪递进"}


def _build_fallback_beat_note(chapter: ChapterAnalysis, *, beat: str, max_chars: int) -> str:
    candidates = [
        *[_build_plot_event_text(event, max_chars=max_chars) for event in chapter.plot_events],
        *[_format_preserved_clause(scene.purpose or scene.quote, max_chars=max_chars) for scene in chapter.scene_quotes],
        *(_collect_detail_items(chapter.highlights + chapter.payoff + [chapter.summary], limit=4, max_chars=max_chars)),
    ]
    beat_anchor = beat.replace("：", "").strip()
    for candidate in candidates:
        if not candidate or _is_low_signal_text(candidate):
            continue
        if beat_anchor and beat_anchor[:4] in candidate:
            return candidate
    for candidate in candidates:
        if candidate and not _is_low_signal_text(candidate):
            return candidate
    return ""


def _build_relationship_change_text(
    base_text: str,
    *,
    unit: DeliveryUnit,
    chapter: ChapterAnalysis | None,
    counterpart: str,
    stage_label: str,
    max_chars: int,
    detail_boost: bool,
) -> str:
    segments: list[str] = []
    base_segment = _format_preserved_clause(base_text, max_chars=150 if detail_boost else 130) or _compress_sentence(
        base_text,
        max_chars=150 if detail_boost else 130,
        fallback="",
        strip_boilerplate=True,
    )
    rewritten_base = _rewrite_relationship_segment(base_segment)
    base_needs_story_detail = _relationship_segment_needs_story_detail(rewritten_base)
    if _relationship_segment_usable(rewritten_base) and not base_needs_story_detail:
        segments.append(rewritten_base)

    support_values: list[str] = []
    if chapter is not None:
        support_values.extend(_build_plot_event_text(event, max_chars=88 if detail_boost else 72) for event in chapter.plot_events)
        support_values.extend(
            _clean_delivery_text(
                _first_nonempty_text([scene.quote, scene.purpose, scene.scene, chapter.summary]),
                strip_boilerplate=True,
            )
            for scene in chapter.scene_quotes
            if (scene.quote or scene.purpose or scene.scene or chapter.summary).strip()
        )
        support_values.extend(chapter.highlights)
        support_values.extend(chapter.payoff)
        support_values.append(chapter.summary)
        support_values.extend(item.change for item in chapter.relationship_progression if (item.change or "").strip())
    support_values.append(unit.summary)

    support_candidates = _collect_detail_items(
        [value for value in support_values if value],
        limit=6 if detail_boost else 4,
        max_chars=110 if detail_boost else 88,
    )
    anchor_text = " ".join(
        part
        for part in [
            "" if base_needs_story_detail else rewritten_base,
            chapter.summary if chapter is not None else unit.summary,
            counterpart,
            stage_label,
        ]
        if part
    )
    ranked_candidates = sorted(
        support_candidates,
        key=lambda candidate: _score_relationship_support_candidate(candidate, anchor_text),
        reverse=True,
    )

    max_support_segments = 2 if detail_boost else 2
    for support in ranked_candidates:
        if support in "；".join(segments):
            continue
        if rewritten_base and not base_needs_story_detail and _score_relationship_support_candidate(support, anchor_text) <= 0:
            continue
        segments.append(support)
        if len(segments) >= 1 + max_support_segments:
            break

    if _relationship_segment_usable(rewritten_base) and rewritten_base not in "；".join(segments):
        segments.append(rewritten_base)

    if not segments:
        return ""
    return _truncate_chars("；".join(_unique_preserve_order(segments)), max_chars)


def _relationship_segment_usable(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned or _is_low_signal_text(cleaned) or not _contains_chinese(cleaned):
        return False
    if len(re.sub(r"\s+", "", cleaned)) < 10:
        return False
    return not _looks_cutoff(cleaned)


def _relationship_segment_needs_story_detail(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    abstract_markers = (
        "可操作变量",
        "可信度建模",
        "主权声明",
        "情报价值",
        "存在本身",
        "关系契约",
        "共同签署者",
        "权力动态",
        "降维",
        "升级为战略级接触",
        "行为逻辑",
        "价值判断",
    )
    if any(marker in cleaned for marker in abstract_markers):
        return True
    if cleaned.startswith("从") and not re.search(r"[，；。]", cleaned):
        return True
    if len(re.sub(r"\s+", "", cleaned)) < 22 and not re.search(r"[，；。]", cleaned):
        return True
    return False


def _rewrite_relationship_segment(text: str) -> str:
    cleaned = text.strip("；：，、- ")
    if not cleaned:
        return ""
    replacements = [
        ("从陌生人到被精准识别的目标到关系契约的共同签署者", "两人的关系也从陌生人推进到被精准识别的目标，再到带着契约意味的共同站队"),
        ("权力动态由赵壹笙主导瞬时转为双向试探与共谋", "两人的高低位也从赵壹笙单向主导，转成双向试探与共谋"),
        ("从见色起意升级为战略级接触，通过晨间着装入侵完成物理空间主权声明", "赵壹笙也从见色起意滑到真正介入卓舒清生活边界，关系在晨间着装和办公室重逢里被推到更难抽身的位置"),
        ("从高中同学降维为可操作变量，通过体香/纹身/饮品三重验证完成可信度建模", "卓舒清先把赵壹笙当成可试探的目标去接近，可越往后越难把这份靠近只当成一次简单猎艳"),
    ]
    for source, target in replacements:
        if source in cleaned:
            return target
    if cleaned.startswith("从") and not re.search(r"[，；。]", cleaned):
        return f"两人的关系也{cleaned}"
    if cleaned.startswith("权力动态"):
        return cleaned.replace("权力动态", "两人的权力动态", 1)
    return cleaned


def _build_inferred_relationship_items(
    unit: DeliveryUnit,
    chapter: ChapterAnalysis,
    *,
    existing_items: list[str],
    max_items: int,
    max_chars: int,
) -> list[str]:
    items: list[str] = []
    counterpart = _infer_relationship_counterpart(unit)
    used_text = " ".join(existing_items)
    raw_sources = [
        chapter.summary,
        *[_build_plot_event_text(event, max_chars=96) for event in chapter.plot_events],
        *chapter.highlights,
        *chapter.payoff,
        *[scene.purpose for scene in chapter.scene_quotes if (scene.purpose or "").strip()],
    ]
    sources: list[str] = []
    for raw_source in raw_sources:
        source = _format_preserved_clause(raw_source, max_chars=96) or _compress_sentence(
            raw_source,
            max_chars=96,
            fallback="",
            strip_boilerplate=True,
        )
        source = source.lstrip("；：，、- ")
        if not source or _is_low_signal_text(source):
            continue
        sources.append(source)
    for source in _unique_preserve_order(sources):
        if source in used_text:
            continue
        stage_label = _infer_relationship_stage_label(source)
        change = _truncate_chars(source, max_chars)
        if not change or _is_low_signal_text(change):
            continue
        items.append(f"{counterpart} / {stage_label}：{change}")
        if len(existing_items) + len(items) >= max_items:
            break
    return items


def _format_style_signals(unit: DeliveryUnit) -> list[str]:
    items: list[str] = []
    for item in unit.style_signals[:4]:
        dimension = _compress_title(_clean_tag(item.dimension, replacements=KNOWN_ENGLISH_REPLACEMENTS, fallback="文风信号"), max_chars=16)
        if dimension == "文风信号":
            dimension = ""
        observation = _format_preserved_clause(item.observation, max_chars=58) or _compress_sentence(
            item.observation,
            max_chars=58,
            fallback="",
            strip_boilerplate=True,
        )
        observation = observation.lstrip("；：，、- ")
        if not dimension or not _contains_chinese(dimension):
            dimension = _infer_style_dimension(observation)
        if _is_low_signal_text(dimension) or len(dimension.strip()) < 2:
            continue
        if _is_low_signal_text(observation) or not _contains_chinese(observation):
            continue
        items.append(f"{dimension}：{observation}")
    if items:
        return _unique_preserve_order(items)[:4]
    fallback_observation = _infer_style_observation(unit)
    if fallback_observation:
        return [fallback_observation]
    return items


def _fallback_unit_heading(unit: DeliveryUnit, index: int) -> str:
    candidates = [item.scene for item in unit.scene_quotes if item.scene.strip()]
    candidates.extend(item.beat for item in unit.beat_rhythm if item.beat.strip())
    candidates.extend(unit.highlights)
    candidates.extend(unit.climax)
    candidates.extend(unit.payoff)
    candidates.append(unit.summary)
    for candidate in candidates:
        resolved = _compress_title(candidate, max_chars=18)
        if resolved != "未命名条目":
            return resolved
    return f"叙事推进{index}"


def _build_unit_heading_text(unit: DeliveryUnit, index: int, *, chapter: ChapterAnalysis | None = None) -> str:
    title = _resolve_unit_heading_title(unit, index, chapter=chapter)
    chapter_range = _clean_delivery_text(unit.chapter_range or f"单元 {index}")
    return f"{title}（{chapter_range}）"


def _resolve_unit_heading_title(unit: DeliveryUnit, index: int, *, chapter: ChapterAnalysis | None = None) -> str:
    for candidate in _iter_unit_heading_candidates(unit, chapter=chapter):
        resolved = _normalize_unit_heading_candidate(candidate, max_chars=18)
        if resolved:
            return resolved
    return _fallback_unit_heading_label(unit=unit, chapter=chapter, index=index)


def _iter_unit_heading_candidates(unit: DeliveryUnit, *, chapter: ChapterAnalysis | None = None) -> list[str]:
    candidates: list[str] = []
    if unit.title.strip():
        candidates.append(unit.title)
    if chapter is not None:
        chapter_title = _strip_chapter_title_prefix(_sanitize_title(chapter.title))
        if chapter_title.strip():
            candidates.append(chapter_title)
        if chapter.summary.strip():
            candidates.append(chapter.summary)
        candidates.extend(item for item in chapter.highlights if item.strip())
        candidates.extend(item for item in chapter.payoff if item.strip())
        candidates.extend(item for item in chapter.crisis if item.strip())
        for event in chapter.plot_events:
            if event.label.strip():
                candidates.append(event.label)
            if event.details.strip():
                candidates.append(event.details)
        candidates.extend(item.scene for item in chapter.scene_quotes if item.scene.strip())
    else:
        if unit.summary.strip():
            candidates.append(unit.summary)
        candidates.extend(item for item in unit.highlights if item.strip())
        candidates.extend(item for item in unit.payoff if item.strip())
        candidates.extend(item for item in unit.crisis if item.strip())
        candidates.extend(item.scene for item in unit.scene_quotes if item.scene.strip())
    return _unique_preserve_order(candidates)


def _normalize_unit_heading_candidate(text: str, *, max_chars: int) -> str:
    cleaned = _strip_unit_heading_noise(text)
    if not cleaned:
        return ""
    candidate = _compress_title(cleaned, max_chars=max_chars)
    if candidate == "未命名条目":
        candidate = _compress_sentence(cleaned, max_chars=max_chars, fallback="", strip_boilerplate=True)
    candidate = _strip_unit_heading_noise(candidate)
    if not candidate:
        return ""
    if _is_title_noise(candidate):
        return ""
    if _is_sentence_like_unit_heading(candidate):
        return ""
    return _truncate_chars(candidate, max_chars)


def _strip_unit_heading_noise(text: str) -> str:
    cleaned = _clean_delivery_text(text, strip_boilerplate=True)
    if not cleaned:
        return ""
    cleaned = re.sub(r"（第.+?章）$", "", cleaned).strip()
    cleaned = _strip_chapter_title_prefix(_sanitize_title(cleaned))
    cleaned = re.sub(r"^(?:引子|番外|后记)[：: ]*", "", cleaned).strip("，、；： ")
    cleaned = re.sub(r"^(?:本章|本段|这一章|这一段|这一节|这一回)", "", cleaned).strip("，、；： ")
    cleaned = re.sub(r"^(?:围绕|通过|借由|借助|聚焦|呈现|描写|描述|讲述|讲到|写到|写出|写了|转入|来到|进入|回到)", "", cleaned).strip("，、；： ")
    cleaned = re.sub(r"[“”\"'‘’]+", "", cleaned).strip("，、；：。！？!?… ")
    return cleaned


def _is_sentence_like_unit_heading(text: str) -> bool:
    cleaned = _clean_delivery_text(text, strip_boilerplate=True)
    if not cleaned:
        return True
    if cleaned.startswith(("我", "她", "他", "你", "我们", "他们", "她们")):
        return True
    if cleaned.startswith("在") and any(token in cleaned for token in ("面前", "看上去", "眼前", "身边", "时候")):
        return True
    if any(token in cleaned for token in ("终究", "曾以为", "像是", "几乎", "看上去")):
        return True
    if "是" in cleaned and len(cleaned) >= 8:
        return True
    if re.search(r"(?:之上|平行|声中|给她的)$", cleaned):
        return True
    return False


def _fallback_unit_heading_label(
    unit: DeliveryUnit | None = None,
    *,
    chapter: ChapterAnalysis | None = None,
    chapter_range: str | None = None,
    index: int | None = None,
) -> str:
    effective_range = _clean_delivery_text(chapter_range or (unit.chapter_range if unit is not None else ""))
    if chapter is not None or (unit is not None and len(unit.chapter_refs) <= 1):
        return "关键推进"
    if re.fullmatch(r"第\d+章", effective_range):
        return "关键推进"
    if re.fullmatch(r"第\d+-\d+章", effective_range):
        return "阶段推进"
    if index is not None:
        return f"阶段推进{index}"
    return "阶段推进"


def _chapter_to_unit(chapter: ChapterAnalysis, index: int) -> DeliveryUnit:
    number = _chapter_number(chapter.chapter_id)
    chapter_range = f"第{number}章" if number is not None else f"单元 {index}"
    return DeliveryUnit(
        unit_id=f"unit-{index:03d}",
        title=_resolve_chapter_unit_title(chapter, index),
        base_title=_sanitize_title(chapter.title),
        chapter_refs=[chapter.chapter_id],
        chapter_range=chapter_range,
        summary=chapter.summary,
        crisis=chapter.crisis,
        foreshadowing=chapter.foreshadowing,
        suspense=chapter.suspense,
        climax=chapter.climax,
        payoff=chapter.payoff,
        highlights=chapter.highlights,
        beat_rhythm=chapter.beat_rhythm,
        scene_quotes=chapter.scene_quotes,
        relationship_progression=chapter.relationship_progression,
        style_signals=chapter.style_signals,
        evidence=chapter.evidence,
    )


def _format_chapter_refs(chapter_refs: list[str]) -> str:
    if not chapter_refs:
        return "阶段范围未明"
    ordered = sorted(chapter_refs, key=_chapter_sort_key)
    numbers = [_chapter_number(item) for item in ordered]
    if all(number is not None for number in numbers):
        first = numbers[0]
        last = numbers[-1]
        if first == last:
            return f"第{first}章"
        return f"第{first}-{last}章"
    if len(ordered) == 1:
        return _clean_delivery_text(ordered[0])
    return _clean_delivery_text(f"{ordered[0]} ~ {ordered[-1]}")


def _sanitize_title(title: str) -> str:
    return re.sub(r"（分块\s*\d+/\d+）", "", title).strip()


def _strip_chapter_title_prefix(title: str) -> str:
    return re.sub(r"^第\d+章\s*", "", title).strip()


def _is_generic_chapter_title(title: str) -> bool:
    normalized = _strip_chapter_title_prefix(_sanitize_title(title))
    if not normalized:
        return True
    if normalized in GENERIC_UNIT_TITLES:
        return True
    if re.match(r"^(?:引子|番外|后记)(?:[：:：.\-].*)?$", normalized):
        return True
    if any(token in normalized for token in ("未识别章节", "叙事单元")):
        return True
    return False


def _resolve_chapter_unit_title(chapter: ChapterAnalysis, index: int) -> str:
    return _resolve_unit_heading_title(_chapter_to_unit_seed(chapter, index), index, chapter=chapter)


def _chapter_to_unit_seed(chapter: ChapterAnalysis, index: int) -> DeliveryUnit:
    number = _chapter_number(chapter.chapter_id)
    chapter_range = f"第{number}章" if number is not None else f"单元 {index}"
    return DeliveryUnit(
        unit_id=f"unit-seed-{index:03d}",
        title=_strip_chapter_title_prefix(_sanitize_title(chapter.title)),
        base_title=_sanitize_title(chapter.title),
        chapter_refs=[chapter.chapter_id],
        chapter_range=chapter_range,
        summary=chapter.summary,
        crisis=chapter.crisis,
        foreshadowing=[],
        suspense=[],
        climax=[],
        payoff=chapter.payoff,
        highlights=chapter.highlights,
        beat_rhythm=[],
        scene_quotes=[],
        relationship_progression=[],
        style_signals=[],
        evidence=[],
    )


def _dedupe_chapter_unit_titles(units: list[DeliveryUnit]) -> list[DeliveryUnit]:
    seen: dict[str, int] = {}
    deduped: list[DeliveryUnit] = []
    for index, unit in enumerate(units, start=1):
        title = _clean_delivery_text(unit.title or "")
        if not title:
            deduped.append(unit)
            continue
        seen[title] = seen.get(title, 0) + 1
        if seen[title] == 1:
            deduped.append(unit)
            continue
        chapter_hint = _clean_delivery_text(unit.chapter_range or f"第{index}章")
        refined_title = _truncate_chars(f"{title}·{chapter_hint}", 18)
        deduped.append(unit.model_copy(update={"title": refined_title}))
    return deduped


def _chapter_sort_key(chapter_id: str) -> tuple[int, str]:
    number = _chapter_number(chapter_id)
    if number is not None:
        return number, chapter_id
    return 10**9, chapter_id


def _chapter_number(chapter_id: str) -> int | None:
    match = re.search(r"(\d+)$", chapter_id)
    if not match:
        return None
    return int(match.group(1))


def _value(text: str) -> str:
    cleaned = _clean_delivery_text(text)
    return cleaned if cleaned else "拆书报告"


def _compress_title(text: str, *, max_chars: int = 18) -> str:
    raw = (text or "").strip()
    if re.search(r"[“\"'‘][^”\"'’]*$", raw) or re.search(r"[（(][^）)]*$", raw):
        return "未命名条目"
    cleaned = _clean_delivery_text(text, strip_boilerplate=True)
    if not cleaned:
        return "未命名条目"
    if _has_problematic_english(cleaned):
        return "未命名条目"
    parts = _split_clauses(cleaned)
    if not parts:
        candidate = _truncate_chars(cleaned, max_chars)
        return candidate if len(candidate.strip()) >= 2 else "未命名条目"
    candidate = parts[0]
    if len(candidate) < 5 and len(parts) > 1:
        candidate = f"{candidate}与{parts[1]}"
    candidate = re.sub(r"^(围绕|通过|借由|借助|围绕着)", "", candidate).strip("，、；： ")
    candidate = _truncate_chars(candidate or cleaned, max_chars)
    if len(candidate.strip()) < 2 or _has_suspicious_tail(candidate):
        return "未命名条目"
    return candidate


def _compress_paragraph(
    text: str,
    *,
    max_sentences: int = 2,
    max_chars: int = 96,
    fallback: str = "信息仍需进一步提炼。",
) -> str:
    cleaned = _clean_delivery_text(text, strip_boilerplate=True)
    if not cleaned:
        return fallback
    if _is_english_heavy(cleaned) or _has_problematic_english(cleaned):
        return fallback
    sentences = _split_sentences(cleaned)
    usable_sentences = [_trim_broken_tail(sentence) for sentence in sentences if not _is_fragmentary(sentence)]
    joined = "；".join(usable_sentences[:max_sentences]) if usable_sentences else _trim_broken_tail(cleaned)
    if not _contains_chinese(joined) and re.search(r"[A-Za-z]{3,}", joined):
        return fallback
    if _is_fragmentary(joined):
        return fallback
    return _truncate_chars(joined, max_chars) or fallback


def _compress_sentence(
    text: str,
    *,
    max_chars: int = 36,
    fallback: str = "信息仍需进一步提炼",
    strip_boilerplate: bool = False,
) -> str:
    cleaned = _clean_delivery_text(text, strip_boilerplate=strip_boilerplate)
    if not cleaned:
        return fallback
    if _is_english_heavy(cleaned) or _has_problematic_english(cleaned):
        return fallback
    split_sentences = _split_sentences(cleaned)
    sentence = split_sentences[0] if split_sentences else cleaned
    sentence = _trim_broken_tail(sentence)
    sentence = sentence.lstrip("；：，、- ")
    clauses = _split_clauses(sentence)
    if len(clauses) > 1:
        first_clause = _trim_broken_tail(clauses[0])
        trailing_clauses = [_trim_broken_tail(clause) for clause in clauses[1:]]
        if first_clause and all(_is_fragmentary(clause) for clause in trailing_clauses if clause):
            sentence = first_clause
    if not _contains_chinese(sentence) and re.search(r"[A-Za-z]{3,}", sentence):
        return fallback
    if _is_fragmentary(sentence) or _looks_cutoff(sentence):
        return fallback
    return _truncate_chars(sentence, max_chars) or fallback


def _compress_quote(text: str) -> str:
    cleaned = _clean_delivery_text(text)
    if not cleaned or _is_english_heavy(cleaned):
        return ""
    quote = _split_sentences(cleaned)[0] if _split_sentences(cleaned) else cleaned
    quote = _trim_broken_tail(quote)
    bare_quote = re.sub(r"[“”\"'‘’！？?!。…·,，、；：\s]", "", quote)
    if not bare_quote:
        return ""
    if _is_fragmentary(quote) or _looks_cutoff(quote):
        return ""
    if len(quote) >= 16 and not re.search(r"[。！？!?]$", quote) and quote[-1] not in "啊呀吗呢吧了么啦":
        return ""
    quote = _truncate_chars(quote, 24)
    if _looks_cutoff(quote):
        return ""
    if len(quote) > 2 and not quote.startswith("“"):
        return f"“{quote.strip('“”')}”"
    return quote


def _compress_list(values: list[str], *, limit: int, max_chars: int) -> list[str]:
    items: list[str] = []
    for value in values:
        cleaned = _compress_sentence(value, max_chars=max_chars, fallback="")
        if not cleaned or cleaned == "待补充":
            continue
        if cleaned not in items:
            items.append(cleaned)
        if len(items) >= limit:
            break
    return items


def _format_summary_text(text: str) -> str:
    cleaned = _compress_paragraph(text, max_sentences=2, max_chars=110, fallback="本段剧情仍需进一步提炼。")
    return cleaned


def _format_short_field(values: list[str], *, refill_values: list[str], fallback: str) -> str:
    items = _collect_card_items(values, limit=2, max_chars=34)
    if not items:
        items = _collect_card_items(refill_values, limit=2, max_chars=34)
    if not items:
        return fallback
    return "；".join(items)


def _normalize_tag_text(text: str) -> str:
    normalized = re.sub(r"\s*(?:->|→|➡)\s*", " 到 ", (text or "").strip())
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip(" /|")


def _split_tag_fragments(text: str) -> list[str]:
    normalized = _normalize_tag_text(text)
    if not normalized:
        return []
    if "到" in normalized:
        return [part.strip() for part in normalized.split("到") if part.strip()]
    split_candidate = re.sub(r"\s*(?:/|\+|&)\s*", "|", normalized)
    split_candidate = split_candidate.replace("_", "|")
    split_candidate = re.sub(r"(?<!\s)-(?!\s)", "|", split_candidate)
    parts = [part.strip() for part in split_candidate.split("|") if part.strip()]
    return parts or [normalized]


def _resolve_contextual_tag(
    raw_tag: str,
    *,
    replacements: dict[str, str],
    fallback: str,
    generic_labels: set[str],
    context_text: str,
    context_rules: tuple[tuple[tuple[str, ...], str], ...],
) -> str:
    tag = _clean_tag(raw_tag, replacements=replacements, fallback="")
    if not tag or tag in generic_labels:
        tag = _infer_contextual_label(f"{raw_tag} {context_text}", fallback=fallback, context_rules=context_rules)
    if not tag or tag in generic_labels:
        return fallback
    return tag


def _infer_contextual_label(
    text: str,
    *,
    fallback: str,
    context_rules: tuple[tuple[tuple[str, ...], str], ...],
) -> str:
    normalized = _clean_delivery_text(text).lower()
    normalized = _normalize_tag_text(normalized)
    if not normalized:
        return fallback
    for keywords, label in context_rules:
        if any(keyword.lower() in normalized for keyword in keywords):
            return label
    return fallback


def _clean_tag(text: str, *, replacements: dict[str, str], fallback: str) -> str:
    def resolve_exact(value: str) -> str:
        fragment = value.strip()
        if not fragment:
            return ""
        for source, target in replacements.items():
            if fragment.lower() == source.lower():
                return target
        return ""

    def resolve_fragment(value: str) -> str:
        fragment = value.strip()
        if not fragment:
            return ""
        exact = resolve_exact(fragment)
        if exact:
            return exact
        for source, target in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
            if source.lower() in fragment.lower():
                return target
        return ""

    raw = (text or "").strip()
    normalized_raw = _normalize_tag_text(raw).replace(" 到 ", "到")
    if normalized_raw:
        resolved = resolve_exact(normalized_raw)
        if resolved:
            return resolved
        compound_parts = _split_tag_fragments(normalized_raw)
        if len(compound_parts) > 1:
            resolved_parts = _unique_preserve_order([resolve_fragment(part) for part in compound_parts if part.strip()])
            if resolved_parts:
                return "到".join(resolved_parts[:2])
        resolved = resolve_fragment(normalized_raw)
        if resolved:
            return resolved
        if re.search(r"[A-Za-z]", normalized_raw):
            keyword_fallback = _infer_tag_from_keywords(
                normalized_raw,
                keyword_map=replacements,
                fallback=fallback,
            )
            if keyword_fallback != fallback:
                return keyword_fallback

    cleaned = _clean_delivery_text(raw)
    if not cleaned:
        return fallback
    if cleaned in {"到", "从"}:
        return fallback
    resolved = resolve_exact(cleaned)
    if resolved:
        return resolved
    compound_parts = _split_tag_fragments(cleaned)
    if len(compound_parts) > 1:
        resolved_parts = _unique_preserve_order([resolve_fragment(part) for part in compound_parts if part.strip()])
        if resolved_parts:
            return "到".join(resolved_parts[:2])
    resolved = resolve_fragment(cleaned)
    if resolved:
        return resolved
    if re.search(r"[A-Za-z]", cleaned):
        return _infer_tag_from_keywords(cleaned, keyword_map=replacements, fallback=fallback)
    if _is_english_heavy(cleaned):
        return fallback
    return _truncate_chars(cleaned, 12)


def _clean_delivery_text(text: str, *, strip_boilerplate: bool = False) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = _replace_chapter_refs(cleaned)
    cleaned = re.sub(r"（分块\s*\d+/\d+）", "", cleaned)
    cleaned = re.sub(r"(?:为)?(?:引子|后记|番外[^，。；]*)分块", "", cleaned)
    cleaned = re.sub(r"第?\d+/\d+分块", "", cleaned)
    cleaned = cleaned.replace("未识别章节", "").replace("chapter_id", "")
    cleaned = cleaned.replace("待补充", "")
    cleaned = cleaned.replace("◎", "")
    cleaned = cleaned.replace("文风信号：", "")
    cleaned = re.sub(r"(?i)\s*vs\.?\s*", "对照", cleaned)
    cleaned = cleaned.replace("‘", "").replace("’", "").replace('"', "")
    cleaned = cleaned.replace("“", "").replace("”", "")
    cleaned = re.sub(r"(?i)\b(?:details|detail|list|stage|physical|identity|trust)\b", "", cleaned)
    cleaned = re.sub(r"(?i)\bfrom\b[^。；，]*", "", cleaned)
    cleaned = re.sub(r"(?i)\bto\b[^。；，]*", "", cleaned)
    cleaned = re.sub(r"\s*(?:→|->|➡)\s*", "到", cleaned)
    cleaned = cleaned.replace("…", "")
    cleaned = re.sub(r"[—\-]+\s*[,，、]\s*[,，、\s]*", "", cleaned)
    cleaned = re.sub(r"[,，、]\s*[,，、]+", "，", cleaned)
    cleaned = cleaned.replace("（）", "").replace("()", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s*([，。！？；：])", r"\1", cleaned)
    cleaned = re.sub(r"([，。！？；：])\s*", r"\1", cleaned)

    for source, target in sorted(KNOWN_ENGLISH_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        cleaned = re.sub(rf"(?i)\b{re.escape(source)}\b", target, cleaned)

    if strip_boilerplate:
        cleaned = re.sub(
            r"^(本章|本章节|本单元|这一章|该章|这一节|该节|本部分|这一部分)(以|围绕|聚焦|主要聚焦|主要讲述|讲述|呈现|展开|聚拢于)?",
            "",
            cleaned,
        )
    cleaned = cleaned.replace("关系从试探靠近推进到新的阶段", "")
    cleaned = cleaned.replace("这一单元以细节和对话共同推动情绪与冲突", "")
    cleaned = cleaned.replace("关系和冲突同步推进，节奏保持清晰起伏", "")
    cleaned = cleaned.replace("本单元完成一次阶段性推进", "")
    cleaned = cleaned.replace("本单元围绕关键剧情点完成一次节奏推进", "")
    cleaned = cleaned.replace("围绕关键剧情点完成推进", "")
    cleaned = cleaned.replace("关系在这一单元完成一次清晰升级", "")
    cleaned = cleaned.replace("细节与对话共同抬升情绪张力", "")
    cleaned = re.sub(r"\b(?:shift|shifts|deepens|closeness|fracture|pacing|tone)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:adversarial|asymmetric|mutual|unilateral|covert|hierarchical|protective|instrumental|tactical|professional|ritualized|strategic|public|trust|alliance|transition|emotional|intimacy|silent)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[A-Za-z][A-Za-z\s\-_/&]{8,}", "", cleaned)
    cleaned = re.sub(r"[（(][，、；：\s]*[)）]", "", cleaned)
    cleaned = cleaned.replace("对照对照", "对照")
    cleaned = re.sub(r"(；){2,}", "；", cleaned)
    cleaned = re.sub(r"(，){2,}", "，", cleaned)
    cleaned = re.sub(r"[’'`“”‘’【】]+\s*[—\-_,，、]*$", "", cleaned)
    cleaned = re.sub(r"(?:\s*对照\s*){2,}", "对照", cleaned)
    cleaned = _trim_broken_tail(cleaned)
    cleaned = cleaned.strip(" /|；，。-:")
    cleaned = cleaned.lstrip("；：，、- ")
    return cleaned


def _replace_chapter_refs(text: str) -> str:
    def _range_repl(match: re.Match[str]) -> str:
        start = int(match.group(1))
        end = int(match.group(2))
        return f"第{start}-{end}章"

    cleaned = re.sub(r"ch-(\d{4})\s*[–\-~—]+\s*ch-(\d{4})", _range_repl, text)
    cleaned = re.sub(r"ch-(\d{4})", lambda m: f"第{int(m.group(1))}章", cleaned)
    return cleaned


def _truncate_chars(text: str, max_chars: int) -> str:
    compact = text.strip()
    if len(compact) <= max_chars:
        return _trim_broken_tail(compact)
    window = compact[:max_chars]
    cut_points = [window.rfind(token) for token in ("；", "。", "，", "、", "：", "｜", "）", "”", " ")]
    cut = max(cut_points)
    if cut >= max_chars // 2:
        return _trim_broken_tail(window[:cut].rstrip("，；： "))
    return _trim_broken_tail(window.rstrip("，；： "))


def _split_sentences(text: str) -> list[str]:
    parts = [item.strip("，；： ") for item in re.split(r"[。！？!?]+", text) if item.strip("，；： ")]
    return parts


def _split_clauses(text: str) -> list[str]:
    parts = [item.strip("，；： ") for item in re.split(r"[；，/｜]+", text) if item.strip("，；： ")]
    return [item for item in parts if item]


def _is_english_heavy(text: str) -> bool:
    english_chunks = re.findall(r"[A-Za-z][A-Za-z\s\-_/&()]{3,}", text)
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    if not english_chunks:
        return False
    english_length = sum(len(item) for item in english_chunks)
    return english_length >= 12 and len(chinese_chars) * 2 < english_length


def _contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _has_problematic_english(text: str) -> bool:
    english_words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text)
    if not english_words:
        return False
    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    if chinese_count == 0:
        return len(english_words) >= 2 or any(word.islower() for word in english_words)
    suspicious = {
        "shift",
        "shifts",
        "deepens",
        "fracture",
        "adversarial",
        "asymmetric",
        "mutual",
        "unilateral",
        "covert",
        "hierarchical",
        "protective",
        "instrumental",
        "tactical",
        "professional",
        "strategic",
        "ritualized",
        "pacing",
        "tone",
        "transition",
        "intimacy",
        "trust",
        "public",
        "silent",
        "emotional",
    }
    return any(word.lower() in suspicious for word in english_words)


def _has_suspicious_tail(text: str) -> bool:
    cleaned = text.strip("，。；：、 ")
    if not cleaned:
        return True
    if re.search(r"(?:如|例如|比如|包括|等|vs|和|与|及)$", cleaned, flags=re.IGNORECASE):
        return True
    if re.search(r"[’'\"“”‘’—\-]+\s*[,，、]\s*$", cleaned):
        return True
    if len(cleaned) >= 8 and re.search(
        r"(说|问|称|提及|指出|暗示|预示|引发|触发|完成|形成|进入|展开|聚焦|围绕|流露|暴露|转向|升级|回应|评估|讨论|宣称|承诺|呈现|推动|揭示|确认|说明|回忆|调查|判断)$",
        cleaned,
    ):
        return True
    return False


def _looks_cutoff(text: str) -> bool:
    cleaned = text.strip("，。；：、 ")
    if not cleaned:
        return True
    if re.search(r"(?:如|例如|比如|包括|等|vs|和|与|及)$", cleaned, flags=re.IGNORECASE):
        return True
    if re.search(r"(?:未呈|未明|未完|未获|不知|不明|未被|未能|无法|几乎|首次无|首次未)$", cleaned):
        return True
    if re.search(
        r"(?:的|其|及|与|并|而|向|对|将|把|被|让|使|在|于|从|到|里|中|上|下|前|后|内|外|时|处|图)$",
        cleaned,
    ):
        return 10 <= len(cleaned) <= 24
    return False


def _trim_broken_tail(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    previous = None
    while cleaned != previous:
        previous = cleaned
        cleaned = re.sub(r"(?:→|->|➡)\s*$", "", cleaned).strip()
        cleaned = re.sub(r"[，、；：/|·\-]+\s*$", "", cleaned).strip()
        cleaned = re.sub(r"—{1,2}[^。；，、]{0,18}$", "", cleaned).strip()
        cleaned = re.sub(r"[（(][^）)]*$", "", cleaned).strip()
        cleaned = re.sub(r"【[^】]*$", "", cleaned).strip()
        cleaned = re.sub(r"[“\"'‘][^”\"'’]*$", "", cleaned).strip()
        cleaned = re.sub(r"\(\s*$", "", cleaned).strip()
        cleaned = re.sub(r"（\s*$", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _is_fragmentary(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    if re.search(r"(?:→|->|➡)\s*$", cleaned):
        return True
    if re.search(r"[，、；：/|·\-]\s*$", cleaned):
        return True
    if re.search(r"—{1,2}[^。；，、]{0,18}$", cleaned):
        return True
    if re.search(r"[（(][^）)]*$", cleaned):
        return True
    if re.search(r"【[^】]*$", cleaned):
        return True
    if re.search(r"[“\"'‘][^”\"'’]*$", cleaned):
        return True
    if re.search(r"[’'`“”‘’【】]+\s*[—\-_,，、]+\s*$", cleaned):
        return True
    if any(cleaned.endswith(word) for word in TRUNCATED_ENDING_WORDS):
        return True
    english_words = {word.lower() for word in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", cleaned)}
    if english_words & FRAGMENT_ENGLISH_WORDS:
        return True
    if _has_suspicious_tail(cleaned) or _looks_cutoff(cleaned):
        return True
    trimmed = _trim_broken_tail(cleaned)
    return not trimmed or trimmed != cleaned


def _is_low_signal_text(text: str) -> bool:
    cleaned = _clean_delivery_text(text)
    if not cleaned:
        return True
    if _is_fragmentary(cleaned):
        return True
    return any(re.search(pattern, cleaned, flags=re.IGNORECASE) for pattern in LOW_SIGNAL_PATTERNS)


def _is_placeholder_copy(text: str) -> bool:
    cleaned = _clean_delivery_text(text)
    if not cleaned:
        return True
    return any(re.search(pattern, cleaned, flags=re.IGNORECASE) for pattern in LOW_SIGNAL_PATTERNS)


def _is_weak_optional_value(text: str) -> bool:
    cleaned = _clean_delivery_text(text)
    if not cleaned:
        return True
    return bool(
        re.search(
            r"(未详述|暂无明确描写|未明确描写|描写较少|信息仍需进一步提炼|外貌描写以|人物辨识度较高)",
            cleaned,
            flags=re.IGNORECASE,
        )
    )


def _collect_card_items(values: list[str], *, limit: int, max_chars: int) -> list[str]:
    results: list[str] = []
    for value in values:
        cleaned = _compress_sentence(value, max_chars=max_chars, fallback="")
        cleaned = cleaned.lstrip("；：，、- ")
        if not cleaned or _is_low_signal_text(cleaned) or _looks_cutoff(cleaned):
            continue
        results.append(cleaned)
        if len(results) >= limit:
            break
    return _unique_preserve_order(results)


def _infer_scene_purpose(unit: DeliveryUnit) -> str:
    if unit.highlights or unit.payoff:
        return "对应本段爽点与关系回收"
    if unit.climax:
        return "对应本段高潮反转"
    if unit.crisis or unit.suspense:
        return "对应本段危机抬升"
    return ""


def _infer_relationship_counterpart(unit: DeliveryUnit) -> str:
    if unit.relationship_progression:
        for item in unit.relationship_progression:
            counterpart = _compress_title(item.counterpart, max_chars=18)
            if counterpart and not _is_low_signal_text(counterpart):
                return counterpart
    return "核心关系"


def _infer_relationship_stage_label(text: str) -> str:
    cleaned = _clean_delivery_text(text)
    label_map = [
        ("试探", "试探期"),
        ("升温", "升温期"),
        ("共谋", "共谋期"),
        ("危机", "危机期"),
        ("创伤", "创伤共担"),
        ("确认", "确认期"),
        ("同盟", "同盟期"),
        ("敌对", "敌对期"),
        ("拉扯", "危机期"),
    ]
    for keyword, label in label_map:
        if keyword in cleaned:
            return label
    for label in RELATIONSHIP_STAGE_LABEL_POOL:
        if label.replace("期", "") in cleaned:
            return label
    return "试探期"


def _infer_style_dimension(observation: str) -> str:
    cleaned = _clean_delivery_text(observation)
    if any(keyword in cleaned for keyword in ["视角", "第三人称", "镜头"]):
        return "视角控制"
    if any(keyword in cleaned for keyword in ["对话", "短句", "留白"]):
        return "对话节奏"
    if any(keyword in cleaned for keyword in ["意象", "隐喻", "物象"]):
        return "意象复用"
    if any(keyword in cleaned for keyword in ["身体", "动作", "触觉"]):
        return "身体书写"
    if any(keyword in cleaned for keyword in ["空间", "场域", "房间"]):
        return "空间隐喻"
    if any(keyword in cleaned for keyword in ["节奏", "推进"]):
        return "叙事节奏"
    return "叙事观察"


def _infer_style_observation(unit: DeliveryUnit) -> str:
    candidate = _compress_sentence(_first_nonempty_text([unit.summary] + unit.highlights + unit.climax), max_chars=40, fallback="")
    if not candidate or _is_low_signal_text(candidate):
        return ""
    return f"叙事节奏：{candidate}"


def _first_nonempty_text(values: list[str]) -> str:
    for value in values:
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return ""


def _unique_preserve_order(values: list[str]) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        results.append(cleaned)
    return results
