import json
import pytest
from pydantic import ValidationError
from app.engine import DemoEngine, enforce_rules, repair_model_output
from app.retrieval import PolicyRetriever
from app.schemas import AnalysisInput, AnalysisOutput

def item(**kw):
    data={"title":"演示素材","ad_copy":"普通说明","feedback":"页面正常","industry":"工具","media_scene":"天气","landing_type":"Web","material_format":"图文"}; data.update(kw); return AnalysisInput(**data)

def test_no_issue_is_mutually_exclusive():
    payload={"labels":[{"label":"no_issue","confidence":.7},{"label":"unclear_material","confidence":.8}],"overall_risk":"low","requires_human_review":False}
    fixed=enforce_rules(payload)
    assert [x["label"] for x in fixed["labels"]]==["unclear_material"]

def test_critical_risk_escalates_and_requires_review():
    result=DemoEngine().analyze(item(feedback="跳到病毒网站疑似诈骗"),[])
    assert result.overall_risk=="critical" and result.requires_human_review
    assert any(x.category in {"delivery","review"} and x.priority=="P0" for x in result.strategy_recommendations)

def test_citation_ids_traceable():
    from pathlib import Path
    retriever=PolicyRetriever(Path(__file__).resolve().parents[2]/"data"/"policies")
    citations=retriever.search("自动跳转 返回很多次",top_k=3)
    result=DemoEngine().analyze(item(feedback="自动跳转，返回很多次"),citations)
    ids={c.citation_id for c in result.citations}
    assert ids and all(not e.citation_id or e.citation_id in ids for e in result.evidence)

def test_schema_validation_and_single_repair():
    raw='模型前缀```json\n{"ok": true}\n```后缀'
    assert repair_model_output(raw)=={"ok":True}
    with pytest.raises(ValidationError):
        AnalysisOutput.model_validate({"analysis_id":"x"})

def test_demo_mode_is_deterministic():
    engine=DemoEngine(); first=engine.analyze(item(feedback="广告太多，一直弹"),[]); second=engine.analyze(item(feedback="广告太多，一直弹"),[])
    assert first.model_dump()==second.model_dump()

@pytest.mark.parametrize("feedback", ["没有自动跳转", "页面并不模糊", "页面也不模糊", "不是恶意网站", "现在不会一直弹"])
def test_negated_feedback_does_not_trigger_issue(feedback):
    result=DemoEngine().analyze(item(feedback=feedback),[])
    assert [x.label for x in result.labels]==["no_issue"]

def test_vague_feedback_stays_conservative_and_explains_uncertainty():
    result=DemoEngine().analyze(item(feedback="感觉奇怪，体验不太好"),[])
    assert [x.label for x in result.labels]==["no_issue"]
    assert any("反馈表达较模糊" in x for x in result.uncertainties)

def test_positive_phrase_inside_negative_sentence_is_still_detected():
    result=DemoEngine().analyze(item(feedback="不是正常返回，而是连续返回很多次"),[])
    assert "return_path_friction" in {x.label for x in result.labels}

