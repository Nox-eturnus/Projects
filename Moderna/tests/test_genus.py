"""
pipeline — Validation Tests

Mandatory validation assertions (hard-assert, not soft-check):
  1. Nested-only structure  ->  genus 0
  2. Single H-type pseudoknot  ->  genus 1
  3. Kissing hairpin (C crosses both A and B)  ->  genus 1 (NOT 2)
  4. FSE genus computation with 3_5 == 0
  5. Dataset integrity (columns, valid pairs, genus consistency, CSV round-trip)
"""

import os
import sys

from genus import (
    parse_dotbracket, pairs_cross, compute_genus,
    build_interlacement_graph, rank_gf2,
)
from data_loader import (
    build_target_a, build_target_b, build_fse_targets,
    build_all_datasets, validate_sequence_structure,
)


# ═══════════════════════════════════════════════════════════════════════════
# Mandatory genus validation (3 hard-assert cases)
# ═══════════════════════════════════════════════════════════════════════════

def test_genus_nested():
    """Nested-only: pairs (0,7), (1,6), (2,5) -> 0 crossings -> genus 0."""
    print("Test 1: Nested-only -> genus 0")
    pairs = [(0, 7), (1, 6), (2, 5)]

    # No pair should cross any other
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            assert not pairs_cross(pairs[i], pairs[j]), (
                f"  FAIL: {pairs[i]} and {pairs[j]} should NOT cross"
            )

    genus = compute_genus(pairs)
    assert genus == 0, f"  FAIL: genus = {genus}, expected 0"
    print(f"  PASS  genus = {genus}")


def test_genus_htype():
    """H-type pseudoknot: 2 helices, 1 crossing -> rank 2 -> genus 1."""
    print("Test 2: H-type pseudoknot -> genus 1")
    pairs = [(0, 10), (5, 15)]

    assert pairs_cross(pairs[0], pairs[1]), "  FAIL: pairs must cross"

    genus = compute_genus(pairs)
    assert genus == 1, f"  FAIL: genus = {genus}, expected 1"
    print(f"  PASS  genus = {genus}")


def test_genus_kissing():
    """Kissing hairpin: A=(0,10), B=(15,25), C=(5,20).

    A-B: don't cross.   A-C: cross.   B-C: cross.
    Naive counting gives 2 crossings, but GF(2) rank = 2 -> genus = 1.
    This catches the double-counting bug the master plan warns about.
    """
    print("Test 3: Kissing hairpin -> genus 1 (NOT 2)")
    A, B, C = (0, 10), (15, 25), (5, 20)

    assert not pairs_cross(A, B), "  FAIL: A and B should NOT cross"
    assert pairs_cross(A, C),     "  FAIL: A and C should cross"
    assert pairs_cross(B, C),     "  FAIL: B and C should cross"

    pairs = [A, B, C]
    adj = build_interlacement_graph(pairs)
    rank = rank_gf2(adj)
    genus = compute_genus(pairs)

    print(f"  adjacency matrix:\n{adj}")
    print(f"  GF(2) rank = {rank}")
    assert genus == 1, (
        f"  FAIL: genus = {genus}, expected 1. "
        f"If genus == 2, crossing test or GF(2) rank is wrong."
    )
    print(f"  PASS  genus = {genus} (correctly NOT 2)")


# ═══════════════════════════════════════════════════════════════════════════
# FSE genus computation
# ═══════════════════════════════════════════════════════════════════════════

