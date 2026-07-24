"""
pipeline — Validation Tests for Stem-Level Candidate Generation.

Three mandatory tests (per Definition of Done):

  Test 1 — Basic stem construction:
      Stems are correctly formed from consecutive valid pairs, deduped,
      and respect MIN_STEM_LEN.

  Test 2 — Crossing-audit, two-stem case:
      Both stems of a known interleaving pair (H-type pseudoknot)
      appear simultaneously in the candidate list.

  Test 3 — Crossing-audit, three-stem case:
      A synthetic sequence with 3 non-nested overlapping helix regions
      produces all 3 as independent candidates.  This is the FSE-relevant
      check (not just the simple pseudoknot case).
"""

from candidates import generate_pair_candidates
from stems import generate_stem_candidates, Stem
from genus import parse_dotbracket, pairs_cross
from data_loader import build_target_b


# ═══════════════════════════════════════════════════════════════════════════
# Test 1 — Basic stem construction
# ═══════════════════════════════════════════════════════════════════════════

def test_basic_stem_construction():
    """Verify that stems are correctly formed from consecutive pairs.

    Uses a short sequence with a single clear hairpin stem and checks:
      - stem pairs are contiguous (i, j), (i+1, j-1), ...
      - stems shorter than MIN_STEM_LEN are excluded
      - deduplication works (same stem not reported twice)
    """
    print("Test 1: Basic stem construction")

    # Simple hairpin: GGGC-AUAU-GCCC
    #                 0123 4567 8901  (indices)
    # Structure:      ((((....))))
    # Expected stem:  (0,11), (1,10), (2,9), (3,8)
    seq = "GGGCAUAUGCCC"
    print(f"  Sequence:  {seq}  ({len(seq)} nt)")

    pairs = generate_pair_candidates(seq)
    stems = generate_stem_candidates(seq, pairs, min_stem_len=2)

    print(f"  Pair candidates:  {len(pairs)}")
    print(f"  Stem candidates:  {len(stems)}")

    # Print all stems
    for s in stems:
        print(f"    Stem: outer={s.outer}, inner={s.inner}, "
              f"len={len(s.pairs)}, pairs={s.pairs}")

    # The hairpin stem (0,11)-(1,10)-(2,9)-(3,8) must be present
    expected_pairs = ((0, 11), (1, 10), (2, 9), (3, 8))
    found = any(s.pairs == expected_pairs for s in stems)
    assert found, (
        f"FAIL: expected hairpin stem {expected_pairs} not found.\n"
        f"  Got: {[s.pairs for s in stems]}"
    )
    print(f"  PASS  main hairpin stem found")

    # All stems must have length >= 2
    for s in stems:
        assert len(s.pairs) >= 2, (
            f"FAIL: stem with {len(s.pairs)} pairs (< 2): {s.pairs}"
        )
    print(f"  PASS  all stems have length >= 2")

    # No duplicate stems
    pair_tuples = [s.pairs for s in stems]
    assert len(pair_tuples) == len(set(pair_tuples)), (
        f"FAIL: duplicate stems detected"
    )
    print(f"  PASS  no duplicate stems")


# ═══════════════════════════════════════════════════════════════════════════
# Test 2 — Crossing-audit: two-stem case
# ═══════════════════════════════════════════════════════════════════════════

