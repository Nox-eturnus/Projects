"""
VQE & QAOA Circuit Construction and Runners.

Provides:
  - build_two_local_ansatz(): VQE ansatz with RY rotation + CZ entangling
  - build_qaoa_circuit(): QAOA circuit with cost layer (RZ/RZZ) and mixer
    (Pauli-X or XY)
  - run_vqe(): full VQE optimization loop using StatevectorEstimator
  - run_qaoa(): full QAOA optimization loop

All circuits are parameterized and optimized with scipy COBYLA.
Validation target: converge to the exact ground energy within tolerance.

IMPORTANT: This is a software-correctness check only (statevector, no noise).
Do NOT draw mixer-performance conclusions here — that's the noise study.
"""

from __future__ import annotations

import numpy as np
from typing import Optional, Dict, Any, Literal

from qiskit.circuit import QuantumCircuit, Parameter, ParameterVector
from qiskit.quantum_info import SparsePauliOp, Statevector

from qubo import QUBOResult
from ising import (
    qubo_to_ising,
    ising_to_sparse_pauli_op,
    spins_to_bitstring,
)


# ──────────────────────────────────────────────────────────────────────────
# VQE Two-Local Ansatz (Step 2)
# ──────────────────────────────────────────────────────────────────────────

def build_two_local_ansatz(
    n_qubits: int,
    reps: int = 1,
) -> QuantumCircuit:
    """Build a hardware-efficient two-local ansatz.

    Architecture:
        For each repetition:
            1. RY(θ) rotation layer on every qubit
            2. CZ entangling layer: linear nearest-neighbor (i, i+1)
        Final RY(θ) rotation layer after the last CZ layer.

    Total parameters: n_qubits * (reps + 1)

    Args:
        n_qubits: Number of qubits.
        reps:     Number of rotation+entangling repetitions (default 1).

    Returns:
        Parameterized QuantumCircuit.
    """
    n_params = n_qubits * (reps + 1)
    theta = ParameterVector('θ', n_params)

    qc = QuantumCircuit(n_qubits)
    param_idx = 0

    for rep in range(reps):
        # Rotation layer
        for q in range(n_qubits):
            qc.ry(theta[param_idx], q)
            param_idx += 1

        # Entangling layer: linear nearest-neighbor CZ
        for q in range(n_qubits - 1):
            qc.cz(q, q + 1)

    # Final rotation layer
    for q in range(n_qubits):
        qc.ry(theta[param_idx], q)
        param_idx += 1

    return qc


# ──────────────────────────────────────────────────────────────────────────
# QAOA Circuit (Step 3)
# ──────────────────────────────────────────────────────────────────────────

def _build_cost_layer(
    qc: QuantumCircuit,
    h: np.ndarray,
    J: np.ndarray,
    gamma: Parameter,
) -> None:
    """Append the QAOA cost layer: exp(-i γ H_C).

    Implements:
        - RZ(2 γ h_i) for each single-qubit term h_i Z_i
        - RZZ(2 γ J_ij) for each coupling term J_ij Z_i Z_j

    The RZZ gate: exp(-i θ/2 Z⊗Z).  For term J_ij Z_i Z_j in the cost
    Hamiltonian, we need exp(-i γ J_ij Z_i Z_j), so θ = 2 γ J_ij.
    Similarly, RZ(θ) = exp(-i θ/2 Z), so θ = 2 γ h_i.
    """
    n = len(h)

    # Single-qubit terms
    for i in range(n):
        if abs(h[i]) > 1e-12:
            qc.rz(2.0 * gamma * h[i], i)

    # Two-qubit terms
    for i in range(n):
        for j in range(i + 1, n):
            if abs(J[i, j]) > 1e-12:
                qc.rzz(2.0 * gamma * J[i, j], i, j)


def _build_mixer_x(
    qc: QuantumCircuit,
    n_qubits: int,
    beta: Parameter,
) -> None:
    """Append Pauli-X mixer layer: RX(2β) on each qubit.

    Implements exp(-i β Σ X_i) as product of single-qubit rotations.
    Zero two-qubit gates.
    """
    for i in range(n_qubits):
        qc.rx(2.0 * beta, i)


