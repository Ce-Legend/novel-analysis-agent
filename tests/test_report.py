import re

from novel_agent.analysis.book import build_delivery_units, postprocess_book_analysis
from novel_agent.exporters.report import (
    DELIVERY_SECTION_ORDER,
    ReportBlock,
    _format_beat_rhythm,
    build_delivery_integrity_review,
    build_delivery_report,
    repair_delivery_report_blocks,
    render_report_markdown,
)
from novel_agent.schemas import (
    AudiencePositioning,
    BeatRhythmItem,
    BookAnalysis,
    ChapterAnalysis,
    CharacterProfile,
    CPAnalysis,
    CPTopic,
    DeliveryUnit,
    HighlightSummaryItem,
    OpeningCraft,
    PhaseOutlineItem,
    PlotEvent,
    PlotOutline,
    RelationshipProgression,
    RelationshipStage,
    SceneQuoteItem,
    SellingPointItem,
    StoryHookLayers,
    StoryLineItem,
    StyleSignal,
    StyleSummary,
    TitleIntroAnalysis,
    WritingBreakdown,
)


def test_delivery_report_sanitizes_internal_refs_and_english_labels() -> None:
    unit = DeliveryUnit(
        unit_id="unit-001",
        title="引子",
        base_title="引子",
        chapter_refs=["ch-0001", "ch-0002"],
        chapter_range="第1-2章",
        summary="本章聚焦主角重逢并迅速进入试探关系，同时完成第一次关键交锋。",
        crisis=["双方都在隐藏真实动机，信任基础极弱。"],
        foreshadowing=["旧日关系和后续合作都已提前埋线。"],
        suspense=["她到底是来赴约，还是来设局→"],
        climax=["洗手间里确认关系边界，局势瞬间反转（"],
        highlights=["初遇即确定名分，关系推进极快，details"],
        beat_rhythm=[
            BeatRhythmItem(
                beat="ch-0001 初遇对峙",
                pacing_tag="controlled detachment",
                emotion_tag="desire",
                note="from calculated seduction to mutual destabilization list",
            )
        ],
        scene_quotes=[
            SceneQuoteItem(
                scene="洗手间里的近距离试探",
                quote="赵壹笙，我只和女朋友接吻。",
                purpose="形成全书首个高辨识关系锚点。",
            )
        ],
        relationship_progression=[
            RelationshipProgression(
                counterpart="赵壹笙 & 卓舒清",
                stage_label="strategic entanglement",
                change="Faye shifts from romantic partner to operational asset.",
            ),
            RelationshipProgression(
                counterpart="周易",
                stage_label="待补充",
                change="关系进入新的推进节点。",
            ),
        ],
        style_signals=[
            StyleSignal(
                dimension="narrative voice",
                observation="身体叙述：身体层面 details (",
            )
        ],
    )
    book = BookAnalysis(
        title="测试书",
        overview="这是一个关于重逢、试探与关系升级的故事。",
        selling_points=["双强对峙", "开篇起势快"],
        audience_positioning=AudiencePositioning(
            comparable_titles=["对标作品A"],
            reader_profiles=["偏好高张力关系推进的读者"],
            marketing_keywords=["双强", "试探"],
            short_term_highlights=["开篇迅速起势"],
            mid_term_highlights=["关系持续拉扯"],
            long_term_highlights=["主线和情感线回收"],
        ),
        title_intro_analysis=TitleIntroAnalysis(
            title_analysis="标题直接点题核心关系。",
            core_hook="重逢即设局，关系同步升温。",
            genre="现代情感",
            intro_analysis="简介强调人物重逢和初始危机。",
            chapter_name_analysis="章节标题围绕关系推进展开。",
        ),
        cp_analysis=CPAnalysis(
            summary="两位主角在试探中逐步确认彼此的重要性。",
            relationship_tension=["靠近与防备并存"],
            stage_progression=["初遇试探", "关系升温"],
            catalyst_roles=["现实压力"],
            emotional_hooks=["第一次确认名分"],
        ),
        main_outline=[],
        delivery_units=[unit],
        relationship_timeline=[
            RelationshipStage(
                pair="赵壹笙 & 卓舒清",
                stage_label="初遇试探",
                chapter_refs=["ch-0001", "ch-0002"],
                description="关系从 ch-0001 的互相打量推进到 ch-0002 的名分确认。",
            )
        ],
        writing_breakdown=WritingBreakdown(
            writing_analysis="冷感克制中带着明显的情欲拉扯。",
            opening_method="开篇直接抛出重逢和互动。",
            dialogue_design="对话承担试探和确认功能。",
            action_detail="动作细节密集。",
            language_style="克制利落。",
        ),
        style_summary=StyleSummary(
            narrative_pacing="起势快，推进稳。",
            information_release="信息逐步释放。",
            conflict_design="冲突和关系同步推进。",
            emotional_leverage="通过试探拉高张力。",
            characterization="人物通过对话和动作建立。",
            language_style="冷感克制。",
            hook_and_payoff="开篇钩子明确。",
        ),
    )

    markdown = render_report_markdown(build_delivery_report(book, []))

    assert "ch-0001" not in markdown
    assert "narrative voice" not in markdown.lower()
    assert "strategic entanglement" not in markdown.lower()
    assert "Faye shifts" not in markdown
    assert "…" not in markdown
    assert "details" not in markdown.lower()
    assert "list" not in markdown.lower()
    assert "→" not in markdown
    assert "未命名条目" not in markdown
    assert "待补充" not in markdown
    assert "关系进入新的推进节点" not in markdown
    assert "本单元完成一次清晰推进" not in markdown
    assert "第1-2章" in markdown
    assert "叙述视角" in markdown or "文风信号" in markdown


def test_delivery_report_drops_cutoff_summary_fragments() -> None:
    unit = DeliveryUnit(
        unit_id="unit-001",
        title="试探其对同性关系及赵壹笙的态度",
        chapter_refs=["ch-0057", "ch-0058"],
        chapter_range="第57-58章",
        summary="卓舒清回邺城向父亲Charles坦白自己为赵壹笙介入与江家事务。",
        crisis=["卓舒清担忧父亲反对其性取向及对赵壹笙的扶持行为；赵壹笙在暴雨中赴约HCBC"],
        foreshadowing=["Charles悄然离开未被察觉——暗示其默许甚至纵容；平井咲问"],
        suspense=["赵壹笙全程不确定Charles真实态度：是宽容；卓舒清在父亲问出‘你有兴趣接手家业吗’时的犹豫"],
        climax=["赵壹笙说出‘阿清’后Charles回应；Charles临时改约"],
        highlights=["赵壹笙在胡同宅院前顿悟‘阿清’称谓即家族准入凭证；赵壹笙此前控制碳水、规律作息等休养行为获得卓舒清明确"],
        scene_quotes=[
            SceneQuoteItem(
                scene="卓舒清回邺城向父亲Charles坦白自己为赵壹笙",
                quote="这份方案，和不久前换CEO的那场董事会上赵壹笙给",
                purpose="提炼本章最强记忆点",
            )
        ],
        relationship_progression=[
            RelationshipProgression(counterpart="卓舒清", stage_label="关系变化", change="从父权单向规训转向双向尊重边界。"),
        ],
        style_signals=[
            StyleSignal(dimension="文风信号", observation="关键转折全由潜台词驱动：如Charles问‘你平常就叫她Cathy吗’实为测试亲"),
        ],
    )
    book = BookAnalysis(title="测试书", delivery_units=[unit])

    markdown = render_report_markdown(build_delivery_report(book, []))

    assert "平井咲问" not in markdown
    assert "实为测试亲" not in markdown
    assert "这份方案，和不久前换CEO的那场董事会上赵壹笙给" not in markdown
    assert "关键场面｜作用：提炼本章最强记忆点" not in markdown
    assert "关系变化：;" not in markdown
    assert "文风信号：关键转折全由潜台词驱动" not in markdown


