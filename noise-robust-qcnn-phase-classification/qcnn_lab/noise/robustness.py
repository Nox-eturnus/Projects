from __future__ import annotations

from typing import Any, Mapping, Sequence
import numpy as np


def evaluate_robustness_threshold(
    records: Sequence[Mapping[str, Any]],
    floor: float = 0.70,
    noise_key: str = "depolarizing_2q",
    metric_key: str = "balanced_accuracy",
) -> dict[str, Any]:
    """Evaluate whether and at what noise level performance drops below `floor`.

    If the zero-noise baseline performance is already below `floor`, reporting a
    failure threshold is invalid and misleading. In that case, this function returns
    `status="baseline_below_floor"` and `robustness_threshold_applicable=False`.

    Otherwise, returns the first tested noise rate where performance falls below floor
    along with a linearly interpolated crossing threshold.
    """
    if not records:
        return {
            "status": "no_records",
            "baseline_metric": None,
            "floor": float(floor),
            "robustness_threshold_applicable": False,
            "first_tested_failure_probability": None,
            "failure_noise_threshold": None,
        }

    # Sort by noise level
    sorted_records = sorted(records, key=lambda r: float(r[noise_key]))

    # Identify zero-noise baseline
    baseline_rec = None
    for r in sorted_records:
        if np.isclose(float(r[noise_key]), 0.0, atol=1e-8):
            baseline_rec = r
            break
    if baseline_rec is None:
        return {
            "status": "zero_noise_baseline_missing",
            "baseline_metric": None,
            "floor": float(floor),
            "robustness_threshold_applicable": False,
            "first_tested_failure_probability": None,
            "failure_noise_threshold": None,
        }

    baseline_val = float(baseline_rec[metric_key])

    if baseline_val < floor:
        return {
            "status": "baseline_below_floor",
            "baseline_metric": baseline_val,
            "floor": float(floor),
            "robustness_threshold_applicable": False,
            "first_tested_failure_probability": None,
            "failure_noise_threshold": None,
        }

    # Find the first point that breaches the floor
    prev_r = baseline_rec
    for r in sorted_records:
        val = float(r[metric_key])
        p = float(r[noise_key])
        if val < floor:
            prev_p = float(prev_r[noise_key])
            prev_val = float(prev_r[metric_key])
            denom = val - prev_val
            if abs(denom) > 1e-12:
                interp = prev_p + ((floor - prev_val) / denom) * (p - prev_p)
            else:
                interp = p
            return {
                "status": "threshold_found",
                "baseline_metric": baseline_val,
                "floor": float(floor),
                "robustness_threshold_applicable": True,
                "first_tested_failure_probability": p,
                "failure_noise_threshold": float(np.clip(interp, prev_p, p)),
            }
        prev_r = r

    return {
        "status": "floor_not_breached",
        "baseline_metric": baseline_val,
        "floor": float(floor),
        "robustness_threshold_applicable": True,
        "first_tested_failure_probability": None,
        "failure_noise_threshold": None,
    }
