from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from qiskit.transpiler import generate_preset_pass_manager
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime import EstimatorV2, QiskitRuntimeService

from qcnn_lab.hardware.circuits import classifier_circuit, two_qubit_count, z_observable
from qcnn_lab.qcnn.architecture import QCNNArchitecture


@dataclass(frozen=True)
class BackendSnapshot:
    name: str
    num_qubits: int
    pending_jobs: int


def service() -> QiskitRuntimeService:
    return QiskitRuntimeService()


def choose_backends(min_qubits: int = 4, count: int = 2) -> list:
    svc = service()
    candidates = svc.backends(simulator=False, operational=True, min_num_qubits=min_qubits)
    if len(candidates) < count:
        raise RuntimeError(f"need at least {count} accessible operational backends")
    candidates = sorted(candidates, key=lambda b: b.status().pending_jobs)
    return candidates[:count]


def snapshot_backend(backend) -> BackendSnapshot:
    return BackendSnapshot(name=backend.name, num_qubits=int(backend.num_qubits), pending_jobs=int(backend.status().pending_jobs))


def device_noise_predict(states: np.ndarray, params: np.ndarray, architecture: QCNNArchitecture, n_qubits: int, backend, *, shots: int = 1024, seed: int = 12345) -> tuple[np.ndarray, list[dict]]:
    sim = AerSimulator.from_backend(backend)
    pm = generate_preset_pass_manager(backend=backend, optimization_level=3, seed_transpiler=seed)
    circuits = []
    metrics = []
    for state in states:
        qc, _ = classifier_circuit(state, params, architecture, n_qubits, measure=True)
        isa = pm.run(qc)
        circuits.append(isa)
        metrics.append({"depth": int(isa.depth()), "two_qubit_operations": int(two_qubit_count(isa))})
    result = sim.run(circuits, shots=shots, seed_simulator=seed).result()
    p1 = []
    for i in range(len(circuits)):
        counts = result.get_counts(i)
        p1.append(counts.get("1", 0) / shots)
    return np.asarray(p1, dtype=float), metrics


def hardware_estimator_predict(states: np.ndarray, params: np.ndarray, architecture: QCNNArchitecture, n_qubits: int, backend, *, precision: float = 0.05, resilience_level: int = 0, dynamical_decoupling: bool = False, seed_transpiler: int = 12345) -> tuple[np.ndarray, str, list[dict]]:
    pm = generate_preset_pass_manager(backend=backend, optimization_level=3, seed_transpiler=seed_transpiler)
    pubs = []
    metrics = []
    for state in states:
        qc, output = classifier_circuit(state, params, architecture, n_qubits, measure=False)
        isa = pm.run(qc)
        obs = z_observable(n_qubits, output).apply_layout(isa.layout)
        pubs.append((isa, obs))
        metrics.append({"depth": int(isa.depth()), "two_qubit_operations": int(two_qubit_count(isa))})
    estimator = EstimatorV2(mode=backend)
    estimator.options.resilience_level = int(resilience_level)
    estimator.options.dynamical_decoupling.enable = bool(dynamical_decoupling)
    if dynamical_decoupling:
        estimator.options.dynamical_decoupling.sequence_type = "XpXm"
    job = estimator.run(pubs, precision=float(precision))
    result = job.result()
    p1 = []
    for pub_result in result:
        ev = float(np.asarray(pub_result.data.evs).reshape(-1)[0])
        p1.append(float(np.clip((1.0 - ev) / 2.0, 0.0, 1.0)))
    return np.asarray(p1), job.job_id(), metrics