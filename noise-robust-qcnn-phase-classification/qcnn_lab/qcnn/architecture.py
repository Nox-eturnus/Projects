from __future__ import annotations

from dataclasses import dataclass
from math import log2

import numpy as np
from qiskit import QuantumCircuit


@dataclass(frozen=True)
class QCNNArchitecture:
    name: str
    conv_kind: str = "light"
    shared: bool = True
    ring: bool = False


def get_architecture(name: str) -> QCNNArchitecture:
    table = {
        "light_shared_line": QCNNArchitecture(name, "light", True, False),
        "light_shared_ring": QCNNArchitecture(name, "light", True, True),
        "expressive_shared_line": QCNNArchitecture(name, "expressive", True, False),
        "light_unshared_line": QCNNArchitecture(name, "light", False, False),
    }
    if name not in table:
        raise ValueError(f"unknown QCNN architecture {name}; choose from {sorted(table)}")
    return table[name]


def _validate_n(n_qubits: int) -> None:
    if n_qubits < 2 or n_qubits & (n_qubits - 1):
        raise ValueError("QCNN implementation requires a power-of-two qubit count >= 2")


def conv_param_count(kind: str) -> int:
    if kind == "light":
        return 3
    if kind == "expressive":
        return 6
    raise ValueError(f"unknown convolution kind {kind}")


def _conv_pairs(active: list[int], ring: bool) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for i in range(0, len(active) - 1, 2):
        pairs.append((active[i], active[i + 1]))
    for i in range(1, len(active) - 1, 2):
        pairs.append((active[i], active[i + 1]))
    if ring and len(active) > 2:
        pairs.append((active[-1], active[0]))
    seen = set()
    unique = []
    for pair in pairs:
        key = tuple(sorted(pair))
        if key not in seen:
            unique.append(pair)
            seen.add(key)
    return unique


def _pool_pairs(active: list[int]) -> list[tuple[int, int]]:
    return [(active[i], active[i + 1]) for i in range(0, len(active), 2)]


def parameter_count(n_qubits: int, architecture: QCNNArchitecture) -> int:
    _validate_n(n_qubits)
    active = list(range(n_qubits))
    total = 0
    cp = conv_param_count(architecture.conv_kind)
    while len(active) > 1:
        conv_pairs = _conv_pairs(active, architecture.ring)
        pool_pairs = _pool_pairs(active)
        if architecture.shared:
            total += cp + 3
        else:
            total += cp * len(conv_pairs) + 3 * len(pool_pairs)
        active = [sink for _, sink in pool_pairs]
    return total


def _apply_conv(qc: QuantumCircuit, q0: int, q1: int, p: np.ndarray, kind: str) -> None:
    if kind == "light":
        qc.rz(-np.pi / 2, q1)
        qc.cx(q1, q0)
        qc.rz(float(p[0]), q0)
        qc.ry(float(p[1]), q1)
        qc.cx(q0, q1)
        qc.ry(float(p[2]), q1)
        qc.cx(q1, q0)
        qc.rz(np.pi / 2, q0)
        return
    if kind == "expressive":
        qc.ry(float(p[0]), q0)
        qc.ry(float(p[1]), q1)
        qc.rz(float(p[2]), q0)
        qc.rz(float(p[3]), q1)
        qc.rxx(float(p[4]), q0, q1)
        qc.rzz(float(p[5]), q0, q1)
        return
    raise ValueError(f"unknown convolution kind {kind}")


def _apply_pool(qc: QuantumCircuit, source: int, sink: int, p: np.ndarray) -> None:
    qc.rz(-np.pi / 2, sink)
    qc.cx(sink, source)
    qc.rz(float(p[0]), source)
    qc.ry(float(p[1]), sink)
    qc.cx(source, sink)
    qc.ry(float(p[2]), sink)


def build_qcnn(n_qubits: int, params: np.ndarray, architecture: QCNNArchitecture) -> tuple[QuantumCircuit, int]:
    _validate_n(n_qubits)
    params = np.asarray(params, dtype=float).reshape(-1)
    expected = parameter_count(n_qubits, architecture)
    if len(params) != expected:
        raise ValueError(f"expected {expected} parameters, got {len(params)}")
    qc = QuantumCircuit(n_qubits, name=architecture.name)
    active = list(range(n_qubits))
    cursor = 0
    cp = conv_param_count(architecture.conv_kind)
    while len(active) > 1:
        conv_pairs = _conv_pairs(active, architecture.ring)
        pool_pairs = _pool_pairs(active)
        if architecture.shared:
            conv_p = params[cursor : cursor + cp]
            cursor += cp
            for q0, q1 in conv_pairs:
                _apply_conv(qc, q0, q1, conv_p, architecture.conv_kind)
            pool_p = params[cursor : cursor + 3]
            cursor += 3
            for source, sink in pool_pairs:
                _apply_pool(qc, source, sink, pool_p)
        else:
            for q0, q1 in conv_pairs:
                _apply_conv(qc, q0, q1, params[cursor : cursor + cp], architecture.conv_kind)
                cursor += cp
            for source, sink in pool_pairs:
                _apply_pool(qc, source, sink, params[cursor : cursor + 3])
                cursor += 3
        active = [sink for _, sink in pool_pairs]
    assert cursor == expected
    return qc, active[0]


def raw_circuit_metrics(n_qubits: int, architecture: QCNNArchitecture) -> dict[str, int]:
    params = np.zeros(parameter_count(n_qubits, architecture))
    qc, output = build_qcnn(n_qubits, params, architecture)
    two_qubit = 0
    for instruction in qc.data:
        if len(instruction.qubits) == 2:
            two_qubit += 1
    return {
        "n_qubits": n_qubits,
        "parameters": len(params),
        "depth": qc.depth(),
        "two_qubit_operations": two_qubit,
        "output_qubit": output,
    }