from __future__ import annotations

from scipy import sparse

from qcnn_lab.physics.operators import local_pauli, pauli_product


def tfim_hamiltonian(n: int, *, j: float = 1.0, h: float = 1.0, periodic: bool = False) -> sparse.csr_matrix:
    """H = -J sum Z_i Z_{i+1} - h sum X_i."""
    if n < 2:
        raise ValueError("n must be >= 2")
    dim = 2**n
    H = sparse.csr_matrix((dim, dim), dtype=complex)
    bonds = [(i, i + 1) for i in range(n - 1)]
    if periodic and n > 2:
        bonds.append((n - 1, 0))
    for i, j2 in bonds:
        H -= j * pauli_product(n, {i: "Z", j2: "Z"})
    for i in range(n):
        H -= h * local_pauli(n, i, "X")
    return H


def xxz_hamiltonian(n: int, *, delta: float = 1.0, j: float = 1.0, periodic: bool = False) -> sparse.csr_matrix:
    """H = J sum (XX + YY + Delta ZZ)."""
    if n < 2:
        raise ValueError("n must be >= 2")
    dim = 2**n
    H = sparse.csr_matrix((dim, dim), dtype=complex)
    bonds = [(i, i + 1) for i in range(n - 1)]
    if periodic and n > 2:
        bonds.append((n - 1, 0))
    for i, j2 in bonds:
        H += j * pauli_product(n, {i: "X", j2: "X"})
        H += j * pauli_product(n, {i: "Y", j2: "Y"})
        H += j * delta * pauli_product(n, {i: "Z", j2: "Z"})
    return H


def cluster_ising_hamiltonian(n: int, *, j_cluster: float = 1.0, h: float = 1.0) -> sparse.csr_matrix:
    """Open-chain cluster field model H = -J sum Z_{i-1} X_i Z_{i+1} - h sum X_i."""
    if n < 3:
        raise ValueError("n must be >= 3")
    dim = 2**n
    H = sparse.csr_matrix((dim, dim), dtype=complex)
    for i in range(1, n - 1):
        H -= j_cluster * pauli_product(n, {i - 1: "Z", i: "X", i + 1: "Z"})
    for i in range(n):
        H -= h * local_pauli(n, i, "X")
    return H