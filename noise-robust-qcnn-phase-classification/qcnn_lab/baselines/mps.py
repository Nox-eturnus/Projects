from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qcnn_lab.physics.states import canonical_global_phase


@dataclass(frozen=True)
class MPSPrototypeModel:
    prototype0: np.ndarray
    prototype1: np.ndarray
    max_bond: int


def state_to_mps(state: np.ndarray, n_qubits: int, max_bond: int) -> list[np.ndarray]:
    if max_bond < 1:
        raise ValueError("max_bond must be positive")
    psi = np.asarray(state, dtype=complex).reshape(-1)
    if len(psi) != 2**n_qubits:
        raise ValueError("state length mismatch")
    tensors = []
    left_dim = 1
    rest = psi.reshape(1, -1)
    for site in range(n_qubits - 1):
        rest = rest.reshape(left_dim * 2, -1)
        u, s, vh = np.linalg.svd(rest, full_matrices=False)
        keep = min(max_bond, len(s))
        u = u[:, :keep]
        s = s[:keep]
        vh = vh[:keep, :]
        tensors.append(u.reshape(left_dim, 2, keep))
        rest = np.diag(s) @ vh
        left_dim = keep
    tensors.append(rest.reshape(left_dim, 2, 1))
    return tensors


def mps_to_state(tensors: list[np.ndarray]) -> np.ndarray:
    cur = tensors[0]
    for tensor in tensors[1:]:
        cur = np.tensordot(cur, tensor, axes=([-1], [0]))
    state = np.squeeze(cur, axis=(0, -1)).reshape(-1)
    return state / np.linalg.norm(state)


def compress_state(state: np.ndarray, n_qubits: int, max_bond: int) -> np.ndarray:
    return canonical_global_phase(mps_to_state(state_to_mps(state, n_qubits, max_bond)))


def _aligned_mean(states: np.ndarray) -> np.ndarray:
    aligned = np.asarray([canonical_global_phase(s) for s in states])
    mean = np.mean(aligned, axis=0)
    if np.linalg.norm(mean) < 1e-12:
        raise ValueError("prototype mean cancelled; increase separation or use medoid prototype")
    return canonical_global_phase(mean)


def fit_mps_prototype(states: np.ndarray, labels: np.ndarray, train_idx: np.ndarray, *, n_qubits: int, max_bond: int = 8) -> MPSPrototypeModel:
    labels = np.asarray(labels, dtype=int)
    p0 = compress_state(_aligned_mean(states[train_idx][labels[train_idx] == 0]), n_qubits, max_bond)
    p1 = compress_state(_aligned_mean(states[train_idx][labels[train_idx] == 1]), n_qubits, max_bond)
    return MPSPrototypeModel(p0, p1, max_bond)


def predict_mps_prototype(model: MPSPrototypeModel, states: np.ndarray) -> np.ndarray:
    out = []
    for state in states:
        f0 = abs(np.vdot(model.prototype0, state)) ** 2
        f1 = abs(np.vdot(model.prototype1, state)) ** 2
        out.append(float(f1 / max(1e-12, f0 + f1)))
    return np.asarray(out)