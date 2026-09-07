import numpy as np
from qcnn_lab.noise.robustness import evaluate_robustness_threshold


def test_robustness_normal_degradation():
    records = [
        {"depolarizing_2q": 0.0, "balanced_accuracy": 0.95},
        {"depolarizing_2q": 0.01, "balanced_accuracy": 0.90},
        {"depolarizing_2q": 0.02, "balanced_accuracy": 0.80},
        {"depolarizing_2q": 0.04, "balanced_accuracy": 0.65},
        {"depolarizing_2q": 0.08, "balanced_accuracy": 0.50},
    ]
    res = evaluate_robustness_threshold(records, floor=0.75)
    assert res["status"] == "threshold_found"
    assert res["robustness_threshold_applicable"] is True
    assert res["first_tested_failure_probability"] == 0.04
    assert res["failure_noise_threshold"] is not None
    assert 0.02 < res["failure_noise_threshold"] < 0.04


def test_robustness_baseline_below_floor():
    records = [
        {"depolarizing_2q": 0.0, "balanced_accuracy": 0.52},
        {"depolarizing_2q": 0.01, "balanced_accuracy": 0.51},
        {"depolarizing_2q": 0.02, "balanced_accuracy": 0.50},
    ]
    res = evaluate_robustness_threshold(records, floor=0.75)
    assert res["status"] == "baseline_below_floor"
    assert res["robustness_threshold_applicable"] is False
    assert res["first_tested_failure_probability"] is None
    assert res["failure_noise_threshold"] is None


def test_robustness_floor_not_breached():
    records = [
        {"depolarizing_2q": 0.0, "balanced_accuracy": 0.98},
        {"depolarizing_2q": 0.01, "balanced_accuracy": 0.95},
        {"depolarizing_2q": 0.02, "balanced_accuracy": 0.90},
    ]
    res = evaluate_robustness_threshold(records, floor=0.75)
    assert res["status"] == "floor_not_breached"
    assert res["robustness_threshold_applicable"] is True
    assert res["first_tested_failure_probability"] is None
    assert res["failure_noise_threshold"] is None


def test_robustness_empty():
    res = evaluate_robustness_threshold([], floor=0.75)
    assert res["status"] == "no_records"
    assert res["robustness_threshold_applicable"] is False
