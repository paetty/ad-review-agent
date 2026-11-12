"""Initialize or run the local enterprise demo."""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timedelta, timezone


# Public fixtures for the loopback-only synthetic workspace.
ACCOUNTS = [
    ("DEMO-PM-01", "广告产品经理", "product", "DemoPM!2026"),
    ("DEMO-OPS-01", "广告治理运营", "operations", "DemoOPS!2026"),
    ("DEMO-LEAD-01", "业务主管", "supervisor", "DemoLead!2026"),
]

FEEDBACK = [
    "没有点击，广告自动跳转到陌生网页。",
    "进入商品页后，返回很多次才回到天气页。",
    "广告写着新人0元，点进去才发现还有资格限制。",
    "这个广告很烦，但说不上哪里不对。",
    "我主动点击查看商品详情，返回正常。",
    "浏览器提示落地页是恶意网站。",
    "广告文案与落地页信息一致，点击和返回正常。",
    "没有遇到自动跳转，返回也正常。",
    "广告太多，同一条广告反复出现。",
    "广告上写最低价，实际支付时价格更高。",
    "文字太小看不清。",
    "点击关闭却自动跳转，连续返回也回不去。",
]


async def initialize(reset_passwords: bool) -> None:
    from sqlalchemy import delete, select
    from app.database import SessionLocal
    from app.enterprise_auth import Employee, StaffSession, hash_password, verify_password
    from app.evaluation_center import RunRequest, Selection, execute_run, preview, reserve_run
    from app.models import Analysis, EvaluationRun, HumanReview
    from app.schemas import AnalysisInput, ReviewInput
    from app.service import analyze_item, init_db, persist_analysis, save_review

    init_db()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        for index, feedback in enumerate(FEEDBACK):
            item = AnalysisInput(
                title=f"synthetic_demo · 治理案例 {index + 1:02}",
                ad_copy="合成示例：点击查看活动详情", feedback=feedback,
                industry="电商", media_scene="天气", landing_type="Web", material_format="图片",
            )
            output = await analyze_item(db, item, mode_override="rules")
            if db.get(Analysis, output.analysis_id):
                continue
            persist_analysis(db, item, output)
            row = db.get(Analysis, output.analysis_id)
            row.created_at = now - timedelta(days=index % 7)
            db.commit()
            if index in (1, 5) and output.requires_human_review:
                for note in ("合成演示：已核查原始反馈", "合成演示：补充核查说明")[:2 if index == 1 else 1]:
                    save_review(db, row, ReviewInput(reviewer="DEMO-OPS-01", decision="accepted", notes=note))

        has_evaluation = db.scalar(select(EvaluationRun.id).limit(1)) is not None
        for employee_id, name, role, password in ACCOUNTS:
            employee = db.get(Employee, employee_id)
            if employee and not reset_passwords and verify_password(password, employee.password_hash):
                continue
            if not employee:
                employee = Employee(employee_id=employee_id, display_name=name, role=role, enabled=True)
                db.add(employee)
            employee.password_hash = hash_password(password)
            db.execute(delete(StaffSession).where(StaffSession.employee_id == employee_id))
        db.commit()
    for employee_id, _, _, password in ACCOUNTS:
        print(f"{employee_id}\t{password}")
    if not has_evaluation:
        meta = preview(Selection(dataset="supplement"))["dataset"]
        run_id, rows, snapshot, prompt = reserve_run(RunRequest(dataset="supplement", dataset_sha256=meta["sha256"]))
        await execute_run(run_id, rows, snapshot, prompt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init", action="store_true", help="seed synthetic cases and local employee accounts")
    parser.add_argument("--reset-passwords", action="store_true", help="restore the fixed demo passwords and revoke their sessions")
    parser.add_argument("--port", type=int, default=8016)
    args = parser.parse_args()
    if args.reset_passwords and not args.init:
        parser.error("--reset-passwords requires --init")
    os.environ["ENTERPRISE_DEMO"] = "1"
    if args.init:
        asyncio.run(initialize(args.reset_passwords))
    else:
        import uvicorn

        uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, reload=False, access_log=False)