def test_delivery_report_preserves_story_line_and_repairs_unit_heading() -> None:
    unit = DeliveryUnit(
        unit_id="unit-029",
        title="以‘叔叔您好",
        chapter_refs=["ch-0057", "ch-0058"],
        chapter_range="第57-58章",
        summary="卓舒清回邺城与父亲摊牌，赵壹笙随后正式见家长并进入更深层的关系确认。",
        scene_quotes=[
            SceneQuoteItem(scene="见家长开场白", quote="叔叔您好，我是赵壹笙。", purpose="把关系从私人推进到家族秩序。"),
        ],
    )
    book = BookAnalysis(
        title="测试书",
        overview="赵壹笙与卓舒清的关系在主线压力下持续升级。",
        plot_outline=PlotOutline(
            story_lines=[
                StoryLineItem(
                    name="情感主线",
                    category="核心线索",
                    content="赵壹笙与卓舒清从KTV初遇到法律绑定的情感螺旋演进",
                    key_points=["KTV告白接吻", "同居日常"],
                )
            ]
        ),
        relationship_timeline=[
            RelationshipStage(
                pair="赵壹笙 & 卓舒清",
                stage_label="创伤共担",
                chapter_refs=["ch-0051", "ch-0052"],
                chapter_range="第51-52章",
                core_change="双方开始把旧伤和代价一起扛起来",
                pressure="旧伤回潮让两人必须面对更深层的脆弱",
                payoff="信任开始从情绪安慰转向共同承担",
                description="双方开始把旧伤和代价一起扛起来；压力：旧伤回潮让两人必须面对更深层的脆弱；回收：信任开始从情绪安慰转向共同承担",
            )
        ],
        delivery_units=[unit],
    )

    markdown = render_report_markdown(build_delivery_report(book, []))

    assert "情感主线｜核心线索：赵壹笙与卓舒清从KTV初遇到法律绑定的情感螺旋演进" in markdown
    assert "赵壹笙 & 卓舒清 / 创伤共担（第51-52章）" in markdown
    assert "未命名条目" not in markdown
    assert "### 以‘叔叔您好（第57-58章）" not in markdown
    assert re.search(r"### (?!关键推进)[^\n]+（第57-58章）", markdown)


def test_delivery_report_skips_weak_character_appearance_and_generic_style_copy() -> None:
    book = BookAnalysis(
        title="人物卡测试书",
        character_profiles=[
            CharacterProfile(
                name="赵壹笙",
                basic_info="核心视角人物。",
                appearance="未详述",
                personality_traits=["克制", "高执行力"],
                major_experiences=["重逢后主动布局", "中段承接关系与主线压力"],
                relationships=["与卓舒清形成核心拉扯"],
            )
        ],
        delivery_units=[
            DeliveryUnit(
                unit_id="unit-001",
                title="试探升温",
                chapter_refs=["ch-0001"],
                chapter_range="第1章",
                summary="主角在试探中完成第一次关系升级。",
                style_signals=[StyleSignal(dimension="文风信号", observation="文风信号：细节与对话共同抬升情绪张力。")],
            )
        ],
    )

    markdown = render_report_markdown(build_delivery_report(book, []))

    assert "外貌特点：未详述" not in markdown
    assert "文风信号：细节与对话共同抬升情绪张力" not in markdown


def test_delivery_report_matches_reference_template_sections() -> None:
    book = BookAnalysis(
        title="模板测试书",
        overview="这是一个围绕关系拉扯与主线推进展开的故事。",
        highlights_summary=[
            HighlightSummaryItem(title="高概念起势", detail="开篇迅速抛出关系冲突与角色张力。"),
        ],
        selling_points_detail=[
            SellingPointItem(category="情感向", detail="关系推进与现实阻力同步抬升。"),
        ],
        story_hook_layers=StoryHookLayers(
            short_term=["开篇重逢与试探"],
            mid_term=["关系与主线双线升级"],
            long_term=["主线与情感线闭环回收"],
        ),
        audience_positioning=AudiencePositioning(
            comps=["对标作品A"],
            reader_profile=["偏好强张力关系推进的读者"],
            marketing_keywords=["双强", "拉扯"],
        ),
        core_hooks=["主线梗示例", "副线梗A", "副线梗B"],
        title_intro_analysis=TitleIntroAnalysis(
            title_analysis="标题直接点题人物关系。",
            core_hook="一句总梗示例。",
            genre="现代情感",
            intro_analysis="简介强调人物重逢和现实阻力。",
            chapter_name_analysis="章节名围绕阶段推进命名。",
        ),
        character_profiles=[
            CharacterProfile(
                name="主角A",
                basic_info="核心行动方。",
                appearance="外在标识明显。",
                personality_traits=["执行力强", "情绪克制"],
                major_experiences=["开篇推进主线", "中段承接危机"],
                relationships=["与主角B形成核心张力"],
            )
        ],
        cp_analysis=CPAnalysis(
            summary="主 CP 在现实压力下持续拉扯。",
            topics=[
                CPTopic(topic="初期建设", analysis="快速建立关系起点。"),
                CPTopic(topic="矛盾与拉扯", analysis="关系推进伴随现实阻力。"),
                CPTopic(topic="第三方催化", analysis="外部压力不断加码。"),
                CPTopic(topic="身体记忆", analysis="高辨识动作形成张力。"),
                CPTopic(topic="细节线索", analysis="物件与台词持续回收。"),
                CPTopic(topic="终极爆发", analysis="后段完成关系闭环。"),
            ],
        ),
        plot_outline=PlotOutline(
            story_lines=[StoryLineItem(name="核心主线", category="主线", content="围绕主线冲突推进。", key_points=["关系建立", "主线升级"])],
            phase_outline=[PhaseOutlineItem(phase="起", chapter_range="第1-3章", events=["开篇建立关系与冲突"])],
        ),
        opening_craft=OpeningCraft(
            core_payoffs=["开篇强互动"],
            core_pain_points=["现实阻力同步压下"],
            flirty_moments=["关键暧昧桥段"],
            character_building=["人物通过选择建立性格"],
            dialogue_design=["对话承担试探和确认"],
            action_details=["动作细节服务情绪变化"],
        ),
        relationship_timeline=[
            RelationshipStage(pair="主角A & 主角B", stage_label="试探期", chapter_refs=["ch-0001"], chapter_range="第1章", description="从初遇进入试探。")
        ],
        delivery_units=[
            DeliveryUnit(unit_id="unit-001", title="初遇试探", chapter_refs=["ch-0001"], chapter_range="第1章", summary="本单元完成第一次关系推进。")
        ],
        writing_breakdown=WritingBreakdown(
            writing_analysis="写法以短句判断和桥段举证为主。",
            opening_method="开篇快速抛出关系与现实冲突。",
            dialogue_design="对话承担试探与确认功能。",
            action_detail="动作细节承载情绪变化。",
            language_style="短句利落。",
        ),
        style_summary=StyleSummary(
            narrative_pacing="起势快。",
            information_release="信息逐步释放。",
            conflict_design="冲突与关系同步推进。",
            emotional_leverage="情绪拉扯明确。",
            characterization="人物通过动作和选择建立。",
            language_style="短句利落。",
            hook_and_payoff="钩子与回收清晰。",
        ),
    )

    markdown = render_report_markdown(build_delivery_report(book, []))
    top_level_sections = [line.removeprefix("## ").strip() for line in markdown.splitlines() if line.startswith("## ")]

    assert top_level_sections == DELIVERY_SECTION_ORDER
    assert "## 核心亮点总结" in markdown
    assert "## 核心卖点" in markdown
    assert "## 剧情看点分层" in markdown
    assert "## 核心梗" in markdown
    assert "## 开篇文法分析" in markdown
    assert "基本信息" in markdown
    assert "支撑桥段" in markdown