def _build_mixer_xy(
    qc: QuantumCircuit,
    n_qubits: int,
    beta: Parameter,
) -> None:
    """Append XY mixer layer: RXX(β) + RYY(β) on nearest-neighbor pairs.

    Implements exp(-i β Σ (X_i X_{i+1} + Y_i Y_{i+1})) approximately
    as a product of pairwise XY exchanges on a linear chain.

    This mixer preserves Hamming weight, making it suitable for
    constrained optimization problems.
    """
    for i in range(n_qubits - 1):
        qc.rxx(beta, i, i + 1)
        qc.ryy(beta, i, i + 1)


def build_qaoa_circuit(
    h: np.ndarray,
    J: np.ndarray,
    n_qubits: int,
    p: int = 1,
    mixer: Literal['x', 'xy'] = 'x',
) -> QuantumCircuit:
    """Build a QAOA circuit with p layers.

    Architecture:
        1. Initial state: |+⟩^n  (Hadamard on each qubit)
        2. For each layer k = 1..p:
           a. Cost layer with parameter γ_k
           b. Mixer layer with parameter β_k

    Total parameters: 2p  (one γ and one β per layer)

    Args:
        h:        Ising linear coefficients.
        J:        Ising coupling matrix (upper triangular).
        n_qubits: Number of qubits.
        p:        Number of QAOA layers (default 1).
        mixer:    'x' for Pauli-X mixer, 'xy' for XY mixer.

    Returns:
        Parameterized QuantumCircuit.
    """
    gammas = ParameterVector('γ', p)
    betas = ParameterVector('β', p)

    qc = QuantumCircuit(n_qubits)

    # Initial state: uniform superposition
    qc.h(range(n_qubits))

    for k in range(p):
        # Cost layer
        _build_cost_layer(qc, h, J, gammas[k])

        # Mixer layer
        if mixer == 'x':
            _build_mixer_x(qc, n_qubits, betas[k])
        elif mixer == 'xy':
            _build_mixer_xy(qc, n_qubits, betas[k])
        else:
            raise ValueError(f"Unknown mixer: {mixer!r}. Use 'x' or 'xy'.")

    return qc


# ──────────────────────────────────────────────────────────────────────────
# Optimization runners
# ──────────────────────────────────────────────────────────────────────────

def _extract_best_bitstring(
    circuit: QuantumCircuit,
    optimal_params: np.ndarray,
    n_qubits: int,
) -> np.ndarray:
    """Extract the highest-probability bitstring from the optimized circuit.

    Uses Statevector simulation to find the most probable measurement
    outcome, then converts from Qiskit qubit ordering to our convention.

    Returns:
        Binary bitstring as numpy array (qubit 0 = index 0).
    """
    bound_circuit = circuit.assign_parameters(optimal_params)
    sv = Statevector(bound_circuit)
    probs = sv.probabilities_dict()

    # Find highest-probability bitstring
    best_key = max(probs, key=probs.get)

    # Qiskit bitstring convention: rightmost bit = qubit 0
    # Our convention: index 0 = qubit 0
    # So we need to reverse the string
    bits = np.array([int(b) for b in reversed(best_key)], dtype=np.float64)

    return bits


