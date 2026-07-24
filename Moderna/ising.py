"""
QUBO -> Ising Mapping.

Converts a QUBO matrix Q into the Ising Hamiltonian:

    H = sum h_i Z_i + sum_{i<j} J_ij Z_i Z_j + constant

via the substitution x_i = (1 - z_i) / 2, z_i in {-1, +1}.

Closed-form derivation (derive once, unit-test, reuse everywhere):

    Given E_QUBO = sum_i Q_ii x_i + sum_{i!=j} Q_ij x_i x_j
    (using x_i^2 = x_i for binary variables)

    Let Q^sym = (Q + Q^T) / 2   (symmetrize once)

    Substituting x_i = (1 - z_i)/2:
      Diagonal terms:    Q_ii x_i = Q_ii (1 - z_i) / 2
      Off-diagonal:      Q_ij x_i x_j = Q_ij (1-z_i)(1-z_j) / 4

    Collecting:
      constant = sum_i Q_ii/2  +  (1/4) sum_{i!=j} Q_ij
      h_i      = -Q_ii/2  -  (1/2) sum_{j!=i} Q^sym_ij
      J_ij     = (1/2) Q^sym_ij    for i != j

The key identity to verify:
    QUBO(bitstring) == Ising(spins)
    where spins = 1 - 2 * bitstring
"""


from __future__ import annotations

import numpy as np
from typing import Tuple

from qubo import QUBOResult


# ──────────────────────────────────────────────────────────────────────────
# Conversion helpers
# ──────────────────────────────────────────────────────────────────────────

def bitstring_to_spins(bitstring: np.ndarray) -> np.ndarray:
    """Convert binary {0, 1} bitstring to Ising spins {+1, -1}.

    x_i = 0  →  z_i = +1
    x_i = 1  →  z_i = -1

    From x_i = (1 - z_i) / 2, we get z_i = 1 - 2*x_i.
    """
    return 1.0 - 2.0 * bitstring


def spins_to_bitstring(spins: np.ndarray) -> np.ndarray:
    """Convert Ising spins {+1, -1} to binary {0, 1} bitstring.

    z_i = +1  →  x_i = 0
    z_i = -1  →  x_i = 1

    From x_i = (1 - z_i) / 2.
    """
    return (1.0 - spins) / 2.0


# ──────────────────────────────────────────────────────────────────────────
# QUBO → Ising conversion
# ──────────────────────────────────────────────────────────────────────────

def qubo_to_ising(
    Q: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, float]:
    """Convert a QUBO matrix to Ising coefficients.

    Derivation:
        E_QUBO = sum_i Q_ii x_i + sum_{i!=j} Q_ij x_i x_j
        (since x_i^2 = x_i for binary variables)

        Substituting x_i = (1 - z_i)/2:
          Diagonal:    Q_ii x_i = Q_ii (1-z_i)/2
          Off-diag:    Q_ij x_i x_j = Q_ij (1-z_i)(1-z_j)/4

        Collecting terms:
          constant = sum_i Q_ii/2  +  (1/4) sum_{i!=j} Q_ij
          h_i      = -Q_ii/2  -  (1/2) sum_{j!=i} Q^sym_ij
          J_ij     = (1/2) Q^sym_ij   for i < j

        where Q^sym = (Q + Q^T)/2.

    Args:
        Q: n x n QUBO matrix (may be asymmetric; will be symmetrized).

    Returns:
        (h, J, constant) where:
            h: 1D array of length n, the linear Ising coefficients.
            J: n x n upper-triangular matrix of coupling coefficients
               (J[i][j] for i < j only; diagonal and lower triangle are 0).
            constant: scalar energy offset.

    The Ising energy for spin vector z in {-1, +1}^n is:
        E_ising = sum_i h_i z_i + sum_{i<j} J_ij z_i z_j + constant
    And the identity QUBO(bits) == Ising(spins) holds exactly.
    """
    n = Q.shape[0]
    assert Q.shape == (n, n), f"Q must be square, got {Q.shape}"

    # Symmetrize
    Q_sym = (Q + Q.T) / 2.0

    # Constant: trace(Q)/2 + (1/4) * sum of off-diagonal Q
    diag = np.diag(Q_sym)
    off_diag_sum = Q_sym.sum() - diag.sum()
    constant = 0.5 * diag.sum() + 0.25 * off_diag_sum

    # Linear coefficients:
    #   h_i = -Q_ii/2  -  (1/2) * sum_{j != i} Q^sym_ij
    # The off-diagonal row sum for row i:
    row_sums = Q_sym.sum(axis=1)  # full row sum including diagonal
    off_diag_row_sums = row_sums - diag  # sum_{j != i} Q^sym_ij
    h = -0.5 * diag - 0.5 * off_diag_row_sums

    # Coupling coefficients: J_ij = (1/2) Q^sym_ij for i < j
    # Store in upper triangular form
    J = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        for j in range(i + 1, n):
            J[i, j] = 0.5 * Q_sym[i, j]


    return h, J, float(constant)


