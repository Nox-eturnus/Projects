from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.linalg import eigh


def compute_thermal_density_matrix(
    H: sparse.spmatrix,
    temperature: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute eigenvalues and thermal Gibbs weights p_k = exp(-E_k / T) / Z.

    Returns:
        (eigenvalues, normalized_weights)
    """
    dim = H.shape[0]
    H_dense = H.toarray() if sparse.issparse(H) else H
    energies, vecs = eigh(H_dense)

    if temperature <= 1e-9:
        # T -> 0 limit: ground state weight = 1, all others = 0
        weights = np.zeros(dim, dtype=float)
        weights[0] = 1.0
        return vecs, weights

    # Shift by ground state energy to ensure numerical stability: exp(-(E_k - E_0) / T)
    e0 = energies[0]
    shifted = (energies - e0) / temperature
    # Clip large values to avoid underflow
    clipped = np.clip(shifted, 0.0, 700.0)
    unnormalized = np.exp(-clipped)
    z = np.sum(unnormalized)
    weights = unnormalized / z
    return vecs, weights


def evaluate_qcnn_thermal_state(
    vecs: np.ndarray,
    weights: np.ndarray,
    predict_fn,
    threshold: float = 1e-6,
) -> float:
    """Compute QCNN prediction probability on a thermal state rho = sum p_k |v_k><v_k|.

    By linearity of quantum mechanics, P(1 | rho) = sum p_k P(1 | v_k).
    Only eigenstates with weight >= threshold are evaluated.
    """
    p1_total = 0.0
    weight_total = 0.0

    for k in range(len(weights)):
        w = float(weights[k])
        if w < threshold:
            continue
        v_k = vecs[:, k]
        # predict_fn takes single statevector
        p_k = float(predict_fn(v_k))
        p1_total += w * p_k
        weight_total += w

    if weight_total > 0:
        return float(np.clip(p1_total / weight_total, 0.0, 1.0))
    return 0.5
