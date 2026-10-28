import io
import struct
import zlib

from fastapi.testclient import TestClient

from app.main import app


def png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def test_comprehensive_groups_feedback_by_ad_and_matches_images(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    body=(
        "ad_id,feedback,title,image_filename\n"
        "AD-001,点击后自动跳转且返回很多次,素材一,ad-001.png\n"
        "AD-001,图片小字看不清,素材一,ad-001.png\n"
        "AD-002,页面打开和返回都正常,素材二,missing.png\n"
    ).encode("utf-8")
    with TestClient(app) as client:
        response=client.post(
            "/api/comprehensive",
            files=[("table",("feedback.csv",body,"text/csv")),("images",("ad-001.png",png(320,180),"image/png"))],
        )
    assert response.status_code==200, response.text
    data=response.json()
    assert data["processed"]==3 and data["summary"]["total_ads"]==2
    first=next(x for x in data["ads"] if x["ad_id"]=="AD-001")
    second=next(x for x in data["ads"] if x["ad_id"]=="AD-002")
    assert first["overall_risk"]=="high"
    assert {x["label"] for x in first["dominant_causes"]}>={"forced_or_unexpected_jump","return_path_friction","unclear_material"}
    assert first["images"][0]["width"]==320
    assert first["images"][0]["semantic_review"]=="not_performed"
    assert second["missing_images"]==["missing.png"] and second["requires_human_review"] is True


def test_comprehensive_rejects_sensitive_columns():
    body="ad_id,feedback,手机号\nAD-001,体验不好,13812345678\n".encode("utf-8")
    with TestClient(app) as client:
        response=client.post("/api/comprehensive",files={"table":("feedback.csv",body,"text/csv")})
    assert response.status_code==400
    assert response.json()["detail"]["code"]=="policy_guardrail_triggered"


def test_low_resolution_image_raises_aggregate_risk_to_medium(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    body="ad_id,feedback,image_filename\nAD-003,页面打开和返回都正常,small.png\n".encode("utf-8")
    with TestClient(app) as client:
        response=client.post(
            "/api/comprehensive",
            files=[("table",("feedback.csv",body,"text/csv")),("images",("small.png",png(200,200),"image/png"))],
        )
    assert response.status_code==200
    ad=response.json()["ads"][0]
    assert ad["overall_risk"]=="medium"
    assert ad["dominant_causes"]==[]
    assert ad["asset_findings"][0]["signal"]=="readability_check"
