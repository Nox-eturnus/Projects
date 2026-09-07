from __future__ import annotations

import numpy as np


def noisy_state_preparation_predict(
    ideal_p1: float | np.ndarray,
    p_state: float,
) -> np.ndarray:
    """Apply input-state preparation depolarizing noise to predicted probabilities.

    Under an input depolarizing channel with noise rate p_state:
        rho = (1 - p_state) |psi><psi| + p_state * (I / 2^N)
    Since Tr(Pi_1 * U (I / 2^N) U^dagger) = 0.5 for any unitary U and projector Pi_1,
    the resulting output probability is:
        P_noisy = (1 - p_state) * P_ideal + 0.5 * p_state
    """
    p = np.clip(np.asarray(ideal_p1, dtype=float), 0.0, 1.0)
    p_state = float(np.clip(p_state, 0.0, 1.0))
    return np.clip((1.0 - p_state) * p + 0.5 * p_state, 0.0, 1.0)


def sample_noisy_statevector(
    state: np.ndarray,
    n_qubits: int,
    p_error: float,
    *,
    seed: int = 12345,
) -> np.ndarray:
    """Apply stochastic Pauli errors during state preparation."""
    state = np.asarray(state, dtype=complex).copy()
    if p_error <= 0.0:
        return state
    rng = np.random.default_rng(seed)
    # With probability p_error on each qubit, apply random X, Y, or Z
    # Local Pauli operations on statevector:
    dim = 2**n_qubits
    reshaped = state.reshape([2] * n_qubits)
    for q in range(n_qubits):
        if rng.random() < p_error:
            error_type = rng.choice(["X", "Y", "Z"])
            if error_type == "X":
                reshaped = np.flip(reshaped, axis=q)
            elif error_type == "Z":
                # multiply slice where qubit q is 1 by -1
                idx = [slice(None)] * n_qubits
                idx[q] = 1
                reshaped[tuple(idx)] *= -1
            elif error_type == "Y":
                idx = [slice(None)] * n_qubits
                idx[q] = 1
                reshaped[tuple(idx)] *= -1
                reshaped = np.flip(reshaped, axis=q) * 1j
    return reshaped.reshape(-1) / np.linalg.norm(reshaped.reshape(-1))
