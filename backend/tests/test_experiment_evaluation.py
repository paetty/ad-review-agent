from app.experiment import assign_experiment
from app.evaluation import calculate_metrics

def test_assignment_stable_and_exclusive():
    a=assign_experiment("anonymous-1","salt"); b=assign_experiment("anonymous-1","salt")
    assert a==b and a["group"] in {"treatment_main","treatment_small","control"}

def test_assignment_ratio_approximate():
    counts={"treatment_main":0,"treatment_small":0,"control":0}
    for i in range(20000): counts[assign_experiment(f"u-{i}","fixed-test-salt")["group"]]+=1
    ratios={k:v/20000 for k,v in counts.items()}
    assert abs(ratios["treatment_main"]-.6)<.025
    assert abs(ratios["treatment_small"]-.1)<.018
    assert abs(ratios["control"]-.3)<.025

def test_metric_calculation_known_values():
    gold=[{"no_issue"},{"unclear_material"}]; pred=[{"no_issue"},{"no_issue"}]
    metrics=calculate_metrics(gold,pred)
    assert metrics["exact_match_ratio"]==.5
    assert metrics["per_label"]["no_issue"]["precision"]==.5
    assert metrics["per_label"]["unclear_material"]["recall"]==0

