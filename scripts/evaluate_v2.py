"""Development evaluation and gated holdout; never silently run unreviewed holdout."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.evaluation import calculate_metrics
from app.schemas import AnalysisInput
from app.service import analyze_item, demo_mode, init_db
from app.database import SessionLocal

DATA = ROOT / "data/evaluation/feedback-candidates-v2.json"
LOCK = ROOT / "data/evaluation/holdout-lock.json"


def validate_groups(cases):
    groups = {}
    texts = set()
    for case in cases:
        group = case["group_id"]
        if group in groups and groups[group] != case["split"]:
            raise ValueError("同一表达家族跨split：" + group)
        groups[group] = case["split"]
        text = case["input"]["feedback"].strip()
        if text in texts: raise ValueError("出现重复反馈文本")
        texts.add(text)
    return groups


async def run(args):
    raw = DATA.read_bytes()
    dataset = json.loads(raw)
    cases = dataset["cases"]
    validate_groups(cases)
    digest = hashlib.sha256(raw).hexdigest()
    held = [x for x in cases if x["split"] == "holdout_candidate"]
    if args.freeze:
        if not held or any(x["annotation_status"] != "reviewed" or not x.get("reviewer") for x in held):
            raise SystemExit("拒绝冻结：留出候选尚未经独立人工标注确认。不能把生成的答案当人工金标。")
        LOCK.write_text(json.dumps({"sha256":digest,"records":len(held),"declared_reviewed":True},indent=2),encoding="utf-8")
        print("已记录冻结指纹。它校验文件变化，不证明评审独立性。")
        return
    if args.split == "holdout_candidate":
        if not LOCK.exists() or json.loads(LOCK.read_text())["sha256"] != digest or any(x["annotation_status"] != "reviewed" or not x.get("reviewer") for x in held):
            raise SystemExit("拒绝运行留出集：需要独立人工标注、冻结指纹；当前只是候选集。")
    if not demo_mode() and not args.allow_provider:
        raise SystemExit("真实模型调用需显式 --allow-provider；请先用少量样例确认成本和兼容性。")
    selected = [x for x in cases if x["split"] == args.split]
    init_db()
    gold=[]; predicted=[]; risks=[]; predicted_risks=[]; reviews=[]; status_hits=[]; timings=[]; details=[]
    with SessionLocal() as db:
        for row in selected:
            started=time.perf_counter()
            result=await analyze_item(db,AnalysisInput(**row["input"]))
            timings.append((time.perf_counter()-started)*1000)
            gold.append(set(row["gold_labels"])); predicted.append({x.label for x in result.labels})
            risks.append(row["gold_risk"]); predicted_risks.append(result.overall_risk); reviews.append(result.requires_human_review)
            status_hits.append(result.assessment_status==row["gold_assessment_status"])
            details.append({"record_id":row["record_id"],"gold_labels":row["gold_labels"],"predicted_labels":sorted(predicted[-1]),"predicted_risk":result.overall_risk,"assessment_status":result.assessment_status})
    metrics=calculate_metrics(gold,predicted,risks,reviews,predicted_risks)
    metrics.update({"records":len(selected),"split":args.split,"dataset_sha256":digest,
        "unique_feedback_texts":len({x["input"]["feedback"] for x in selected}),
        "annotation_status":"human_reviewed" if all(x["annotation_status"]=="reviewed" for x in selected) else "draft_not_gold",
        "assessment_status_accuracy":round(sum(status_hits)/len(status_hits),3),
        "measured_mean_pipeline_ms":round(sum(timings)/len(timings),2),
        "mode":"rules_baseline" if demo_mode() else "provider", "estimated_cost_usd":0 if demo_mode() else None,
        "warning":"候选合成集结果仅作开发诊断；不是独立人工金标、真实业务效果或已完成盲测。"})
    output=ROOT/(".tmp/evaluation-v2-"+args.split+".json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({"metrics":metrics,"details":details},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(metrics,ensure_ascii=False,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--split",choices=["development","validation","holdout_candidate"],default="development")
    parser.add_argument("--freeze",action="store_true")
    parser.add_argument("--allow-provider",action="store_true")
    asyncio.run(run(parser.parse_args()))
