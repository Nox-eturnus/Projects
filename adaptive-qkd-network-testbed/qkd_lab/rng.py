from __future__ import annotations

import secrets

import numpy as np


def make_rng(seed: int | None = None) -> np.random.Generator:
    """Deterministic-capable RNG for Monte Carlo simulation."""
    return np.random.default_rng(seed)


def secure_random_bytes(n: int) -> bytes:
    """Cryptographically secure bytes for application/KMS demonstrations."""
    if n < 0:
        raise ValueError("n must be non-negative")
    return secrets.token_bytes(n)