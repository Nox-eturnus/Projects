"""
the stem candidate generator — Candidate Generation: Stem-Level Encoding.

Groups consecutive valid base pairs into maximal helical stems.

A stem is a contiguous run of stacked base pairs (i,j), (i+1,j-1), ...,
(i+k,j-k).  Each stem must contain at least MIN_STEM_LEN base pairs
(default: 2).

CRITICAL DESIGN DECISION (from master plan):
    Do NOT discard a stem for crossing a previously-accepted stem.
    That greedy discard is exactly the silent non-crossing assumption
    that kills pseudoknot detection.  Every maximal stem from every
    starting pair is generated independently; crossing exclusion is a
    QUBO-time penalty decision (the genus penalty module), never a candidate-generation-
    time filter.
"""

from typing import List, Tuple, NamedTuple

from candidates import generate_pair_candidates


class Stem(NamedTuple):
    """A helical stem: a contiguous run of stacked base pairs.

    Attributes:
        pairs:  Tuple of (i, j) base-pair tuples forming the stem,
                ordered from outermost to innermost.
        outer:  The outermost (first) pair  — same as pairs[0].
        inner:  The innermost (last) pair   — same as pairs[-1].
    """
    pairs: Tuple[Tuple[int, int], ...]
    outer: Tuple[int, int]
    inner: Tuple[int, int]


# Default minimum stem length (number of stacked base pairs).
# Configurable per the plan; 2 captures the smallest biologically
# meaningful helix.
MIN_STEM_LEN: int = 2


def generate_stem_candidates(
    sequence: str,
    pair_candidates: List[Tuple[int, int]] | None = None,
    min_stem_len: int = MIN_STEM_LEN,
) -> List[Stem]:
    """Generate all maximal stem candidates for an RNA sequence.

    Starting from every candidate pair (i, j), extend inward by
    repeatedly checking whether (i+1, j-1) is also a valid candidate
    pair.  Keep only stems with length >= *min_stem_len*.

    Deduplication: two starting positions can produce the identical
    pair set (e.g., starting at (3,20) yields the same stem as
    starting at (4,19) if the latter is a subset).  We deduplicate
    by keeping only *maximal* stems — if stem A's pair set is a
    strict subset of stem B's, A is dropped.

    No crossing filter is applied.  Crossing stems are retained so
    that pseudoknots can be discovered by the downstream QUBO solver.

    Args:
        sequence:        RNA sequence string (A/U/G/C).
        pair_candidates: Pre-computed list of valid (i,j) pairs from
                         ``generate_pair_candidates``.  If ``None``,
                         it will be computed internally.
        min_stem_len:    Minimum number of stacked pairs for a stem
                         to be retained.

    Returns:
        List of ``Stem`` objects, sorted by outer pair for
        deterministic ordering.
    """
    if pair_candidates is None:
        pair_candidates = generate_pair_candidates(sequence)

    # Fast look-up for candidate membership
    pair_set = set(pair_candidates)

    # ------------------------------------------------------------------
    # 1. From every candidate pair, extend inward to build maximal stems
    # ------------------------------------------------------------------
    raw_stems: List[List[Tuple[int, int]]] = []

    for (i, j) in pair_candidates:
        stem: List[Tuple[int, int]] = [(i, j)]
        ci, cj = i, j

        while True:
            ci_next, cj_next = ci + 1, cj - 1
            # Loop-closure constraint: inner pair must leave room
            # for at least a 3-nt hairpin loop (cj_next - ci_next >= 3,
            # but our pair_candidates already enforce j - i >= 4 which
            # covers 4-nt minimum; the extension just needs cj_next > ci_next).
            if cj_next <= ci_next:
                break
            if (ci_next, cj_next) in pair_set:
                stem.append((ci_next, cj_next))
                ci, cj = ci_next, cj_next
            else:
                break

        if len(stem) >= min_stem_len:
            raw_stems.append(stem)

    # ------------------------------------------------------------------
    # 2. Deduplicate: keep only maximal stems
    # ------------------------------------------------------------------
    # Convert to frozensets for subset checking, preserving order mapping.
    stem_sets = [frozenset(s) for s in raw_stems]

    # A stem is maximal if no other stem is a strict superset of it.
    maximal_indices: List[int] = []
    for idx, sset in enumerate(stem_sets):
        is_subset = False
        for jdx, other in enumerate(stem_sets):
            if idx != jdx and sset < other:  # strict subset
                is_subset = True
                break
        if not is_subset:
            maximal_indices.append(idx)

    # Deduplicate identical pair sets (same stem reached from
    # different starting positions after extension).
    seen: set[frozenset[Tuple[int, int]]] = set()
    stems: List[Stem] = []
    for idx in maximal_indices:
        key = stem_sets[idx]
        if key in seen:
            continue
        seen.add(key)

        # Canonical ordering: outermost to innermost
        ordered = sorted(raw_stems[idx], key=lambda p: p[0])
        stems.append(Stem(
            pairs=tuple(ordered),
            outer=ordered[0],
            inner=ordered[-1],
        ))

    # Sort by outer pair for deterministic ordering
    stems.sort(key=lambda s: s.outer)
    return stems
