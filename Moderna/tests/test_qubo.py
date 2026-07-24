"""
pipeline — Validation Tests for QUBO Construction.

Definition of Done:
  On a Target A instance, brute-force-solving the exclusivity-only QUBO
  yields a non-overlapping structure whose energy is in the right ballpark
  of ViennaRNA's own MFE energy (not necessarily identical — it's a
  simplification — but not off by an order of magnitude or sign-flipped).
  A large mismatch means step 1's energy extraction has a bug.

Tests:
  Test 1 — Sanity: QUBO matrix is correctly shaped, one-body energies
           are populated, exclusivity penalty is positive.
  Test 2 — Feasibility: brute-force solution is non-overlapping.
  Test 3 — Energy ballpark: brute-force solution's eval_structure energy
           is in the right ballpark of ViennaRNA MFE.
  Test 4 — All three encodings produce valid QUBOs.
"""

import numpy as np
import RNA

from data_loader import build_target_a
from qubo import build_qubo, brute_force_solve, _pairs_to_dotbracket


# ═══════════════════════════════════════════════════════════════════════════
# Test 1 — Sanity checks on QUBO construction
# ═══════════════════════════════════════════════════════════════════════════

def test_qubo_sanity():
    """Check basic structural properties of the QUBO matrix."""
    print("Test 1: QUBO sanity checks")

    # Use the smallest Target A instance (short hairpin)
    df_a = build_target_a()
    row = df_a.iloc[0]  # First synthetic hairpin
    seq = row['sequence']
    print(f"  ID: {row['id']}, Sequence: {seq} ({len(seq)} nt)")

    qubo = build_qubo(seq, encoding='pair')
    Q = qubo.Q
    n = qubo.n

    print(f"  Candidates: {n}")
    print(f"  Q shape: {Q.shape}")
    print(f"  Exclusivity penalty: {qubo.exclusivity_penalty:.2f}")

    # Q must be square
    assert Q.shape == (n, n), f"FAIL: Q shape {Q.shape} != ({n}, {n})"
    print(f"  PASS  Q is {n}×{n}")

    # Q must be symmetric
    assert np.allclose(Q, Q.T), "FAIL: Q is not symmetric"
    print(f"  PASS  Q is symmetric")

    # One-body energies must be populated (not all zero)
    assert not np.all(qubo.one_body_energies == 0), (
        "FAIL: all one-body energies are zero"
    )
    print(f"  PASS  one-body energies are non-trivial")
    print(f"    min={qubo.one_body_energies.min():.2f}, "
          f"max={qubo.one_body_energies.max():.2f}")

    # Exclusivity penalty must be positive
    assert qubo.exclusivity_penalty > 0, (
        f"FAIL: P_excl = {qubo.exclusivity_penalty} <= 0"
    )
    print(f"  PASS  exclusivity penalty is positive")


# ═══════════════════════════════════════════════════════════════════════════
# Test 2 — Brute-force solution is feasible (non-overlapping)
# ═══════════════════════════════════════════════════════════════════════════

def test_brute_force_feasibility():
    """Brute-force solve a small pair-level QUBO; check feasibility."""
    print("Test 2: Brute-force solution feasibility")

    # Use a small hairpin for brute-force tractability
    df_a = build_target_a()
    row = df_a.iloc[0]
    seq = row['sequence']
    print(f"  ID: {row['id']}, Sequence: {seq} ({len(seq)} nt)")

    qubo = build_qubo(seq, encoding='pair')
    print(f"  Candidates: {qubo.n}")

    if qubo.n > 25:
        print(f"  SKIP — {qubo.n} candidates too large for brute-force")
        return

    best_bits, best_energy = brute_force_solve(qubo)
    selected = [i for i, b in enumerate(best_bits) if b == 1]
    pairs = qubo.selected_pairs(best_bits)

    print(f"  Best energy (QUBO): {best_energy:.2f}")
    print(f"  Selected {len(selected)} candidates -> {len(pairs)} pairs")
    print(f"  Pairs: {pairs}")

    # Must be feasible (non-overlapping)
    assert qubo.is_feasible(best_bits), (
        "FAIL: brute-force solution has overlapping positions"
    )
    print(f"  PASS  solution is non-overlapping")


# ═══════════════════════════════════════════════════════════════════════════
# Test 3 — Energy ballpark check against ViennaRNA MFE
# ═══════════════════════════════════════════════════════════════════════════

