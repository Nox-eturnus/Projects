from __future__ import annotations

import numpy as np
from qiskit.quantum_info import Statevector

from qcnn_lab.physics.states import physics_to_qiskit_state
from qcnn_lab.qcnn.architecture import QCNNArchitecture, build_qcnn


def predict_p1(state: np.ndarray, params: np.ndarray, architecture: QCNNArchitecture, n_qubits: int) -> float:
    qstate = physics_to_qiskit_state(state, n_qubits)
    qc, output = build_qcnn(n_qubits, params, architecture)
    out = Statevector(qstate).evolve(qc)
    probs = out.probabilities(qargs=[output])
    return float(np.clip(probs[1], 0.0, 1.0))


def batch_predict(states: np.ndarray, params: np.ndarray, architecture: QCNNArchitecture, n_qubits: int) -> np.ndarray:
    return np.asarray([predict_p1(state, params, architecture, n_qubits) for state in states], dtype=float)


def binary_cross_entropy(y: np.ndarray, p1: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    p1 = np.clip(np.asarray(p1, dtype=float), 1e-7, 1 - 1e-7)
    return float(-np.mean(y * np.log(p1) + (1 - y) * np.log(1 - p1)))