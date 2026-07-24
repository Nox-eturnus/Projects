"""
pipeline — Validation Tests for Quartet-Level Candidate Generation.

Four mandatory tests (per Definition of Done):

  Test 1 — Basic quartet construction:
      Quartets are correctly formed from consecutive valid pairs and
      the quartet structure matches expectations.

  Test 2 — Crossing-audit, two-stem case:
      Quartets from both stems of a known H-type pseudoknot appear
      simultaneously.

  Test 3 — Crossing-audit, three-stem case:
      Quartets from 3 non-nested overlapping helix regions all appear
      as independent candidates.

  Test 4 — Quartet count > stem count:
      On the same test sequence, quartet count exceeds stem count
      (expected scaling relationship from overlapping decomposition).
"""

from candidates import generate_pair_candidates
from quartets import generate_quartet_candidates, Quartet
from stems import generate_stem_candidates
from genus import parse_dotbracket, pairs_cross
from data_loader import build_target_b


# ═══════════════════════════════════════════════════════════════════════════
# Test 1 — Basic quartet construction
# ═══════════════════════════════════════════════════════════════════════════

def test_basic_quartet_construction():
    """Verify quartets are correctly formed from consecutive valid pairs.

    Uses a simple hairpin: GGGCAUAUGCCC
    Structure:              ((((....))))
    Expected quartets from the main helix:
      Q1: (0,11) + (1,10)
      Q2: (1,10) + (2,9)
      Q3: (2,9)  + (3,8)
    """
    print("Test 1: Basic quartet construction")

    seq = "GGGCAUAUGCCC"
    print(f"  Sequence:  {seq}  ({len(seq)} nt)")

    pairs = generate_pair_candidates(seq)
    quartets = generate_quartet_candidates(seq, pairs)

    print(f"  Pair candidates:  {len(pairs)}")
    print(f"  Quartet candidates: {len(quartets)}")

    for q in quartets:
        print(f"    Quartet: {q.pair1} + {q.pair2}")

    # The main helix quartets must be present
    expected = [
        Quartet(pair1=(0, 11), pair2=(1, 10)),
        Quartet(pair1=(1, 10), pair2=(2, 9)),
        Quartet(pair1=(2, 9),  pair2=(3, 8)),
    ]
    for eq in expected:
        assert eq in quartets, (
            f"FAIL: expected quartet {eq} not found.\n"
            f"  Got: {quartets}"
        )
    print(f"  PASS  all 3 main helix quartets found")

    # Each quartet's pair2 must be (pair1[0]+1, pair1[1]-1)
    for q in quartets:
        assert q.pair2 == (q.pair1[0] + 1, q.pair1[1] - 1), (
            f"FAIL: quartet inner pair mismatch: {q}"
        )
    print(f"  PASS  all quartets have correct outer/inner structure")


# ═══════════════════════════════════════════════════════════════════════════
# Test 2 — Crossing-audit: two-stem case
# ═══════════════════════════════════════════════════════════════════════════

def test_crossing_audit_two_stem():
    """Quartets from both stems of an H-type pseudoknot must appear.

    Uses pk_htype_001:  structure '((((..[[[[))))...]]]]'
    Stem 1 (S1):  pairs (0,13), (1,12), (2,11), (3,10)
    Stem 2 (S2):  pairs (6,20), (7,19), (8,18), (9,17)

    S1 quartets: (0,13)+(1,12), (1,12)+(2,11), (2,11)+(3,10)
    S2 quartets: (6,20)+(7,19), (7,19)+(8,18), (8,18)+(9,17)

    These two stems cross.  Quartets from both must be present.
    """
    print("Test 2: Crossing-audit — two-stem case (H-type pseudoknot)")

    df_b = build_target_b()
    row = df_b[df_b['id'] == 'pk_htype_001'].iloc[0]
    seq = row['sequence']
    structure = row['known_structure_dotbracket']

    print(f"  ID:        {row['id']}")
    print(f"  Sequence:  {seq}")
    print(f"  Structure: {structure}")

    known_pairs = parse_dotbracket(structure)

    # Identify stem pairs by bracket type
    stem1_pairs = sorted(
        [p for p in known_pairs if structure[p[0]] == '(']
    )
    stem2_pairs = sorted(
        [p for p in known_pairs if structure[p[0]] == '[']
    )

    print(f"  S1 pairs: {stem1_pairs}")
    print(f"  S2 pairs: {stem2_pairs}")

    # Confirm crossing
    assert pairs_cross(stem1_pairs[0], stem2_pairs[0]), "S1 x S2 should cross"
    print(f"  Confirmed: S1 and S2 cross")

    # Build expected quartets from each stem
    def quartets_from_stem_pairs(stem_pairs):
        """Extract expected quartets from a list of consecutive stem pairs."""
        sp = sorted(stem_pairs, key=lambda p: p[0])
        qs = []
        for idx in range(len(sp) - 1):
            i1, j1 = sp[idx]
            i2, j2 = sp[idx + 1]
            if i2 == i1 + 1 and j2 == j1 - 1:
                qs.append(Quartet(pair1=(i1, j1), pair2=(i2, j2)))
        return qs

    s1_quartets = quartets_from_stem_pairs(stem1_pairs)
    s2_quartets = quartets_from_stem_pairs(stem2_pairs)

    print(f"  Expected S1 quartets: {len(s1_quartets)}")
    print(f"  Expected S2 quartets: {len(s2_quartets)}")

    # Generate quartets
    pairs = generate_pair_candidates(seq)
    quartets = generate_quartet_candidates(seq, pairs)
    quartet_set = set(quartets)

    print(f"  Total quartet candidates: {len(quartets)}")

    # Check all expected quartets are present
    for q in s1_quartets:
        assert q in quartet_set, (
            f"FAIL: S1 quartet {q} not in candidates"
        )
    print(f"  PASS  all {len(s1_quartets)} S1 quartets present")

    for q in s2_quartets:
        assert q in quartet_set, (
            f"FAIL: S2 quartet {q} not in candidates"
        )
    print(f"  PASS  all {len(s2_quartets)} S2 quartets present")


