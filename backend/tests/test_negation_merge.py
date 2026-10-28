import pytest
from app.engine import DemoEngine
from app.schemas import AnalysisInput, LabelResult, ProviderAnalysisDraft
from app.provider import ProviderResponse
from app.service import _normalize_provider_output

def item(text):
    return AnalysisInput(title="合成回归案例",ad_copy="普通产品介绍",feedback=text,industry="工具",media_scene="天气",landing_type="Web",material_format="图文")

@pytest.mark.parametrize("text",[
    "我没有遇到自动跳转，返回也正常",
    "没有出现自动跳转", "未发现恶意网站", "并没有索取通讯录",
    "没有要求读取通讯录", "也没有申请定位权限",
    "已经确认不是钓鱼网站，也没有索取通讯录，关闭和返回都正常。",
])
def test_extended_negations_do_not_trigger_problem(text):
    output=DemoEngine().analyze(item(text),[])
    assert [x.label for x in output.labels]==["no_issue"]
    assert output.overall_risk=="low"

@pytest.mark.parametrize("text,expected",[
    ("没有自动跳转，但页面要求读取通讯录",{"potential_privacy_risk"}),
    ("我没有遇到自动跳转，返回也正常，但浏览器确实提示这个落地页是恶意网站。",{"malicious_or_suspicious_redirect"}),
    ("没有同意授权，但页面要求读取通讯录",{"potential_privacy_risk"}),
    ("不是没有自动跳转",{"forced_or_unexpected_jump"}),
    ("之前没有自动跳转，今天却自动跳转到病毒网站",{"forced_or_unexpected_jump","malicious_or_suspicious_redirect"}),
])
def test_negation_does_not_erase_positive_clause(text,expected):
    output=DemoEngine().analyze(item(text),[])
    assert {x.label for x in output.labels}==expected

def test_evidence_uses_positive_occurrence_not_earlier_negation():
    text="没有自动跳转。"+"此前观察结果正常。"*8+"但今天自动跳转到商店。"
    output=DemoEngine().analyze(item(text),[])
    assert any("今天自动跳转" in ev.quote for ev in output.evidence)
    assert all("没有自动跳转" not in ev.quote for ev in output.evidence)

def test_stale_rule_false_positive_does_not_pollute_correct_model():
    text="我没有遇到自动跳转，返回也正常，但浏览器确实提示这个落地页是恶意网站。"
    source=item(text)
    rules=DemoEngine().analyze(source,[])
    # Simulate the older cached rule result, which included a false jump label.
    rules=rules.model_copy(update={"labels":rules.labels+[LabelResult(label="forced_or_unexpected_jump",confidence=.9)]})
    data={"labels":[{"label":"malicious_or_suspicious_redirect","confidence":.9}],"overall_risk":"critical","confidence":.9,"evidence":[{"source":"input","field":"feedback","quote":"浏览器确实提示这个落地页是恶意网站","citation_id":None}],"strategy_recommendations":[],"requires_human_review":True,"uncertainties":[],"assessment_status":"issue_detected"}
    output=_normalize_provider_output(source,[],ProviderAnalysisDraft.model_validate(data),ProviderResponse(data=data,provider="offline",model="fixture",latency_ms=0),"test",rules,False)
    assert {x.label for x in output.labels}=={"malicious_or_suspicious_redirect"}
    assert output.overall_risk=="critical" and output.requires_human_review
