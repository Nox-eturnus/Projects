from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qkd_lab.rng import make_rng


@dataclass(frozen=True)
class IdealBB84Result:
    pulses: int
    sifted_bits: int
    errors: int
    qber: float
    sifting_fraction: float


def simulate_ideal_bb84(
    pulses: int,
    *,
    p_x_alice: float = 0.5,
    p_x_bob: float = 0.5,
    channel_flip_probability: float = 0.0,
    intercept_resend_fraction: float = 0.0,
    seed: int | None = None,
) -> IdealBB84Result:
    if pulses <= 0:
        raise ValueError("pulses must be positive")
    for name, value in (
        ("p_x_alice", p_x_alice),
        ("p_x_bob", p_x_bob),
        ("channel_flip_probability", channel_flip_probability),
        ("intercept_resend_fraction", intercept_resend_fraction),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must lie in [0,1]")

    rng = make_rng(seed)
    alice_bits = rng.integers(0, 2, size=pulses, dtype=np.uint8)
    alice_x = rng.random(pulses) < p_x_alice
    bob_x = rng.random(pulses) < p_x_bob

    bob_bits = alice_bits.copy()

    attacked = rng.random(pulses) < intercept_resend_fraction
    if np.any(attacked):
        eve_x = rng.random(pulses) < 0.5
        eve_bits = alice_bits.copy()
        wrong_eve_basis = attacked & (eve_x != alice_x)
        eve_bits[wrong_eve_basis] = rng.integers(0, 2, size=int(wrong_eve_basis.sum()), dtype=np.uint8)

        same_bob_eve = attacked & (bob_x == eve_x)
        bob_bits[same_bob_eve] = eve_bits[same_bob_eve]
        wrong_bob_eve = attacked & (bob_x != eve_x)
        bob_bits[wrong_bob_eve] = rng.integers(0, 2, size=int(wrong_bob_eve.sum()), dtype=np.uint8)

    channel_flips = rng.random(pulses) < channel_flip_probability
    bob_bits[channel_flips] ^= 1

    sift = alice_x == bob_x
    sifted = int(sift.sum())
    errors = int(np.count_nonzero(alice_bits[sift] != bob_bits[sift]))
    qber = errors / sifted if sifted else 0.0

    return IdealBB84Result(
        pulses=pulses,
        sifted_bits=sifted,
        errors=errors,
        qber=qber,
        sifting_fraction=sifted / pulses,
    )