def test_build_delivery_units_generates_readable_titles_for_generic_units() -> None:
    chapters = [
        ChapterAnalysis(
            chapter_id="ch-0001",
            title="第0章 引子（分块 1/2）",
            summary="本章以同学聚会重逢为引，迅速建立主角之间的试探与拉扯。",
            crisis=["双方都在隐藏真实目的。"],
            relationship_progression=[RelationshipProgression(counterpart="主 CP", stage_label="初遇试探", change="关系从陌生进入试探。")],
        ),
        ChapterAnalysis(
            chapter_id="ch-0002",
            title="第0章 引子（分块 2/2）",
            summary="二人顺着留宿与近距离互动继续试探，关系明显升温。",
            climax=["留宿后的近距离互动让关系迅速升温。"],
            relationship_progression=[RelationshipProgression(counterpart="主 CP", stage_label="关系升温", change="从试探进入明显靠近。")],
        ),
    ]

    units = build_delivery_units(chapters)

    assert len(units) == 1
    assert units[0].title != "引子"
    assert "分块" not in units[0].title
    assert "叙事单元" not in units[0].title
    assert len(units[0].title) <= 18


def test_delivery_report_preserves_complete_quoted_sentences_and_skips_low_signal_theme_items() -> None:
    book = BookAnalysis(
        title="主题过滤测试书",
        highlights_summary=[
            HighlightSummaryItem(title="未命名条目", detail="肺动脉高压、胃出血等医疗细节强化生理真实感，并反向抬高情感压力。"),
            HighlightSummaryItem(title="情感与资本的精密耦合", detail="信息仍需进一步提炼。"),
        ],
        title_intro_analysis=TitleIntroAnalysis(
            title_analysis="标题直接点题关系内核。",
            core_hook="久别重逢之后，双方都发现这场相遇早有伏笔。",
            genre="都市情感",
            intro_analysis="开篇以同学会重逢切入，表面是偶然重聚，实为赵壹笙与齐简臻策划的‘捕获行动’，迅速建立高张力情感起点。",
            chapter_name_analysis="章节名围绕阶段推进命名。",
        ),
    )

    markdown = render_report_markdown(build_delivery_report(book, []))

    assert "简介分析：开篇以同学会重逢切入" in markdown
    assert "未命名条目" not in markdown
    assert "### 情感与资本的精密耦合" not in markdown


def test_delivery_report_preserves_field_specific_copy_without_placeholder_fallbacks() -> None:
    book = BookAnalysis(
        title="字段专用渲染测试书",
        overview="这是一个围绕重逢、试探与现实博弈展开的故事。",
        title_intro_analysis=TitleIntroAnalysis(
            title_analysis="标题直接点出久别重逢与双向试探。",
            core_hook="重逢即设局，情感和权力同步开战。",
            genre="都市情感+金融职场+百合向",
            intro_analysis="简介先把猎人与猎物的错位关系抛出来，所以读者会立刻进入局中局。",
            chapter_name_analysis="章节名把情感推进包装成职场协作语言。",
        ),
        character_profiles=[
            CharacterProfile(
                name="康壹竽",
                basic_info="核心侧翼角色。",
                appearance="   ",
                personality_traits=["果断"],
                major_experiences=["推动姐妹线进入主线"],
                relationships=["与赵壹笙互为创伤映照"],
            ),
            CharacterProfile(
                name="方新箬",
                basic_info="关系见证者。",
                appearance="外貌描写以气质、动作与身体细节呈现，人物辨识度较高。",
                personality_traits=["敏锐"],
                major_experiences=["见证关系回收"],
                relationships=["与康壹竽形成长期牵引"],
            ),
        ],
        cp_analysis=CPAnalysis(
            summary="这对关系的抓人处在于情感吸引和现实博弈始终同步升温。",
            topics=[
                CPTopic(
                    topic="身体记忆",
                    analysis="这对的好嗑点在创伤、照料和欲望都会被身体细节记住，所以每次回收都像关系再次落锚。",
                    supporting_moments=["第一次近距离试探", "病中照料形成身体记忆"],
                )
            ],
        ),
        writing_breakdown=WritingBreakdown(
            writing_analysis="以冷感反讽为基底，高频使用身体书写、专业术语软化与空间政治隐喻，将情感线和金融战场牢牢缝在一起。",
            opening_method="开篇直接设局。",
            dialogue_design="对话承担试探与确认。",
            action_detail="动作细节服务情绪变化。",
            language_style="冷感反讽+高密度感官修辞",
        ),
        style_summary=StyleSummary(
            narrative_pacing="起势快，回收密。",
            information_release="信息通过对话和物件回收逐步放出。",
            conflict_design="情感与权力双轨并进。",
            emotional_leverage="以病态躯体、创伤记忆与生死危机撬动情感高潮",
            characterization="通过微动作与感官细节构建人物",
            language_style="冷感反讽+高密度感官修辞",
            hook_and_payoff="每章以悬念启动，以情感爆破点收束。",
        ),
    )

    markdown = render_report_markdown(build_delivery_report(book, []))

    assert "类型：都市情感+金融职场+百合向" in markdown
    assert "简介分析：简介先把猎人与猎物的错位关系抛出来" in markdown
    assert "写法分析：以冷感反讽为基底" in markdown
    assert "情绪调动：以病态躯体、创伤记忆与生死危机撬动情感高潮" in markdown
    assert "人物塑造：通过微动作与感官细节构建人物" in markdown
    assert "语言风格：冷感反讽+高密度感官修辞" in markdown
    assert "康壹竽" in markdown
    assert "方新箬" in markdown
    assert "外貌特点：信息仍需进一步提炼" not in markdown
    assert markdown.count("外貌特点：") == 0
    assert "信息仍需进一步提炼" not in markdown


