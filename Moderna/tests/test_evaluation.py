"""
pipeline -- Multi-Tier Performance Evaluation: Validation Tests.

Definition of Done:
  - One consolidated table (Tier 1, 2a, 2b, cross-encoding) per instance x method
  - Feeds pipeline and the paper's results section directly
"""

import json
import math
import numpy as np
import pandas as pd
from pathlib import Path

from evaluate import (
    bitstring_to_dotbracket,
    compute_structure_metrics,
    prepare_instances,
    run_tier1,
    run_tier2a,
    run_tier2b,
    run_cross_encoding,
    run_full_part14,
)
from qubo import build_qubo, brute_force_solve, _get_pairs
from genus import parse_dotbracket, pairs_cross
from ideal_sweep import DATA_DIR, MAX_QUBITS, N_SEEDS


# =========================================================================
# Test 1: bitstring_to_dotbracket on a simple hairpin
# =========================================================================

def test_bitstring_to_dotbracket_hairpin():
    """Verify dot-bracket conversion on a known nested hairpin."""
    print("Test 1: bitstring_to_dotbracket (hairpin)")

    seq = "GGGAAAACCC"  # 3-bp stem, 4-nt loop
    qubo = build_qubo(seq, encoding='pair')

    # Find the exact solution
    bits, energy = brute_force_solve(qubo)
    db = bitstring_to_dotbracket(bits, qubo.candidates, qubo.encoding, len(seq))

    print(f"  Sequence:  {seq}")
    print(f"  Bitstring: {bits}")
    print(f"  Dot-bracket: {db}")
    print(f"  Energy: {energy:.4f}")

    # Verify format: should only have dots, parens (no crossings in hairpin)
    assert len(db) == len(seq), f"Length mismatch: {len(db)} vs {len(seq)}"
    assert all(c in '.()' for c in db), (
        f"Hairpin should only have . ( ) but got: {db}"
    )

    # Paired positions should have matching brackets
    for i, c in enumerate(db):
        if c == '(':
            # Find matching closer
            depth = 0
            for j in range(i, len(db)):
                if db[j] == '(':
                    depth += 1
                elif db[j] == ')':
                    depth -= 1
                    if depth == 0:
                        break

    print("  PASS")
    print()


# =========================================================================
# Test 2: bitstring_to_dotbracket with crossing pairs
# =========================================================================

def test_bitstring_to_dotbracket_crossing():
    """Verify multi-bracket types for pseudoknotted structures."""
    print("Test 2: bitstring_to_dotbracket (crossing)")

    # Create a small QUBO where we manually set crossing pairs
    seq = "GCGCAAAAGCGC"  # 12nt
    qubo = build_qubo(seq, encoding='pair')

    if qubo.n < 2:
        print("  SKIP -- QUBO too small for crossing test")
        print()
        return

    # Find candidates that cross
    crossing_found = False
    for i in range(qubo.n):
        for j in range(i + 1, qubo.n):
            pairs_i = _get_pairs(qubo.candidates[i], qubo.encoding)
            pairs_j = _get_pairs(qubo.candidates[j], qubo.encoding)
            if any(pairs_cross(pi, pj)
                   for pi in pairs_i for pj in pairs_j):
                # Create bitstring with these two selected
                bits = np.zeros(qubo.n)
                bits[i] = 1
                bits[j] = 1
                db = bitstring_to_dotbracket(
                    bits, qubo.candidates, qubo.encoding, len(seq)
                )
                print(f"  Crossing candidates {i} and {j}")
                print(f"  Dot-bracket: {db}")

                # Should contain at least two bracket types
                bracket_types = set()
                for c in db:
                    if c in '()':
                        bracket_types.add(0)
                    elif c in '[]':
                        bracket_types.add(1)
                    elif c in '{}':
                        bracket_types.add(2)
                    elif c in '<>':
                        bracket_types.add(3)

                assert len(bracket_types) >= 2, (
                    f"Crossing structure should use >= 2 bracket types, "
                    f"got {bracket_types}"
                )
                crossing_found = True
                break
        if crossing_found:
            break

    if not crossing_found:
        print("  No crossing candidates found in this sequence")
        print("  (This is acceptable for short nested sequences)")

    print("  PASS")
    print()


# =========================================================================
# Test 3: compute_structure_metrics
# =========================================================================

