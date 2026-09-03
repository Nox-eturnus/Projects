from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ReconciliationResult:
    alice_key: np.ndarray
    bob_key: np.ndarray
    success: bool
    disclosed_bits: int
    messages: int
    rounds: int
    elapsed_ms: float
    algorithm: str