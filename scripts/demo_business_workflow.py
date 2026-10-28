"""Generate clearly simulated before/after handoff artifacts through actual APIs."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from fastapi.testclient import TestClient
from app.main import app
from app.service import demo_mode


def main():
    if not demo_mode(): raise SystemExit("此脚本仅允许规则Demo模式，避免意外模型批量调用")
    target=ROOT/"output/mvp-demo"
    target.mkdir(parents=True,exist_ok=True)
    with TestClient(app) as client:
        source=client.get("/api/business/demo-input").json()
        response=client.post("/api/business/reports",json=source)
        response.raise_for_status()
        before=response.json()
        rid=before["report_id"]
        (target/"report-before-review.json").write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding="utf-8")
        (target/"draft.md").write_text(client.get(f"/api/business/reports/{rid}/export").text,encoding="utf-8")
        blocked=client.get(f"/api/business/reports/{rid}/export?final=true").status_code
        for case in before["cases"]:
            if case["handoff_status"]=="draft_ready": continue
            body={"decision":"accepted","notes":"模拟人工环节：仅演示核查确认与交接门禁，并非真实素材验证。","evidence_confirmed":True}
            if case["ad_id"]=="AD-C":
                body.update(decision="modified",corrected_labels=["no_issue"],corrected_risk="low",notes="模拟补充信息：用户确认没有具体故障；这里只演示人工修正，不作真实业务事实。")
            response=client.post(f"/api/business/reports/{rid}/cases/{case['case_id']}/review",json=body)
            response.raise_for_status()
        after=client.get(f"/api/business/reports/{rid}").json()
        final=client.get(f"/api/business/reports/{rid}/export?final=true")
        final.raise_for_status()
        (target/"report-after-review.json").write_text(json.dumps(after,ensure_ascii=False,indent=2),encoding="utf-8")
        (target/"handoff.md").write_text(final.text,encoding="utf-8")
        summary={"scenario":"entirely_synthetic_including_human_steps","before":before["summary"],"before_final_export_http":blocked,"after":after["summary"],"after_final_export_http":final.status_code,"dispatch_performed":False}
        (target/"run-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=="__main__": main()