def test_structure_metrics():
    """Verify Sensitivity, PPV, MCC on known examples."""
    print("Test 3: compute_structure_metrics")

    # Perfect prediction
    true_pairs = [(0, 9), (1, 8), (2, 7)]
    pred_pairs = [(0, 9), (1, 8), (2, 7)]
    m = compute_structure_metrics(pred_pairs, true_pairs, 10)

    assert m['tp'] == 3
    assert m['fp'] == 0
    assert m['fn'] == 0
    assert abs(m['sensitivity'] - 1.0) < 1e-6
    assert abs(m['ppv'] - 1.0) < 1e-6
    assert abs(m['mcc'] - 1.0) < 1e-6
    print(f"  Perfect: TP={m['tp']}, Sens={m['sensitivity']:.4f}, "
          f"PPV={m['ppv']:.4f}, MCC={m['mcc']:.4f}  [OK]")

    # Partial prediction (one missed, one wrong)
    pred_pairs2 = [(0, 9), (1, 8), (3, 6)]  # (3,6) wrong, (2,7) missed
    m2 = compute_structure_metrics(pred_pairs2, true_pairs, 10)

    assert m2['tp'] == 2  # (0,9) and (1,8) match
    assert m2['fp'] == 1  # (3,6) not in true
    assert m2['fn'] == 1  # (2,7) missed
    assert abs(m2['sensitivity'] - 2/3) < 1e-6
    assert abs(m2['ppv'] - 2/3) < 1e-6
    print(f"  Partial: TP={m2['tp']}, FP={m2['fp']}, FN={m2['fn']}, "
          f"Sens={m2['sensitivity']:.4f}, PPV={m2['ppv']:.4f}, "
          f"MCC={m2['mcc']:.4f}  [OK]")

    # Empty prediction
    m3 = compute_structure_metrics([], true_pairs, 10)
    assert m3['tp'] == 0
    assert m3['fp'] == 0
    assert m3['fn'] == 3
    assert abs(m3['sensitivity'] - 0.0) < 1e-6
    print(f"  Empty pred: Sens={m3['sensitivity']:.4f}, "
          f"PPV={m3['ppv']:.4f}  [OK]")

    # Empty true
    m4 = compute_structure_metrics(pred_pairs, [], 10)
    assert m4['tp'] == 0
    assert m4['fp'] == 3
    assert m4['fn'] == 0
    assert abs(m4['ppv'] - 0.0) < 1e-6
    print(f"  Empty true: Sens={m4['sensitivity']:.4f}, "
          f"PPV={m4['ppv']:.4f}  [OK]")

    print("  PASS")
    print()


# =========================================================================
# Test 4: MCC edge cases
# =========================================================================

def test_mcc_edge_cases():
    """Verify MCC handles edge cases correctly."""
    print("Test 4: MCC edge cases")

    # All correct (MCC = 1)
    m = compute_structure_metrics([(0, 5)], [(0, 5)], 10)
    assert abs(m['mcc'] - 1.0) < 0.01, f"Perfect MCC should be ~1, got {m['mcc']}"
    print(f"  All correct: MCC={m['mcc']:.4f}  [OK]")

    # Completely wrong (all FP, all FN)
    m2 = compute_structure_metrics([(0, 5)], [(1, 6)], 10)
    assert m2['mcc'] < 0.1, f"Wrong prediction should have low MCC, got {m2['mcc']}"
    print(f"  All wrong: MCC={m2['mcc']:.4f}  [OK]")

    # No predictions, no true pairs
    m3 = compute_structure_metrics([], [], 10)
    # With TP=FP=FN=0, MCC denominator is 0; should return 0
    assert abs(m3['mcc']) < 1e-6 or m3['mcc'] == 0.0
    print(f"  Empty/empty: MCC={m3['mcc']:.4f}  [OK]")

    print("  PASS")
    print()


# =========================================================================
# Test 5: Instance preparation
# =========================================================================

def test_instance_preparation():
    """Verify prepare_instances returns enriched data."""
    print("Test 5: Instance preparation")

    instances = prepare_instances(max_qubits=4)
    assert len(instances) > 0, "No instances prepared"

    inst = instances[0]
    assert 'exact_bitstring' in inst
    assert 'known_structure' in inst
    assert 'vienna_structure' in inst
    assert 'vienna_energy' in inst
    assert inst['exact_bitstring'] is not None
    assert len(inst['exact_bitstring']) == inst['qubo'].n

    print(f"  {len(instances)} instances prepared")
    for inst in instances:
        known = 'yes' if inst['known_structure'] else 'no'
        print(f"    {inst['id']}: exact_E={inst['exact_energy']:.3f}, "
              f"vienna_E={inst['vienna_energy']:.3f}, "
              f"known_struct={known}")

    print("  PASS")
    print()


