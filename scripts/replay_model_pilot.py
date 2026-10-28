"""Offline postprocessing regression. Never calls a model or evaluates new prompts."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.engine import DemoEngine
from app.provider import ProviderResponse
from app.schemas import AnalysisInput, ProviderAnalysisDraft
from app.service import _normalize_provider_output

FIXTURE = ROOT / "data/evaluation/pilot-model-responses-v1.json"


def replay(fixture):
    rows = []
    criteria = ("labels_match", "risk_match", "status_match", "review_match")
    for case in fixture["cases"]:
        ref = case["reference"]
        if ref["split"] != "development" or ref["annotation_status"] != "reviewed":
            raise ValueError("Replay fixture must contain reviewed development cases only")
        item = AnalysisInput.model_validate(ref["input"])
        raw = case["provider_raw_json"]
        meta = ProviderResponse(data=raw, provider="offline_replay", model="recorded-response", latency_ms=0)
        output = _normalize_provider_output(
            item, case["retrieved_citations"], ProviderAnalysisDraft.model_validate(raw), meta,
            "offline-historical-response", DemoEngine().analyze(item, case["retrieved_citations"]), False,
        )
        expected_review = ref["gold_risk"] in {"high", "critical"} or ref["gold_assessment_status"] == "insufficient_evidence"
        after = {
            "labels_match": set(ref["gold_labels"]) == {x.label for x in output.labels},
            "risk_match": ref["gold_risk"] == output.overall_risk,
            "status_match": ref["gold_assessment_status"] == output.assessment_status,
            "review_match": expected_review == output.requires_human_review,
        }
        # Do not copy old model latency/token counters into new offline measurements.
        decision = output.model_dump(include={"labels", "overall_risk", "assessment_status", "requires_human_review", "uncertainties", "disclaimers", "abstained_labels", "analysis_policy_version", "strategy_recommendations"})
        rows.append({"record_id": ref["record_id"], "feedback": item.feedback, "before_checks": case["before_checks"],
                     "after_checks": after, "before_decision": case["before_decision"], "after_decision": decision})
    return {
        "verification_mode": "offline_historical_response_replay", "source_run_id": fixture["source_run_id"],
        "records": len(rows), "new_api_calls": 0, "new_api_tokens": 0,
        "limitation": "Same historical provider JSON, changed postprocessing only. New prompt and live model quality not measured. Not independent validation.",
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / "backend/app/service.py", ROOT / "backend/app/engine.py", ROOT / "backend/app/evidence_policy.py", ROOT / "backend/app/schemas.py")},
        "counts": {key: {"before": sum(r["before_checks"][key] for r in rows), "after": sum(r["after_checks"][key] for r in rows)} for key in criteria},
        "all_four_match": {"before": sum(all(r["before_checks"][k] for k in criteria) for r in rows), "after": sum(all(r["after_checks"][k] for k in criteria) for r in rows)},
        "cases": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    report = replay(json.loads(FIXTURE.read_text(encoding="utf-8")))
    report["fixture_sha256"] = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    directory = ROOT / ".tmp/evidence-boundary-replay"
    directory.mkdir(exist_ok=True, parents=True)
    (directory / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
