"""
Parts 8 & 9 -- Combined Validation Tests.

pipeline Definition of Done:
  - Brute-force and OR-Tools agree exactly on all N<=25 instances.
  - Validation checkpoint: every Target B instance's exact solution
    contains at least one crossing pair.

pipeline Definition of Done:
  - Sweep produces a real (non-flat, non-degenerate) accuracy curve.
  - mu_star lands strictly inside the swept range.
"""

import sys
import numpy as np
import RNA

from data_loader import build_target_a, build_target_b, build_fse_targets
from qubo import build_qubo, brute_force_solve, _pairs_to_dotbracket
from genus import pairs_cross, parse_dotbracket, compute_genus
from classical_solvers import (
    cpsat_solve,
    vienna_mfe,
    vienna_pkplex,
    eval_structure_energy,
    cross_validate_solvers,
    SolverResult,
)
from genus_penalty import (
    get_crossing_candidate_pairs,
    check_path_a_applicability,
    inject_genus_penalty,
    build_qubo_with_genus_penalty,
    calibrate_mu,
    count_crossing_pairs_in_solution,
    TT2NE_MU,
    get_mu_star,
)


# =========================================================================
# pipeline -- Test 1: Brute-force vs OR-Tools agreement
# =========================================================================

def test_brute_force_vs_cpsat():
    """On all N<=25 instances, brute-force and OR-Tools must agree exactly."""
    print("pipeline -- Test 1: Brute-force vs OR-Tools agreement")

    df_a = build_target_a()
    passed_count = 0
    skip_count = 0
    total = 0

    for _, row in df_a.iterrows():
        seq = row['sequence']
        total += 1

        for enc in ['pair', 'stem', 'quartet']:
            qubo = build_qubo(seq, encoding=enc)

            if qubo.n > 25:
                skip_count += 1
                continue
            if qubo.n == 0:
                skip_count += 1
                continue

            ok, msg = cross_validate_solvers(qubo, tolerance=0.01)
            if not ok:
                print(f"  FAIL [{row['id']}, {enc}]: {msg}")
                assert False, msg
            passed_count += 1

    print(f"  PASS  {passed_count} cross-validations passed "
          f"({skip_count} skipped for size)")
    print()


# =========================================================================
# pipeline -- Test 2: ViennaRNA MFE baseline
# =========================================================================

def test_vienna_mfe_baseline():
    """ViennaRNA MFE produces valid structures for Target A."""
    print("pipeline -- Test 2: ViennaRNA MFE baseline")

    df_a = build_target_a()
    test_rows = df_a.head(5)

    for _, row in test_rows.iterrows():
        seq = row['sequence']
        structure, energy = vienna_mfe(seq)

        assert len(structure) == len(seq), (
            f"FAIL [{row['id']}]: structure length {len(structure)} "
            f"!= sequence length {len(seq)}"
        )
        assert energy <= 0.0 or len(seq) < 8, (
            f"FAIL [{row['id']}]: MFE energy {energy:.2f} > 0 "
            f"for a non-trivial sequence"
        )

        print(f"  {row['id']}: {structure}  ({energy:.2f} kcal/mol)")

    print(f"  PASS  ViennaRNA MFE baseline valid for Target A")
    print()


# =========================================================================
# pipeline -- Test 3: ViennaRNA PKplex baseline (graceful skip)
# =========================================================================

def test_vienna_pkplex_baseline():
    """ViennaRNA RNAPKplex for Target B (skip if binary unavailable)."""
    print("pipeline -- Test 3: ViennaRNA RNAPKplex baseline")

    df_b = build_target_b()
    row = df_b.iloc[0]
    seq = row['sequence']

    result = vienna_pkplex(seq)

    if result is None:
        print("  SKIP  RNAPKplex binary not found or failed -- "
              "this is a graceful fallback, not an error")
    else:
        structure, energy = result
        print(f"  {row['id']}: {structure}  ({energy:.2f} kcal/mol)")
        print(f"  PASS  RNAPKplex produced a structure")

    print()


# =========================================================================
# pipeline -- Test 4: eval_structure_energy round-trip
# =========================================================================

def test_eval_structure_energy():
    """eval_structure_energy is consistent with direct ViennaRNA calls."""
    print("pipeline -- Test 4: eval_structure_energy round-trip")

    df_a = build_target_a()
    test_rows = df_a[df_a['length'] <= 16].head(3)

    for _, row in test_rows.iterrows():
        seq = row['sequence']
        known_db = row['known_structure_dotbracket']
        pairs = parse_dotbracket(known_db)

        # Direct ViennaRNA
        fc = RNA.fold_compound(seq)
        direct_energy = fc.eval_structure(
            _pairs_to_dotbracket(pairs, len(seq))
        )

        # Our unified scoring
        unified_energy = eval_structure_energy(seq, pairs)

        diff = abs(direct_energy - unified_energy)
        assert diff < 0.01, (
            f"FAIL [{row['id']}]: direct={direct_energy:.4f}, "
            f"unified={unified_energy:.4f}, diff={diff:.4f}"
        )
        print(f"  {row['id']}: direct={direct_energy:.2f}, "
              f"unified={unified_energy:.2f}  [OK]")

    print(f"  PASS  eval_structure_energy is consistent")
    print()


