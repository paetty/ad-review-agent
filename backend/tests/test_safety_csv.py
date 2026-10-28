from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.pii import detect_pii_text, detect_sensitive_columns

def test_pii_detection():
    assert "phone" in detect_pii_text("联系 13812345678")
    assert detect_sensitive_columns(["title","imei","手机号"])
    assert detect_sensitive_columns(["image_filename"])==[]

def test_csv_validation_and_sensitive_columns():
    with TestClient(app) as client:
        bad=b"title,imei\ndemo,123456789012345\n"
        res=client.post("/api/batch",files={"file":("bad.csv",bad,"text/csv")})
        assert res.status_code==400
        assert res.json()["detail"]["code"]=="policy_guardrail_triggered"

def test_api_key_not_in_frontend_or_logs(monkeypatch):
    secret="synthetic-credential-for-test-only"; monkeypatch.setenv("LLM_API_KEY",secret)
    root=Path(__file__).resolve().parents[2]
    frontend="\n".join(p.read_text(encoding="utf-8") for p in (root/"app").rglob("*.ts*") if ".test." not in p.name)
    assert secret not in frontend and "LLM_API_KEY" not in frontend

def test_repeated_analysis_is_idempotent():
    payload={"title":"幂等合成样例","ad_copy":"演示","feedback":"自动跳转","industry":"工具","media_scene":"天气","landing_type":"Web","material_format":"图文"}
    with TestClient(app) as client:
        first=client.post("/api/analyses",json=payload)
        second=client.post("/api/analyses",json=payload)
    assert first.status_code==second.status_code==200
    assert first.json()["analysis_id"]==second.json()["analysis_id"]
