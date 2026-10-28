from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Analysis(Base):
    __tablename__="analyses"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    input_json: Mapped[dict] = mapped_column(JSON)
    original_output_json: Mapped[dict] = mapped_column(JSON)
    overall_risk: Mapped[str] = mapped_column(String, index=True)
    confidence: Mapped[float] = mapped_column(Float)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, index=True)
    prompt_version: Mapped[str] = mapped_column(String)
    labels: Mapped[list[AnalysisLabel]] = relationship(back_populates="analysis", cascade="all,delete-orphan")

class AnalysisLabel(Base):
    __tablename__="analysis_labels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String, index=True)
    confidence: Mapped[float] = mapped_column(Float)
    analysis: Mapped[Analysis] = relationship(back_populates="labels")

class EvidenceChunk(Base):
    __tablename__="evidence_chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    citation_id: Mapped[str] = mapped_column(String)
    chunk_id: Mapped[str] = mapped_column(String)
    document_title: Mapped[str] = mapped_column(String)
    snippet: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)

class RecommendationDB(Base):
    __tablename__="recommendations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String); action: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text); priority: Mapped[str] = mapped_column(String)
    expected_metric: Mapped[str] = mapped_column(String); guardrail_metric: Mapped[str] = mapped_column(String)

class HumanReview(Base):
    __tablename__="human_reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reviewer: Mapped[str] = mapped_column(String); decision: Mapped[str] = mapped_column(String)
    corrected_output_json: Mapped[dict] = mapped_column(JSON); notes: Mapped[str] = mapped_column(Text, default="")

class PromptVersion(Base):
    __tablename__="prompt_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String); content: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

class EvaluationRun(Base):
    __tablename__="evaluation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    model_version: Mapped[str] = mapped_column(String); prompt_version: Mapped[str] = mapped_column(String)
    metrics_json: Mapped[dict] = mapped_column(JSON)

class BusinessReport(Base):
    __tablename__ = "business_reports"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    report_json: Mapped[dict] = mapped_column(JSON)

class EvaluationItem(Base):
    __tablename__="evaluation_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("evaluation_runs.id"), index=True)
    record_id: Mapped[str] = mapped_column(String); gold_json: Mapped[dict] = mapped_column(JSON); prediction_json: Mapped[dict] = mapped_column(JSON)

class ExperimentAssignment(Base):
    __tablename__="experiment_assignments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anonymous_id_hash: Mapped[str] = mapped_column(String, unique=True)
    bucket: Mapped[int] = mapped_column(Integer); group_name: Mapped[str] = mapped_column(String, index=True)

