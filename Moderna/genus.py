"""
the datasets moduled — Genus computation via interlacement graph and GF(2) rank.

Computes the topological genus of an RNA secondary structure from its
base-pair list by:
  1. Building the interlacement (crossing) graph
  2. Constructing the adjacency matrix over GF(2)
  3. Computing rank via Gaussian elimination
  4. genus = rank // 2

References:
  - RNA-As-Graphs framework (Schlick lab)
  - TT2NE topological classification
"""

import numpy as np
from typing import List, Tuple


def parse_dotbracket(db_string: str) -> List[Tuple[int, int]]:
    """Parse multi-level dot-bracket notation into a sorted list of (i, j) pairs.

    Supports bracket types: () [] {} <>
    Dots '.' represent unpaired positions.

    Args:
        db_string: Dot-bracket string using . ( ) [ ] { } < >

    Returns:
        Sorted list of (i, j) tuples where i < j.

    Raises:
        ValueError: On unmatched brackets or unknown characters.
    """
    pairs: List[Tuple[int, int]] = []
    openers: dict[str, list[int]] = {'(': [], '[': [], '{': [], '<': []}
    closers = {')': '(', ']': '[', '}': '{', '>': '<'}

    for i, ch in enumerate(db_string):
        if ch in openers:
            openers[ch].append(i)
        elif ch in closers:
            opener_type = closers[ch]
            if not openers[opener_type]:
                raise ValueError(
                    f"Unmatched closing bracket '{ch}' at position {i}"
                )
            j = openers[opener_type].pop()
            pairs.append((j, i))
        elif ch == '.':
            continue
        else:
            raise ValueError(f"Unknown character '{ch}' at position {i}")

    for opener_type, stack in openers.items():
        if stack:
            raise ValueError(
                f"Unmatched opening bracket(s) '{opener_type}' "
                f"at positions {stack}"
            )

    return sorted(pairs)


def pairs_cross(p1: Tuple[int, int], p2: Tuple[int, int]) -> bool:
    """Check if two base pairs cross (interleave).

    Two pairs (a1,b1) and (a2,b2) with a1<b1, a2<b2 cross iff
    exactly one endpoint of one lies strictly inside the other's interval:
      (a1 < a2 < b1 < b2)  OR  (a2 < a1 < b2 < b1)

    Args:
        p1: First base pair (i, j).
        p2: Second base pair (i, j).

    Returns:
        True if the pairs cross.
    """
    a1, b1 = min(p1), max(p1)
    a2, b2 = min(p2), max(p2)
    return (a1 < a2 < b1 < b2) or (a2 < a1 < b2 < b1)


def build_interlacement_graph(base_pairs: List[Tuple[int, int]]) -> np.ndarray:
    """Build the adjacency matrix of the interlacement (crossing) graph.

    Nodes correspond to base pairs (or stems/quartets — genus depends
    only on the crossing relation, so pick one granularity and stay
    consistent).  An edge connects nodes i and j iff the corresponding
    pairs cross.

    Args:
        base_pairs: List of (i, j) base-pair tuples.

    Returns:
        k x k symmetric binary adjacency matrix (dtype int8).
    """
    k = len(base_pairs)
    adj = np.zeros((k, k), dtype=np.int8)
    for i in range(k):
        for j in range(i + 1, k):
            if pairs_cross(base_pairs[i], base_pairs[j]):
                adj[i][j] = 1
                adj[j][i] = 1
    return adj


def rank_gf2(matrix: np.ndarray) -> int:
    """Compute the rank of a binary matrix over GF(2) via Gaussian elimination.

    Uses XOR-based row reduction.  The input matrix is not modified.

    Args:
        matrix: Binary matrix (0/1 entries).

    Returns:
        The rank over GF(2).
    """
    m = matrix.copy().astype(np.int8)
    rows, cols = m.shape
    rank = 0

    for col in range(cols):
        # Find a pivot row with a 1 in this column, starting at row 'rank'
        pivot = None
        for row in range(rank, rows):
            if m[row, col] == 1:
                pivot = row
                break
        if pivot is None:
            continue

        # Swap pivot row into position 'rank'
        m[[rank, pivot]] = m[[pivot, rank]]

        # XOR into every other row that has a 1 in this column
        for row in range(rows):
            if row != rank and m[row, col] == 1:
                m[row] = m[row] ^ m[rank]

        rank += 1

    return rank


def compute_genus(base_pairs: List[Tuple[int, int]]) -> int:
    """Compute the topological genus of an RNA secondary structure.

    genus = rank_GF2(adjacency_matrix_of_interlacement_graph) // 2

    The theorem guarantees the GF(2) rank of the interlacement graph's
    adjacency matrix is always even.

    Args:
        base_pairs: List of (i, j) base-pair tuples.  Can be individual
            pairs, grouped stems, or quartets — genus depends only on the
            crossing relation.

    Returns:
        Non-negative integer.
        genus == 0  <=>  nested (pseudoknot-free) structure.
        genus >= 1  <=>  pseudoknotted structure.
    """
    if len(base_pairs) == 0:
        return 0

    adj = build_interlacement_graph(base_pairs)
    rank = rank_gf2(adj)

    assert rank % 2 == 0, (
        f"GF(2) rank is {rank} (odd) — theorem violation. "
        f"Check the interlacement graph construction."
    )

    return rank // 2
