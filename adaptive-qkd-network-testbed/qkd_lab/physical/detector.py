from __future__ import annotations

from qkd_lab.math_utils import clamp_probability


def combine_independent_bit_error(base_qber: float, added_error: float) -> float:
    """Combine a baseline binary error with an independent additional flip probability."""
    if not 0.0 <= base_qber <= 1.0 or not 0.0 <= added_error <= 1.0:
        raise ValueError("error probabilities must lie in [0,1]")
    return clamp_probability(base_qber * (1.0 - added_error) + (1.0 - base_qber) * added_error)