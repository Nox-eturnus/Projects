"""
the pair candidate generator — Candidate Generation: Pair-Level Encoding.

Enumerates all valid candidate base pairs (i, j) in a given RNA sequence,
where "valid" means:
  - (sequence[i], sequence[j]) is a Watson–Crick or wobble pair
  - j - i >= 4   (minimum loop-closure constraint)

No non-crossing filter is applied — the full candidate set includes pairs
that cross, enabling pseudoknot detection downstream.
"""

from typing import List, Tuple


# All valid base pairings (WC + wobble)
VALID_BP = {
    ('A', 'U'), ('U', 'A'),
    ('G', 'C'), ('C', 'G'),
    ('G', 'U'), ('U', 'G'),
}


def generate_pair_candidates(sequence: str) -> List[Tuple[int, int]]:
    """Generate all valid candidate base pairs for an RNA sequence.

    A pair (i, j) is a candidate iff:
      1. (sequence[i], sequence[j]) is in {AU, UA, GC, CG, GU, UG}
      2. j - i >= 4   (enforces minimum hairpin loop closure)

    No non-crossing filter is applied.  Crossing pairs are retained so
    that pseudoknots can be discovered by the downstream QUBO solver.

    Args:
        sequence: RNA sequence string (characters in {A, U, G, C}).

    Returns:
        Sorted list of (i, j) tuples with i < j.
    """
    n = len(sequence)
    candidates: List[Tuple[int, int]] = []

    for i in range(n):
        for j in range(i + 4, n):
            if (sequence[i], sequence[j]) in VALID_BP:
                candidates.append((i, j))

    return candidates
