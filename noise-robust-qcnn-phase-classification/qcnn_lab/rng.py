from __future__ import annotations

import random

import numpy as np


def seed_everything(seed: int) -> np.random.Generator:
    """Seed Python/NumPy and return the NumPy generator used by the project."""
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
    except ImportError:
        torch = None
    return np.random.default_rng(seed)