def test_delivery_report_tightens_long_overview_into_shorter_editorial_copy() -> None:
    book = BookAnalysis(
        title="综述压缩测试书",
        overview="小说以双向狩猎关系为主线，串联资本博弈与家族旧账；主角一边推进复仇计划，一边在亲密关系里不断失衡；人物关系、主线风险与身体创伤彼此缠绕，最终完成情感与权力的双重回收；并在终局把前文所有悬念统一闭环。",
    )

    markdown = render_report_markdown(build_delivery_report(book, []))

    assert "并在终局把前文所有悬念统一闭环" not in markdown
    assert "双向狩猎关系为主线" in markdown
    assert "资本博弈与家族旧账" in markdown


def test_delivery_report_adds_editorial_overview_followup_and_style_lead() -> None:
    book = BookAnalysis(
        title="文案抛光测试书",
        overview="小说先用双强关系起势，迅速把吸引、利用与危险感并排立住。主线随后把情感拉扯和现实博弈同步推高。人物关系与旧账压力持续缠绕。文风上偏冷调克制，靠身体细节和对话潜台词托住张力。",
        core_hooks=["双强关系一边试探一边设局"],
        writing_breakdown=WritingBreakdown(
            writing_analysis="采用冷感克制的判断句与身体细节并行，让情感张力一直贴着主线走。",
        ),
        style_summary=StyleSummary(
            conflict_design="情感推进和现实博弈始终同步抬升。",
            emotional_leverage="通过身体反应和潜台词把压力外化。",
            language_style="冷调克制+潜台词密度高",
        ),
    )

    markdown = render_report_markdown(build_delivery_report(book, []))

    assert "人物关系与旧账压力持续缠绕" in markdown
    assert "整体看，采用冷感克制的判断句与身体细节并行" in markdown
    assert "叙事上情感推进和现实博弈始终同步抬升" in markdown
    assert "情绪上通过身体反应和潜台词把压力外化" in markdown


def test_delivery_report_translates_english_stage_and_rhythm_tags() -> None:
    unit = DeliveryUnit(
        unit_id="unit-001",
        title="关系升温",
        chapter_refs=["ch-0001", "ch-0002"],
        chapter_range="第1-2章",
        summary="两人在试探和照料里明显靠近。",
        beat_rhythm=[
            BeatRhythmItem(
                beat="病房照料",
                pacing_tag="intimate acceleration",
                emotion_tag="playfulness -> tactile hunger",
                note="照料动作迅速把关系推入更贴身的拉扯。",
            )
        ],
        relationship_progression=[
            RelationshipProgression(
                counterpart="主 CP",
                stage_label="instrumental alliance",
                change="从互相利用转向更明显的关系升温。",
            )
        ],
        style_signals=[
            StyleSignal(
                dimension="Syntax",
                observation="短句切分与停顿让情绪压强始终在线。",
            )
        ],
    )

    markdown = render_report_markdown(build_delivery_report(BookAnalysis(title="标签清洗测试书", delivery_units=[unit]), []))

    assert "intimate acceleration" not in markdown
    assert "playfulness" not in markdown
    assert "instrumental alliance" not in markdown
    assert "Syntax" not in markdown
    assert "节奏：贴身升温" in markdown
    assert "情绪：玩笑试探到身体渴望" in markdown
    assert "关系升温" in markdown
    assert "句法控制：短句切分与停顿让情绪压强始终在线" in markdown


def test_delivery_report_chapter_outline_prefers_single_chapter_units() -> None:
    book = BookAnalysis(
        title="章节级交付测试书",
        delivery_units=[
            DeliveryUnit(
                unit_id="unit-001",
                title="合并单元",
                chapter_refs=["ch-0001", "ch-0002"],
                chapter_range="第1-2章",
                summary="本单元完成一次阶段性推进。",
            )
        ],
    )
    chapters = [
        ChapterAnalysis(
            chapter_id="ch-0001",
            title="第0章 引子（分块 1/2）",
            summary="赵壹笙在同学会上重逢卓舒清，并借舞池试探逼对方正面接招。",
            plot_events=[
                PlotEvent(
                    label="同学会重逢",
                    details="赵壹笙主动把旧账和新局一起抛到台面上，让卓舒清必须在众人注视下回应。",
                )
            ],
            scene_quotes=[SceneQuoteItem(scene="同学会重逢", quote="你终于舍得回来了。", purpose="把两人的旧关系重新点亮。")],
            beat_rhythm=[
                BeatRhythmItem(
                    beat="公开试探",
                    pacing_tag="fast",
                    emotion_tag="testing",
                    note="赵壹笙借众人围观制造压力，让卓舒清没法继续回避两人的旧账和新局。",
                )
            ],
        ),
        ChapterAnalysis(
            chapter_id="ch-0002",
            title="第0章 引子（分块 2/2）",
            summary="卓舒清把赵壹笙带回住处，两人在留宿、照料和名分试探里明显失守。",
            plot_events=[
                PlotEvent(
                    label="留宿试探",
                    details="卓舒清默许赵壹笙留宿，又在照料和近距离对峙里把关系推到更暧昧的位置。",
                )
            ],
            scene_quotes=[SceneQuoteItem(scene="留宿试探", quote="今晚别走了。", purpose="把两人的距离从公开试探推到私人空间。")],
        ),
    ]

    markdown = render_report_markdown(build_delivery_report(book, chapters))

    assert "### 合并单元（第1-2章）" not in markdown
    assert re.search(r"### [^\n]+（第1章）", markdown)
    assert re.search(r"### [^\n]+（第2章）", markdown)
    assert "剧情：同学会重逢" in markdown
    assert "赵壹笙在同学会上重逢卓舒清" in markdown
    assert "本单元完成一次阶段性推进" not in markdown


