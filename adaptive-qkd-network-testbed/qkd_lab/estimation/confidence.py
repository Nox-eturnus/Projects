from __future__ import annotations

from dataclasses import dataclass
from math import log, sqrt

from scipy.stats import beta


@dataclass(frozen=True)
class ProbabilityInterval:
    lower: float
    upper: float


def clopper_pearson_interval(successes: int, trials: int, failure_probability: float) -> ProbabilityInterval:
    if trials <= 0:
        raise ValueError("trials must be positive")
    if not 0 <= successes <= trials:
        raise ValueError("successes must lie in [0,trials]")
    if not 0.0 < failure_probability < 1.0:
        raise ValueError("failure_probability must lie in (0,1)")

    alpha = failure_probability
    lower = 0.0 if successes == 0 else float(beta.ppf(alpha / 2.0, successes, trials - successes + 1))
    upper = 1.0 if successes == trials else float(beta.ppf(1.0 - alpha / 2.0, successes + 1, trials - successes))
    return ProbabilityInterval(lower=max(0.0, lower), upper=min(1.0, upper))


def inverse_chernoff_deviations(observed: float, failure_probability: float) -> tuple[float, float]:
    """Inverse multiplicative-Chernoff deviations used as a finite-statistics utility.

    Returns (delta_minus, delta_plus) such that an expectation is bounded around
    an observed count using the conservative closed forms commonly used in QKD
    engineering analyses.
    """
    if observed < 0:
        raise ValueError("observed must be non-negative")
    if not 0.0 < failure_probability < 1.0:
        raise ValueError("failure_probability must lie in (0,1)")
    b = log(1.0 / failure_probability)
    delta_plus = b + sqrt(2.0 * b * observed + b * b)
    delta_minus = b / 2.0 + sqrt(2.0 * b * observed + b * b / 4.0)
    return delta_minus, delta_plus


def hoeffding_count_radius(total_count: int, failure_probability: float) -> float:
    if total_count < 0:
        raise ValueError("total_count must be non-negative")
    if not 0.0 < failure_probability < 1.0:
        raise ValueError("failure_probability must lie in (0,1)")
    return sqrt(total_count / 2.0 * log(1.0 / failure_probability))