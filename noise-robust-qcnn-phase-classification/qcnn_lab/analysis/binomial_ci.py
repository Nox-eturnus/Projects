"""Exact and asymptotic confidence intervals for binomial proportions.

Provides Clopper-Pearson exact confidence intervals (via the beta distribution)
and Wilson score intervals for reporting finite-sample hardware and generalization
accuracy metrics with honest statistical uncertainty.
"""

from typing import Tuple
import numpy as np
import scipy.stats as stats


def clopper_pearson_interval(
    k: int,
    n: int,
    confidence: float = 0.95,
) -> Tuple[float, float]:
    """Calculate the Clopper-Pearson exact confidence interval for a binomial proportion.

    Parameters
    ----------
    k : int
        Number of successes (e.g., correctly classified states).
    n : int
        Total number of trials (e.g., total test states).
    confidence : float, default=0.95
        Confidence level (e.g., 0.95 for 95% CI).

    Returns
    -------
    Tuple[float, float]
        (lower_bound, upper_bound) rounded to 4 decimal places.
    """
    if n <= 0:
        raise ValueError(f"Sample size n must be positive, got {n}")
    if k < 0 or k > n:
        raise ValueError(f"Success count k must be between 0 and n, got k={k}, n={n}")

    alpha = 1.0 - confidence
    lower = 0.0 if k == 0 else float(stats.beta.ppf(alpha / 2.0, k, n - k + 1))
    upper = 1.0 if k == n else float(stats.beta.ppf(1.0 - alpha / 2.0, k + 1, n - k))

    return round(float(lower), 4), round(float(upper), 4)


def wilson_score_interval(
    k: int,
    n: int,
    confidence: float = 0.95,
) -> Tuple[float, float]:
    """Calculate the Wilson score confidence interval for a binomial proportion.

    Parameters
    ----------
    k : int
        Number of successes.
    n : int
        Total number of trials.
    confidence : float, default=0.95
        Confidence level.

    Returns
    -------
    Tuple[float, float]
        (lower_bound, upper_bound) rounded to 4 decimal places.
    """
    if n <= 0:
        raise ValueError(f"Sample size n must be positive, got {n}")
    if k < 0 or k > n:
        raise ValueError(f"Success count k must be between 0 and n, got k={k}, n={n}")

    alpha = 1.0 - confidence
    z = float(stats.norm.ppf(1.0 - alpha / 2.0))
    p = k / n

    denom = 1.0 + (z**2) / n
    center = (p + (z**2) / (2.0 * n)) / denom
    half_width = (z * np.sqrt((p * (1.0 - p) / n) + (z**2) / (4.0 * (n**2)))) / denom

    lower = max(0.0, center - half_width)
    upper = min(1.0, center + half_width)

    return round(float(lower), 4), round(float(upper), 4)