def test_delivery_report_expands_beats_phase_outline_and_relationship_timeline() -> None:
    book = BookAnalysis(
        title="结构展开测试书",
        plot_outline=PlotOutline(
            phase_outline=[
                PhaseOutlineItem(
                    phase="起：联姻启动与关系建构",
                    chapter_range="第1-4章",
                    events=[
                        "开局设局",
                        "重逢升温",
                        "职场压迫",
                        "关系回锚",
                    ],
                )
            ]
        ),
        relationship_timeline=[
            RelationshipStage(
                pair="赵壹笙 & 卓舒清",
                stage_label="创伤共担",
                chapter_refs=["ch-0001", "ch-0002"],
                chapter_range="第1-2章",
                core_change="双方第一次把旧伤和当前计划放到同一张桌面上谈。",
                pressure="重逢后的旧账、家族压力和利益顾虑一起压上来。",
                payoff="两人开始从互相试探转向愿意替对方承担风险。",
            )
        ],
    )
    chapters = [
        ChapterAnalysis(
            chapter_id="ch-0001",
            title="第1章 重逢试探",
            summary="赵壹笙在公开场合逼卓舒清回应旧账，先把关系火药味重新点燃。",
            plot_events=[
                PlotEvent(label="同学会重逢", details="赵壹笙在同学会公开挑明旧账，把卓舒清重新拉回自己的视线中心。"),
                PlotEvent(label="KTV告白", details="洗手间里的直球告白与接吻让两人的关系一开场就失去安全距离。"),
            ],
            beat_rhythm=[
                BeatRhythmItem(
                    beat="公开对峙",
                    pacing_tag="fast",
                    emotion_tag="testing",
                    note="赵壹笙借公开场合迫使卓舒清表态，先把两人的旧伤和新局一起抬到台面。",
                ),
                BeatRhythmItem(
                    beat="关系压迫",
                    pacing_tag="escalation",
                    emotion_tag="tension",
                    note="卓舒清没有退让，反而把回应压得更近，让场面从口头试探逼到身体距离。",
                ),
            ],
            relationship_progression=[
                RelationshipProgression(
                    counterpart="卓舒清",
                    stage_label="旧账复燃",
                    change="重逢让两人重新正视旧伤与吸引，关系从冷置状态回到高压拉扯。",
                )
            ],
        ),
        ChapterAnalysis(
            chapter_id="ch-0002",
            title="第2章 留宿升温",
            summary="卓舒清把赵壹笙带回住处，留宿与照料把试探推成贴身暧昧。",
            plot_events=[
                PlotEvent(label="留宿试探", details="卓舒清默许赵壹笙留宿，照料、近距离对视和衣物细节把关系推向更亲密位置。"),
            ],
        ),
        ChapterAnalysis(
            chapter_id="ch-0003",
            title="第3章 职场重逢",
            summary="两人在咨询会议上正式重逢，专业交锋把私人张力重新包进工作关系。",
            plot_events=[
                PlotEvent(label="咨询会交锋", details="项目会议上的专业试探与身份博弈，让私人吸引第一次进入公开职场场域。"),
            ],
        ),
        ChapterAnalysis(
            chapter_id="ch-0004",
            title="第4章 名分回锚",
            summary="名分、边界和欲望在新一轮对话里再次被确认。",
            plot_events=[
                PlotEvent(label="名分确认", details="两人借边界对话和身体靠近重新确认名分，让关系从暧昧回到明确拉扯。"),
            ],
        ),
    ]

    markdown = render_report_markdown(build_delivery_report(book, chapters))

    assert "- 【起：联姻启动与关系建构】（第1-4章）" in markdown
    assert "  - 事件1：开局设局（第1章）" in markdown
    assert "    - 同学会重逢→告白" in markdown
    assert "  - 事件2：重逢升温（第2章）" in markdown
    assert "    - 留宿试探" in markdown
    assert "  - 事件3：职场压迫（第3章）" in markdown
    assert "  - 事件4：关系回锚（第4章）" in markdown
    assert "项目会议上的专业试探与身份博弈" in markdown
    assert "节奏：紧凑｜情绪：试探拉扯｜作用：赵壹笙借公开场合迫使卓舒清表态" in markdown
    assert "推进：双方第一次把旧伤和当前计划放到同一张桌面上谈" in markdown
    assert "压力：重逢后的旧账、家族压力和利益顾虑一起压上来" in markdown
    assert "回收：两人开始从互相试探转向愿意替对方承担风险" in markdown


def test_delivery_report_supports_chapter_id_ranges_in_phase_outline() -> None:
    book = BookAnalysis(
        title="章节范围兼容测试书",
        plot_outline=PlotOutline(
            phase_outline=[
                PhaseOutlineItem(
                    phase="起：关系建立",
                    chapter_range="ch-0001–ch-0002",
                    events=["关系启动"],
                )
            ]
        ),
    )
    chapters = [
        ChapterAnalysis(
            chapter_id="ch-0001",
            title="第1章 重逢",
            plot_events=[PlotEvent(label="同学会重逢", details="两人在同学会重新碰面，旧账与吸引同时被点燃。")],
        ),
        ChapterAnalysis(
            chapter_id="ch-0002",
            title="第2章 告白",
            plot_events=[PlotEvent(label="洗手间告白", details="KTV洗手间里的直球告白让关系直接越过安全距离。")],
        ),
    ]

    markdown = render_report_markdown(build_delivery_report(book, chapters))

    assert "【起：关系建立】（第1-2章）" in markdown
    assert "同学会重逢→告白" in markdown
    assert "对应阶段剧情待结合章节补齐" not in markdown


def test_delivery_report_renders_detailed_opening_and_story_lines_after_postprocess() -> None:
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
    processed = postprocess_book_analysis(
        BookAnalysis(
            title="细化渲染测试书",
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
        ),
        chapters,
    )

    markdown = render_report_markdown(build_delivery_report(processed, chapters))

    assert "情感主线｜核心线索：赵壹笙在同学会公开挑明旧账" in markdown
    assert "两人在KTV洗手间直球告白接吻" in markdown
    assert any(token in markdown for token in ["开篇回报", "关系启动", "直接起局", "名分确认"])
    assert "赵壹笙在高压工作和旧伤阴影里硬撑" in markdown
    assert "KTV洗手间" in markdown or "对白本身就在承担剧情推进功能" in markdown
    assert any(token in markdown for token in ["主动权", "划界", "关系分寸"])


def test_report_repair_keeps_detailed_story_line_items() -> None:
    blocks = [
        ReportBlock(kind="heading", level=2, text="剧情大纲", style="section_heading"),
        ReportBlock(kind="heading", level=3, text="核心故事线-主线/副线", style="group_heading"),
        ReportBlock(
            kind="bullet",
            level=1,
            text="情感主线｜核心线索：赵壹笙与卓舒清从KTV初遇到法律绑定的情感螺旋演进",
            style="section_item",
        ),
        ReportBlock(
            kind="bullet",
            level=1,
            text="资本主线｜并行线索：资本主线围绕梅肯兹裁员13%、景致资本注资、法人变更等关键节点层层推进，高科股改、资本博弈与权力格局也因此持续改写。",
            style="section_item",
        ),
        ReportBlock(kind="bullet", level=1, text="关键点", style="group_label"),
        ReportBlock(kind="bullet", level=2, text="KTV告白接吻", style="group_detail"),
    ]

    repaired = repair_delivery_report_blocks(blocks)
    markdown = render_report_markdown(repaired)

    assert "情感主线｜核心线索：赵壹笙与卓舒清从KTV初遇到法律绑定的情感螺旋演进" in markdown
    assert "资本主线｜并行线索：资本主线围绕梅肯兹裁员13%" in markdown
    assert markdown.index("情感主线｜核心线索") < markdown.index("关键点")


