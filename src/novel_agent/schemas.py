from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator


class InputType(StrEnum):
    TXT = "txt"
    DOCX = "docx"
    PDF = "pdf"


class RunManifest(BaseModel):
    run_id: str
    book_id: str
    input_path: str
    input_type: InputType
    profile: str
    provider: str
    book_provider: str | None = None
    export_formats: list[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class OCRMetadata(BaseModel):
    used_ocr: bool = False
    average_confidence: float | None = None
    warnings: list[str] = Field(default_factory=list)


class IngestedBook(BaseModel):
    book_id: str
    title: str
    input_path: str
    input_type: InputType
    normalized_text: str
    page_texts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ocr: OCRMetadata = Field(default_factory=OCRMetadata)


class ChapterRecord(BaseModel):
    chapter_id: str
    title: str
    order: int
    raw_text: str
    token_count: int
    split_warnings: list[str] = Field(default_factory=list)


class ChapterFailureRecord(BaseModel):
    chapter_id: str
    title: str
    order: int
    error_type: str
    error_message: str
    stage_name: str = "chapter-analyze"


class EvidenceItem(BaseModel):
    chapter_id: str
    source_ref: str
    snippet: str
    note: str

    @model_validator(mode="before")
    @classmethod
    def _fill_missing_snippet(cls, value):  # noqa: ANN001
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if not str(data.get("snippet", "")).strip():
            for key in ("quote", "text", "content", "detail", "details", "anchor", "observation"):
                candidate = data.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    data["snippet"] = candidate.strip()
                    break
        if not str(data.get("note", "")).strip():
            for key in ("observation", "detail", "details", "anchor"):
                candidate = data.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    data["note"] = candidate.strip()
                    break
        data.setdefault("snippet", "")
        data.setdefault("note", "")
        return data


class PlotEvent(BaseModel):
    label: str = ""
    details: str = ""


class EmotionState(BaseModel):
    primary: str = ""
    secondary: list[str] = Field(default_factory=list)
    trajectory: str = ""


class RelationshipProgression(BaseModel):
    counterpart: str = ""
    stage_label: str = ""
    change: str = ""


class StyleSignal(BaseModel):
    dimension: str = ""
    observation: str = ""


class BeatRhythmItem(BaseModel):
    beat: str = ""
    pacing_tag: str = ""
    emotion_tag: str = ""
    note: str = ""


class SceneQuoteItem(BaseModel):
    scene: str = ""
    quote: str = ""
    purpose: str = ""


class HighlightSummaryItem(BaseModel):
    title: str = ""
    detail: str = ""


class SellingPointItem(BaseModel):
    category: str = ""
    detail: str = ""


class StoryHookLayers(BaseModel):
    short_term: list[str] = Field(default_factory=list)
    mid_term: list[str] = Field(default_factory=list)
    long_term: list[str] = Field(default_factory=list)


class AudiencePositioning(BaseModel):
    comps: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("comps", "comparable_titles"),
    )
    reader_profile: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("reader_profile", "reader_profiles"),
    )
    marketing_keywords: list[str] = Field(default_factory=list)
    short_term_hooks: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("short_term_hooks", "short_term_highlights"),
    )
    mid_term_hooks: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("mid_term_hooks", "mid_term_highlights"),
    )
    long_term_hooks: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("long_term_hooks", "long_term_highlights"),
    )

    @property
    def comparable_titles(self) -> list[str]:
        return self.comps

    @property
    def reader_profiles(self) -> list[str]:
        return self.reader_profile

    @property
    def short_term_highlights(self) -> list[str]:
        return self.short_term_hooks

    @property
    def mid_term_highlights(self) -> list[str]:
        return self.mid_term_hooks

    @property
    def long_term_highlights(self) -> list[str]:
        return self.long_term_hooks


class TitleIntroAnalysis(BaseModel):
    title_analysis: str = ""
    core_hook: str = ""
    genre: str = ""
    intro_analysis: str = ""
    chapter_name_analysis: str = ""


class CPTopic(BaseModel):
    topic: str = ""
    analysis: str = ""
    supporting_moments: list[str] = Field(default_factory=list)


class CPAnalysis(BaseModel):
    summary: str = ""
    topics: list[CPTopic] = Field(default_factory=list)
    relationship_tension: list[str] = Field(default_factory=list)
    stage_progression: list[str] = Field(default_factory=list)
    catalyst_roles: list[str] = Field(default_factory=list)
    emotional_hooks: list[str] = Field(default_factory=list)


class WritingBreakdown(BaseModel):
    writing_analysis: str = ""
    opening_method: str = ""
    dialogue_design: str = ""
    action_detail: str = ""
    language_style: str = ""
    evidence_chapters: list[str] = Field(default_factory=list)


class StoryLineItem(BaseModel):
    name: str = ""
    category: str = ""
    content: str = ""
    key_points: list[str] = Field(default_factory=list)


class PhaseOutlineItem(BaseModel):
    phase: str = ""
    chapter_range: str = ""
    events: list[str] = Field(default_factory=list)


class PlotOutline(BaseModel):
    story_lines: list[StoryLineItem] = Field(default_factory=list)
    phase_outline: list[PhaseOutlineItem] = Field(default_factory=list)


