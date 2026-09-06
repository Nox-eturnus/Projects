from __future__ import annotations

import numpy as np

from qcnn_lab.physics.operators import expectation, local_pauli, pauli_product


def site_feature_map(state: np.ndarray, n: int) -> np.ndarray:
    """Return five local/bond channels shaped (5, n): X, Z, XX, ZZ, ZXZ."""
    feat = np.zeros((5, n), dtype=float)
    for i in range(n):
        feat[0, i] = expectation(state, local_pauli(n, i, "X"))
        feat[1, i] = expectation(state, local_pauli(n, i, "Z"))
        if i < n - 1:
            feat[2, i] = expectation(state, pauli_product(n, {i: "X", i + 1: "X"}))
            feat[3, i] = expectation(state, pauli_product(n, {i: "Z", i + 1: "Z"}))
        if 0 < i < n - 1:
            feat[4, i] = expectation(state, pauli_product(n, {i - 1: "Z", i: "X", i + 1: "Z"}))
    return feat


def tfim_long_range_zz(state: np.ndarray, n: int) -> float:
    return expectation(state, pauli_product(n, {0: "Z", n - 1: "Z"}))


def xxz_staggered_structure(state: np.ndarray, n: int) -> float:
    acc = 0.0
    count = 0
    for i in range(n):
        for j in range(i + 1, n):
            acc += ((-1) ** (j - i)) * expectation(state, pauli_product(n, {i: "Z", j: "Z"}))
            count += 1
    return float(acc / max(1, count))


def cluster_stabilizer_order(state: np.ndarray, n: int) -> float:
    vals = [expectation(state, pauli_product(n, {i - 1: "Z", i: "X", i + 1: "Z"})) for i in range(1, n - 1)]
    return float(np.mean(vals))