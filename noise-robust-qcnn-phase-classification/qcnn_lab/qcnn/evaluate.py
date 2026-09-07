from __future__ import annotations

import numpy as np
from qiskit.quantum_info import Operator, Statevector

from qcnn_lab.physics.states import physics_to_qiskit_state
from qcnn_lab.qcnn.architecture import QCNNArchitecture, build_qcnn


def predict_p1(state: np.ndarray, params: np.ndarray, architecture: QCNNArchitecture, n_qubits: int) -> float:
    qstate = physics_to_qiskit_state(state, n_qubits)
    qc, output = build_qcnn(n_qubits, params, architecture)
    out = Statevector(qstate).evolve(qc)
    probs = out.probabilities(qargs=[output])
    return float(np.clip(probs[1], 0.0, 1.0))


def batch_predict(states: np.ndarray, params: np.ndarray, architecture: QCNNArchitecture, n_qubits: int) -> np.ndarray:
    if len(states) == 0:
        return np.empty(0, dtype=float)
    qc, output = build_qcnn(n_qubits, params, architecture)
    U = np.asarray(Operator(qc).data)
    qstates = np.asarray([physics_to_qiskit_state(st, n_qubits) for st in states], dtype=complex)
    out_states = qstates @ U.T
    dim = 2**n_qubits
    mask = [(idx >> output) & 1 == 1 for idx in range(dim)]
    probs_p1 = np.sum(np.abs(out_states[:, mask]) ** 2, axis=1)
    return np.clip(probs_p1, 0.0, 1.0)


def binary_cross_entropy(y: np.ndarray, p1: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    p1 = np.clip(np.asarray(p1, dtype=float), 1e-7, 1 - 1e-7)
    return float(-np.mean(y * np.log(p1) + (1 - y) * np.log(1 - p1)))