from __future__ import annotations

import operator
import uuid
from typing import Annotated, Any, Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .database import SessionLocal
from .pii import detect_pii_text
from .schemas import AnalysisInput, AnalysisOutput, AgentResumeInput
from .service import analyze_item, retriever


class AdReviewAgentState(TypedDict, total=False):
    input: dict[str, Any]
    citations: list[dict[str, Any]]
    output: dict[str, Any]
    status: Literal["running", "awaiting_review", "completed"]
    human_decision: dict[str, Any]
    corrected_output: dict[str, Any]
    trace: Annotated[list[dict[str, Any]], operator.add]


def _event(node: str, detail: str) -> list[dict[str, str]]:
    return [{"node": node, "detail": detail}]


def validate_input(state: AdReviewAgentState) -> dict:
    item=AnalysisInput.model_validate(state["input"])
    text=" ".join([item.title,item.ad_copy,item.feedback,item.first_three_seconds or ""])
    pii=detect_pii_text(text)
    if pii:
        raise ValueError("policy_guardrail_triggered: 检测到疑似敏感信息："+", ".join(pii))
    return {"input":item.model_dump(),"status":"running","trace":_event("validate_input","字段与正文安全校验通过")}


def retrieve_policy(state: AdReviewAgentState) -> dict:
    item=AnalysisInput.model_validate(state["input"])
    query=" ".join([item.title,item.ad_copy,item.feedback,item.first_three_seconds or "",item.industry,item.media_scene,item.landing_type])
    citations=retriever.search(query,top_k=4,scenario=item.media_scene,platform=item.platform)
    return {"citations":citations,"trace":_event("retrieve_policy",f"检索到 {len(citations)} 条可追溯规则")}


async def analyze_risk(state: AdReviewAgentState) -> dict:
    item=AnalysisInput.model_validate(state["input"])
    with SessionLocal() as db:
        output=await analyze_item(db,item,citations_override=state.get("citations",[]))
    labels="、".join(label.label for label in output.labels)
    return {"output":output.model_dump(),"trace":_event("analyze_risk",f"输出风险 {output.overall_risk}，标签 {labels}")}


def route_review(state: AdReviewAgentState) -> Literal["human_review", "finalize"]:
    return "human_review" if state["output"]["requires_human_review"] else "finalize"


def human_review(state: AdReviewAgentState) -> dict:
    output=state["output"]
    decision=interrupt({
        "reason":"高风险、低置信度、证据不足或视觉信息未确认，必须由人工决定后才能完成任务。",
        "analysis_id":output["analysis_id"],
        "risk":output["overall_risk"],
        "labels":[item["label"] for item in output["labels"]],
    })
    review=AgentResumeInput.model_validate(decision)
    corrected=dict(output)
    if review.decision=="modified":
        corrected.update(labels=[{"label":x,"confidence":1.0} for x in review.corrected_labels],
                         overall_risk=review.corrected_risk,
                         strategy_recommendations=[x.model_dump() for x in review.edited_recommendations])
        corrected["assessment_status"]="no_explicit_issue" if review.corrected_labels==["no_issue"] else "issue_detected"
        corrected["requires_human_review"]=True
        if review.recommendation_label_links is not None:
            corrected["recommendation_label_links"]=review.recommendation_label_links
        AnalysisOutput.model_validate(corrected)
    return {"human_decision":decision,"corrected_output":corrected,"trace":_event("human_review","人工修正版已保存到执行状态，AI原始结论保留")}


def finalize(state: AdReviewAgentState) -> dict:
    detail="低风险路径自动完成"
    if state.get("human_decision"):
        detail=f"人工复核完成：{state['human_decision'].get('decision','unknown')}"
    return {"status":"completed","trace":_event("finalize",detail)}


def build_agent():
    graph=StateGraph(AdReviewAgentState)
    graph.add_node("validate_input",validate_input)
    graph.add_node("retrieve_policy",retrieve_policy)
    graph.add_node("analyze_risk",analyze_risk)
    graph.add_node("human_review",human_review)
    graph.add_node("finalize",finalize)
    graph.add_edge(START,"validate_input")
    graph.add_edge("validate_input","retrieve_policy")
    graph.add_edge("retrieve_policy","analyze_risk")
    graph.add_conditional_edges("analyze_risk",route_review,{"human_review":"human_review","finalize":"finalize"})
    graph.add_edge("human_review","finalize")
    graph.add_edge("finalize",END)
    return graph.compile(checkpointer=InMemorySaver(),name="ad-review-agent")


agent=build_agent()


async def start_agent_run(item: AnalysisInput, thread_id: str | None = None) -> tuple[str, dict]:
    thread_id=thread_id or str(uuid.uuid4())
    result=await agent.ainvoke(
        {"input":item.model_dump(),"status":"running","trace":[]},
        config={"configurable":{"thread_id":thread_id}},
    )
    return thread_id,result


async def resume_agent_run(thread_id: str, decision: dict[str, Any]) -> dict:
    config={"configurable":{"thread_id":thread_id}}
    snapshot=await agent.aget_state(config)
    if "human_review" not in snapshot.next:
        raise ValueError("agent run is not waiting for human review")
    return await agent.ainvoke(Command(resume=decision),config=config)
