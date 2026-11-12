import json

from fastapi.testclient import TestClient

from app import diagnostics
from app import diagnostic_requests
from app.main import app
from app.provider import ProviderResponse


def test_monitor_filters_strictly_and_separates_metric_and_text_evidence():
    with TestClient(app) as client:
        result = client.post("/api/diagnostics/monitor").json()
        assert result["source"] == "synthetic"
        assert result["mode"] == "rules"
        assert result["skipped"] == 1 and result["flagged"] == 2
        by_ad = {item["ad_id"]: item for item in result["items"]}
        assert by_ad["DEMO-A"]["quotes"]
        assert by_ad["DEMO-A"]["citations"]
        assert by_ad["DEMO-B"]["findings"] == ["反馈事件率达到监测阈值"]
        assert by_ad["DEMO-B"]["risk"] is None
        equal = client.post("/api/diagnostics/monitor", data={"min_impressions": 156000}).json()
        assert equal["items"] == []


def test_strategy_observed_improvement_can_coexist_with_rollback_review():
    with TestClient(app) as client:
        result = client.post("/api/diagnostics/strategy", data=diagnostics.SAMPLE_DATES).json()
        assert result["comparable"] is True
        assert result["target_met"] is True
        assert result["status"] == "触发护栏，人工评估回滚"
        assert result["guardrails"] == ["M02", "M04"]
        assert result["before"]["impressions"] == result["after"]["impressions"] == 156000
        assert result["after"]["ecpm"] == 515 / 52
        assert result["after"]["payer_rate"] == 3.4000000000000004
        invalid = client.post("/api/diagnostics/strategy", data=diagnostics.SAMPLE_DATES | {"before_end": "2026-11-07"})
        assert invalid.status_code == 422
        incomplete = client.post("/api/diagnostics/strategy", data=diagnostics.SAMPLE_DATES | {"after_end": "2026-11-11"}).json()
        assert incomplete["status"] == "数据不足，暂不判断"
        assert incomplete["expected_days"] == [3, 4]


def test_csv_upload_missing_values_and_duplicate_keys():
    csv = "date,ad_id,creative_id,impressions,ecpm,paying_users,eligible_users\n2026-11-01,AD-X,C-1,100001,10,2,10\n2026-11-02,AD-X,C-1,300003,20,3,90\n"
    with TestClient(app) as client:
        upload = client.post("/api/diagnostics/monitor", files={"file":("daily.csv", csv, "text/csv")})
        assert upload.status_code == 200
        data = upload.json()["items"][0]["metrics"]
        assert data["ecpm"] == 17.5
        assert data["payer_rate"] == 5.0
        assert data["feedback_rate"] is None and data["revenue"] is None
        duplicate = csv + csv.splitlines()[1] + "\n"
        assert client.post("/api/diagnostics/monitor", files={"file":("daily.csv", duplicate)}).status_code == 422
        invalid = csv.replace(",2,10", ",11,10")
        assert client.post("/api/diagnostics/monitor", files={"file":("daily.csv", invalid)}).status_code == 422


def test_provider_sees_computed_evidence_only_and_invalid_reference_falls_back(monkeypatch):
    calls = []
    reference = "A001"

    class ProviderStub:
        configured = True

        async def generate(self, messages, schema):
            calls.append(messages)
            return ProviderResponse(
                data={"summary":"优先核查异常","recommendations":[{"action":"复现跳转","evidence_ids":[reference]}]},
                provider="fixture", model="fixture", latency_ms=0,
            )

    monkeypatch.setattr(diagnostics, "OpenAICompatibleProvider", ProviderStub)
    with TestClient(app) as client:
        client.post("/api/diagnostics/monitor")
        assert not calls
        result = client.post("/api/diagnostics/monitor", data={"use_model":"true"}).json()
        assert result["mode"] == "provider"
        payload = calls[0][1]["content"]
        assert "DEMO-A" not in payload and "浏览器提示" not in payload
        assert json.loads(payload)["evidence"]["A001"]["metrics"]["impressions"] == 156000
        reference = "UNKNOWN"
        fallback = client.post("/api/diagnostics/monitor", data={"use_model":"true"}).json()
        assert fallback["mode"] == "rules"
        assert fallback["model_summary"] is None and fallback["model_notice"]


HISTORY_CSV = """date,ad_id,creative_id,industry,impressions,negative_feedback
2026-11-08,AD-H,C-H,电商,20000,100
2026-11-10,AD-H,C-H,电商,15000,225
2026-11-10,AD-E,C-E,电商,10000,300
2026-11-10,AD-N,C-N,电商,11000,80
2026-11-10,AD-G,C-G,游戏,20000,600
"""


def test_free_text_invokes_model_and_compares_matched_history(monkeypatch):
    calls = []

    class ModelStub:
        configured = True

        async def generate(self, messages, schema):
            content = json.loads(messages[1]["content"])
            calls.append(content)
            if "evidence" in content:
                data = {"summary":"反馈事件率出现上升线索","recommendations":[{"action":"抽查反馈原文","evidence_ids":["A001"]}]}
            else:
                data = {"industry":"电商", "compare_history":True}
            return ProviderResponse(data=data, provider="fixture", model="fixture", latency_ms=0)

    monkeypatch.setattr(diagnostics, "OpenAICompatibleProvider", ModelStub)
    monkeypatch.setattr(diagnostic_requests, "OpenAICompatibleProvider", ModelStub)
    with TestClient(app) as client:
        response = client.post("/api/diagnostics/monitor",
            data={"analysis_request":"检查电商行业曝光量大于一万的素材，比较风险是否高于历史平均"},
            files={"file":("daily.csv", HISTORY_CSV)})
        assert response.status_code == 200
        report = response.json()
        assert report["industry"] == "电商" and report["min_impressions"] == 10000
        assert report["mode"] == report["planning_mode"] == "provider"
        assert [item["ad_id"] for item in report["items"]] == ["AD-H", "AD-N"]
        assert report["items"][0]["history"]["rate"] == 0.5
        assert report["items"][0]["history"]["delta"] == 1
        assert report["items"][1]["history"]["delta"] is None
        assert report["history_summary"]["rate"] is None
        assert len(calls) == 2
        assert "AD-H" not in json.dumps(calls)


def test_free_text_missing_history_and_inclusive_exposure(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    with TestClient(app) as client:
        response = client.post("/api/diagnostics/monitor",
            data={"analysis_request":"检查电商行业曝光量至少一万的素材，比较此前30天历史平均"},
            files={"file":("daily.csv", HISTORY_CSV)})
        assert response.status_code == 200
        report = response.json()
        assert report["mode"] == "rules" and report["model_notice"]
        assert {item["ad_id"] for item in report["items"]} == {"AD-H","AD-N","AD-E"}
        assert all(item["history"]["delta"] is None for item in report["items"])
        missing = client.post("/api/diagnostics/monitor", data={"analysis_request":"检查金融行业"})
        assert missing.status_code == 422


def test_strategy_request_keeps_selected_windows_and_extracts_thresholds(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    with TestClient(app) as client:
        response = client.post("/api/diagnostics/strategy", data=diagnostics.SAMPLE_DATES | {
            "analysis_request":"分析电商行业。反馈事件率目标降幅30%，商业护栏降幅15%。",
        })
        assert response.status_code == 200
        report = response.json()
        assert report["dates"] == diagnostics.SAMPLE_DATES
        assert report["common_materials"] == 2
        assert report["target_drop"] == 30 and report["guardrail_drop"] == 15
        assert report["status"] == "触发护栏，人工评估回滚"