def run_vqe(
    qubo: QUBOResult,
    reps: int = 1,
    max_iter: int = 300,
    seed: Optional[int] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Run VQE with a two-local ansatz on a QUBO.

    Uses StatevectorEstimator (exact expectation values, no shot noise)
    and scipy COBYLA optimizer.

    Args:
        qubo:     QUBOResult from build_qubo().
        reps:     Number of ansatz repetitions.
        max_iter: Maximum optimizer iterations.
        seed:     Random seed for initial parameter guess.
        verbose:  Print optimization progress.

    Returns:
        Dict with keys:
            'optimal_energy': Best Ising energy found (includes constant).
            'qubo_energy':    Corresponding QUBO energy.
            'optimal_params': Optimal parameter values.
            'bitstring':      Best bitstring (binary).
            'n_evals':        Number of function evaluations.
            'converged':      Whether optimizer converged.
    """
    from qiskit.primitives import StatevectorEstimator
    from scipy.optimize import minimize as scipy_minimize

    n = qubo.n
    h, J, constant = qubo_to_ising(qubo.Q)
    hamiltonian = ising_to_sparse_pauli_op(h, J, constant)

    ansatz = build_two_local_ansatz(n, reps=reps)
    n_params = ansatz.num_parameters

    estimator = StatevectorEstimator()

    eval_count = 0

    def cost_function(params):
        nonlocal eval_count
        eval_count += 1

        pub = (ansatz, hamiltonian, params)
        result = estimator.run([pub]).result()
        energy = float(result[0].data.evs)

        if verbose and eval_count % 50 == 0:
            print(f"  VQE eval {eval_count}: energy = {energy:.6f}")

        return energy

    # Initial parameters
    rng = np.random.default_rng(seed)
    x0 = rng.uniform(-np.pi, np.pi, n_params)

    if verbose:
        print(f"VQE: n_qubits={n}, reps={reps}, n_params={n_params}")

    result = scipy_minimize(
        cost_function,
        x0,
        method='COBYLA',
        options={'maxiter': max_iter, 'rhobeg': 0.5},
    )

    optimal_energy = float(result.fun)
    optimal_params = result.x

    # Extract best bitstring
    bitstring = _extract_best_bitstring(ansatz, optimal_params, n)
    qubo_energy = float(bitstring @ qubo.Q @ bitstring)

    if verbose:
        print(f"  VQE converged: {result.success}")
        print(f"  Ising energy: {optimal_energy:.6f}")
        print(f"  QUBO energy:  {qubo_energy:.6f}")
        print(f"  Evals: {eval_count}")

    return {
        'optimal_energy': optimal_energy,
        'qubo_energy': qubo_energy,
        'optimal_params': optimal_params,
        'bitstring': bitstring,
        'n_evals': eval_count,
        'converged': result.success,
        'method': 'VQE',
        'reps': reps,
    }


def run_qaoa(
    qubo: QUBOResult,
    p: int = 1,
    mixer: Literal['x', 'xy'] = 'x',
    max_iter: int = 300,
    seed: Optional[int] = None,
    n_restarts: int = 3,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Run QAOA on a QUBO.

    Uses StatevectorEstimator (exact expectation values, no shot noise)
    and scipy COBYLA optimizer with multiple random restarts.

    Args:
        qubo:       QUBOResult from build_qubo().
        p:          Number of QAOA layers.
        mixer:      'x' for Pauli-X, 'xy' for XY mixer.
        max_iter:   Maximum optimizer iterations per restart.
        seed:       Random seed for initial parameter guesses.
        n_restarts: Number of random restarts (best result kept).
        verbose:    Print optimization progress.

    Returns:
        Dict with keys matching run_vqe output, plus 'mixer' and 'p'.
    """
    from qiskit.primitives import StatevectorEstimator
    from scipy.optimize import minimize as scipy_minimize

    n = qubo.n
    h, J, constant = qubo_to_ising(qubo.Q)
    hamiltonian = ising_to_sparse_pauli_op(h, J, constant)

    qaoa_circuit = build_qaoa_circuit(h, J, n, p=p, mixer=mixer)
    n_params = qaoa_circuit.num_parameters  # 2p

    estimator = StatevectorEstimator()
    total_evals = 0

    def cost_function(params):
        nonlocal total_evals
        total_evals += 1

        pub = (qaoa_circuit, hamiltonian, params)
        result = estimator.run([pub]).result()
        energy = float(result[0].data.evs)
        return energy

    rng = np.random.default_rng(seed)

    best_result = None
    best_energy = float('inf')

    if verbose:
        print(f"QAOA: n_qubits={n}, p={p}, mixer={mixer}, "
              f"n_params={n_params}, restarts={n_restarts}")

    for restart in range(n_restarts):
        x0 = rng.uniform(-np.pi, np.pi, n_params)

        result = scipy_minimize(
            cost_function,
            x0,
            method='COBYLA',
            options={'maxiter': max_iter, 'rhobeg': 0.5},
        )

        if result.fun < best_energy:
            best_energy = result.fun
            best_result = result

        if verbose:
            print(f"  Restart {restart+1}/{n_restarts}: "
                  f"energy = {result.fun:.6f}")

    optimal_energy = float(best_result.fun)
    optimal_params = best_result.x

    # Extract best bitstring
    bitstring = _extract_best_bitstring(qaoa_circuit, optimal_params, n)
    qubo_energy = float(bitstring @ qubo.Q @ bitstring)

    if verbose:
        print(f"  Best Ising energy: {optimal_energy:.6f}")
        print(f"  QUBO energy:       {qubo_energy:.6f}")
        print(f"  Total evals:       {total_evals}")

    return {
        'optimal_energy': optimal_energy,
        'qubo_energy': qubo_energy,
        'optimal_params': optimal_params,
        'bitstring': bitstring,
        'n_evals': total_evals,
        'converged': best_result.success,
        'method': 'QAOA',
        'mixer': mixer,
        'p': p,
    }
