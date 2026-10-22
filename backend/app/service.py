from __future__ import annotations
import json, os, uuid
from pathlib import Path
from dotenv import load_dotenv
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import Base, engine
from .engine import DemoEngine, RECOMMENDATIONS, enforce_rules
from .models import Analysis, AnalysisLabel, EvidenceChunk, HumanReview, PromptVersion, RecommendationDB
from .pii import detect_pii_text
from .provider import OpenAICompatibleProvider, ProviderError
from .retrieval import PolicyRetriever
from .schemas import AnalysisInput, AnalysisOutput, Evidence, LabelResult, ModelInfo, ProviderAnalysisDraft, Recommendation, ReviewInput
from .taxonomy import LABELS

ROOT=Path(__file__).resolve().parents[2]
load_dotenv(ROOT/".env", override=False)
retriever=PolicyRetriever(ROOT/"data"/"policies")
demo_engine=DemoEngine()

def demo_mode() -> bool:
    return os.getenv("DEMO_MODE", "true").strip().lower() not in {"0", "false", "no", "off"}

def init_db():
    Base.metadata.create_all(engine)
    from .database import SessionLocal
    with SessionLocal() as db:
        if not db.scalar(select(PromptVersion).limit(1)):
            db.add(PromptVersion(version="demo-v1.0",name="默认演示 Prompt",content="基于输入证据和检索片段进行多标签广告体验分析；证据不足时输出 uncertainty。",is_active=True)); db.commit()

def _provider_messages(item: AnalysisInput, citations: list[dict], prompt: str, image_data_url: str | None) -> list[dict]:
    source={"input":item.model_dump(exclude_none=True),"retrieved_policy_chunks":citations}
    instruction=(
        prompt+"\n只输出符合 JSON Schema 的对象。只能使用给定 taxonomy；否定表达不得作为正例；"
        "模糊反馈不得补全不存在的事实。input 证据必须逐字引用输入，retrieval 证据必须使用给出的 citation_id。"
        "若提供图片，image 证据应描述可见事实，不推断人物身份或敏感属性。taxonomy="+json.dumps(LABELS,ensure_ascii=False)
    )
    content: str | list[dict]=json.dumps(source,ensure_ascii=False)
    if image_data_url:
        content=[{"type":"text","text":content},{"type":"image_url","image_url":{"url":image_data_url,"detail":"high"}}]
    return [{"role":"system","content":instruction},{"role":"user","content":content}]

def _recommendation(label: str) -> Recommendation:
    r=RECOMMENDATIONS[label]
    return Recommendation(category=r[0],action=r[1],rationale=r[2],priority=r[3],expected_metric=r[4],guardrail_metric=r[5])

def _normalize_provider_output(item: AnalysisInput, citations: list[dict], draft: ProviderAnalysisDraft, meta, prompt_version: str, rule_output: AnalysisOutput, has_image: bool) -> AnalysisOutput:
    labels={x.label:x for x in draft.labels if x.label in LABELS}
    # Deterministic positive rules are a safety floor, while their negation-aware
    # matching prevents the old false-positive behavior.
    for label in rule_output.labels:
        if label.label != "no_issue": labels.setdefault(label.label,label)
    if len(labels)>1: labels.pop("no_issue",None)
    if not labels: labels={"no_issue":LabelResult(label="no_issue",confidence=.6)}
    valid_citations={x["citation_id"] for x in citations}
    input_text="\n".join([item.title,item.ad_copy,item.feedback,item.first_three_seconds or ""])
    evidence=[]
    for ev in draft.evidence:
        if ev.source=="retrieval" and ev.citation_id in valid_citations: evidence.append(ev)
        elif ev.source=="input" and ev.quote and ev.quote in input_text: evidence.append(ev)
        elif ev.source=="image" and has_image: evidence.append(ev)
    existing_actions={x.category+"\0"+x.action:x for x in draft.strategy_recommendations}
    recommendations=list(existing_actions.values())
    covered={x.label for x in draft.labels if x.label in labels}
    recommendations.extend(_recommendation(label) for label in labels if label not in covered)
    if not recommendations: recommendations=[_recommendation(next(iter(labels)))]
    uncertainties=list(dict.fromkeys(draft.uncertainties))
    if rule_output.uncertainties:
        uncertainties=list(dict.fromkeys(uncertainties+rule_output.uncertainties))
    payload={
        "analysis_id":str(uuid.uuid4()),"labels":[x.model_dump() for x in labels.values()],
        "overall_risk":draft.overall_risk,"confidence":draft.confidence,
        "evidence":[x.model_dump() for x in evidence],"citations":citations,
        "strategy_recommendations":[x.model_dump() for x in recommendations],
        "requires_human_review":draft.requires_human_review,"uncertainties":uncertainties,
        "model_info":ModelInfo(provider=meta.provider,model=meta.model,mode="provider",latency_ms=meta.latency_ms,input_tokens=meta.input_tokens,output_tokens=meta.output_tokens,estimated_cost_usd=0,simulated=False).model_dump(),
        "prompt_version":prompt_version,
    }
    return AnalysisOutput.model_validate(enforce_rules(payload))

