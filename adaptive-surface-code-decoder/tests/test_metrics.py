from qec_lab.metrics import (
    per_round_logical_error,
    wilson_interval,
)


def test_wilson_bounds():
    x = wilson_interval(
        failures=10,
        shots=1000,
    )

    assert 0 <= x.low
    assert x.low <= x.p_hat
    assert x.p_hat <= x.high
    assert x.high <= 1


def test_round_conversion():
    p = per_round_logical_error(
        shot_error_rate=0.1,
        rounds=2,
    )

    assert 0 < p < 0.1