"""
the exact solver — Classical Ground Truth Establishment.

Provides exact solvers and baseline methods for establishing ground-truth
solutions to RNA folding QUBOs:

  1. OR-Tools CP-SAT exact solver (linearized QUBO → MIP)
  2. ViennaRNA MFE baseline (nested structures)
  3. ViennaRNA RNAPKplex baseline (pseudoknotted structures)
  4. eval_structure_energy() — unified Turner-model scoring for any method
  5. Brute-force vs OR-Tools cross-validation

IMPORTANT: If CP-SAT times out without proving optimality, the result
is NOT valid ground truth — it is flagged explicitly via `is_optimal`.
"""

from __future__ import annotations

import subprocess
import shutil
import numpy as np
from typing import List, Tuple, Optional

import RNA

from qubo import QUBOResult, brute_force_solve, _pairs_to_dotbracket, _get_pairs
from genus import pairs_cross


# ──────────────────────────────────────────────────────────────────────────
# 1. OR-Tools CP-SAT Exact Solver
# ──────────────────────────────────────────────────────────────────────────

# Scale factor for converting float Q entries to integers for CP-SAT.
# ViennaRNA energies have ~2 decimal places; ×1000 gives sub-0.001
# kcal/mol precision loss.
CPSAT_SCALE = 1000


class SolverResult:
    """Container for solver output."""

    def __init__(
        self,
        bitstring: np.ndarray,
        energy: float,
        is_optimal: bool,
        solver: str,
        qubo: QUBOResult,
    ):
        self.bitstring = bitstring
        self.energy = energy
        self.is_optimal = is_optimal
        self.solver = solver
        self.qubo = qubo

    @property
    def selected_pairs(self) -> List[Tuple[int, int]]:
        """Return base pairs selected by this solution."""
        return self.qubo.selected_pairs(self.bitstring)

    @property
    def is_feasible(self) -> bool:
        """Check if the solution is non-overlapping."""
        return self.qubo.is_feasible(self.bitstring)

    def has_crossing_pair(self) -> bool:
        """Check if the selected structure contains at least one crossing pair."""
        pairs = self.selected_pairs
        for i in range(len(pairs)):
            for j in range(i + 1, len(pairs)):
                if pairs_cross(pairs[i], pairs[j]):
                    return True
        return False


def cpsat_solve(
    qubo: QUBOResult,
    time_limit_sec: float = 60.0,
) -> SolverResult:
    """Solve a QUBO exactly using OR-Tools CP-SAT.

    Linearizes the quadratic objective via auxiliary variables:
        y_ij <= x_i
        y_ij <= x_j
        y_ij >= x_i + x_j - 1
        objective += Q[i][j] * y_ij

    The Q matrix is symmetrized: for each (i,j) pair, the effective
    coefficient is Q[i][j] + Q[j][i].

    Args:
        qubo:           QUBOResult from build_qubo() (with or without
                        genus penalty).
        time_limit_sec: Maximum solver wall-clock time in seconds.

    Returns:
        SolverResult with is_optimal=False if the solver timed out
        without proving optimality.
    """
    from ortools.sat.python import cp_model

    n = qubo.n
    Q = qubo.Q

    model = cp_model.CpModel()

    # Binary decision variables
    x = [model.new_bool_var(f'x_{i}') for i in range(n)]

    # Build objective with integer-scaled coefficients
    objective_terms = []

    # Diagonal terms: Q[i][i] * x_i  (linear since x_i^2 = x_i for binary)
    for i in range(n):
        coeff = int(round(Q[i, i] * CPSAT_SCALE))
        if coeff != 0:
            objective_terms.append(coeff * x[i])

    # Off-diagonal terms: (Q[i][j] + Q[j][i]) * x_i * x_j
    # Linearized via auxiliary y_ij = x_i AND x_j
    for i in range(n):
        for j in range(i + 1, n):
            coeff = int(round((Q[i, j] + Q[j, i]) * CPSAT_SCALE))
            if coeff == 0:
                continue

            y_ij = model.new_bool_var(f'y_{i}_{j}')

            # y_ij <= x_i
            model.add(y_ij <= x[i])
            # y_ij <= x_j
            model.add(y_ij <= x[j])
            # y_ij >= x_i + x_j - 1
            model.add(y_ij >= x[i] + x[j] - 1)

            objective_terms.append(coeff * y_ij)

    model.minimize(sum(objective_terms))

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_sec

    status = solver.solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        bitstring = np.array(
            [solver.value(x[i]) for i in range(n)], dtype=np.float64
        )
        # Compute actual QUBO energy (not the scaled integer objective)
        energy = float(bitstring @ Q @ bitstring)
        is_optimal = (status == cp_model.OPTIMAL)
    else:
        # No solution found — return all-zeros
        bitstring = np.zeros(n, dtype=np.float64)
        energy = 0.0
        is_optimal = False

    return SolverResult(
        bitstring=bitstring,
        energy=energy,
        is_optimal=is_optimal,
        solver='CP-SAT',
        qubo=qubo,
    )


# ──────────────────────────────────────────────────────────────────────────
# 2. ViennaRNA MFE Baseline
# ──────────────────────────────────────────────────────────────────────────

