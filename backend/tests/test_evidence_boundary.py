import pytest

from app.engine import DemoEngine
from app.provider import ProviderResponse
from app.schemas import AnalysisInput, ProviderAnalysisDraft
from app.service import _normalize_provider_output


def item(feedback):
    return AnalysisInput(title="演示素材", ad_copy="普通说明", feedback=feedback,
                         industry="工具", media_scene="天气", landing_type="Web", material_format="图文")


def normalize(feedback, label="no_issue", confidence=.95, status=None, evidence=None, **overrides):
    source = item(feedback)
    data = {"labels": [{"label": label, "confidence": confidence}], "overall_risk": "low",
            "confidence": confidence, "evidence": evidence if evidence is not None else [
                {"source": "input", "field": "feedback", "quote": feedback, "citation_id": None}],
            "strategy_recommendations": [], "requires_human_review": False, "uncertainties": []}
    if status is not None:
        data["assessment_status"] = status
    data.update(overrides)
    draft = ProviderAnalysisDraft.model_validate(data)
    meta = ProviderResponse(data=data, provider="test", model="test", latency_ms=1)
    return _normalize_provider_output(source, [], draft, meta, "test-prompt", DemoEngine().analyze(source, []), False)


@pytest.mark.parametrize("feedback", ["没有自动跳转，关闭按钮也正常", "广告信息能看清，点击和返回都正常"])
def test_normal_feedback_is_not_escalated_by_disclaimer(feedback):
    result = normalize(feedback)
    assert result.assessment_status == "no_explicit_issue"
    assert result.requires_human_review is False
    assert result.disclaimers and not result.uncertainties


@pytest.mark.parametrize("confidence", [.35, .99])
def test_vague_only_guess_is_abstained_even_at_high_confidence(confidence):
    result = normalize("感觉怪怪的，但我说不上来哪里不对", "unclear_material", confidence)
    assert [x.label for x in result.labels] == ["no_issue"]
    assert result.assessment_status == "insufficient_evidence" and result.requires_human_review
    assert [x.label for x in result.abstained_labels] == ["unclear_material"]
    assert result.overall_risk == "low"
    assert any("补充" in x.action for x in result.strategy_recommendations)
    assert all("无需自动限制" not in x.action for x in result.strategy_recommendations)


def test_low_confidence_concrete_semantic_issue_is_retained():
    result = normalize("进入商品页后按了好多下返回，才回到天气页", "return_path_friction", .35)
    assert [x.label for x in result.labels] == ["return_path_friction"]
    assert result.assessment_status == "issue_detected" and result.requires_human_review
    assert result.overall_risk == "high" and not result.abstained_labels


def test_vague_prefix_does_not_erase_concrete_problem():
    result = normalize("感觉怪怪的，但我按了六次返回键才退出", "return_path_friction")
    assert [x.label for x in result.labels] == ["return_path_friction"]


@pytest.mark.parametrize("feedback", ["感觉有点怪", "不怎么喜欢，但也没有具体想投诉的地方", "说不清哪里不对"])
def test_other_vague_expressions_do_not_become_specific_labels(feedback):
    result = normalize(feedback, "unclear_material", .99)
    assert result.assessment_status == "insufficient_evidence"
    assert [x.label for x in result.labels] == ["no_issue"]


def test_model_cannot_call_pure_vague_feedback_normal():
    result = normalize("感觉怪怪的", status="no_explicit_issue")
    assert result.assessment_status == "insufficient_evidence" and result.requires_human_review


def test_valid_multi_label_signals_are_not_collapsed_into_abstention():
    source = "自动跳转，而且画面模糊"
    result = normalize(source, "unclear_material", .35)
    assert {x.label for x in result.labels} == {"forced_or_unexpected_jump", "unclear_material"}
    assert result.assessment_status == "issue_detected" and result.requires_human_review


def test_state_does_not_depend_on_generic_model_uncertainty_text():
    result = normalize("页面正常", status="no_explicit_issue", uncertainties=["未对实际素材做合规认证"])
    assert result.assessment_status == "no_explicit_issue" and not result.requires_human_review


def test_explicit_model_abstention_overrides_unsupported_label():
    result = normalize("这里的交互需要再调查", "unclear_material", status="insufficient_evidence")
    assert result.assessment_status == "insufficient_evidence"
    assert [x.label for x in result.labels] == ["no_issue"]


def test_model_cannot_erase_deterministic_high_risk_signal():
    result = normalize("广告自动跳转到病毒网站", status="insufficient_evidence")
    assert {x.label for x in result.labels} >= {"forced_or_unexpected_jump", "malicious_or_suspicious_redirect"}
    assert result.overall_risk == "critical" and result.requires_human_review


def test_wrong_field_quote_cannot_support_model_label():
    result = normalize("进入商品页后按了好多下返回，才回到天气页", "return_path_friction", evidence=[
        {"source": "input", "field": "ad_copy", "quote": "按了好多下返回", "citation_id": None}])
    assert result.evidence == []
    assert result.assessment_status == "insufficient_evidence"
    assert [x.label for x in result.labels] == ["no_issue"]


def test_retrieval_alone_does_not_prove_current_ad_has_issue():
    result = normalize("感觉怪怪的", "unclear_material", evidence=[])
    assert result.assessment_status == "insufficient_evidence"


def test_unknown_empty_case_still_requires_review():
    result = normalize("")
    assert result.assessment_status == "insufficient_evidence" and result.requires_human_review


def test_prompt_and_schema_declare_state_and_policy_version():
    from app.service import _provider_messages
    from app.schemas import provider_analysis_schema
    schema = provider_analysis_schema()
    assert "assessment_status" in schema["required"]
    assert schema["additionalProperties"] is False
    message = _provider_messages(item("感觉怪怪的"), [], "只依据证据分析", None)[0]["content"]
    assert "insufficient_evidence" in message and "no_explicit_issue" in message
    assert "候选" in message and "阈值" in message
    result = normalize("页面正常")
    assert result.analysis_policy_version == "evidence-boundary-v2"
