from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.database import SessionLocal
from app.models import Analysis, HumanReview

BASE={"title":"人工编辑回归样例","ad_copy":"产品介绍","feedback":"自动跳转，返回很多次","industry":"工具","media_scene":"天气","landing_type":"Web","material_format":"图文"}

def test_actual_edits_are_saved_without_overwriting_ai(monkeypatch):
    monkeypatch.setenv("DEMO_MODE","true")
    with TestClient(app) as client:
        run=client.post("/api/agent/runs",json=BASE).json()
        original=run["output"]
        recs=[dict(x,action="人工核实返回入口和实际返回步骤") for x in original["strategy_recommendations"]]
        response=client.post(f"/api/agent/runs/{run['thread_id']}/resume",json={"decision":"modified","corrected_labels":["return_path_friction"],"corrected_risk":"high","edited_recommendations":recs,"notes":"人工确认只有返回困难"})
        assert response.status_code==200,response.text
        body=response.json()
        assert body["status"]=="completed"
        assert body["output"]==original
        assert [x["label"] for x in body["corrected_output"]["labels"]]==["return_path_friction"]
        with SessionLocal() as db:
            assert db.get(Analysis,original["analysis_id"]).original_output_json==original
            reviews=db.scalars(select(HumanReview).where(HumanReview.analysis_id==original["analysis_id"])).all()
            assert any(x.corrected_output_json==body["corrected_output"] and x.notes=="人工确认只有返回困难" for x in reviews)

def test_invalid_corrections_do_not_consume_interruption(monkeypatch):
    monkeypatch.setenv("DEMO_MODE","true")
    with TestClient(app) as client:
        run=client.post("/api/agent/runs",json=BASE).json()
        url=f"/api/agent/runs/{run['thread_id']}/resume"
        assert client.post(url,json={"decision":"modified"}).status_code==422
        recs=run["output"]["strategy_recommendations"]
        for labels in [["unknown"],["no_issue","return_path_friction"],[]]:
            assert client.post(url,json={"decision":"modified","corrected_labels":labels,"corrected_risk":"high","edited_recommendations":recs}).status_code==422
        assert client.post(url,json={"decision":"accepted"}).status_code==200

def test_reduced_labels_and_recommendations_are_saved_together(monkeypatch):
    monkeypatch.setenv("DEMO_MODE","true")
    with TestClient(app) as client:
        run=client.post("/api/agent/runs",json=BASE).json()
        original=run["output"]
        kept=[x for x in original["strategy_recommendations"] if "一键返回" in x["action"]]
        assert len(kept)==1
        payload={"decision":"modified","corrected_labels":["return_path_friction"],"corrected_risk":"high","edited_recommendations":kept,"recommendation_label_links":[["return_path_friction"]],"notes":"移除跳转，仅保留返回问题"}
        url=f"/api/agent/runs/{run['thread_id']}/resume"
        invalid={**payload,"recommendation_label_links":[["forced_or_unexpected_jump"]]}
        assert client.post(url,json=invalid).status_code==422
        response=client.post(url,json=payload)
        assert response.status_code==200,response.text
        corrected=response.json()["corrected_output"]
        assert corrected["strategy_recommendations"]==kept
        assert corrected["recommendation_label_links"]==[["return_path_friction"]]
        assert len(response.json()["output"]["strategy_recommendations"])>len(kept)
        with SessionLocal() as db:
            saved=db.scalars(select(HumanReview).where(HumanReview.analysis_id==original["analysis_id"])).all()
            assert any(x.corrected_output_json==corrected for x in saved)
