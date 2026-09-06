from __future__ import annotations

from time import perf_counter

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector
from scipy.optimize import minimize

from qcnn_lab.physics.states import physics_to_qiskit_state
from qcnn_lab.qcnn.evaluate import binary_cross_entropy


def vqc_parameter_count(n_qubits: int, layers: int = 2) -> int:
    return 2 * n_qubits * layers


def build_vqc(n_qubits: int, params: np.ndarray, layers: int = 2) -> tuple[QuantumCircuit, int]:
    params = np.asarray(params, dtype=float).reshape(-1)
    expected = vqc_parameter_count(n_qubits, layers)
    if len(params) != expected:
        raise ValueError(f"expected {expected} parameters")
    qc = QuantumCircuit(n_qubits)
    cursor = 0
    for _ in range(layers):
        for q in range(n_qubits):
            qc.ry(float(params[cursor]), q)
            cursor += 1
            qc.rz(float(params[cursor]), q)
            cursor += 1
        for q in range(n_qubits - 1):
            qc.cx(q, q + 1)
    return qc, n_qubits - 1


def vqc_circuit_metrics(n_qubits: int, layers: int = 2) -> dict[str, int]:
    qc, output = build_vqc(n_qubits, np.zeros(vqc_parameter_count(n_qubits, layers)), layers)
    return {
        "parameters": vqc_parameter_count(n_qubits, layers),
        "depth": int(qc.depth()),
        "two_qubit_operations": int(sum(1 for inst in qc.data if len(inst.qubits) == 2)),
        "output_qubit": int(output),
    }


def vqc_predict(states: np.ndarray, params: np.ndarray, n_qubits: int, layers: int = 2) -> np.ndarray:
    qc, output = build_vqc(n_qubits, params, layers)
    out = []
    for state in states:
        qstate = physics_to_qiskit_state(state, n_qubits)
        sv = Statevector(qstate).evolve(qc)
        out.append(float(sv.probabilities(qargs=[output])[1]))
    return np.asarray(out)


def train_vqc(states: np.ndarray, labels: np.ndarray, train_idx: np.ndarray, *, n_qubits: int, layers: int = 2, maxiter: int = 120, seed: int = 12345) -> tuple[np.ndarray, float]:
    rng = np.random.default_rng(seed)
    x0 = rng.normal(0.0, 0.15, size=vqc_parameter_count(n_qubits, layers))

    def obj(x):
        return binary_cross_entropy(labels[train_idx], vqc_predict(states[train_idx], x, n_qubits, layers))

    started = perf_counter()
    result = minimize(obj, x0, method="COBYLA", options={"maxiter": maxiter, "rhobeg": 0.25, "tol": 1e-4})
    return np.asarray(result.x), perf_counter() - started