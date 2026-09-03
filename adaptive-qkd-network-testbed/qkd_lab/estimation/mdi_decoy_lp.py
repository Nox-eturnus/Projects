from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from qkd_lab.estimation.confidence import ProbabilityInterval
from qkd_lab.math_utils import poisson_vector


@dataclass(frozen=True)
class MDIDecoyBounds:
    y11_lower: float
    w11_upper: float
    e11_upper: float


def _pair_weights(mu_a: float, mu_b: float, n_max: int) -> tuple[np.ndarray, float]:
    pa = poisson_vector(mu_a, n_max)
    pb = poisson_vector(mu_b, n_max)
    weights = np.outer(pa, pb).reshape(-1)
    tail = max(0.0, 1.0 - float(weights.sum()))
    return weights, tail


def estimate_mdi_bounds(
    intensity_pairs: list[tuple[float, float]],
    gain_intervals: list[ProbabilityInterval],
    error_gain_intervals: list[ProbabilityInterval],
    *,
    n_max: int = 6,
) -> MDIDecoyBounds:
    if not (len(intensity_pairs) == len(gain_intervals) == len(error_gain_intervals)):
        raise ValueError("MDI arrays must have equal length")
    side = n_max + 1
    n_y = side * side
    rows: list[np.ndarray] = []
    rhs: list[float] = []

    for (mu_a, mu_b), q_int, t_int in zip(intensity_pairs, gain_intervals, error_gain_intervals):
        p, tail = _pair_weights(mu_a, mu_b, n_max)
        row = np.zeros(2 * n_y)
        row[:n_y] = p
        rows.append(row)
        rhs.append(q_int.upper)
        rows.append(-row)
        rhs.append(-max(0.0, q_int.lower - tail))

        erow = np.zeros(2 * n_y)
        erow[n_y:] = p
        rows.append(erow)
        rhs.append(t_int.upper)
        rows.append(-erow)
        rhs.append(-max(0.0, t_int.lower - tail))

    for i in range(n_y):
        row = np.zeros(2 * n_y)
        row[n_y + i] = 1.0
        row[i] = -1.0
        rows.append(row)
        rhs.append(0.0)

    A = np.vstack(rows)
    b = np.asarray(rhs, dtype=float)
    var_bounds = [(0.0, 1.0)] * (2 * n_y)
    idx11 = 1 * side + 1

    def solve(c: np.ndarray) -> np.ndarray:
        result = linprog(c, A_ub=A, b_ub=b, bounds=var_bounds, method="highs")
        if not result.success:
            raise RuntimeError(f"MDI decoy LP failed: {result.message}")
        return result.x

    c_y = np.zeros(2 * n_y)
    c_y[idx11] = 1.0
    y11_lower = float(solve(c_y)[idx11])

    c_w = np.zeros(2 * n_y)
    c_w[n_y + idx11] = -1.0
    w11_upper = float(solve(c_w)[n_y + idx11])
    e11_upper = 1.0 if y11_lower <= 1e-15 else min(1.0, w11_upper / y11_lower)
    return MDIDecoyBounds(y11_lower, w11_upper, e11_upper)