def test_fse_genus():
    """Compute genus for FSE 3_5, 3_6, 3_3. Hard-assert 3_5 == 0."""
    print("Test 4: FSE genus computation")

    df_fse = build_fse_targets()
    results = {}
    for _, row in df_fse.iterrows():
        topo = row['topology_class']
        g = row['genus']
        results[topo] = g
        print(f"  {topo}: genus = {g}")

    assert results['3_5'] == 0, (
        f"  FAIL: 3_5 genus = {results['3_5']}, expected 0"
    )
    print(f"  PASS  3_5 genus = 0 (confirmed nested)")

    assert results['3_6'] >= 1, (
        f"  FAIL: 3_6 genus = {results['3_6']}, expected >= 1"
    )
    print(f"  PASS  3_6 genus = {results['3_6']} (pseudoknotted)")

    assert results['3_3'] >= 1, (
        f"  FAIL: 3_3 genus = {results['3_3']}, expected >= 1"
    )
    print(f"  PASS  3_3 genus = {results['3_3']} (pseudoknotted)")

    return results


# ═══════════════════════════════════════════════════════════════════════════
# Dataset integrity
# ═══════════════════════════════════════════════════════════════════════════

def test_dataset_integrity():
    """Verify columns, valid pairs, genus consistency, and CSV round-trip."""
    print("Test 5: Dataset integrity")

    required_cols = [
        'id', 'sequence', 'known_structure_dotbracket',
        'source', 'length', 'topology_class',
    ]

    df_a = build_target_a()
    df_b = build_target_b()
    df_fse = build_fse_targets()

    # --- columns ---
    for name, df in [('Target A', df_a), ('Target B', df_b)]:
        for col in required_cols:
            assert col in df.columns, f"  FAIL: {name} missing '{col}'"
    print("  PASS  required columns present")

    # --- valid base pairs ---
    for name, df in [('Target A', df_a), ('Target B', df_b), ('FSE', df_fse)]:
        for _, row in df.iterrows():
            validate_sequence_structure(
                row['sequence'], row['known_structure_dotbracket']
            )
    print("  PASS  all base pairs are valid WC/wobble")

    # --- Target A genus 0 ---
    for _, row in df_a.iterrows():
        pairs = parse_dotbracket(row['known_structure_dotbracket'])
        g = compute_genus(pairs)
        assert g == 0, f"  FAIL: {row['id']} genus = {g}"
    print(f"  PASS  Target A: all {len(df_a)} entries have genus 0")

    # --- Target B genus >= 1 ---
    for _, row in df_b.iterrows():
        pairs = parse_dotbracket(row['known_structure_dotbracket'])
        g = compute_genus(pairs)
        assert g >= 1, f"  FAIL: {row['id']} genus = {g}"
    print(f"  PASS  Target B: all {len(df_b)} entries have genus >= 1")

    # --- CSV round-trip ---
    output_dir = 'data'
    datasets = build_all_datasets(output_dir)
    for key, filename in [('target_a', 'target_a.csv'),
                          ('target_b', 'target_b.csv'),
                          ('fse_targets', 'fse_targets.csv')]:
        path = os.path.join(output_dir, filename)
        assert os.path.exists(path), f"  FAIL: {path} not found"
        import pandas as pd
        df_read = pd.read_csv(path)
        assert len(df_read) == len(datasets[key]), (
            f"  FAIL: {filename} row-count mismatch"
        )
    print("  PASS  CSV files written and readable")

    return datasets


# ═══════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("pipeline — Validation Tests")
    print("=" * 60)
    print()

    test_genus_nested()
    print()
    test_genus_htype()
    print()
    test_genus_kissing()
    print()
    fse_results = test_fse_genus()
    print()
    datasets = test_dataset_integrity()
    print()

    # ── Summary ──
    print("=" * 60)
    print("ALL TESTS PASSED — pipeline Definition of Done satisfied")
    print("=" * 60)
    print()
    print("Summary:")
    print(f"  Target A : {len(datasets['target_a'])} entries (all genus 0)")
    print(f"  Target B : {len(datasets['target_b'])} entries (all genus >= 1)")
    print(f"  FSE      : {len(datasets['fse_targets'])} entries")
    for topo in ('3_5', '3_6', '3_3'):
        print(f"    {topo} : genus = {fse_results[topo]}")


if __name__ == '__main__':
    main()
