import numpy as np

from qkd_lab.estimation.decoy_lp import estimate_decoy_bounds, point_intervals
from qkd_lab.math_utils import poisson_vector


def main():
    intensities = [0.5, 0.1, 0.0002]
    n_max = 10
    y = np.array([1e-6] + [1.0 - (1.0 - 0.08) ** n for n in range(1, n_max + 1)])
    e = np.array([0.5] + [0.015] * n_max)
    w = y * e
    gains = [float(poisson_vector(mu, n_max) @ y) for mu in intensities]
    errors = [float(poisson_vector(mu, n_max) @ w) for mu in intensities]
    bound = estimate_decoy_bounds(intensities, point_intervals(gains), point_intervals(errors), n_max=n_max)
    print("true Y1:", y[1], "lower:", bound.y1_lower)
    print("true e1:", e[1], "upper:", bound.e1_upper)
    assert bound.y1_lower <= y[1] + 1e-8
    assert bound.e1_upper + 1e-8 >= e[1]
    print("Decoy LP validation PASSED")


if __name__ == "__main__":
    main()