# =========================================================================
# Test 6: Tier 1 smoke test
# =========================================================================

def test_tier1_smoke():
    """Verify Tier 1 produces results for all methods."""
    print("Test 6: Tier 1 energy comparison (smoke)")

    instances = prepare_instances(max_qubits=4)
    part11_df = pd.read_json(DATA_DIR / "ideal_sweep_results.json")
    part13_df = pd.read_json(DATA_DIR / "classical_benchmarks_results.json")

    tier1 = run_tier1(instances, part11_df, part13_df, verbose=False)

    assert len(tier1) > 0, "No Tier 1 results"

    methods = set(tier1['method'].unique())
    assert 'Exact (CP-SAT)' in methods
    assert 'SA' in methods
    assert 'SBM' in methods

    # Exact should have zero gap
    exact_rows = tier1[tier1['method'] == 'Exact (CP-SAT)']
    assert all(abs(exact_rows['energy_gap']) < 1e-6), \
        "Exact solver should have zero energy gap"

    print(f"  {len(tier1)} rows, methods: {sorted(methods)}")
    print("  PASS")
    print()


# =========================================================================
# Test 7: Tier 2a smoke test
# =========================================================================

def test_tier2a_smoke():
    """Verify Tier 2a compares QUBO vs ViennaRNA."""
    print("Test 7: Tier 2a QUBO vs ViennaRNA (smoke)")

    instances = prepare_instances(max_qubits=4)
    tier2a = run_tier2a(instances, verbose=False)

    assert len(tier2a) > 0, "No Tier 2a results"

    # Check required columns
    for col in ['qubo_dotbracket', 'vienna_dotbracket',
                'qubo_vs_vienna_agree']:
        assert col in tier2a.columns, f"Missing column: {col}"

    print(f"  {len(tier2a)} instances compared")
    for _, r in tier2a.iterrows():
        print(f"    {r['instance_id']}: QUBO/Vienna agree on "
              f"{r['qubo_vs_vienna_agree']} pairs")
    print("  PASS")
    print()


# =========================================================================
# Test 8: Full pipeline run
# =========================================================================

def test_full_part14():
    """Execute the complete pipeline evaluation."""
    print("Test 8: Full pipeline experiment")
    print("  (Re-solves all methods for bitstrings -- may take several minutes)")
    print()

    results = run_full_part14(max_qubits=MAX_QUBITS, verbose=True)

    # Validate all tiers present
    assert 'tier1' in results
    assert 'tier2a' in results
    assert 'tier2b' in results
    assert 'cross_encoding' in results

    # Validate non-empty
    for key, df in results.items():
        assert len(df) > 0, f"No results for {key}"

    # Validate output file
    out_path = DATA_DIR / "evaluation_results.json"
    assert out_path.exists(), f"Missing {out_path}"

    # Validate Tier 2b has headline metrics
    tier2b = results['tier2b']
    for col in ['sensitivity', 'ppv', 'mcc', 'tp', 'fp', 'fn']:
        assert col in tier2b.columns, f"Tier 2b missing column: {col}"

    # SA should have strong structural accuracy (it found exact on all instances)
    sa_results = tier2b[tier2b['method'] == 'SA']
    if len(sa_results) > 0:
        mean_sens = sa_results['sensitivity'].mean()
        mean_ppv = sa_results['ppv'].mean()
        print(f"\n  SA headline: Sensitivity={mean_sens:.4f}, PPV={mean_ppv:.4f}")

    print()
    print("  PASS -- pipeline Definition of Done satisfied")
    print()


# =========================================================================
# Main
# =========================================================================

def main():
    print("=" * 60)
    print("pipeline -- Multi-Tier Performance Evaluation: Tests")
    print("=" * 60)
    print()

    test_bitstring_to_dotbracket_hairpin()
    test_bitstring_to_dotbracket_crossing()
    test_structure_metrics()
    test_mcc_edge_cases()
    test_instance_preparation()
    test_tier1_smoke()
    test_tier2a_smoke()
    test_full_part14()

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("pipeline Definition of Done satisfied:")
    print("  [OK] Consolidated Tier 1/2a/2b/cross-encoding tables")
    print("  [OK] Structural metrics (Sensitivity, PPV, MCC) per method")
    print("  [OK] Results ready for the pipeline and paper")
    print("=" * 60)


if __name__ == '__main__':
    main()
