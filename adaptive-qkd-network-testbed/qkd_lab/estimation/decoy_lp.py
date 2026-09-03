from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from qkd_lab.estimation.confidence import ProbabilityInterval
from qkd_lab.math_utils import poisson_tail, poisson_vector


@dataclass(frozen=True)
class DecoyBounds:
    y0_lower: float
    y1_lower: float
    w1_upper: float
    e1_upper: float


def _build_joint_constraints(
    intensities: list[float],
    gain_intervals: list[ProbabilityInterval],
    error_gain_intervals: list[ProbabilityInterval],
    n_max: int,
) -> tuple[np.ndarray, np.ndarray]:
    if not (len(intensities) == len(gain_intervals) == len(error_gain_intervals)):
        raise ValueError("all decoy arrays must have the same length")
    if n_max < 1:
        raise ValueError("n_max must be >= 1")

    nvar = n_max + 1
    rows: list[np.ndarray] = []
    rhs: list[float] = []

    for mu, q_int, t_int in zip(intensities, gain_intervals, error_gain_intervals):
        p = poisson_vector(mu, n_max)
        tail = poisson_tail(mu, n_max)

        row = np.zeros(2 * nvar)
        row[:nvar] = p
        rows.append(row)
        rhs.append(q_int.upper)

        rows.append(-row)
        rhs.append(-(max(0.0, q_int.lower - tail)))

        erow = np.zeros(2 * nvar)
        erow[nvar:] = p
        rows.append(erow)
        rhs.append(t_int.upper)

        rows.append(-erow)
        rhs.append(-(max(0.0, t_int.lower - tail)))

    # W_n <= Y_n for every n.
    for n in range(nvar):
        row = np.zeros(2 * nvar)
        row[nvar + n] = 1.0
        row[n] = -1.0
        rows.append(row)
        rhs.append(0.0)

    return np.vstack(rows), np.asarray(rhs, dtype=float)


def estimate_decoy_bounds(
    intensities: list[float],
    gain_intervals: list[ProbabilityInterval],
    error_gain_intervals: list[ProbabilityInterval],
    n_max: int = 10,
) -> DecoyBounds:
    A_ub, b_ub = _build_joint_constraints(
        intensities,
        gain_intervals,
        error_gain_intervals,
        n_max,
    )
    nvar = n_max + 1
    bounds = [(0.0, 1.0)] * (2 * nvar)

    def solve(c: np.ndarray) -> np.ndarray:
        res = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
        if not res.success:
            raise RuntimeError(f"decoy LP infeasible/failed: {res.message}")
        return res.x

    c_y0 = np.zeros(2 * nvar)
    c_y0[0] = 1.0
    y0_lower = float(solve(c_y0)[0])

    c_y1 = np.zeros(2 * nvar)
    c_y1[1] = 1.0
    y1_lower = float(solve(c_y1)[1])

    c_w1 = np.zeros(2 * nvar)
    c_w1[nvar + 1] = -1.0
    x_w1 = solve(c_w1)
    w1_upper = float(x_w1[nvar + 1])

    if y1_lower <= 1e-15:
        e1_upper = 1.0
    else:
        e1_upper = min(1.0, w1_upper / y1_lower)

    return DecoyBounds(y0_lower=y0_lower, y1_lower=y1_lower, w1_upper=w1_upper, e1_upper=e1_upper)


def point_intervals(values: list[float]) -> list[ProbabilityInterval]:
    return [ProbabilityInterval(float(x), float(x)) for x in values]