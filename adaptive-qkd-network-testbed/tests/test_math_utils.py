import numpy as np
import pytest

from qkd_lab.math_utils import h2, poisson_tail, poisson_vector
from qkd_lab.metrics import wilson_interval


def test_binary_entropy_known_values():
    assert h2(0.0) == 0.0
    assert h2(1.0) == 0.0
    assert np.isclose(h2(0.5), 1.0)


def test_poisson_normalizes():
    assert np.isclose(poisson_vector(0.5, 30).sum(), 1.0, atol=1e-12)
    assert poisson_tail(0.5, 30) < 1e-12


def test_wilson_contains_point_estimate():
    x = wilson_interval(10, 1000)
    assert x.low <= x.p_hat <= x.high


def test_invalid_entropy_raises():
    with pytest.raises(ValueError):
        h2(1.1)