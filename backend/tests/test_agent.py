from fastapi.testclient import TestClient

from app.main import app


BASE={
    "title":"Agent 合成样例","ad_copy":"功能介绍","feedback":"页面打开和返回都正常",
    "industry":"工具","media_scene":"天气","landing_type":"Web","material_format":"图文",
}


def test_low_risk_agent_run_completes_with_trace(monkeypatch):
    monkeypatch.setenv("DEMO_MODE","true")
    with TestClient(app) as client:
        response=client.post("/api/agent/runs",json=BASE)
    assert response.status_code==200
    body=response.json()
    assert body["status"]=="completed" and body["interrupt"] is None
    assert [x["node"] for x in body["trace"]]==["validate_input","retrieve_policy","analyze_risk","finalize"]


def test_high_risk_agent_interrupts_and_resumes_once(monkeypatch):
    monkeypatch.setenv("DEMO_MODE","true")
    payload={**BASE,"feedback":"点击后自动跳转，返回很多次还是回不去"}
    with TestClient(app) as client:
        started=client.post("/api/agent/runs",json=payload)
        assert started.status_code==200
        run=started.json()
        assert run["status"]=="awaiting_review"
        assert run["interrupt"]["risk"]=="high"
        resumed=client.post(f"/api/agent/runs/{run['thread_id']}/resume",json={"decision":"accepted","notes":"合成测试确认"})
        repeated=client.post(f"/api/agent/runs/{run['thread_id']}/resume",json={"decision":"accepted"})
    assert resumed.status_code==200 and resumed.json()["status"]=="completed"
    assert [x["node"] for x in resumed.json()["trace"]][-2:]==["human_review","finalize"]
    assert repeated.status_code==404


def test_agent_graph_documents_safety_boundary():
    with TestClient(app) as client:
        response=client.get("/api/agent/graph")
    assert response.status_code==200
    body=response.json()
    assert "human_review" in body["nodes"]
    assert "不执行下线" in body["safety_boundary"]