async def analyze_item(
    db: Session,
    item: AnalysisInput,
    image_data_url: str | None = None,
    citations_override: list[dict] | None = None,
) -> AnalysisOutput:
    pii=detect_pii_text(" ".join([item.title,item.ad_copy,item.feedback,item.first_three_seconds or ""]))
    if pii: raise ValueError("policy_guardrail_triggered: 检测到疑似敏感信息："+", ".join(pii))
    query=" ".join([item.title,item.ad_copy,item.feedback,item.first_three_seconds or "",item.industry,item.media_scene,item.landing_type])
    citations=citations_override if citations_override is not None else retriever.search(query,top_k=4,scenario=item.media_scene)
    active=db.scalar(select(PromptVersion).where(PromptVersion.is_active==True))
    prompt_version=active.version if active else "demo-v1.0"
    rule_output=demo_engine.analyze(item,citations,prompt_version)
    if demo_mode():
        output=rule_output
    else:
        provider=OpenAICompatibleProvider()
        if not provider.configured:
            raise ProviderError("provider_not_configured", "DEMO_MODE=false，但 LLM_API_KEY、LLM_BASE_URL 或 LLM_MODEL 未完整配置")
        if image_data_url and os.getenv("ENABLE_IMAGE_REVIEW", "false").lower()!="true":
            raise ProviderError("image_review_disabled", "图片审核未启用；确认数据边界后设置 ENABLE_IMAGE_REVIEW=true")
        try:
            meta=await provider.generate(_provider_messages(item,citations,active.content if active else "基于输入和检索证据进行广告体验分析。",image_data_url),ProviderAnalysisDraft.model_json_schema())
            draft=ProviderAnalysisDraft.model_validate(meta.data)
        except ValidationError as exc:
            raise ProviderError("malformed_model_output", "模型输出未通过结构化校验") from exc
        output=_normalize_provider_output(item,citations,draft,meta,prompt_version,rule_output,bool(image_data_url))
    return output

def persist_analysis(db: Session, item: AnalysisInput, output: AnalysisOutput) -> AnalysisOutput:
    # Demo IDs are deterministic. Re-running the same input should be idempotent
    # rather than duplicating child rows or violating the primary key.
    if db.get(Analysis, output.analysis_id):
        return output
    row=Analysis(id=output.analysis_id,input_json=item.model_dump(),original_output_json=output.model_dump(),overall_risk=output.overall_risk,confidence=output.confidence,requires_human_review=output.requires_human_review,prompt_version=output.prompt_version)
    db.add(row)
    for label in output.labels: db.add(AnalysisLabel(analysis_id=row.id,label=label.label,confidence=label.confidence))
    for c in output.citations: db.add(EvidenceChunk(analysis_id=row.id,citation_id=c.citation_id,chunk_id=c.chunk_id,document_title=c.document_title,snippet=c.snippet,score=c.score))
    for r in output.strategy_recommendations: db.add(RecommendationDB(analysis_id=row.id,**r.model_dump()))
    db.commit(); return output

async def analyze_and_save(db: Session, item: AnalysisInput, image_data_url: str | None = None) -> AnalysisOutput:
    output=await analyze_item(db,item,image_data_url)
    return persist_analysis(db,item,output)

def save_review(db: Session, analysis: Analysis, review: ReviewInput) -> dict:
    corrected=dict(analysis.original_output_json)
    if review.corrected_labels is not None: corrected["labels"]=[{"label":x,"confidence":1.0} for x in review.corrected_labels]
    if review.corrected_risk is not None: corrected["overall_risk"]=review.corrected_risk
    if review.edited_recommendations is not None: corrected["strategy_recommendations"]=[x.model_dump() for x in review.edited_recommendations]
    db.add(HumanReview(analysis_id=analysis.id,reviewer=review.reviewer,decision=review.decision,corrected_output_json=corrected,notes=review.notes)); db.commit()
    return {"analysis_id":analysis.id,"original":analysis.original_output_json,"corrected":corrected,"decision":review.decision}