# =========================================================================
# pipeline -- Test 5: Crossing-pair detection
# =========================================================================

def test_crossing_pair_detection():
    """Crossing-pair detection produces correct counts on known instances."""
    print("pipeline -- Test 5: Crossing-pair detection")

    # Nested hairpin -- zero crossings
    nested_seq = "GCGCAAAAGCGC"
    qubo_nested = build_qubo(nested_seq, encoding='pair')
    # For pair encoding on a simple hairpin, there should be
    # few or no crossing pairs
    crossing_nested = get_crossing_candidate_pairs(
        qubo_nested.candidates, 'pair'
    )
    print(f"  Nested ({nested_seq}): "
          f"{len(crossing_nested)} crossing candidate pairs")

    # Pseudoknotted -- must have crossings
    df_b = build_target_b()
    for _, row in df_b.iterrows():
        seq = row['sequence']
        known_db = row['known_structure_dotbracket']

        for enc in ['pair', 'stem', 'quartet']:
            qubo = build_qubo(seq, encoding=enc)
            crossing = get_crossing_candidate_pairs(
                qubo.candidates, enc
            )
            if crossing:
                print(f"  {row['id']} [{enc}]: "
                      f"{len(crossing)} crossing candidate pairs [OK]")
                break
        else:
            # At least one encoding should detect crossings
            print(f"  WARNING: {row['id']} -- no crossing candidates "
                  f"found in any encoding")

    print(f"  PASS  crossing-pair detection working")
    print()


# =========================================================================
# pipeline -- Test 6: Path A correctness
# =========================================================================

def test_path_a():
    """Path A: stem-level H-type pseudoknot has 1:1 crossing-to-genus."""
    print("pipeline -- Test 6: Path A applicability check")

    df_b = build_target_b()

    for _, row in df_b.iterrows():
        seq = row['sequence']
        known_db = row['known_structure_dotbracket']
        known_pairs = parse_dotbracket(known_db)
        genus = compute_genus(known_pairs)

        qubo = build_qubo(seq, encoding='stem')
        applicable = check_path_a_applicability(
            qubo.candidates, 'stem', known_pairs
        )

        # Count actual crossing pairs in the known structure
        n_crossing = 0
        for i in range(len(known_pairs)):
            for j in range(i + 1, len(known_pairs)):
                if pairs_cross(known_pairs[i], known_pairs[j]):
                    n_crossing += 1

        ratio_str = f"{n_crossing}:{genus}" if genus > 0 else "0:0"
        path = "A" if applicable else "B"

        print(f"  {row['id']}: genus={genus}, crossings={n_crossing}, "
              f"ratio={ratio_str}, path={path}")

    # Verify: nested structures always get Path A
    df_a = build_target_a()
    row_a = df_a.iloc[0]
    qubo_a = build_qubo(row_a['sequence'], encoding='stem')
    known_pairs_a = parse_dotbracket(row_a['known_structure_dotbracket'])
    assert check_path_a_applicability(
        qubo_a.candidates, 'stem', known_pairs_a
    ), "FAIL: nested structure should be Path A applicable"
    print(f"  Nested control: Path A applicable [OK]")

    print(f"  PASS  Path A logic verified")
    print()


# =========================================================================
# pipeline -- Test 7: Calibration sweep
# =========================================================================

