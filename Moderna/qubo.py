"""
the QUBO module — QUBO Construction (energies + exclusivity; no genus penalty yet).

Builds the QUBO matrix Q = one_body + two_body + exclusivity for each of
the three encoding levels (pair, stem, quartet).

Energy terms use ViennaRNA's eval_structure() to extract Turner-model
energies.  Each candidate's one-body energy is its isolated hairpin/stack
energy.  Two-body stacking bonuses capture the incremental gain from
combining structurally-adjacent candidates.  Mutual exclusivity penalties
prevent any two candidates from sharing a nucleotide position.

The genus penalty (topological crossing term) is NOT included here —
that is the genus penalty module's responsibility.

ACCEPTED APPROXIMATION (documented per plan item 7.4):
    Multiloop penalties scale with the number of closing helices and
    don't map onto fixed pairwise Q terms.  This is a known limitation
    of the pairwise QUBO formulation.  The one-body eval_structure()
    call captures the hairpin loop and stacking contributions but not
    the multi-loop junction penalty that would apply in a full structure.
    This approximation is acceptable for the project scope.
"""

from __future__ import annotations

import numpy as np
from typing import List, Tuple, Dict, Any

import RNA

from candidates import generate_pair_candidates
from stems import generate_stem_candidates, Stem
from quartets import generate_quartet_candidates, Quartet


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _pairs_to_dotbracket(
    pairs: List[Tuple[int, int]], seq_len: int
) -> str:
    """Build a dot-bracket string with only the specified pairs filled in.

    All other positions are dots.  Uses only '(' and ')' — no crossing
    bracket types, since ViennaRNA eval_structure cannot handle them.
    The caller is responsible for ensuring the pairs are non-crossing
    within this single call (which they always are for isolated one-body
    or structurally-adjacent two-body evaluations).
    """
    db = ['.'] * seq_len
    for i, j in pairs:
        db[i] = '('
        db[j] = ')'
    return ''.join(db)


def _get_positions(candidate: Any, encoding: str) -> set[int]:
    """Return the set of nucleotide positions occupied by a candidate.

    Args:
        candidate: A pair tuple, Stem, or Quartet.
        encoding:  One of 'pair', 'stem', 'quartet'.
    """
    if encoding == 'pair':
        i, j = candidate
        return {i, j}
    elif encoding == 'stem':
        positions: set[int] = set()
        for i, j in candidate.pairs:
            positions.add(i)
            positions.add(j)
        return positions
    elif encoding == 'quartet':
        i1, j1 = candidate.pair1
        i2, j2 = candidate.pair2
        return {i1, j1, i2, j2}
    else:
        raise ValueError(f"Unknown encoding: {encoding}")


def _get_pairs(candidate: Any, encoding: str) -> List[Tuple[int, int]]:
    """Return the list of base pairs for a candidate."""
    if encoding == 'pair':
        return [candidate]
    elif encoding == 'stem':
        return list(candidate.pairs)
    elif encoding == 'quartet':
        return [candidate.pair1, candidate.pair2]
    else:
        raise ValueError(f"Unknown encoding: {encoding}")


def _are_structurally_adjacent(
    c1: Any, c2: Any, encoding: str
) -> bool:
    """Check if two candidates are structurally adjacent (stackable).

    Two candidates are adjacent if they can form a contiguous helix
    extension — i.e. one's innermost pair is immediately followed by
    the other's outermost pair (or vice versa), meaning (i, j) and
    (i+1, j-1) are present across the two candidates.

    For pair-level: (i1, j1) and (i2, j2) are adjacent if
        i2 == i1+1, j2 == j1-1  or  i1 == i2+1, j1 == j2-1.

    For stem-level: the inner pair of one stem is adjacent to the
        outer pair of the other (they would form one longer helix).

    For quartet-level: the inner pair of one quartet is adjacent to
        the outer pair of the other.
    """
    if encoding == 'pair':
        i1, j1 = c1
        i2, j2 = c2
        return (
            (i2 == i1 + 1 and j2 == j1 - 1) or
            (i1 == i2 + 1 and j1 == j2 - 1)
        )
    elif encoding == 'stem':
        # Check if inner of one == adjacent to outer of other
        inner1 = c1.inner
        inner2 = c2.inner
        outer1 = c1.outer
        outer2 = c2.outer
        return (
            (outer2[0] == inner1[0] + 1 and outer2[1] == inner1[1] - 1) or
            (outer1[0] == inner2[0] + 1 and outer1[1] == inner2[1] - 1)
        )
    elif encoding == 'quartet':
        # Inner of one quartet adjacent to outer of the other
        inner1 = c1.pair2
        inner2 = c2.pair2
        outer1 = c1.pair1
        outer2 = c2.pair1
        return (
            (outer2[0] == inner1[0] + 1 and outer2[1] == inner1[1] - 1) or
            (outer1[0] == inner2[0] + 1 and outer1[1] == inner2[1] - 1)
        )
    return False


