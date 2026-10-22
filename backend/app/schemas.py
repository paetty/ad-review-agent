from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Risk = Literal["low", "medium", "high", "critical"]
Category = Literal["product", "creative", "delivery", "review"]

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
    estimated_cost_usd: float
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
    model_info: ModelInfo
    prompt_version: str

    @model_validator(mode="after")
    def enforce_invariants(self):
        names = {item.label for item in self.labels}
        if "no_issue" in names and len(names) > 1:
            raise ValueError("no_issue cannot coexist with issue labels")
        if self.overall_risk == "critical" and not self.requires_human_review:
            raise ValueError("critical risk requires human review")
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

class ReviewInput(BaseModel):
    reviewer: str = "demo_reviewer"
    decision: Literal["accepted", "modified"]
    corrected_labels: list[str] | None = None
    corrected_risk: Risk | None = None
    edited_recommendations: list[Recommendation] | None = None
    notes: str = Field(default="", max_length=2000)

class PromptCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    content: str = Field(min_length=20, max_length=20000)

class ExperimentInput(BaseModel):
    anonymous_user_id: str = Field(min_length=3, max_length=256)

class AgentResumeInput(BaseModel):
    decision: Literal["accepted", "modified"]
    notes: str = Field(default="", max_length=2000)

