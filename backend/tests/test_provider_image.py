from fastapi.testclient import TestClient

from app.main import app
from app.provider import ProviderResponse


PAYLOAD={
    "title":"Provider 集成样例","ad_copy":"点击查看活动","feedback":"自动跳转到病毒网站",
    "industry":"工具","media_scene":"浏览器","landing_type":"Web","material_format":"图文",
}


def test_real_provider_consumes_rag_and_cannot_lower_rule_risk(monkeypatch):
    captured={}

    class FakeProvider:
        configured=True
        provider="fake-compatible"
        model="fake-vision"

        async def generate(self,messages,schema):
            captured["messages"]=messages; captured["schema"]=schema
            return ProviderResponse(
                data={
                    "labels":[{"label":"malicious_or_suspicious_redirect","confidence":.91}],
                    "overall_risk":"low","confidence":.91,
                    "evidence":[
                        {"source":"input","field":"feedback","quote":"病毒网站","citation_id":None},
                        {"source":"retrieval","field":None,"quote":"伪造引用","citation_id":"NOT_REAL"},
                    ],
                    "strategy_recommendations":[],"requires_human_review":False,"uncertainties":[],
                },provider=self.provider,model=self.model,latency_ms=9,input_tokens=20,output_tokens=10,
            )

    monkeypatch.setenv("DEMO_MODE","false")
    monkeypatch.setattr("app.service.OpenAICompatibleProvider",FakeProvider)
    with TestClient(app) as client:
        response=client.post("/api/analyses",json=PAYLOAD)
    assert response.status_code==200
    body=response.json()
    assert body["overall_risk"]=="critical" and body["requires_human_review"] is True
    assert body["model_info"]["mode"]=="provider" and body["model_info"]["simulated"] is False
    assert all(x.get("citation_id")!="NOT_REAL" for x in body["evidence"])
    assert "retrieved_policy_chunks" in captured["messages"][1]["content"]
    assert captured["schema"]["additionalProperties"] is False
    assert captured["schema"]["$defs"]["ProviderEvidence"]["additionalProperties"] is False
    assert set(captured["schema"]["$defs"]["ProviderEvidence"]["required"])=={"source","quote","field","citation_id"}


def test_image_upload_is_validated_and_demo_never_claims_visual_understanding(monkeypatch):
    monkeypatch.setenv("DEMO_MODE","true")
    png=b"\x89PNG\r\n\x1a\n"+b"synthetic-image-bytes"
    with TestClient(app) as client:
        good=client.post("/api/analyses/image",data={"payload":__import__("json").dumps(PAYLOAD)},files={"file":("demo.png",png,"image/png")})
        bad=client.post("/api/analyses/image",data={"payload":__import__("json").dumps(PAYLOAD)},files={"file":("fake.png",b"not-an-image","image/png")})
    assert good.status_code==200
    assert good.json()["requires_human_review"] is True
    assert any("不支持视觉理解" in x for x in good.json()["uncertainties"])
    assert bad.status_code==400 and bad.json()["detail"]["code"]=="validation_error"
