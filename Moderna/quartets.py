"""
the quartet candidate generator — Candidate Generation: Quartet-Level Encoding.

A quartet is a stacked pair-of-base-pairs: two consecutive WC/wobble
pairs (i, j) and (i+1, j-1) that form a single stacking unit.

Long helices decompose into multiple overlapping quartets, producing a
larger candidate set than stem-level encoding.  This is expected and
needed for the scalability analysis's scaling comparison.

CRITICAL DESIGN DECISION (from master plan):
    The published utility-scale quartet formulation bakes a crossing-
    exclusion penalty directly into its cost function.  That penalty
    belongs in QUBO/genus penalty's QUBO, NOT here.  ``generate_quartet_candidates``
    stays pseudoknot-agnostic — no crossing filter is applied.
"""

from typing import List, Tuple, NamedTuple

from candidates import generate_pair_candidates


class Quartet(NamedTuple):
    """A stacked pair-of-base-pairs.

    Attributes:
        pair1:  The outer pair (i, j).
        pair2:  The inner pair (i+1, j-1).
    """
    pair1: Tuple[int, int]
    pair2: Tuple[int, int]


def generate_quartet_candidates(
    sequence: str,
    pair_candidates: List[Tuple[int, int]] | None = None,
) -> List[Quartet]:
    """Generate all quartet candidates for an RNA sequence.

    A quartet exists whenever two consecutive valid base pairs
    (i, j) and (i+1, j-1) both appear in the pair-candidate list.

    No crossing filter is applied.  Crossing quartets are retained
    so that pseudoknots can be discovered by the downstream QUBO
    solver.

    Args:
        sequence:        RNA sequence string (A/U/G/C).
        pair_candidates: Pre-computed list of valid (i, j) pairs from
                         ``generate_pair_candidates``.  If ``None``,
                         it will be computed internally.

    Returns:
        List of ``Quartet`` objects, sorted by outer pair for
        deterministic ordering.
    """
    if pair_candidates is None:
        pair_candidates = generate_pair_candidates(sequence)

    pair_set = set(pair_candidates)
    quartets: List[Quartet] = []

    for (i, j) in pair_candidates:
        inner = (i + 1, j - 1)
        if inner in pair_set:
            quartets.append(Quartet(pair1=(i, j), pair2=inner))

    # Sort by outer pair for deterministic output
    quartets.sort(key=lambda q: q.pair1)
    return quartets