def test_crossing_audit_two_stem():
    """Confirm both stems of a known H-type pseudoknot appear.

    Uses pk_htype_001:  structure '((((..[[[[))))...]]]]'
    Stem 1 (S1):  pairs from '(' → positions 0-3 paired with 10-13
    Stem 2 (S2):  pairs from '[' → positions 6-9 paired with 17-20

    These two stems cross (interleave).  Both must be present —
    no greedy crossing filter should have removed either.
    """
    print("Test 2: Crossing-audit — two-stem case (H-type pseudoknot)")

    df_b = build_target_b()
    row = df_b[df_b['id'] == 'pk_htype_001'].iloc[0]
    seq = row['sequence']
    structure = row['known_structure_dotbracket']

    print(f"  ID:        {row['id']}")
    print(f"  Sequence:  {seq}")
    print(f"  Structure: {structure}")

    # Parse the known structure into stems
    known_pairs = parse_dotbracket(structure)

    # Identify the two stems manually from the bracket types
    # '(' pairs: (0,13), (1,12), (2,11), (3,10)
    # '[' pairs: (6,20), (7,19), (8,18), (9,17)
    stem1_pairs = set()
    stem2_pairs = set()
    for p in known_pairs:
        i, j = p
        if structure[i] == '(':
            stem1_pairs.add(p)
        elif structure[i] == '[':
            stem2_pairs.add(p)

    print(f"  Known S1 pairs: {sorted(stem1_pairs)}")
    print(f"  Known S2 pairs: {sorted(stem2_pairs)}")

    # Confirm the stems cross
    s1_rep = sorted(stem1_pairs)[0]
    s2_rep = sorted(stem2_pairs)[0]
    assert pairs_cross(s1_rep, s2_rep), (
        f"FAIL: S1 {s1_rep} and S2 {s2_rep} don't cross — test setup bug"
    )
    print(f"  Confirmed: S1 and S2 cross (interleave)")

    # Generate stem candidates
    pairs = generate_pair_candidates(seq)
    stems = generate_stem_candidates(seq, pairs, min_stem_len=2)

    print(f"  Stem candidates generated: {len(stems)}")
    for s in stems:
        print(f"    Stem: outer={s.outer}, inner={s.inner}, "
              f"len={len(s.pairs)}, pairs={s.pairs}")

    # Check: does a stem exist whose pair-set is a superset of stem1_pairs?
    def find_covering_stem(target_pairs, all_stems):
        """Find a stem candidate whose pairs cover all target pairs."""
        for s in all_stems:
            if target_pairs.issubset(set(s.pairs)):
                return s
        return None

    s1_stem = find_covering_stem(stem1_pairs, stems)
    s2_stem = find_covering_stem(stem2_pairs, stems)

    assert s1_stem is not None, (
        f"FAIL: no stem candidate covers S1 pairs {sorted(stem1_pairs)}"
    )
    print(f"  PASS  S1 covered by stem {s1_stem.outer}-{s1_stem.inner}")

    assert s2_stem is not None, (
        f"FAIL: no stem candidate covers S2 pairs {sorted(stem2_pairs)}"
    )
    print(f"  PASS  S2 covered by stem {s2_stem.outer}-{s2_stem.inner}")

    # Both appear simultaneously (not just one)
    assert s1_stem != s2_stem, (
        f"FAIL: S1 and S2 mapped to same stem — impossible if they cross"
    )
    print(f"  PASS  both crossing stems present simultaneously")


# ═══════════════════════════════════════════════════════════════════════════
# Test 3 — Crossing-audit: three-stem case (FSE-relevant)
# ═══════════════════════════════════════════════════════════════════════════