class OpeningCraft(BaseModel):
    core_payoffs: list[str] = Field(default_factory=list)
    core_pain_points: list[str] = Field(default_factory=list)
    flirty_moments: list[str] = Field(default_factory=list)
    character_building: list[str] = Field(default_factory=list)
    dialogue_design: list[str] = Field(default_factory=list)
    action_details: list[str] = Field(default_factory=list)


class ChapterChunkExtraction(BaseModel):
    chapter_id: str = ""
    source_ref: str = ""
    summary: str = ""
    plot_events: list[PlotEvent] = Field(default_factory=list)
    crisis: list[str] = Field(default_factory=list)
    foreshadowing: list[str] = Field(default_factory=list)
    suspense: list[str] = Field(default_factory=list)
    climax: list[str] = Field(default_factory=list)
    payoff: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    beat_rhythm: list[BeatRhythmItem] = Field(default_factory=list)
    scene_quotes: list[SceneQuoteItem] = Field(default_factory=list)
    emotion_state: EmotionState = Field(default_factory=EmotionState)
    relationship_progression: list[RelationshipProgression] = Field(default_factory=list)
    key_characters: list[str] = Field(default_factory=list)
    style_signals: list[StyleSignal] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class ChapterAnalysis(BaseModel):
    chapter_id: str = ""
    title: str = ""
    summary: str = ""
    plot_events: list[PlotEvent] = Field(default_factory=list)
    crisis: list[str] = Field(default_factory=list)
    foreshadowing: list[str] = Field(default_factory=list)
    suspense: list[str] = Field(default_factory=list)
    climax: list[str] = Field(default_factory=list)
    payoff: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    beat_rhythm: list[BeatRhythmItem] = Field(default_factory=list)
    scene_quotes: list[SceneQuoteItem] = Field(default_factory=list)
    emotion_state: EmotionState = Field(default_factory=EmotionState)
    relationship_progression: list[RelationshipProgression] = Field(default_factory=list)
    key_characters: list[str] = Field(default_factory=list)
    style_signals: list[StyleSignal] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class CharacterProfile(BaseModel):
    name: str = ""
    role: str = ""
    traits: list[str] = Field(default_factory=list)
    arc: str = ""
    basic_info: str = ""
    appearance: str = ""
    personality_traits: list[str] = Field(default_factory=list)
    major_experiences: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)


class OutlineBeat(BaseModel):
    label: str = ""
    chapter_refs: list[str] = Field(default_factory=list)
    description: str = ""


class RelationshipStage(BaseModel):
    pair: str = ""
    stage_label: str = ""
    chapter_refs: list[str] = Field(default_factory=list)
    chapter_range: str | None = None
    description: str = ""
    core_change: str = ""
    pressure: str = ""
    payoff: str = ""


class StyleSummary(BaseModel):
    narrative_pacing: str = ""
    information_release: str = ""
    conflict_design: str = ""
    emotional_leverage: str = ""
    characterization: str = ""
    language_style: str = ""
    hook_and_payoff: str = ""
    evidence_chapters: list[str] = Field(default_factory=list)


class ChapterOutlineItem(BaseModel):
    chapter_id: str = ""
    title: str = ""
    one_line: str = ""
    key_conflict: str = ""
    emotional_progression: str = ""
    plot: str = ""
    crisis: str = ""
    foreshadowing: str = ""
    suspense: str = ""
    climax: str = ""
    payoff: str = ""
    beats: list[str] = Field(default_factory=list)
    signature_scenes: list[str] = Field(default_factory=list)
    relationship_progress: list[str] = Field(default_factory=list)
    style_signals: list[str] = Field(default_factory=list)

    @field_validator(
        "chapter_id",
        "title",
        "one_line",
        "key_conflict",
        "emotional_progression",
        "plot",
        "crisis",
        "foreshadowing",
        "suspense",
        "climax",
        "payoff",
        mode="before",
    )
    @classmethod
    def _coerce_scalar_text(cls, value):  # noqa: ANN001
        if isinstance(value, list):
            return "；".join(str(item).strip() for item in value if str(item).strip())
        if value is None:
            return ""
        return str(value).strip() if not isinstance(value, str) else value.strip()


class DeliveryUnit(BaseModel):
    unit_id: str = ""
    title: str = ""
    base_title: str = ""
    chapter_refs: list[str] = Field(default_factory=list)
    chapter_range: str | None = None
    summary: str = ""
    crisis: list[str] = Field(default_factory=list)
    foreshadowing: list[str] = Field(default_factory=list)
    suspense: list[str] = Field(default_factory=list)
    climax: list[str] = Field(default_factory=list)
    payoff: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    beat_rhythm: list[BeatRhythmItem] = Field(default_factory=list)
    scene_quotes: list[SceneQuoteItem] = Field(default_factory=list)
    relationship_progression: list[RelationshipProgression] = Field(default_factory=list)
    style_signals: list[StyleSignal] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class BatchSummary(BaseModel):
    batch_label: str = ""
    overview: str = ""
    outline_beats: list[OutlineBeat] = Field(default_factory=list)
    relationship_stages: list[RelationshipStage] = Field(default_factory=list)
    style_signals: list[StyleSignal] = Field(default_factory=list)
    key_characters: list[str] = Field(default_factory=list)


