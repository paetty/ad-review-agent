import copy

from fastapi.testclient import TestClient

from app.main import app
from app.engine import enforce_rules
from app.evaluation import calculate_metrics
from app.retrieval import PolicyRetriever
from app.service import ROOT


def test_exposure_denominator_and_media_checks(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    with TestClient(app) as client:
        payload = client.get("/api/business/demo-input").json()
        response = client.post("/api/business/reports", json=payload)
    assert response.status_code == 200, response.text
    report = response.json()
    cases = {x["ad_id"]: x for x in report["cases"]}
    assert report["summary"]["feedback_rows"] == 6
    assert report["summary"]["pending_review"] == 4
    assert cases["AD-A"]["rate"]["feedback_events_per_10k_impressions"] == 2
    assert cases["AD-B"]["rate"]["feedback_events_per_10k_impressions"] is None
    assert cases["AD-C"]["assessment_status"] == "insufficient_evidence"
    assert cases["AD-D"]["handoff_status"] == "draft_ready"
    assert cases["AD-E"]["rate"]["feedback_events_per_10k_impressions"] is None
    assert "视频" in str(cases["AD-B"]["media_checks"])
    assert "小程序" in str(cases["AD-C"]["media_checks"])
    assert report["permissions"]["send_to_department"] is False


def test_review_modifies_effective_result_without_overwriting_original(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    with TestClient(app) as client:
        payload = client.get("/api/business/demo-input").json()
        report = client.post("/api/business/reports", json=payload).json()
        rid = report["report_id"]
        assert client.get(f"/api/business/reports/{rid}/export?final=true").status_code == 409
        for case in report["cases"]:
            if case["handoff_status"] == "draft_ready": continue
            path = f"/api/business/reports/{rid}/cases/{case['case_id']}/review"
            assert client.post(path, json={"decision":"accepted","notes":"模拟核查"}).status_code == 400
            if case["ad_id"] == "AD-C":
                result = client.post(path, json={"decision":"modified","notes":"合成演示：补充说明后未发现明确问题","evidence_confirmed":True,"corrected_labels":["no_issue"],"corrected_risk":"low"})
            else:
                result = client.post(path, json={"decision":"accepted","notes":"合成演示：人工确认反馈线索和待处理方向","evidence_confirmed":True})
            assert result.status_code == 200, result.text
        final = client.get(f"/api/business/reports/{rid}").json()
        assert final["summary"]["handoff_ready"] is True
        item = next(x for x in final["cases"] if x["ad_id"] == "AD-C")
        assert item["observations"][0]["analysis"]["assessment_status"] == "insufficient_evidence"
        assert item["effective_labels"] == ["no_issue"]
        assert len(item["review_history"]) == 1
        assert client.get(f"/api/business/reports/{rid}/export?final=true").status_code == 200


def test_duplicate_keys_wrong_window_and_unknown_fields(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    with TestClient(app) as client:
        original = client.get("/api/business/demo-input").json()
        duplicate = copy.deepcopy(original)
        duplicate["feedback"].append(duplicate["feedback"][0])
        assert client.post("/api/business/reports", json=duplicate).status_code == 422
        duplicate = copy.deepcopy(original)
        duplicate["exposures"].append(duplicate["exposures"][0])
        assert client.post("/api/business/reports", json=duplicate).status_code == 422
        pii = copy.deepcopy(original)
        pii["feedback"][0]["user_id"] = "raw-user-identifier"
        assert client.post("/api/business/reports", json=pii).status_code == 422
        shifted = copy.deepcopy(original)
        shifted["exposures"][0]["window_end"] = "2026-10-08"
        r = client.post("/api/business/reports", json=shifted).json()
        assert next(x for x in r["cases"] if x["ad_id"] == "AD-A")["rate"]["impressions"] is None


def test_upload_templates_and_duplicate_header_rejection(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    with TestClient(app) as client:
        feedback = client.get("/api/business/template?kind=feedback").content
        exposures = client.get("/api/business/template?kind=exposures").content
        r = client.post("/api/business/reports/upload", files={"feedback_file":("feedback.csv",feedback,"text/csv"),"exposure_file":("exposures.csv",exposures,"text/csv")})
        assert r.status_code == 200, r.text
        bad = client.post("/api/business/reports/upload", files={"feedback_file":("bad.csv",b"feedback_id,feedback_id\nA,B\n","text/csv")})
        assert bad.status_code == 400


def test_platform_rules_are_not_applied_globally():
    retriever = PolicyRetriever(ROOT / "data" / "policies")
    generic = retriever.search("素材文案落地页一致性 下载入口", top_k=100)
    oppo = retriever.search("素材文案落地页一致性 下载入口", top_k=100, platform="oppo")
    assert all(x["platform"] == "all" for x in generic)
    assert any(x["platform"] == "oppo" and x["source_url"] for x in oppo)
    assert not any(x["platform"] == "vivo" for x in oppo)


def test_high_risk_guardrail_and_actual_risk_recall():
    payload = {"labels":[{"label":"forced_or_unexpected_jump","confidence":.95}],"overall_risk":"low","requires_human_review":False}
    assert enforce_rules(payload)["requires_human_review"] is True
    metrics = calculate_metrics([{"forced_or_unexpected_jump"}], [{"forced_or_unexpected_jump"}], ["high"], [False], ["low"])
    assert metrics["high_risk_recall"] == 0 and metrics["human_review_trigger_recall"] == 0