# ═══════════════════════════════════════════════════════════════════════════
# Test 3 — Crossing-audit: three-stem case (FSE-relevant)
# ═══════════════════════════════════════════════════════════════════════════

def test_crossing_audit_three_stem():
    """Quartets from 3 non-nested overlapping helix regions must appear.

    Same synthetic sequence as pipeline's three-stem test:
        S1: (0,9), (1,8)        → 1 quartet
        S2: (4,15), (5,14)      → 1 quartet
        S3: (12,21), (13,20)    → 1 quartet

    S1 x S2 cross, S2 x S3 cross.  All 3 quartets must be present.
    """
    print("Test 3: Crossing-audit — three-stem case (FSE-relevant)")

    n = 22
    seq_list = ['A'] * n

    # S1: (0,9), (1,8)
    seq_list[0] = 'G'; seq_list[9] = 'C'
    seq_list[1] = 'G'; seq_list[8] = 'C'

    # S2: (4,15), (5,14)
    seq_list[4] = 'G'; seq_list[15] = 'C'
    seq_list[5] = 'G'; seq_list[14] = 'C'

    # S3: (12,21), (13,20)
    seq_list[12] = 'G'; seq_list[21] = 'C'
    seq_list[13] = 'G'; seq_list[20] = 'C'

    seq = ''.join(seq_list)
    print(f"  Sequence:  {seq}  ({len(seq)} nt)")

    # Verify crossings
    assert pairs_cross((0, 9), (4, 15)), "S1 x S2 should cross"
    assert pairs_cross((4, 15), (12, 21)), "S2 x S3 should cross"
    print(f"  Confirmed: S1 x S2 cross, S2 x S3 cross")

    # Expected quartets
    q1 = Quartet(pair1=(0, 9), pair2=(1, 8))
    q2 = Quartet(pair1=(4, 15), pair2=(5, 14))
    q3 = Quartet(pair1=(12, 21), pair2=(13, 20))

    pairs = generate_pair_candidates(seq)
    quartets = generate_quartet_candidates(seq, pairs)
    quartet_set = set(quartets)

    print(f"  Total quartet candidates: {len(quartets)}")
    for q in quartets:
        print(f"    Quartet: {q.pair1} + {q.pair2}")

    assert q1 in quartet_set, f"FAIL: S1 quartet {q1} not found"
    print(f"  PASS  S1 quartet present")
    assert q2 in quartet_set, f"FAIL: S2 quartet {q2} not found"
    print(f"  PASS  S2 quartet present")
    assert q3 in quartet_set, f"FAIL: S3 quartet {q3} not found"
    print(f"  PASS  S3 quartet present")

    print(f"  PASS  all 3 crossing quartets present as independent candidates")


# ═══════════════════════════════════════════════════════════════════════════
# Test 4 — Quartet count > stem count
# ═══════════════════════════════════════════════════════════════════════════

def test_quartet_count_exceeds_stem_count():
    """Verify quartet count > stem count on the same test sequence.

    This is the expected scaling relationship: long helices decompose
    into multiple overlapping quartets, while stem-level encoding
    collapses each helix into a single candidate.

    Uses pk_htype_001 which has two 4-bp stems → 3 quartets each
    (vs. 1 maximal stem each, plus sub-stems).
    """
    print("Test 4: Quartet count > stem count (scaling relationship)")

    df_b = build_target_b()
    row = df_b[df_b['id'] == 'pk_htype_001'].iloc[0]
    seq = row['sequence']

    print(f"  Sequence:  {seq}  ({len(seq)} nt)")

    pairs = generate_pair_candidates(seq)
    stems = generate_stem_candidates(seq, pairs, min_stem_len=2)
    quartets = generate_quartet_candidates(seq, pairs)

    print(f"  Stem candidates:    {len(stems)}")
    print(f"  Quartet candidates: {len(quartets)}")

    assert len(quartets) > len(stems), (
        f"FAIL: expected quartet count ({len(quartets)}) > "
        f"stem count ({len(stems)}). "
        f"This is unexpected — investigate the scaling relationship."
    )
    print(f"  PASS  quartet count ({len(quartets)}) > "
          f"stem count ({len(stems)})")


# ═══════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("pipeline — Quartet-Level Candidate Generation Tests")
    print("=" * 60)
    print()

    test_basic_quartet_construction()
    print()
    test_crossing_audit_two_stem()
    print()
    test_crossing_audit_three_stem()
    print()
    test_quartet_count_exceeds_stem_count()
    print()

    print("=" * 60)
    print("ALL TESTS PASSED — pipeline Definition of Done satisfied")
    print("=" * 60)


if __name__ == '__main__':
    main()
