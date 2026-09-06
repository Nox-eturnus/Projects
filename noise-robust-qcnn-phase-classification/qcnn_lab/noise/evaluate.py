from __future__ import annotations

import numpy as np
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

from qcnn_lab.physics.states import physics_to_qiskit_state
from qcnn_lab.qcnn.architecture import QCNNArchitecture, build_qcnn


def build_noisy_evaluation_circuit(state: np.ndarray, params: np.ndarray, architecture: QCNNArchitecture, n_qubits: int) -> QuantumCircuit:
    qstate = physics_to_qiskit_state(state, n_qubits)
    qcnn, output = build_qcnn(n_qubits, params, architecture)
    qc = QuantumCircuit(n_qubits, 1)
    qc.initialize(qstate, range(n_qubits))
    qc.compose(qcnn, inplace=True)
    qc.measure(output, 0)
    return qc


def noisy_predict(
    states: np.ndarray,
    params: np.ndarray,
    architecture: QCNNArchitecture,
    n_qubits: int,
    noise_model,
    *,
    shots: int = 512,
    seed: int = 12345,
) -> np.ndarray:
    if shots <= 0:
        raise ValueError("shots must be positive")
    backend = AerSimulator(noise_model=noise_model)
    circuits = [build_noisy_evaluation_circuit(s, params, architecture, n_qubits) for s in states]
    result = backend.run(circuits, shots=shots, seed_simulator=seed).result()
    p = []
    for i in range(len(circuits)):
        counts = result.get_counts(i)
        p.append(counts.get("1", 0) / shots)
    return np.asarray(p, dtype=float)