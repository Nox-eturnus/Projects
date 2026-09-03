from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class BinomialEstimate:
    successes: int
    trials: int
    p_hat: float
    low: float
    high: float


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> BinomialEstimate:
    if trials <= 0:
        raise ValueError("trials must be positive")
    if not 0 <= successes <= trials:
        raise ValueError("successes must lie between 0 and trials")
    p = successes / trials
    denom = 1.0 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = z * sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return BinomialEstimate(successes, trials, p, max(0.0, centre - half), min(1.0, centre + half))