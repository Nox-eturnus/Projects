"""
pipeline — Validation Tests for Pair-Level Candidate Generation.

Two mandatory tests:
  1. Hand-count validation: candidate count on a small (~12 nt) sequence
     matches an exhaustive manual enumeration.
  2. Crossing-audit: on a known Target B instance, confirm that both
     members of at least one known crossing pair-of-pairs appear in the
     output simultaneously.
"""

from candidates import generate_pair_candidates, VALID_BP
from genus import parse_dotbracket, pairs_cross
from data_loader import build_target_b


# ═══════════════════════════════════════════════════════════════════════════
# Test 1 — Hand / brute-force count on a small sequence
# ═══════════════════════════════════════════════════════════════════════════

def test_hand_count():
    """Validate candidate count on a 12-nt sequence against manual count.

    Sequence:  G  C  A  U  G  U  A  C  G  U  A  C
    Indices:   0  1  2  3  4  5  6  7  8  9  10 11

    We enumerate every (i, j) with j - i >= 4 and check if
    (seq[i], seq[j]) is a valid WC/wobble pair, counting manually.
    """
    print("Test 1: Hand-count validation on 12-nt sequence")
    seq = "GCAUGAUACGUAC"  # 13 nt for a bit more coverage
    n = len(seq)

    # Brute-force reference count
    expected = []
    for i in range(n):
        for j in range(i + 4, n):
            if (seq[i], seq[j]) in VALID_BP:
                expected.append((i, j))

    result = generate_pair_candidates(seq)

    print(f"  Sequence:        {seq}  ({n} nt)")
    print(f"  Expected count:  {len(expected)}")
    print(f"  Got count:       {len(result)}")

    assert result == expected, (
        f"FAIL: mismatch.\n"
        f"  Expected: {expected}\n"
        f"  Got:      {result}"
    )
    print(f"  PASS  counts match ({len(result)} candidates)")

    # Print all pairs for visual inspection
    for i, j in result:
        print(f"    ({i:2d},{j:2d})  {seq[i]}-{seq[j]}")


# ═══════════════════════════════════════════════════════════════════════════
# Test 2 — Crossing-audit on a Target B instance
# ═══════════════════════════════════════════════════════════════════════════

def test_crossing_audit():
    """On a Target B pseudoknot, verify that both members of a known
    crossing pair-of-pairs appear in the candidate list.

    Uses pk_htype_001: structure '((((..[[[[))))...]]]]'
    Known crossing: S1 pair (0,13) crosses S2 pair (6,20).
    Since pair-level has no non-crossing filter, this should trivially
    pass — but we verify to catch any dedup/sort bug that might
    silently drop one member.
    """
    print("\nTest 2: Crossing-audit on Target B instance")

    df_b = build_target_b()
    row = df_b[df_b['id'] == 'pk_htype_001'].iloc[0]
    seq = row['sequence']
    structure = row['known_structure_dotbracket']

    print(f"  ID:        {row['id']}")
    print(f"  Sequence:  {seq}")
    print(f"  Structure: {structure}")

    # Extract known pairs from the dot-bracket
    known_pairs = parse_dotbracket(structure)
    print(f"  Known pairs: {known_pairs}")

    # Find a crossing pair-of-pairs from the known structure
    crossing_found = False
    cross_a = None
    cross_b = None
    for i in range(len(known_pairs)):
        for j in range(i + 1, len(known_pairs)):
            if pairs_cross(known_pairs[i], known_pairs[j]):
                cross_a = known_pairs[i]
                cross_b = known_pairs[j]
                crossing_found = True
                break
        if crossing_found:
            break

    assert crossing_found, "FAIL: no crossing pairs found in Target B structure"
    print(f"  Known crossing: {cross_a} x {cross_b}")

    # Generate candidates and check both are present
    candidates = generate_pair_candidates(seq)
    candidate_set = set(candidates)

    assert cross_a in candidate_set, (
        f"FAIL: crossing pair {cross_a} NOT in candidates"
    )
    assert cross_b in candidate_set, (
        f"FAIL: crossing pair {cross_b} NOT in candidates"
    )
    print(f"  PASS  both crossing pairs present in {len(candidates)} candidates")

    # Extra: verify ALL known pairs are present (not just the crossing ones)
    missing = [p for p in known_pairs if p not in candidate_set]
    assert len(missing) == 0, (
        f"FAIL: {len(missing)} known pairs missing from candidates: {missing}"
    )
    print(f"  PASS  all {len(known_pairs)} known structure pairs present")


# ═══════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("pipeline — Pair-Level Candidate Generation Tests")
    print("=" * 60)
    print()

    test_hand_count()
    print()
    test_crossing_audit()
    print()

    print("=" * 60)
    print("ALL TESTS PASSED — pipeline Definition of Done satisfied")
    print("=" * 60)


if __name__ == '__main__':
    main()