def _candidates_are_noncrossing(
    pairs1: List[Tuple[int, int]], pairs2: List[Tuple[int, int]]
) -> bool:
    """Check that the combined pair set is non-crossing.

    Required before passing to ViennaRNA eval_structure, which only
    handles nested structures.
    """
    all_pairs = pairs1 + pairs2
    for idx_a in range(len(all_pairs)):
        a1, a2 = all_pairs[idx_a]
        if a1 > a2:
            a1, a2 = a2, a1
        for idx_b in range(idx_a + 1, len(all_pairs)):
            b1, b2 = all_pairs[idx_b]
            if b1 > b2:
                b1, b2 = b2, b1
            # Crossing: a1 < b1 < a2 < b2 or b1 < a1 < b2 < a2
            if (a1 < b1 < a2 < b2) or (b1 < a1 < b2 < a2):
                return False
    return True


# ──────────────────────────────────────────────────────────────────────────
# QUBO Builder
# ──────────────────────────────────────────────────────────────────────────

class QUBOResult:
    """Container for a built QUBO matrix and its metadata."""

    def __init__(
        self,
        Q: np.ndarray,
        candidates: list,
        encoding: str,
        sequence: str,
        one_body_energies: np.ndarray,
        exclusivity_penalty: float,
    ):
        self.Q = Q
        self.candidates = candidates
        self.encoding = encoding
        self.sequence = sequence
        self.one_body_energies = one_body_energies
        self.exclusivity_penalty = exclusivity_penalty
        self.n = len(candidates)

    def evaluate(self, bitstring: np.ndarray) -> float:
        """Compute x^T Q x for a given binary bitstring."""
        return float(bitstring @ self.Q @ bitstring)

    def selected_pairs(self, bitstring: np.ndarray) -> List[Tuple[int, int]]:
        """Return all base pairs selected by the bitstring."""
        pairs: List[Tuple[int, int]] = []
        for idx, bit in enumerate(bitstring):
            if bit == 1:
                pairs.extend(
                    _get_pairs(self.candidates[idx], self.encoding)
                )
        return sorted(set(pairs))

    def copy(self) -> 'QUBOResult':
        """Return a deep copy of this QUBOResult.

        The Q matrix and one_body_energies are copied so that
        modifications (e.g. genus penalty injection) don't mutate
        the original.
        """
        return QUBOResult(
            Q=self.Q.copy(),
            candidates=list(self.candidates),
            encoding=self.encoding,
            sequence=self.sequence,
            one_body_energies=self.one_body_energies.copy(),
            exclusivity_penalty=self.exclusivity_penalty,
        )

    def is_feasible(self, bitstring: np.ndarray) -> bool:
        """Check if the bitstring has no overlapping nucleotide positions."""
        used: set[int] = set()
        for idx, bit in enumerate(bitstring):
            if bit == 1:
                positions = _get_positions(
                    self.candidates[idx], self.encoding
                )
                if positions & used:
                    return False
                used |= positions
        return True