def test_delivery_report_repairs_short_beat_notes_and_truncated_relationship_change() -> None:
    chapter = ChapterAnalysis(
        chapter_id="ch-0076",
        title="后记自白",
        summary="赵壹笙在后记自白里回望阿竽之死与卓舒清接住自己的过程，把创伤重构和关系回收一起说透。",
        plot_events=[
            PlotEvent(label="阿竽死亡瞬间", details="赵壹笙回望阿竽遇害瞬间的身体共感与心理崩塌，让后记先把创伤底色完全摊开。"),
            PlotEvent(label="卓舒清接住她", details="卓舒清在赵壹笙最失序的时候成为新的情感支柱，把原本断裂的人生重新锚回现实。"),
        ],
        highlights=["后记把创伤重构和关系确认一并完成收束。"],
        relationship_progression=[
            RelationshipProgression(
                counterpart="赵壹笙 & 卓舒清",
                stage_label="创伤共担",
                change="卓舒清接住赵壹笙最失序的时刻，让信任真正从情绪安慰推进到共同承担。",
            )
        ],
    )
    unit = DeliveryUnit(
        unit_id="unit-076",
        title="后记自白",
        chapter_refs=["ch-0076"],
        chapter_range="第76章",
        summary=chapter.summary,
        beat_rhythm=[
            BeatRhythmItem(
                beat="阿竽死亡瞬间",
                pacing_tag="hold",
                emotion_tag="grief",
                note="用",
            )
        ],
        relationship_progression=[
            RelationshipProgression(
                counterpart="赵壹笙 & 卓舒清",
                stage_label="世界支柱更替",
                change="从赵壹笙单向依赖阿竽，转变为双向共生：卓舒清成为新支柱，赵壹笙则以",
            )
        ],
    )

    markdown = render_report_markdown(
        repair_delivery_report_blocks(
            build_delivery_report(
                BookAnalysis(title="修复细节测试书", delivery_units=[unit]),
                [chapter],
            )
        )
    )

    assert "作用：用" not in markdown
    assert "阿竽遇害瞬间的身体共感与心理崩塌" in markdown
    assert "赵壹笙则以" not in markdown
    assert "共同承担" in markdown


def test_delivery_report_falls_back_to_chinese_for_unknown_rhythm_tags() -> None:
    chapter = ChapterAnalysis(
        chapter_id="ch-0001",
        title="第1章 标签清洗",
        summary="两人在会面与离场之间不断试探。",
        beat_rhythm=[
            BeatRhythmItem(
                beat="共享牙刷决策瞬间",
                pacing_tag="quick",
                emotion_tag="guarded",
                note="微小动作承载巨大信任跃迁，节奏陡然收紧。",
            ),
            BeatRhythmItem(
                beat="金光抚脸",
                pacing_tag="soft",
                emotion_tag="yearning",
                note="结尾镜头回归身体感知，温柔收束所有张力。",
            ),
            BeatRhythmItem(
                beat="临门对峙",
                pacing_tag="orbital-break",
                emotion_tag="unknown-charge",
                note="门口停顿和视线拉扯把情绪继续拽紧。",
            ),
        ],
    )

    markdown = render_report_markdown(build_delivery_report(BookAnalysis(title="标签回退测试书"), [chapter]))

    assert "quick" not in markdown
    assert "soft" not in markdown
    assert "guarded" not in markdown
    assert "yearning" not in markdown
    assert "orbital-break" not in markdown
    assert "unknown-charge" not in markdown
    assert "节奏：紧凑" in markdown
    assert "节奏：柔缓推进" in markdown
    assert "情绪：戒备观望" in markdown
    assert "情绪：渴望牵引" in markdown
    assert "节奏：断裂反弹｜情绪：高压拉扯｜作用：门口停顿和视线拉扯把情绪继续拽紧" in markdown
    assert "情绪：情绪变化" not in markdown
    assert "情绪：+" not in markdown
    assert "节奏：推进" not in markdown


def test_delivery_report_strengthens_weak_chapter_cards_with_specific_copy() -> None:
    chapter = ChapterAnalysis(
        chapter_id="ch-0001",
        title="番外：过年搞事（分块 1/49）",
        summary="卓舒清在病房门口撞见赵壹笙强撑清醒，关系一下被逼到必须正面回应的地步。",
        plot_events=[
            PlotEvent(label="病房重逢", details="卓舒清赶到病房时，赵壹笙正带病硬撑工作，两人在压抑对视里把旧账与现实风险一起摊开。"),
            PlotEvent(label="失控落泪", details="卓舒清在门外短暂失控，转身又被赵壹笙逼着回到现场，两人的情绪防线同时失守。"),
        ],
        highlights=["赵壹笙主动让卓舒清留下，把原本可撤回的照料关系推成必须回应的情感站位。"],
        payoff=["两人第一次把病痛、旧账和当前计划放在同一张桌面上谈。"],
        scene_quotes=[SceneQuoteItem(scene="病房重逢", quote="别走。", purpose="把原本可回避的情感问题逼成现场回应。")],
        beat_rhythm=[
            BeatRhythmItem(
                beat="门外停步",
                pacing_tag="micro-pause",
                emotion_tag="guarded_vulnerability",
                note="卓舒清在门口短暂停住，先想逃开又被赵壹笙一句话拽回现场。",
            ),
            BeatRhythmItem(
                beat="病房对视",
                pacing_tag="slow-tension",
                emotion_tag="vulnerability",
                note="两人都不肯先示弱，但病房环境逼得所有克制都变得摇摇欲坠。",
            ),
        ],
        relationship_progression=[
            RelationshipProgression(counterpart="卓舒清", stage_label="待补充", change="两人第一次在现实风险面前同时暴露脆弱。"),
        ],
    )

    markdown = render_report_markdown(build_delivery_report(BookAnalysis(title="弱卡片补强测试书"), [chapter]))

    assert "番外：过年搞事" not in markdown
    assert re.search(r"### (?!关键推进)[^\n]+（第1章）", markdown)
    assert "剧情：病房重逢：卓舒清赶到病房时" in markdown
    assert "情绪：情绪变化" not in markdown
    assert "节奏：推进" not in markdown
    assert "情绪：戒备松动" in markdown
    assert "节奏：微停顿" in markdown
    assert markdown.count(" / ") >= 3
    assert "主动让卓舒清留下" in markdown


def test_delivery_report_preserves_distinct_detailed_beats_per_chapter() -> None:
    chapter = ChapterAnalysis(
        chapter_id="ch-0001",
        title="第1章 初遇试探",
        summary="两人在会议室里从职业试探一路推进到身体越界。",
        beat_rhythm=[
            BeatRhythmItem(
                beat="赵壹笙拽走齐简臻咖啡，换冰水，手指划过颧骨留水痕",
                pacing_tag="intimate acceleration",
                emotion_tag="playfulness → tactile hunger",
                note="肢体越界三连击把试探直接推成贴身张力。",
            ),
            BeatRhythmItem(
                beat="齐简臻合电脑，抽纸擦脸，笑问不接吻都不合适了",
                pacing_tag="comedic release",
                emotion_tag="amusement → controlled vulnerability",
                note="用玩笑打断升温，让松弛表象下的紧绷继续成立。",
            ),
            BeatRhythmItem(
                beat="赵壹笙咬冰作响，耳语玩死MD高伙",
                pacing_tag="percussive climax",
                emotion_tag="defiance → lethal confidence",
                note="冰裂声和耳语一起把压迫感推到顶点。",
            ),
        ],
    )

    markdown = render_report_markdown(build_delivery_report(BookAnalysis(title="beat细化测试书"), [chapter]))

    assert "赵壹笙拽走齐简臻咖啡，换冰水，手指划过颧骨留水痕" in markdown
    assert "把隔桌试探一步步推成贴身暧昧" in markdown
    assert "表面把失控拐回玩笑" in markdown
    assert "把原本暧昧试探一下劈成正面交锋" in markdown


