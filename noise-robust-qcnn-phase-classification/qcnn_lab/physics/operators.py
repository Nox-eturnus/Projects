from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy import sparse

I2 = sparse.csr_matrix(np.eye(2, dtype=complex))
X = sparse.csr_matrix(np.array([[0, 1], [1, 0]], dtype=complex))
Y = sparse.csr_matrix(np.array([[0, -1j], [1j, 0]], dtype=complex))
Z = sparse.csr_matrix(np.array([[1, 0], [0, -1]], dtype=complex))

PAULI = {"I": I2, "X": X, "Y": Y, "Z": Z}


@lru_cache(maxsize=None)
def pauli_string(label: str) -> sparse.csr_matrix:
    """Return kron(label[0], label[1], ...) using site-0 as the leftmost factor."""
    if any(ch not in PAULI for ch in label):
        raise ValueError(f"invalid Pauli label: {label}")
    op = sparse.csr_matrix([[1.0 + 0.0j]])
    for ch in label:
        op = sparse.kron(op, PAULI[ch], format="csr")
    return op


def local_pauli(n: int, site: int, kind: str) -> sparse.csr_matrix:
    if not 0 <= site < n:
        raise ValueError("site out of range")
    label = ["I"] * n
    label[site] = kind
    return pauli_string("".join(label))


def pauli_product(n: int, placements: dict[int, str]) -> sparse.csr_matrix:
    label = ["I"] * n
    for site, kind in placements.items():
        if not 0 <= site < n:
            raise ValueError("site out of range")
        label[site] = kind
    return pauli_string("".join(label))


def expectation(state: np.ndarray, op: sparse.spmatrix) -> float:
    state = np.asarray(state, dtype=complex).reshape(-1)
    value = np.vdot(state, op @ state)
    return float(np.real_if_close(value).real)