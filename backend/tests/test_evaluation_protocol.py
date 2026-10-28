import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def test_candidates_are_disjoint_by_group_and_text():
    data=json.loads((ROOT/"data/evaluation/feedback-candidates-v2.json").read_text(encoding="utf-8"))
    groups={}; texts=set()
    for row in data["cases"]:
        assert row["group_id"] not in groups or groups[row["group_id"]]==row["split"]
        groups[row["group_id"]]=row["split"]
        assert row["input"]["feedback"] not in texts
        texts.add(row["input"]["feedback"])
    assert len(data["cases"])==48


def test_unreviewed_holdout_cannot_be_run():
    # Calls only the gate; no model request occurs before the rejection.
    result=subprocess.run([sys.executable,str(ROOT/"scripts/evaluate_v2.py"),"--split","holdout_candidate"],cwd=ROOT,capture_output=True)
    assert result.returncode != 0


def test_bm25_respects_platform_filter():
    from app.retrieval import PolicyRetriever
    retriever=PolicyRetriever(ROOT/"data/policies")
    generic=retriever.search("OPPO 素材 文案 落地页一致性",method="bm25",top_k=100)
    oppo=retriever.search("OPPO 素材 文案 落地页一致性",platform="oppo",method="bm25",top_k=100)
    assert all(x["platform"]=="all" for x in generic)
    assert any(x["platform"]=="oppo" for x in oppo)