def test_delivery_report_backfills_short_beats_with_distinct_scene_or_event_anchors() -> None:
    chapter = ChapterAnalysis(
        chapter_id="ch-0003",
        title="第3章 车前亮相",
        summary="赵壹笙归还卓舒清的车后一路把关系推进到家中亲密试探。",
        beat_rhythm=[
            BeatRhythmItem(beat="车前亮相", pacing_tag="medium-slow", emotion_tag="defiant", note="静态凝视+肢体语言主导，节奏沉稳蓄力"),
            BeatRhythmItem(beat="厨房切菜凝视", pacing_tag="slow", emotion_tag="tender", note="细节特写延缓时间感"),
            BeatRhythmItem(beat="刀疤暴露与耳语", pacing_tag="hold", emotion_tag="vulnerable", note="长句中断+感官聚焦让节奏骤停"),
        ],
        plot_events=[
            PlotEvent(label="车归还与身份亮相", details="赵壹笙将卓舒清的SUV停在深蓝国际大厦前，解扣露锁骨、戴墨镜倚车，直面旧同事打量。"),
            PlotEvent(label="关键坦白与创伤暴露", details="卓舒清回应你是第一个，赵壹笙被动袒露胸口刀疤，触发更深层的不安与靠近。"),
        ],
        scene_quotes=[
            SceneQuoteItem(scene="车前亮相", quote="她戴着墨镜，半依在车门上，冲着看向她的几个人扬了扬下巴。", purpose="确立赵壹笙强势人格锚点"),
            SceneQuoteItem(scene="厨房切菜", quote="发丝有那么调皮的一缕落下，她顺手挽到了耳后。", purpose="以生活化细节软化精英形象"),
            SceneQuoteItem(scene="刀疤触碰", quote="会过去吗？真的过去的话，为什么要警告自己呢？", purpose="将外部亲密与内在警觉并置"),
        ],
    )

    unit = DeliveryUnit(unit_id="unit-001", title="车前亮相", chapter_refs=["ch-0003"], chapter_range="第3章", summary=chapter.summary, beat_rhythm=chapter.beat_rhythm)

    lines = _format_beat_rhythm(unit, chapter=chapter)

    assert len(lines) == 3
    assert "情节点：" in lines[0]
    assert "情节点：" in lines[1]
    assert "情节点：" in lines[2]
    anchors = [line.split("｜", 1)[0] for line in lines]
    assert len(set(anchors)) == 3
    assert any("厨房切菜" in anchor for anchor in anchors)
    assert any("刀疤" in anchor for anchor in anchors)
    assert any("先把她强势归来的姿态钉在众人面前" in line for line in lines)
    assert any("把锋利试探缓缓拖进带家感的暧昧" in line for line in lines)


def test_delivery_report_expands_sequence_beats_into_narrative_and_keeps_change_point() -> None:
    chapter = ChapterAnalysis(
        chapter_id="ch-0002",
        title="第2章 密码门对视",
        summary="赵壹笙与卓舒清从KTV外搭话一路推到门内试探和身体越界。",
        beat_rhythm=[
            BeatRhythmItem(
                beat="递手机→扫码→打量同款车",
                pacing_tag="slow-burn setup",
                emotion_tag="curiosity + calculation",
                note="目光扫车而非人，建立物质逻辑先行的认知框架",
            ),
            BeatRhythmItem(
                beat="密码门注视→‘记住了吗？’",
                pacing_tag="tension spike",
                emotion_tag="daring + invitation",
                note="桃花眼特写与语言挑衅同步，启动权力博弈",
            ),
        ],
        scene_quotes=[
            SceneQuoteItem(scene="密码门对视", quote="记住了吗？", purpose="以教学姿态实施诱惑，消解引狼入室的被动性"),
        ],
    )

    unit = DeliveryUnit(unit_id="unit-002", title="密码门对视", chapter_refs=["ch-0002"], chapter_range="第2章", summary=chapter.summary, beat_rhythm=chapter.beat_rhythm)
    lines = _format_beat_rhythm(unit, chapter=chapter)

    assert any("从递手机到扫码，再到打量同款车" in line for line in lines)
    assert any("先把这场靠近落到算计和试探上" in line for line in lines)
    assert any("把引狼入室的暧昧一下推成主导权试探" in line for line in lines)
    assert all("以教学姿态实施诱惑" not in line for line in lines)


def test_delivery_report_dedupes_relationship_timeline_parts_and_keeps_relational_payoff() -> None:
    chapter = ChapterAnalysis(
        chapter_id="ch-0001",
        title="第1章 试探启动",
        summary="赵壹笙与卓舒清在会议与私下试探里同时靠近。",
        plot_events=[
            PlotEvent(label="会议试探", details="赵壹笙与卓舒清在公开会议里互相压价试探，把职业博弈直接拖进私人张力。"),
        ],
        crisis=["双方都不愿先交底，任何一步靠近都可能把底牌提前暴露。"],
        payoff=["两人第一次把试探从会议室带到私下场域，关系获得继续推进的基础。"],
        relationship_progression=[
            RelationshipProgression(
                counterpart="赵壹笙 & 卓舒清",
                stage_label="试探启动",
                change="两人第一次把职业试探转成私下靠近，关系从陌生对手变成必须回应彼此的人。",
            )
        ],
    )
    book = BookAnalysis(
        title="情感线去重测试书",
        relationship_timeline=[
            RelationshipStage(
                pair="赵壹笙 & 卓舒清",
                stage_label="试探启动",
                chapter_refs=["ch-0001"],
                chapter_range="第1章",
                description="这一阶段，本章以会议试探展开；压力：双方都不愿先交底；回收：好戳性癖啊。",
                core_change="这一阶段，本章以会议试探展开",
                pressure="双方都不愿先交底",
                payoff="好戳性癖啊。",
            )
        ],
    )

    markdown = render_report_markdown(build_delivery_report(book, [chapter]))

    assert "这一阶段，本章以" not in markdown
    assert "两人第一次把职业试探转成私下靠近" in markdown
    assert "双方都不愿先交底" in markdown
    assert "关系获得继续推进的基础" in markdown
    assert "好戳性癖啊" not in markdown


