from __future__ import annotations

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import StatePreparation
from qiskit.quantum_info import SparsePauliOp

from qcnn_lab.physics.states import physics_to_qiskit_state
from qcnn_lab.qcnn.architecture import QCNNArchitecture, build_qcnn


def classifier_circuit(state: np.ndarray, params: np.ndarray, architecture: QCNNArchitecture, n_qubits: int, *, measure: bool = False) -> tuple[QuantumCircuit, int]:
    qstate = physics_to_qiskit_state(state, n_qubits)
    qcnn, output = build_qcnn(n_qubits, params, architecture)
    qc = QuantumCircuit(n_qubits, 1 if measure else 0)
    qc.append(StatePreparation(qstate), range(n_qubits))
    qc.compose(qcnn, inplace=True)
    if measure:
        qc.measure(output, 0)
    return qc, output


def z_observable(n_qubits: int, output_qubit: int) -> SparsePauliOp:
    label = ["I"] * n_qubits
    label[n_qubits - 1 - output_qubit] = "Z"
    return SparsePauliOp("".join(label))


def two_qubit_count(qc: QuantumCircuit) -> int:
    return sum(1 for inst in qc.data if len(inst.qubits) == 2)