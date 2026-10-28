"""Fixed five-case development comparison; --call makes real API requests.

No tuning, gold-answer edits, validation/holdout execution, or demo fallback.
Raw provider JSON is retained separately from the post-rule application output.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
# Keep this verification away from the application's user-facing database.
os.environ.setdefault("DATABASE_URL", "sqlite:///" + (ROOT / ".tmp/model-pilot.db").as_posix())

import httpx
from app import service
from app.database import SessionLocal
from app.evaluation import calculate_metrics
from app.provider import OpenAICompatibleProvider, ProviderError
from app.schemas import AnalysisInput
from app.taxonomy import LABEL_NAMES

DATA = ROOT / "data/evaluation/feedback-candidates-v2.json"
SELECTION = [
    ("V2-return-flow-1", "返回困难／同义表达"),
    ("V2-activity-expired-1", "活动过期／同义表达"),
    ("V2-explicit-normal-2", "否定表达"),
    ("V2-uncertain-object-1", "模糊反馈"),
    ("V2-explicit-normal-1", "明确正常"),
]


def select_cases(dataset):
    by_id = {x["record_id"]: x for x in dataset["cases"]}
    selected = []
    for record_id, category in SELECTION:
        row = by_id[record_id]
        if row["split"] != "development":
            raise ValueError("Pilot may use development only: " + record_id)
        if row["annotation_status"] != "reviewed" or not row.get("reviewer"):
            raise ValueError("Human confirmation missing: " + record_id)
        selected.append({"category": category, "reference": row})
    return selected


def assess(row, output):
    expected_review = row["gold_risk"] in {"high", "critical"} or row["gold_assessment_status"] == "insufficient_evidence"
    return {
        "labels_match": set(row["gold_labels"]) == {x.label for x in output.labels},
        "risk_match": row["gold_risk"] == output.overall_risk,
        "status_match": row["gold_assessment_status"] == output.assessment_status,
        "expected_human_review_by_policy": expected_review,
        "review_match": expected_review == output.requires_human_review,
    }


def summarize(rows, key):
    completed = [r for r in rows if key in r]
    if not completed:
        return {"completed": 0}
    references = [r["reference"] for r in completed]
    outputs = [r[key]["output"] for r in completed]
    metrics = calculate_metrics(
        [set(r["gold_labels"]) for r in references],
        [{x["label"] for x in o["labels"]} for o in outputs],
        [r["gold_risk"] for r in references],
        [o["requires_human_review"] for o in outputs],
        [o["overall_risk"] for o in outputs],
    )
    metrics.update({
        "completed": len(completed),
        "labels_exact_count": sum(r[key]["checks"]["labels_match"] for r in completed),
        "risk_exact_count": sum(r[key]["checks"]["risk_match"] for r in completed),
        "status_exact_count": sum(r[key]["checks"]["status_match"] for r in completed),
        "review_exact_count": sum(r[key]["checks"]["review_match"] for r in completed),
        "all_four_exact_count": sum(all(r[key]["checks"][x] for x in ("labels_match", "risk_match", "status_match", "review_match")) for r in completed),
        "mean_measured_pipeline_ms": round(sum(r[key]["measured_pipeline_ms"] for r in completed) / len(completed), 2),
        "timing_scope": "analyze_item with precomputed identical citations; excludes TF-IDF retrieval, HTTP routing and front-end time. Historical field name contains pipeline, but this is not full end-to-end latency.",
        "api_input_tokens": sum(o["model_info"]["input_tokens"] for o in outputs) if key == "provider" else 0,
        "api_output_tokens": sum(o["model_info"]["output_tokens"] for o in outputs) if key == "provider" else 0,
        "estimated_cost_usd": None if key == "provider" else 0,
        "macro_f1_scope": "All 13 taxonomy values including zero-support labels; not a meaningful headline for five cases.",
    })
    return metrics


def write_artifacts(report, directory):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 5条开发样本：规则与真实模型对照", "", report["limitations"], "",
             "| 样本ID | 用户反馈 | 参考标签／状态 | 规则标签／状态 | 模型最终标签／状态 |", "|---|---|---|---|---|"]
    names = lambda values: "、".join(LABEL_NAMES[x] for x in values)
    for row in report["cases"]:
        ref = row["reference"]
        cells = [ref["record_id"], ref["input"]["feedback"], names(ref["gold_labels"]) + " / " + ref["gold_assessment_status"]]
        for key in ("rules", "provider"):
            output = row.get(key, {}).get("output")
            cells.append(names([x["label"] for x in output["labels"]]) + " / " + output["assessment_status"] if output else "未完成")
        lines.append("| " + " | ".join(x.replace("|", "／").replace("\n", " ") for x in cells) + " |")
    lines += ["", "## 真实计量与保留证据", "", "```json", json.dumps(report["summary"], ensure_ascii=False, indent=2), "```", "",
              "results.json保存完整输入、参考答案、规则输出、模型原始JSON、最终输出、引用片段和HTTP请求标识。未保存密钥。规则输出中的模拟时延/Token不当成实测；以measured_pipeline_ms和模型API返回usage为准。"]
    (directory / "comparison.md").write_text("\n".join(lines), encoding="utf-8")


async def run(call):
    raw = DATA.read_bytes()
    selected = select_cases(json.loads(raw))
    plan = {"records": len(selected), "split": "development", "record_ids": [r["reference"]["record_id"] for r in selected], "call_performed": False}
    print(json.dumps(plan, ensure_ascii=False), flush=True)
    if not call:
        return
    if service.demo_mode() or not OpenAICompatibleProvider().configured:
        raise SystemExit("拒绝调用：先完整配置真实模型并关闭DEMO_MODE。")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    directory = ROOT / ".tmp" / ("model-pilot-" + run_id)
    service.init_db()
    report = {
        "run_id": run_id, "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "selection_fixed_before_calls": True, "validation_or_holdout_executed": False,
        "limitations": "5条开发者编写、本人复核的合成文本目的抽样，不是随机抽样、独立盲测或线上效果；没有多标签案例或真实广告素材。比较规则+固定检索与规则+相同检索+模型，不是纯模型或RAG消融。未改规则、提示词或参考答案。",
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT / "scripts/verify_model_pilot.py", *sorted((ROOT / "backend/app").glob("*.py")), *sorted((ROOT / "data/policies").glob("*.md"))]},
        "provider_config": {k: os.getenv(k, "") for k in ("LLM_BASE_URL", "LLM_MODEL", "LLM_PROVIDER", "LLM_ENABLE_THINKING")},
        "cases": [], "http_attempts": [], "summary": {},
    }
    current = {}
    real_post = httpx.AsyncClient.post
    real_generate = OpenAICompatibleProvider.generate

    async def observed_post(client, url, **kwargs):
        attempt = {"record_id": current.get("record_id"), "status_code": None}
        report["http_attempts"].append(attempt)
        response = await real_post(client, url, **kwargs)
        attempt["status_code"] = response.status_code
        try:
            body = response.json()
            attempt["response_id"] = body.get("id")
            attempt["request_id"] = response.headers.get("x-request-id") or body.get("request_id")
            attempt["usage"] = body.get("usage")
        except ValueError:
            pass
        return response

    async def observed_generate(provider, messages, schema):
        result = await real_generate(provider, messages, schema)
        current["provider_raw_json"] = result.data
        return result

    with SessionLocal() as db:
        for entry in selected:
            ref = entry["reference"]
            item = AnalysisInput(**ref["input"])
            query = " ".join([item.title, item.ad_copy, item.feedback, item.first_three_seconds or "", item.industry, item.media_scene, item.landing_type])
            # Exactly the same retrieved snippets are passed to both arms.
            citations = service.retriever.search(query, top_k=4, scenario=item.media_scene, platform=item.platform)
            row = {**entry, "retrieved_citations": citations}
            report["cases"].append(row)
            with patch.dict(os.environ, {"DEMO_MODE": "true"}):
                started = time.perf_counter()
                baseline = await service.analyze_item(db, item, citations_override=citations)
                row["rules"] = {"output": baseline.model_dump(), "checks": assess(ref, baseline), "measured_pipeline_ms": round((time.perf_counter() - started) * 1000, 2)}
            current.clear()
            current["record_id"] = ref["record_id"]
            started = time.perf_counter()
            try:
                with patch.dict(os.environ, {"DEMO_MODE": "false"}), patch.object(httpx.AsyncClient, "post", observed_post), patch.object(OpenAICompatibleProvider, "generate", observed_generate):
                    output = await service.analyze_item(db, item, citations_override=citations)
                row["provider"] = {"output": output.model_dump(), "checks": assess(ref, output), "measured_pipeline_ms": round((time.perf_counter() - started) * 1000, 2)}
            except ProviderError as exc:
                row["error_code"] = exc.code
            finally:
                row["provider_raw_json"] = current.get("provider_raw_json")
                report["summary"] = {"rules": summarize(report["cases"], "rules"), "provider": summarize(report["cases"], "provider"), "http_attempts": len(report["http_attempts"]), "http_successes": sum(x["status_code"] == 200 for x in report["http_attempts"])}
                write_artifacts(report, directory)
            print(json.dumps({"record_id": ref["record_id"], "rules": row["rules"]["checks"], "provider": row.get("provider", {}).get("checks"), "error_code": row.get("error_code")}, ensure_ascii=False), flush=True)
            if row.get("error_code"):
                raise SystemExit("运行遇到错误，已保存部分结果且停止后续调用：" + row["error_code"] + "；" + str(directory))
    print(json.dumps({"output_directory": str(directory), "summary": report["summary"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call", action="store_true", help="实际调用固定5条；会消耗模型额度。")
    asyncio.run(run(parser.parse_args().call))
