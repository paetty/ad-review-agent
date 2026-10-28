import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("verify_model_pilot", ROOT / "scripts/verify_model_pilot.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def dataset():
    return json.loads(pilot.DATA.read_text(encoding="utf-8"))


def test_pilot_fixed_five_use_reviewed_development_only():
    selected = pilot.select_cases(dataset())
    assert len(selected) == 5
    assert len({x["reference"]["record_id"] for x in selected}) == 5
    assert all(x["reference"]["split"] == "development" for x in selected)
    assert any(x["reference"]["gold_assessment_status"] == "insufficient_evidence" for x in selected)


@pytest.mark.parametrize("field,value", [("split", "validation"), ("annotation_status", "draft"), ("reviewer", None)])
def test_pilot_rejects_unreviewed_or_non_development(field, value):
    data = dataset()
    selected_id = pilot.SELECTION[0][0]
    next(x for x in data["cases"] if x["record_id"] == selected_id)[field] = value
    with pytest.raises(ValueError):
        pilot.select_cases(data)


def test_pilot_distinguishes_label_status_and_review_correctness():
    from app.schemas import AnalysisInput
    from app.engine import DemoEngine
    row = pilot.select_cases(dataset())[3]["reference"]
    output = DemoEngine().analyze(AnalysisInput(**row["input"]), [])
    checks = pilot.assess(row, output)
    assert checks["labels_match"] and checks["status_match"] and checks["review_match"]
    assert checks["expected_human_review_by_policy"] is True
    row_result = {"reference": row, "rules": {"output": output.model_dump(), "checks": checks, "measured_pipeline_ms": 1.25}}
    summary = pilot.summarize([row_result], "rules")
    assert summary["api_input_tokens"] == summary["api_output_tokens"] == 0
    assert summary["mean_measured_pipeline_ms"] == 1.25