def vienna_mfe(sequence: str) -> Tuple[str, float]:
    """Compute the MFE structure using ViennaRNA.

    Args:
        sequence: RNA sequence string (A/U/G/C).

    Returns:
        (dot_bracket_structure, mfe_energy_kcal_mol)
    """
    fc = RNA.fold_compound(sequence)
    structure, energy = fc.mfe()
    return structure, energy


# ──────────────────────────────────────────────────────────────────────────
# 3. ViennaRNA RNAPKplex Baseline (pseudoknots)
# ──────────────────────────────────────────────────────────────────────────

def _find_pkplex_binary() -> Optional[str]:
    """Locate the RNAPKplex binary on the system."""
    return shutil.which('RNAPKplex')


def vienna_pkplex(
    sequence: str,
    energy_cutoff: float = -1.0,
) -> Optional[Tuple[str, float]]:
    """Predict pseudoknotted structure using RNAPKplex.

    Shells out to the RNAPKplex binary and parses output.
    Returns None if the binary is not available.

    Args:
        sequence:       RNA sequence string.
        energy_cutoff:  Minimum interaction energy for PKplex.

    Returns:
        (dot_bracket_structure, energy) or None if binary unavailable
        or no pseudoknot found.
    """
    binary = _find_pkplex_binary()
    if binary is None:
        return None

    try:
        result = subprocess.run(
            [binary, '-e', str(energy_cutoff)],
            input=sequence,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return None

        # Parse RNAPKplex output: lines contain dot-bracket structures
        # with energies in parentheses
        lines = result.stdout.strip().split('\n')

        best_structure = None
        best_energy = float('inf')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('>'):
                continue
            # Look for lines with structure and energy
            # Format: "..((..))..[[[..))]]]  (-5.30)"
            parts = line.rsplit('(', 1)
            if len(parts) == 2:
                struct = parts[0].strip()
                try:
                    energy = float(parts[1].rstrip(')').strip())
                    if energy < best_energy and len(struct) == len(sequence):
                        best_structure = struct
                        best_energy = energy
                except ValueError:
                    continue

        if best_structure is not None:
            return best_structure, best_energy
        return None

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


# ──────────────────────────────────────────────────────────────────────────
# 4. Unified eval_structure scoring
# ──────────────────────────────────────────────────────────────────────────

def eval_structure_energy(
    sequence: str,
    pairs: List[Tuple[int, int]],
) -> float:
    """Score a structure using ViennaRNA's full Turner model.

    This is the one comparable energy for every structure produced
    anywhere in the project (exact-solver, VQE/QAOA, SBM/SA outputs).

    For pseudoknotted structures (crossing pairs), the energy is
    computed on only the non-crossing subset (the largest nested
    subset), since ViennaRNA's eval_structure cannot handle crossing
    brackets.  The crossing pairs' contribution is NOT included.
    This is a known limitation — documented here for transparency.

    Args:
        sequence: RNA sequence string.
        pairs:    List of (i, j) base-pair tuples.

    Returns:
        Energy in kcal/mol from eval_structure().
    """
    if not pairs:
        return 0.0

    # Separate non-crossing pairs from crossing ones
    # Use a greedy approach: add pairs one by one, skip if it crosses
    # an already-accepted pair.  Sort by pair energy proxy (shorter
    # enclosing interval first) to prefer inner pairs.
    sorted_pairs = sorted(pairs, key=lambda p: (p[1] - p[0]))

    accepted: List[Tuple[int, int]] = []
    for p in sorted_pairs:
        crosses_any = False
        for a in accepted:
            if pairs_cross(p, a):
                crosses_any = True
                break
        if not crosses_any:
            accepted.append(p)

    if not accepted:
        return 0.0

    db = _pairs_to_dotbracket(accepted, len(sequence))
    fc = RNA.fold_compound(sequence)
    return fc.eval_structure(db)


# ──────────────────────────────────────────────────────────────────────────
# 5. Cross-validation: brute-force vs OR-Tools
# ──────────────────────────────────────────────────────────────────────────

def cross_validate_solvers(
    qubo: QUBOResult,
    tolerance: float = 0.01,
) -> Tuple[bool, str]:
    """Compare brute-force and OR-Tools solutions on a small QUBO.

    Both must agree on the optimal energy (within floating-point
    tolerance).

    Args:
        qubo:      QUBOResult with n <= 25.
        tolerance: Maximum allowed energy difference.

    Returns:
        (passed, message) tuple.
    """
    if qubo.n > 25:
        return True, f"SKIP — {qubo.n} variables too large for brute-force"

    bf_bits, bf_energy = brute_force_solve(qubo)
    cpsat_result = cpsat_solve(qubo, time_limit_sec=30.0)

    if not cpsat_result.is_optimal:
        return False, (
            f"CP-SAT did not prove optimality (energy={cpsat_result.energy:.4f}). "
            f"Cannot validate against brute-force (energy={bf_energy:.4f})."
        )

    diff = abs(bf_energy - cpsat_result.energy)
    if diff > tolerance:
        return False, (
            f"MISMATCH: brute-force={bf_energy:.4f}, "
            f"CP-SAT={cpsat_result.energy:.4f}, diff={diff:.4f}"
        )

    return True, (
        f"MATCH: brute-force={bf_energy:.4f}, "
        f"CP-SAT={cpsat_result.energy:.4f}, diff={diff:.6f}"
    )