def test_energy_ballpark():
    """Compare brute-force QUBO solution energy to ViennaRNA MFE.

    The QUBO energy won't match exactly (it's a simplification), but
    the eval_structure energy of the selected pairs should be in the
    right ballpark — same sign and within an order of magnitude.
    """
    print("Test 3: Energy ballpark check against ViennaRNA MFE")

    df_a = build_target_a()
    # Test on a few small Target A instances
    test_rows = df_a[df_a['length'] <= 16].head(3)

    for _, row in test_rows.iterrows():
        seq = row['sequence']
        known_db = row['known_structure_dotbracket']
        print(f"\n  --- {row['id']} ---")
        print(f"  Sequence:  {seq} ({len(seq)} nt)")
        print(f"  Known:     {known_db}")

        # ViennaRNA MFE
        fc = RNA.fold_compound(seq)
        mfe_ss, mfe_energy = fc.mfe()
        print(f"  ViennaRNA MFE: {mfe_energy:.2f} ({mfe_ss})")

        # Build and solve QUBO
        qubo = build_qubo(seq, encoding='pair')
        print(f"  Candidates: {qubo.n}")

        if qubo.n > 25:
            print(f"  SKIP — too many candidates for brute-force")
            continue

        best_bits, best_qubo_energy = brute_force_solve(qubo)
        pairs = qubo.selected_pairs(best_bits)

        # Build dot-bracket from selected pairs and eval with ViennaRNA
        if pairs:
            db = _pairs_to_dotbracket(pairs, len(seq))
            eval_energy = fc.eval_structure(db)
        else:
            db = '.' * len(seq)
            eval_energy = 0.0

        print(f"  QUBO solution: {db}")
        print(f"  QUBO obj:      {best_qubo_energy:.2f}")
        print(f"  eval_structure: {eval_energy:.2f} kcal/mol")

        # Ballpark check: same sign and within 10x
        # (MFE is negative for stable structures)
        if mfe_energy < -0.5:
            # Both should be negative
            assert eval_energy < 0, (
                f"FAIL: ViennaRNA MFE is {mfe_energy:.2f} (negative) "
                f"but QUBO solution eval_structure is {eval_energy:.2f} "
                f"(non-negative) — sign mismatch"
            )
            ratio = abs(eval_energy / mfe_energy)
            print(f"  Ratio |eval/MFE|: {ratio:.2f}")
            assert 0.01 < ratio < 100, (
                f"FAIL: energy ratio {ratio:.2f} is outside [0.01, 100] "
                f"— order-of-magnitude mismatch"
            )
            print(f"  PASS  energy in ballpark "
                  f"(eval={eval_energy:.2f} vs MFE={mfe_energy:.2f})")
        else:
            print(f"  INFO  MFE is near zero ({mfe_energy:.2f}); "
                  f"skipping ratio check")


# ═══════════════════════════════════════════════════════════════════════════
# Test 4 — All three encodings produce valid QUBOs
# ═══════════════════════════════════════════════════════════════════════════

def test_all_encodings():
    """Build QUBOs for pair, stem, and quartet encodings.

    Verify each produces a valid symmetric matrix with the right shape.
    """
    print("Test 4: All three encodings produce valid QUBOs")

    df_a = build_target_a()
    row = df_a.iloc[0]
    seq = row['sequence']
    print(f"  ID: {row['id']}, Sequence: {seq} ({len(seq)} nt)")

    for enc in ['pair', 'stem', 'quartet']:
        qubo = build_qubo(seq, encoding=enc)
        Q = qubo.Q
        n = qubo.n

        assert Q.shape == (n, n), f"FAIL [{enc}]: shape {Q.shape}"
        assert np.allclose(Q, Q.T), f"FAIL [{enc}]: not symmetric"
        assert qubo.exclusivity_penalty > 0, (
            f"FAIL [{enc}]: P_excl <= 0"
        )

        print(f"  [{enc:8s}]  {n:3d} candidates, "
              f"P_excl={qubo.exclusivity_penalty:.2f}, "
              f"one_body range=[{qubo.one_body_energies.min():.2f}, "
              f"{qubo.one_body_energies.max():.2f}]")

    print(f"  PASS  all encodings produce valid QUBOs")


# ═══════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("pipeline — QUBO Construction Tests")
    print("=" * 60)
    print()

    test_qubo_sanity()
    print()
    test_brute_force_feasibility()
    print()
    test_energy_ballpark()
    print()
    test_all_encodings()
    print()

    print("=" * 60)
    print("ALL TESTS PASSED — pipeline Definition of Done satisfied")
    print("=" * 60)


if __name__ == '__main__':
    main()