class BookAnalysis(BaseModel):
    title: str = ""
    overview: str = ""
    highlights_summary: list[HighlightSummaryItem] = Field(default_factory=list)
    selling_points: list[str] = Field(default_factory=list)
    selling_points_detail: list[SellingPointItem] = Field(default_factory=list)
    positioning: list[str] = Field(default_factory=list)
    core_hooks: list[str] = Field(default_factory=list)
    story_hook_layers: StoryHookLayers = Field(default_factory=StoryHookLayers)
    audience_positioning: AudiencePositioning = Field(default_factory=AudiencePositioning)
    title_intro_analysis: TitleIntroAnalysis = Field(default_factory=TitleIntroAnalysis)
    character_profiles: list[CharacterProfile] = Field(default_factory=list)
    cp_analysis: CPAnalysis = Field(default_factory=CPAnalysis)
    main_outline: list[OutlineBeat] = Field(default_factory=list)
    plot_outline: PlotOutline = Field(default_factory=PlotOutline)
    opening_craft: OpeningCraft = Field(default_factory=OpeningCraft)
    chapter_outlines: list[ChapterOutlineItem] = Field(default_factory=list)
    delivery_units: list[DeliveryUnit] = Field(default_factory=list)
    emotion_observations: list[str] = Field(default_factory=list)
    relationship_timeline: list[RelationshipStage] = Field(default_factory=list)
    writing_breakdown: WritingBreakdown = Field(default_factory=WritingBreakdown)
    style_summary: StyleSummary = Field(default_factory=StyleSummary)
    chapter_evidence_index: dict[str, list[str]] = Field(default_factory=dict)


class StageStats(BaseModel):
    stage_name: str
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float | None = None
    latency_ms: int | None = None
    retries: int = 0
    warnings: list[str] = Field(default_factory=list)


class EvalReport(BaseModel):
    expected_chapters: int = 0
    total_chapters: int
    analyzed_chapters: int
    failed_chapters: int = 0
    content_filter_failed_chapters: int = 0
    other_failed_chapters: int = 0
    schema_valid: bool
    evidence_coverage_ratio: float
    required_sections_present: list[str]
    warnings: list[str] = Field(default_factory=list)


class RunStatsSummary(BaseModel):
    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_latency_ms: int = 0
    stages: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ChapterStatusSummary(BaseModel):
    total_chapters: int = 0
    completed_chapters: int = 0
    failed_chapters: int = 0
    pending_chapters: int = 0
    latest_completed_chapter_id: str | None = None
    latest_completed_title: str | None = None
    latest_failed_chapter_id: str | None = None
    latest_failed_title: str | None = None
    current_stage: str = "pending"


class RunSummary(BaseModel):
    run_id: str
    book_id: str
    input_path: str
    provider: str
    book_provider: str
    chapter_model: str
    book_model: str
    total_chapters: int = 0
    completed_chapters: int = 0
    failed_chapters: int = 0
    degraded_split_chapters: int = 0
    latest_completed_chapter_id: str | None = None
    latest_completed_title: str | None = None
    latest_failed_chapter_id: str | None = None
    latest_failed_title: str | None = None
    current_stage: str = "pending"
    aggregate_used_file_id_path: bool = False
    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_latency_ms: int = 0
    average_chapter_latency_ms: int = 0
    chapter_merge_latency_ms: int = 0
    aggregate_latency_ms: int = 0
    estimated_cost_cny: float | None = None
    split_quality_note: str = ""
    warnings: list[str] = Field(default_factory=list)


class QualityReview(BaseModel):
    status: str
    covered_items: list[str] = Field(default_factory=list)
    quality_gaps: list[str] = Field(default_factory=list)
    high_risks: list[str] = Field(default_factory=list)
    metrics: dict[str, bool | str | int | float] = Field(default_factory=dict)


class DeliveryIntegrityIssue(BaseModel):
    issue_type: str
    severity: str
    repairable: bool = True
    section: str = ""
    block_title: str = ""
    group_title: str = ""
    text: str = ""


class DeliveryIntegrityReview(BaseModel):
    overall_status: str
    total_issue_count: int = 0
    blocking_issue_count: int = 0
    repairable_issue_count: int = 0
    round_issue_counts: list[int] = Field(default_factory=list)
    issue_type_counts: dict[str, int] = Field(default_factory=dict)
    issues: list[DeliveryIntegrityIssue] = Field(default_factory=list)


class ReferenceAlignmentDimensionReview(BaseModel):
    name: str
    status: str
    evidence_lines: list[int] = Field(default_factory=list)
    remaining_issue_count: int = 0
    top_examples: list[str] = Field(default_factory=list)
    recommendation: str = ""


class ReferenceAlignmentReview(BaseModel):
    overall_status: str
    summary: str = ""
    dimensions: list[ReferenceAlignmentDimensionReview] = Field(default_factory=list)
    metrics: dict[str, int] = Field(default_factory=dict)
