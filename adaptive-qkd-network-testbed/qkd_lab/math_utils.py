from __future__ import annotations

from math import exp, factorial, log2

import numpy as np


def h2(p: float) -> float:
    if not 0.0 <= p <= 1.0:
        raise ValueError("p must lie in [0, 1]")
    if p in (0.0, 1.0):
        return 0.0
    return -p * log2(p) - (1.0 - p) * log2(1.0 - p)


def poisson_pmf(n: int, mu: float) -> float:
    if n < 0:
        raise ValueError("n must be non-negative")
    if mu < 0:
        raise ValueError("mu must be non-negative")
    return exp(-mu) * mu**n / factorial(n)


def poisson_vector(mu: float, n_max: int) -> np.ndarray:
    if n_max < 0:
        raise ValueError("n_max must be non-negative")
    return np.asarray([poisson_pmf(n, mu) for n in range(n_max + 1)], dtype=float)


def poisson_tail(mu: float, n_max: int) -> float:
    return max(0.0, 1.0 - float(poisson_vector(mu, n_max).sum()))


def clamp_probability(x: float) -> float:
    return float(min(1.0, max(0.0, x)))