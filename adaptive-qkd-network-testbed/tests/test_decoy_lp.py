from qkd_lab.estimation.decoy_lp import estimate_decoy_bounds, point_intervals
from qkd_lab.math_utils import poisson_vector


def test_decoy_bounds_contain_synthetic_truth():
    intensities = [0.5, 0.1, 0.0002]
    n_max = 10
    y = [1e-6] + [1.0 - (1.0 - 0.08) ** n for n in range(1, n_max + 1)]
    e = [0.5] + [0.015] * n_max
    gains = []
    error_gains = []
    for mu in intensities:
        p = poisson_vector(mu, n_max)
        gains.append(float(sum(pi * yi for pi, yi in zip(p, y))))
        error_gains.append(float(sum(pi * yi * ei for pi, yi, ei in zip(p, y, e))))
    b = estimate_decoy_bounds(intensities, point_intervals(gains), point_intervals(error_gains), n_max=n_max)
    assert b.y1_lower <= y[1] + 1e-12
    assert b.e1_upper + 1e-12 >= e[1]