def test_delivery_report_repairs_repeated_noisy_chapter_titles() -> None:
    chapters = [
        ChapterAnalysis(
            chapter_id="ch-0027",
            title="番外：过年搞事（分块 1/49）",
            summary="卓舒清在雪夜赶到现场。",
            scene_quotes=[SceneQuoteItem(scene="雪夜赶赴", quote="我来了。", purpose="把人物重新拉回主线冲突中心。")],
        ),
        ChapterAnalysis(
            chapter_id="ch-0028",
            title="番外：过年搞事（分块 2/49）",
            summary="灵堂对峙把关系逼入新阶段。",
            scene_quotes=[SceneQuoteItem(scene="灵堂对峙", quote="你现在才来。", purpose="把旧账和哀伤一起抬高。")],
        ),
        ChapterAnalysis(
            chapter_id="ch-0029",
            title="番外：过年搞事（分块 3/49）",
            summary="泳池边界重新被确认。",
            scene_quotes=[SceneQuoteItem(scene="泳池宣言", quote="我不会松手。", purpose="把关系从摇摆重新拉回确认。")],
        ),
    ]

    markdown = render_report_markdown(build_delivery_report(BookAnalysis(title="标题修复测试书"), chapters))

    assert "番外：过年搞事" not in markdown
    assert re.search(r"### (?!关键推进)[^\n]+（第27章）", markdown)
    assert re.search(r"### (?!关键推进)[^\n]+（第28章）", markdown)
    assert re.search(r"### (?!关键推进)[^\n]+（第29章）", markdown)


def test_delivery_integrity_repair_drops_broken_fragments_and_dirty_quotes() -> None:
    blocks = [
        ReportBlock(kind="heading", level=2, text="章节细纲", style="section_heading"),
        ReportBlock(kind="heading", level=3, text="番外：过年搞事（第66章）", style="unit_heading"),
        ReportBlock(kind="bullet", level=1, text="文风信号", style="group_label"),
        ReportBlock(kind="bullet", level=2, text="对话节奏：大量使用短句切分与留白，如", style="unit_detail"),
        ReportBlock(kind="bullet", level=1, text="名场面与金句", style="group_label"),
        ReportBlock(kind="bullet", level=2, text="卓家车内对话｜金句：?｜作用：粤语原句保留，制造文化隔阂感与家族规训的冰冷", style="unit_detail"),
    ]

    repaired = repair_delivery_report_blocks(blocks)
    markdown = render_report_markdown(repaired)

    assert "番外：过年搞事" not in markdown
    assert "对话节奏：大量使用短句切分与留白，如" not in markdown
    assert "金句：?" not in markdown


def test_delivery_integrity_review_flags_field_pollution_and_generic_labels() -> None:
    blocks = [
        ReportBlock(kind="heading", level=2, text="章节细纲", style="section_heading"),
        ReportBlock(kind="heading", level=3, text="试探升温（第35章）", style="unit_heading"),
        ReportBlock(kind="bullet", level=1, text="情感推进", style="group_label"),
        ReportBlock(kind="bullet", level=2, text="祝施 / 关系推进：从必须清算的对象转为技术共生体；共识参与对抗祝施的暗指试探", style="unit_detail"),
        ReportBlock(kind="bullet", level=2, text="康壹竽 / 关系推进：从必须清算的对象转为技术共生体；共识参与对抗祝施的暗指试探", style="unit_detail"),
    ]

    review = build_delivery_integrity_review(blocks, rendered_report=render_report_markdown(blocks))
    issue_types = {issue.issue_type for issue in review.issues}

    assert "generic_label" in issue_types
    assert "field_pollution" in issue_types


def test_delivery_report_rewrites_customer_sample_title_noise_cases() -> None:
    chapters = [
        ChapterAnalysis(
            chapter_id="ch-0016",
            title="第15章  我知道我终究是不一样的",
            summary="利曼珊拜访养母卡罗尔，在与葫芦共处的温情氛围中追忆亡友克洛伊的成长创伤与身份认同历程；随后转入现实危机——她请求卡罗尔动用FBI职权秘密调查联邦检察官Yvonne Chi。",
            plot_events=[PlotEvent(label="关系托付", details="利曼珊正式委托卡罗尔启动秘密调查。")],
        ),
        ChapterAnalysis(
            chapter_id="ch-0033",
            title="第32章  在看上去胸有成竹的纪希颐面前，她输了",
            summary="利曼珊试图推动立案调查却遭纪希颐断然拒绝，公事上全面溃败。",
            plot_events=[PlotEvent(label="证据驳回", details="纪希颐以证据不足为由拒绝受理。")],
        ),
        ChapterAnalysis(
            chapter_id="ch-0065",
            title="第64章  录音是当年一个叫蒂凡尼的女人给她的",
            summary="鄢澜、卡罗尔与利曼珊共进晚餐，梳理绑架案证据链与紫狐诉讼的规避风险。",
            plot_events=[PlotEvent(label="证据链闭合", details="关键录音成为闭合纪希颐证据链的核心一环。")],
        ),
        ChapterAnalysis(
            chapter_id="ch-0089",
            title="第88章  枪声几乎湮没在锣鼓声中",
            summary="鄢澜与利曼珊共度春节街头庆典时突遭蒂凡尼伏击；利曼珊为救鄢澜中弹重伤。",
            plot_events=[PlotEvent(label="枪击发生", details="蒂凡尼混入舞龙队伍开枪，利曼珊舍身挡枪。")],
        ),
        ChapterAnalysis(
            chapter_id="ch-0090",
            title="第89章  她曾以为",
            summary="纪希颐在联邦监狱得知利曼珊挡枪重伤；与此同时，ICU中的利曼珊苏醒，与鄢澜完成重逢。",
            plot_events=[PlotEvent(label="术后苏醒", details="利曼珊苏醒后与鄢澜完成创伤后的温柔重逢。")],
        ),
        ChapterAnalysis(
            chapter_id="ch-0092",
            title="第91章  她像是漂浮在这座城市之上，与星光平行",
            summary="司法线中动议听证会启动；情感线中利曼珊与鄢澜于39楼泳池完成首次正式吻。",
            plot_events=[PlotEvent(label="动议听证会启动", details="杰森代表纪希颐向联邦法院提交关键动议。")],
        ),
    ]

    markdown = render_report_markdown(build_delivery_report(BookAnalysis(title="客户样本标题测试书"), chapters))

    for chapter_range, original_title in [
        ("第16章", "我知道我终究是不一样的"),
        ("第33章", "在看上去胸有成竹的纪希颐面前"),
        ("第65章", "录音是当年一个叫蒂凡尼的女人给她的"),
        ("第89章", "枪声几乎湮没在锣鼓声中"),
        ("第90章", "她曾以为"),
        ("第92章", "她像是漂浮在这座城市之上"),
    ]:
        assert original_title not in markdown
        assert re.search(rf"### (?!关键推进)[^\n]+（{chapter_range}）", markdown)


def test_delivery_report_preserves_clean_v18_style_unit_titles() -> None:
    book = BookAnalysis(
        title="v18标题回归测试书",
        delivery_units=[
            DeliveryUnit(unit_id="unit-001", title="病房重逢", chapter_refs=["ch-0001"], chapter_range="第1章", summary="卓舒清赶到病房。"),
            DeliveryUnit(unit_id="unit-002", title="试探升温", chapter_refs=["ch-0035"], chapter_range="第35章", summary="两人的试探持续升温。"),
        ],
    )

    markdown = render_report_markdown(build_delivery_report(book, []))

    assert "### 病房重逢（第1章）" in markdown
    assert "### 试探升温（第35章）" in markdown