def test_crossing_audit_three_stem():
    """Synthetic sequence with 3 non-nested overlapping helix regions.

    Build a sequence where three stems S1, S2, S3 are all mutually
    crossing (or at least pairwise crossing in a non-nested arrangement).
    All 3 must appear as independent candidates.

    Design:
        S1: positions 0-2 pair with 12-14  (3 bp)
        S2: positions 5-7 pair with 17-19  (3 bp)
        S3: positions 10-11 pair with 22-23 (2 bp)

        S1 and S2 interleave: 0<5<14 but 12<17 → check if (0,14) x (5,19)
        Actually let's construct a clearer three-stem crossing:

        S1: positions 0-1  pair with 8-9    → (0,9), (1,8)
        S2: positions 4-5  pair with 14-15  → (4,15), (5,14)
        S3: positions 12-13 pair with 20-21 → (12,21), (13,20)

        Crossing check:
        S1 outer (0,9), S2 outer (4,15): 0<4<9<15 → CROSS ✓
        S2 outer (4,15), S3 outer (12,21): 4<12<15<21 → CROSS ✓
        S1 outer (0,9), S3 outer (12,21): 0<9<12<21 → nested, not crossing

        So S1 crosses S2, S2 crosses S3 — that's 3 non-nested stems,
        which is the FSE-relevant pattern.

    Construct the sequence explicitly with WC pairs at those positions.
    """
    print("Test 3: Crossing-audit — three-stem case (FSE-relevant)")

    # We need at least 22 positions.
    # Place G-C pairs for S1, S2, S3 at specific positions.
    # Fill everything else with A (won't pair with anything at distance >= 4
    # because A only pairs with U).
    n = 22
    seq_list = ['A'] * n

    # S1: (0,9), (1,8) → G-C pairs
    seq_list[0] = 'G'; seq_list[9] = 'C'
    seq_list[1] = 'G'; seq_list[8] = 'C'

    # S2: (4,15), (5,14) → G-C pairs
    seq_list[4] = 'G'; seq_list[15] = 'C'
    seq_list[5] = 'G'; seq_list[14] = 'C'

    # S3: (12,21), (13,20) → G-C pairs
    seq_list[12] = 'G'; seq_list[21] = 'C'
    seq_list[13] = 'G'; seq_list[20] = 'C'

    seq = ''.join(seq_list)
    print(f"  Sequence:  {seq}  ({len(seq)} nt)")
    print(f"  Designed stems:")
    print(f"    S1: (0,9), (1,8)")
    print(f"    S2: (4,15), (5,14)")
    print(f"    S3: (12,21), (13,20)")

    # Verify crossings
    assert pairs_cross((0, 9), (4, 15)), "S1 x S2 should cross"
    assert pairs_cross((4, 15), (12, 21)), "S2 x S3 should cross"
    print(f"  Confirmed: S1 x S2 cross, S2 x S3 cross")

    # Generate stem candidates
    pairs = generate_pair_candidates(seq)
    stems = generate_stem_candidates(seq, pairs, min_stem_len=2)

    print(f"  Pair candidates:  {len(pairs)}")
    print(f"  Stem candidates:  {len(stems)}")
    for s in stems:
        print(f"    Stem: outer={s.outer}, inner={s.inner}, "
              f"len={len(s.pairs)}, pairs={s.pairs}")

    # Check all three stems are present
    s1_pairs = {(0, 9), (1, 8)}
    s2_pairs = {(4, 15), (5, 14)}
    s3_pairs = {(12, 21), (13, 20)}

    def find_covering_stem(target_pairs, all_stems):
        for s in all_stems:
            if target_pairs.issubset(set(s.pairs)):
                return s
        return None

    s1 = find_covering_stem(s1_pairs, stems)
    s2 = find_covering_stem(s2_pairs, stems)
    s3 = find_covering_stem(s3_pairs, stems)

    assert s1 is not None, (
        f"FAIL: S1 pairs {sorted(s1_pairs)} not found in any stem candidate"
    )
    print(f"  PASS  S1 present: {s1.pairs}")

    assert s2 is not None, (
        f"FAIL: S2 pairs {sorted(s2_pairs)} not found in any stem candidate"
    )
    print(f"  PASS  S2 present: {s2.pairs}")

    assert s3 is not None, (
        f"FAIL: S3 pairs {sorted(s3_pairs)} not found in any stem candidate"
    )
    print(f"  PASS  S3 present: {s3.pairs}")

    # All three are distinct
    stem_ids = {id(s1), id(s2), id(s3)}
    assert len(stem_ids) == 3, "FAIL: some stems collapsed to the same object"
    print(f"  PASS  all 3 stems are distinct independent candidates")


# ═══════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("pipeline — Stem-Level Candidate Generation Tests")
    print("=" * 60)
    print()

    test_basic_stem_construction()
    print()
    test_crossing_audit_two_stem()
    print()
    test_crossing_audit_three_stem()
    print()

    print("=" * 60)
    print("ALL TESTS PASSED — pipeline Definition of Done satisfied")
    print("=" * 60)


if __name__ == '__main__':
    main()
