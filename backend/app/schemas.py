from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Risk = Literal["low", "medium", "high", "critical"]
Category = Literal["product", "creative", "delivery", "review"]
AssessmentStatus = Literal["issue_detected", "insufficient_evidence", "no_explicit_issue"]

class AnalysisInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    ad_copy: str = Field(default="", max_length=4000)
    feedback: str = Field(default="", max_length=4000)
    industry: str
    media_scene: str
    landing_type: str
    material_format: str
    first_three_seconds: str | None = Field(default=None, max_length=1000)
    image_filename: str | None = None
    platform: Literal["generic", "vivo", "oppo"] = "generic"

class LabelResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    confidence: float = Field(ge=0, le=1)

class Evidence(BaseModel):
    source: Literal["input", "retrieval", "image"]
    quote: str
    field: str | None = None
    citation_id: str | None = None

class Citation(BaseModel):
    citation_id: str
    chunk_id: str
    document_title: str
    snippet: str
    score: float = Field(ge=0)
    source_type: str
    source_url: str | None = None
    publisher: str | None = None
    section: str | None = None
    version: str | None = None
    checked_at: str | None = None
    platform: str = "all"
    content_type: str = "authored_demo"

class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Category
    action: str
    rationale: str
    priority: Literal["P0", "P1", "P2"]
    expected_metric: str
    guardrail_metric: str

class ModelInfo(BaseModel):
    provider: str
    model: str
    mode: Literal["demo", "provider"]
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float | None
    simulated: bool = False

class AnalysisOutput(BaseModel):
    analysis_id: str
    labels: list[LabelResult]
    overall_risk: Risk
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence]
    citations: list[Citation]
    strategy_recommendations: list[Recommendation]
    requires_human_review: bool
    uncertainties: list[str]
    disclaimers: list[str] = Field(default_factory=list)
    abstained_labels: list[LabelResult] = Field(default_factory=list)
    analysis_policy_version: str = "legacy-v1"
    model_info: ModelInfo
    prompt_version: str
    assessment_status: AssessmentStatus = "issue_detected"

    @model_validator(mode="after")
    def enforce_invariants(self):
        names = {item.label for item in self.labels}
        if "no_issue" in names and len(names) > 1:
            raise ValueError("no_issue cannot coexist with issue labels")
        if (self.overall_risk in {"high", "critical"} or self.assessment_status == "insufficient_evidence") and not self.requires_human_review:
            raise ValueError("high risk or insufficient evidence requires human review")
        citation_ids = {c.citation_id for c in self.citations}
        for ev in self.evidence:
            if ev.citation_id and ev.citation_id not in citation_ids:
                raise ValueError("evidence citation_id is not traceable")
        return self

class ProviderEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["input", "retrieval", "image"]
    quote: str
    # Required-but-nullable fields keep the schema compatible with strict
    # Structured Outputs while preserving a single shape for all evidence.
    field: str | None
    citation_id: str | None

class ProviderAnalysisDraft(BaseModel):
    """Only fields the external model is allowed to decide."""
    model_config = ConfigDict(extra="forbid")
    labels: list[LabelResult]
    overall_risk: Risk
    confidence: float = Field(ge=0, le=1)
    evidence: list[ProviderEvidence]
    strategy_recommendations: list[Recommendation]
    requires_human_review: bool
    uncertainties: list[str]
    # Accept historical stored responses; new API requests require an explicit state.
    assessment_status: AssessmentStatus | None = None


def provider_analysis_schema() -> dict:
    schema = ProviderAnalysisDraft.model_json_schema()
    schema["properties"]["assessment_status"] = {
        "type": "string", "enum": ["issue_detected", "insufficient_evidence", "no_explicit_issue"],
        "description": "区分具体问题线索、信息不足与未见明确问题；免责声明不等于信息不足。",
    }
    schema["required"] = list(schema["properties"])
    return schema

class ReviewInput(BaseModel):
    reviewer: str = "demo_reviewer"
    decision: Literal["accepted", "modified"]
    corrected_labels: list[str] | None = None
    corrected_risk: Risk | None = None
    edited_recommendations: list[Recommendation] | None = None
    recommendation_label_links: list[list[str]] | None = None
    notes: str = Field(default="", max_length=2000)

class PromptCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    content: str = Field(min_length=20, max_length=20000)

class ExperimentInput(BaseModel):
    anonymous_user_id: str = Field(min_length=3, max_length=256)

class AgentResumeInput(BaseModel):
    decision: Literal["accepted", "modified"]
    notes: str = Field(default="", max_length=2000)
    corrected_labels: list[str] | None = None
    corrected_risk: Risk | None = None
    edited_recommendations: list[Recommendation] | None = None
    recommendation_label_links: list[list[str]] | None = None

    @model_validator(mode="after")
    def validate_corrections(self):
        from .taxonomy import LABELS
        if self.decision == "modified" and (not self.corrected_labels or self.corrected_risk is None or not self.edited_recommendations):
            raise ValueError("修改后继续必须提交标签、风险和建议")
        if self.corrected_labels is not None:
            if not self.corrected_labels or any(x not in LABELS for x in self.corrected_labels):
                raise ValueError("请选择有效标签")
            if "no_issue" in self.corrected_labels and len(self.corrected_labels)>1:
                raise ValueError("no_issue不能与问题标签共存")
        if self.recommendation_label_links is not None:
            if self.edited_recommendations is None or len(self.recommendation_label_links)!=len(self.edited_recommendations):
                raise ValueError("每条建议必须有对应的标签关联")
            if any(not links or any(x not in (self.corrected_labels or []) for x in links) for links in self.recommendation_label_links):
                raise ValueError("建议只能关联人工保留的标签")
        if self.decision == "accepted" and any(x is not None for x in [self.corrected_labels,self.corrected_risk,self.edited_recommendations,self.recommendation_label_links]):
            raise ValueError("接受原结论不能同时提交修改")
        return self