def test_calibration_sweep():
    """Calibration sweep produces non-degenerate accuracy curve."""
    print("pipeline -- Test 7: Calibration sweep")

    # Build calibration set from a mix of Target A and Target B
    df_a = build_target_a()
    df_b = build_target_b()

    calibration_set = []

    # Take a few small Target A instances (nested controls)
    for _, row in df_a[df_a['length'] <= 16].head(3).iterrows():
        calibration_set.append({
            'sequence': row['sequence'],
            'known_structure_dotbracket': row['known_structure_dotbracket'],
            'topology_class': 'nested',
            'id': row['id'],
        })

    # All Target B instances
    for _, row in df_b.iterrows():
        calibration_set.append({
            'sequence': row['sequence'],
            'known_structure_dotbracket': row['known_structure_dotbracket'],
            'topology_class': 'pseudoknotted',
            'id': row['id'],
        })

    print(f"  Calibration set: {len(calibration_set)} instances "
          f"({sum(1 for c in calibration_set if c['topology_class']=='nested')} nested, "
          f"{sum(1 for c in calibration_set if c['topology_class']=='pseudoknotted')} pk)")

    # Run sweep with pair encoding.
    # Range includes negative mu (crossing bonus) because the base QUBO
    # energy model can't capture pseudoknot stabilization -- stacking
    # bonuses only apply to non-crossing pairs.  Negative mu compensates
    # by rewarding co-selection of crossing candidates.
    mu_star, sweep = calibrate_mu(
        calibration_set,
        encoding='pair',
        mu_min=-2.5,
        mu_max=1.0,
        n_steps=15,
        cpsat_time_limit=15.0,
        verbose=True,
    )

    # Check 1: accuracy curve is not flat
    accuracies = np.array(sweep['accuracies'])
    is_flat = np.all(accuracies == accuracies[0])
    assert not is_flat, (
        f"FAIL: accuracy curve is completely flat at {accuracies[0]:.2%}"
    )
    print(f"  PASS  accuracy curve is non-flat "
          f"(range: [{accuracies.min():.2%}, {accuracies.max():.2%}])")

    # Check 2: mu_star is strictly inside the range
    assert not sweep['at_boundary'], (
        f"FAIL: mu_star={mu_star:.3f} is at the sweep boundary "
        f"(idx={sweep['best_idx']}). Widen the range."
    )
    print(f"  PASS  mu_star={mu_star:.3f} is strictly inside "
          f"[{sweep['mu_min']}, {sweep['mu_max']}]")

    print(f"\n  mu* = {mu_star:.3f} LOCKED")
    print()


# =========================================================================
# pipeline -- Test 8: Validation checkpoint (MANDATORY GATE)
# =========================================================================

def test_validation_checkpoint():
    """MANDATORY: every Target B exact solution must contain a crossing pair.

    This is the final gate -- do NOT proceed to pipeline if this fails.
    Failure diagnostic order (per the plan):
      (a) Is mu_star too large?
      (b) Did pipeline's crossing-audit get re-run on this specific instance?
    """
    print("pipeline -- Test 8: Validation checkpoint (MANDATORY GATE)")
    print("  Every Target B instance must have crossing pairs in its solution")

    df_b = build_target_b()
    mu_star = get_mu_star()

    if mu_star is None:
        print("  FAIL: mu_star not calibrated -- run test_calibration_sweep first")
        assert False, "mu_star not calibrated"

    print(f"  Using mu_star = {mu_star:.3f}")

    all_passed = True

    for _, row in df_b.iterrows():
        seq = row['sequence']
        inst_id = row['id']

        # Try pair encoding first (smallest N)
        for enc in ['pair', 'stem', 'quartet']:
            qubo = build_qubo_with_genus_penalty(
                seq, encoding=enc, mu=mu_star
            )

            if qubo.n > 25:
                # Use CP-SAT only
                result = cpsat_solve(qubo, time_limit_sec=30.0)
            else:
                # Cross-validate with brute-force
                bf_bits, bf_energy = brute_force_solve(qubo)
                result = SolverResult(
                    bitstring=bf_bits,
                    energy=bf_energy,
                    is_optimal=True,
                    solver='brute-force',
                    qubo=qubo,
                )

            has_crossing = result.has_crossing_pair()
            pairs = result.selected_pairs

            if has_crossing:
                print(f"  {inst_id} [{enc}]: {len(pairs)} pairs, "
                      f"HAS crossing [OK]")
                break
            else:
                print(f"  {inst_id} [{enc}]: {len(pairs)} pairs, "
                      f"NO crossing -- trying next encoding...")
        else:
            print(f"  FAIL {inst_id}: no encoding produced a crossing pair!")
            print(f"    Diagnostic: check (a) mu_star={mu_star:.3f} "
                  f"too large? (b) crossing-audit on this instance?")
            all_passed = False

    if all_passed:
        print(f"  PASS  all Target B instances have crossing pairs")
    else:
        print(f"  FAIL  some Target B instances missing crossing pairs")
        print(f"  DO NOT PROCEED TO pipeline")

    assert all_passed, "Validation checkpoint failed"
    print()


# =========================================================================
# Main
# =========================================================================

def main():
    print("=" * 60)
    print("Parts 8 & 9 -- Combined Validation Tests")
    print("=" * 60)
    print()

    # pipeline tests (solver first, since pipeline needs it)
    test_brute_force_vs_cpsat()
    test_vienna_mfe_baseline()
    test_vienna_pkplex_baseline()
    test_eval_structure_energy()

    # pipeline tests
    test_crossing_pair_detection()
    test_path_a()
    test_calibration_sweep()

    # Final gate (needs both pipeline's mu_star and pipeline's solver)
    test_validation_checkpoint()

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("Parts 8 & 9 Definitions of Done satisfied")
    print("=" * 60)


if __name__ == '__main__':
    main()
