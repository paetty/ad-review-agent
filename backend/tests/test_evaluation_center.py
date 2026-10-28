from fastapi.testclient import TestClient
from sqlalchemy import func, select
from app.main import app
from app.database import SessionLocal
from app.models import Analysis, EvaluationItem
from app.provider import OpenAICompatibleProvider, ProviderResponse, ProviderError
from app.engine import DemoEngine
from app.schemas import AnalysisInput
import json

def preview(client,dataset="supplement",mode="rules"):
    response=client.post("/api/evaluations/preview",json={"dataset":dataset,"mode":mode})
    assert response.status_code==200,response.text
    return response.json()

def test_catalog_sizes_and_no_holdout_access():
    with TestClient(app) as client:
        data=client.get("/api/evaluations/datasets").json()
        assert {x["id"]:x["count"] for x in data["datasets"]}=={"development":28,"validation":8,"supplement":12,"legacy":80}
        assert client.post("/api/evaluations/preview",json={"dataset":"holdout_candidate","mode":"rules"}).status_code==422
        assert preview(client,"validation")["expected_model_calls"]==0
        assert preview(client,"legacy")["dataset"]["status_reference_count"]==0

def test_rule_run_is_isolated_and_never_calls_provider(monkeypatch):
    monkeypatch.setenv("DEMO_MODE","false")
    async def forbidden(*args,**kwargs):raise AssertionError("rules mode called provider")
    monkeypatch.setattr(OpenAICompatibleProvider,"generate",forbidden)
    with TestClient(app) as client:
        with SessionLocal() as db:before=db.scalar(select(func.count()).select_from(Analysis))
        p=preview(client)
        response=client.post("/api/evaluations/runs",json={"dataset":"supplement","mode":"rules","dataset_sha256":p["dataset"]["sha256"]})
        assert response.status_code==202,response.text
        result=client.get(f"/api/evaluations/runs/{response.json()['run_id']}").json()
        assert result["status"]=="completed" and result["processed"]==12 and result["failed"]==0
        assert len(result["items"])==12 and result["metrics"]["records"]==12
        assert result["metrics"]["tokens_simulated"] is True
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(Analysis))==before
            assert db.scalar(select(func.count()).select_from(EvaluationItem).where(EvaluationItem.run_id==result["run_id"]))==12

def test_provider_requires_confirmation_and_unchanged_dataset(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY","synthetic-test-key")
    monkeypatch.setenv("LLM_MODEL","synthetic-test-model")
    monkeypatch.setenv("LLM_BASE_URL","https://example.invalid")
    calls=[]
    async def forbidden(*args,**kwargs):calls.append(1);raise AssertionError()
    monkeypatch.setattr(OpenAICompatibleProvider,"generate",forbidden)
    with TestClient(app) as client:
        p=preview(client,"validation","provider")
        assert p["expected_model_calls"]==8 and p["estimated_cost_usd"] is None
        base={"dataset":"validation","mode":"provider","dataset_sha256":p["dataset"]["sha256"]}
        assert client.post("/api/evaluations/runs",json=base).status_code==400
        assert client.post("/api/evaluations/runs",json={**base,"dataset_sha256":"0"*64,"confirm_provider":True}).status_code==409
        assert calls==[]

def test_mock_provider_errors_are_visible_and_counted(monkeypatch):
    monkeypatch.setenv("DEMO_MODE","true")
    monkeypatch.setenv("LLM_API_KEY","synthetic-test-key")
    monkeypatch.setenv("LLM_MODEL","synthetic-test-model")
    monkeypatch.setenv("LLM_BASE_URL","https://example.invalid")
    calls=[]
    async def generate(self,messages,schema):
        calls.append(1)
        if len(calls)==1:raise ProviderError("provider_timeout","test timeout")
        item=AnalysisInput.model_validate(json.loads(messages[-1]["content"])["input"])
        rule=DemoEngine().analyze(item,[])
        payload={k:getattr(rule,k) for k in ["overall_risk","confidence","requires_human_review","uncertainties","assessment_status"]}
        payload.update(labels=[x.model_dump() for x in rule.labels],evidence=[x.model_dump() for x in rule.evidence],strategy_recommendations=[x.model_dump() for x in rule.strategy_recommendations])
        return ProviderResponse(data=payload,provider="mock",model="test",latency_ms=1,input_tokens=10,output_tokens=5)
    monkeypatch.setattr(OpenAICompatibleProvider,"generate",generate)
    with TestClient(app) as client:
        p=preview(client,"validation","provider")
        started=client.post("/api/evaluations/runs",json={"dataset":"validation","mode":"provider","confirm_provider":True,"dataset_sha256":p["dataset"]["sha256"]})
        assert started.status_code==202,started.text
        result=client.get(f"/api/evaluations/runs/{started.json()['run_id']}").json()
        assert len(calls)==8
        assert result["status"]=="partial" and result["failed"]==1
        assert result["items"][0]["error"]["code"]=="provider_timeout"
        assert result["items"][0]["matched"] is False
        assert result["metrics"]["records"]==8
        assert result["metrics"]["tokens_simulated"] is False
        assert result["metrics"]["input_tokens"]==70
        assert result["metrics"]["estimated_cost_usd"] is None
