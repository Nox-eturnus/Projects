from __future__ import annotations


def compute_service_utility(
    delivered_bits: float,
    deficit_bits: float,
    duration_seconds: float,
    *,
    abort: bool = False,
    switch_cost: float = 0.0,
    latency_weight: float = 0.05,
    deficit_weight: float = 2.0,
    abort_penalty: float = 1.0e6,
) -> float:
    """Canonical service utility function for adaptive QKD evaluation and dataset generation.

    Evaluates time-normalized service rate (bps), deficit penalty (bps), duration latency penalty,
    switching cost rate (bps), and abort penalty.

    U = delivered_rate - deficit_weight * deficit_rate - latency_weight * duration_seconds
        - (switch_cost / duration_seconds) - (abort_penalty if abort else 0.0)
    """
    if duration_seconds <= 0.0:
        raise ValueError("duration_seconds must be positive")

    delivered_rate = delivered_bits / duration_seconds
    deficit_rate = deficit_bits / duration_seconds
    latency_penalty = latency_weight * duration_seconds
    switch_rate_penalty = switch_cost / duration_seconds

    util = delivered_rate - deficit_weight * deficit_rate - latency_penalty - switch_rate_penalty
    if abort:
        util -= abort_penalty
    return util
