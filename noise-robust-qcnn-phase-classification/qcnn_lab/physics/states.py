from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import eigsh


def canonical_global_phase(state: np.ndarray, tol: float = 1e-12) -> np.ndarray:
    state = np.asarray(state, dtype=complex).reshape(-1).copy()
    nz = np.flatnonzero(np.abs(state) > tol)
    if len(nz) == 0:
        raise ValueError("zero state")
    phase = np.angle(state[nz[0]])
    state *= np.exp(-1j * phase)
    if state[nz[0]].real < 0:
        state *= -1
    return state / np.linalg.norm(state)


def ground_state(H: sparse.spmatrix) -> tuple[float, np.ndarray]:
    if H.shape[0] != H.shape[1]:
        raise ValueError("Hamiltonian must be square")
    dim = H.shape[0]
    if dim <= 64:
        vals, vecs = np.linalg.eigh(H.toarray())
        idx = int(np.argmin(vals))
        return float(vals[idx].real), canonical_global_phase(vecs[:, idx])
    vals, vecs = eigsh(H, k=1, which="SA", tol=1e-10, maxiter=100_000)
    return float(vals[0].real), canonical_global_phase(vecs[:, 0])


def physics_to_qiskit_state(state: np.ndarray, n: int) -> np.ndarray:
    """Map site-0-leftmost tensor ordering to Qiskit's qubit-0-rightmost ordering."""
    state = np.asarray(state, dtype=complex).reshape([2] * n)
    return np.transpose(state, axes=list(reversed(range(n)))).reshape(-1)


def qiskit_to_physics_state(state: np.ndarray, n: int) -> np.ndarray:
    state = np.asarray(state, dtype=complex).reshape([2] * n)
    return np.transpose(state, axes=list(reversed(range(n)))).reshape(-1)