def build_qubo(
    sequence: str,
    encoding: str = 'pair',
    min_stem_len: int = 2,
    excl_multiplier: float = 10.0,
) -> QUBOResult:
    """Build the QUBO matrix for RNA folding.

    Constructs Q = one_body + two_body_stacking + exclusivity.
    No genus/crossing penalty — that is the genus penalty module.

    Args:
        sequence:        RNA sequence string (A/U/G/C).
        encoding:        One of 'pair', 'stem', 'quartet'.
        min_stem_len:    Min stem length (only for stem encoding).
        excl_multiplier: P_excl = excl_multiplier × max(|one_body|).
                         Adapted per-instance, not a global constant.

    Returns:
        QUBOResult with the Q matrix and metadata.
    """
    # ── Generate candidates ──────────────────────────────────────────
    pair_candidates = generate_pair_candidates(sequence)

    if encoding == 'pair':
        candidates = pair_candidates
    elif encoding == 'stem':
        candidates = generate_stem_candidates(
            sequence, pair_candidates, min_stem_len=min_stem_len
        )
    elif encoding == 'quartet':
        candidates = generate_quartet_candidates(
            sequence, pair_candidates
        )
    else:
        raise ValueError(f"Unknown encoding: {encoding}")

    n = len(candidates)
    Q = np.zeros((n, n), dtype=np.float64)
    seq_len = len(sequence)

    # ViennaRNA fold compound — reused for all evaluations
    fc = RNA.fold_compound(sequence)

    # ── Step 1: One-body energies (diagonal) ─────────────────────────
    one_body = np.zeros(n, dtype=np.float64)

    for idx, cand in enumerate(candidates):
        pairs = _get_pairs(cand, encoding)
        db = _pairs_to_dotbracket(pairs, seq_len)
        energy = fc.eval_structure(db)
        one_body[idx] = energy
        Q[idx, idx] = energy

    # ── Step 2: Two-body stacking bonus (off-diagonal) ───────────────
    for i in range(n):
        for j in range(i + 1, n):
            if not _are_structurally_adjacent(
                candidates[i], candidates[j], encoding
            ):
                continue

            pairs_i = _get_pairs(candidates[i], encoding)
            pairs_j = _get_pairs(candidates[j], encoding)

            # Can only evaluate with ViennaRNA if the combined
            # pair set is non-crossing
            if not _candidates_are_noncrossing(pairs_i, pairs_j):
                continue

            # Check for shared positions — if they share positions,
            # the combined structure is not meaningful for stacking
            pos_i = _get_positions(candidates[i], encoding)
            pos_j = _get_positions(candidates[j], encoding)
            if pos_i & pos_j:
                continue

            combined_pairs = pairs_i + pairs_j
            db_combined = _pairs_to_dotbracket(combined_pairs, seq_len)
            e_combined = fc.eval_structure(db_combined)

            # Stacking bonus = combined energy - sum of individual
            bonus = e_combined - one_body[i] - one_body[j]

            # Only apply if it's actually a bonus (negative = stabilizing)
            if bonus < 0:
                Q[i, j] += bonus / 2.0
                Q[j, i] += bonus / 2.0

    # ── Step 3: Mutual exclusivity penalty (off-diagonal) ────────────
    max_one_body_mag = max(abs(one_body).max(), 1e-6)  # avoid zero
    P_excl = excl_multiplier * max_one_body_mag

    for i in range(n):
        for j in range(i + 1, n):
            pos_i = _get_positions(candidates[i], encoding)
            pos_j = _get_positions(candidates[j], encoding)
            if pos_i & pos_j:
                Q[i, j] += P_excl / 2.0
                Q[j, i] += P_excl / 2.0

    return QUBOResult(
        Q=Q,
        candidates=candidates,
        encoding=encoding,
        sequence=sequence,
        one_body_energies=one_body,
        exclusivity_penalty=P_excl,
    )


def brute_force_solve(qubo: QUBOResult) -> Tuple[np.ndarray, float]:
    """Brute-force solve a QUBO by exhaustive enumeration.

    Only practical for small N (≤ ~25 variables).

    Args:
        qubo: A QUBOResult from build_qubo().

    Returns:
        (best_bitstring, best_energy) tuple.
    """
    n = qubo.n
    if n > 25:
        raise ValueError(
            f"Brute-force on {n} variables would enumerate {2**n} "
            f"states — use OR-Tools (the exact solver) instead."
        )

    best_bits = None
    best_energy = float('inf')

    for state in range(2 ** n):
        bits = np.array(
            [(state >> k) & 1 for k in range(n)], dtype=np.float64
        )
        energy = bits @ qubo.Q @ bits
        if energy < best_energy:
            best_energy = energy
            best_bits = bits.copy()

    return best_bits, best_energy
