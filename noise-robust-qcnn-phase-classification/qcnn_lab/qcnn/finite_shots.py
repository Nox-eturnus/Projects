from __future__ import annotations

import numpy as np


def simulate_finite_shot_probability(
    exact_p1: float | np.ndarray,
    shots: int,
    *,
    seed: int = 12345,
) -> np.ndarray:
    """Simulate finite-shot binomial sampling for Bernoulli probabilities."""
    p = np.clip(np.asarray(exact_p1, dtype=float), 0.0, 1.0)
    rng = np.random.default_rng(seed)
    counts = rng.binomial(shots, p)
    return counts / float(shots)


def simulate_finite_shot_observable(
    exact_expval: float | np.ndarray,
    shots_per_observable: int,
    *,
    seed: int = 12345,
) -> np.ndarray:
    """Simulate finite-shot estimation for a Pauli observable with eigenvalues in {-1, +1}.

    For observable O with <O> = mu in [-1, +1], P(+1) = (1 + mu)/2.
    """
    mu = np.clip(np.asarray(exact_expval, dtype=float), -1.0, 1.0)
    prob_plus = 0.5 * (1.0 + mu)
    rng = np.random.default_rng(seed)
    if shots_per_observable <= 0:
        return mu
    n_plus = rng.binomial(shots_per_observable, prob_plus)
    # Estimated expectation value = (n_plus - n_minus) / S = (2 * n_plus / S) - 1
    est_mu = (2.0 * n_plus / float(shots_per_observable)) - 1.0
    return est_mu