# ──────────────────────────────────────────────────────────────────────────
# Ising energy evaluation
# ──────────────────────────────────────────────────────────────────────────

def ising_energy(
    spins: np.ndarray,
    h: np.ndarray,
    J: np.ndarray,
    constant: float,
) -> float:
    """Evaluate the Ising Hamiltonian energy for a given spin configuration.

    E = Σ_i h_i z_i + Σ_{i<j} J_ij z_i z_j + constant

    Args:
        spins:    1D array of {-1, +1} values.
        h:        Linear coefficients.
        J:        Upper-triangular coupling matrix.
        constant: Energy offset.

    Returns:
        Ising energy as a float.
    """
    n = len(spins)
    energy = constant

    # Linear terms
    energy += np.dot(h, spins)

    # Quadratic terms (upper triangle only)
    for i in range(n):
        for j in range(i + 1, n):
            if J[i, j] != 0.0:
                energy += J[i, j] * spins[i] * spins[j]

    return float(energy)


# ──────────────────────────────────────────────────────────────────────────
# Qiskit SparsePauliOp construction
# ──────────────────────────────────────────────────────────────────────────

def ising_to_sparse_pauli_op(
    h: np.ndarray,
    J: np.ndarray,
    constant: float,
) -> 'SparsePauliOp':
    """Build a Qiskit SparsePauliOp from Ising coefficients.

    Constructs H = Σ h_i Z_i + Σ_{i<j} J_ij Z_i Z_j + constant * I

    The SparsePauliOp uses Qiskit's qubit ordering convention where
    the rightmost character in the Pauli string corresponds to qubit 0.

    Args:
        h:        Linear coefficients.
        J:        Upper-triangular coupling matrix.
        constant: Energy offset (becomes coefficient of identity).

    Returns:
        SparsePauliOp representing the Ising Hamiltonian.
    """
    from qiskit.quantum_info import SparsePauliOp

    n = len(h)
    pauli_list = []

    # Identity term (constant)
    if abs(constant) > 1e-12:
        pauli_list.append(('I' * n, constant))

    # Single-qubit Z terms: h_i Z_i
    for i in range(n):
        if abs(h[i]) > 1e-12:
            # Qiskit convention: rightmost char = qubit 0
            label = ['I'] * n
            label[n - 1 - i] = 'Z'
            pauli_list.append((''.join(label), h[i]))

    # Two-qubit ZZ terms: J_ij Z_i Z_j
    for i in range(n):
        for j in range(i + 1, n):
            if abs(J[i, j]) > 1e-12:
                label = ['I'] * n
                label[n - 1 - i] = 'Z'
                label[n - 1 - j] = 'Z'
                pauli_list.append((''.join(label), J[i, j]))

    if not pauli_list:
        # Edge case: zero Hamiltonian
        pauli_list.append(('I' * n, 0.0))

    return SparsePauliOp.from_list(pauli_list).simplify()


def qubo_to_sparse_pauli_op(qubo: QUBOResult) -> 'SparsePauliOp':
    """Convenience: convert a QUBOResult directly to a SparsePauliOp.

    Args:
        qubo: A QUBOResult from build_qubo() or build_qubo_with_genus_penalty().

    Returns:
        SparsePauliOp representing the equivalent Ising Hamiltonian.
    """
    h, J, constant = qubo_to_ising(qubo.Q)
    return ising_to_sparse_pauli_op(h, J, constant)
