import importlib.util
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("replay_model_pilot", ROOT / "scripts/replay_model_pilot.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_five_recorded_responses_pass_without_network_or_gold_changes(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Offline replay must not use network")

    monkeypatch.setattr(httpx.AsyncClient, "post", no_network)
    monkeypatch.setattr(httpx.Client, "post", no_network)
    fixture = json.loads(module.FIXTURE.read_text(encoding="utf-8"))
    before = json.dumps(fixture, ensure_ascii=False, sort_keys=True)
    report = module.replay(fixture)
    assert report["records"] == 5
    assert report["new_api_calls"] == report["new_api_tokens"] == 0
    assert report["all_four_match"] == {"before": 2, "after": 5}
    assert all(count["after"] == 5 for count in report["counts"].values())
    assert json.dumps(fixture, ensure_ascii=False, sort_keys=True) == before
    vague = next(r for r in report["cases"] if r["record_id"] == "V2-uncertain-object-1")
    assert vague["after_decision"]["abstained_labels"][0]["label"] == "unclear_material"
    assert vague["after_decision"]["requires_human_review"] is True
