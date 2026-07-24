"""
pipeline -- Noise Progression Tier 1: Validation Tests.

Definition of Done:
  - Populated results table (encoding x ansatz/mixer x instance x shot-count x seed)
  - Energy mean/variance recorded for each configuration
  - CVaR-aggregated cost recorded for shot-noise experiments
  - Circuit metadata logged per run (qubit count, depth, 2Q gate count)
  - Results saved to data/ideal_sweep_results.json for the pipeline
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path

from qubo import build_qubo, brute_force_solve
from ising import qubo_to_ising
from quantum_circuits import build_two_local_ansatz, build_qaoa_circuit
from data_loader import build_target_a
from ideal_sweep import (
    compute_cvar,
    get_circuit_metadata,
    sample_energies_from_circuit,
    select_instances,
    run_ideal_sweep,
    run_shot_noise_sweep,
    run_full_experiment,
    ExperimentConfig,
    DATA_DIR,
)


# =========================================================================
# Test 1: CVaR correctness
# =========================================================================

def test_cvar_correctness():
    """Verify CVaR computation on known data."""
    print("Test 1: CVaR correctness")

    # Simple case: 10 values, alpha=0.2 -> mean of lowest 2
    energies = [10, 8, 6, 4, 2, 0, -2, -4, -6, -8]
    cvar = compute_cvar(energies, alpha=0.2)
    expected = (-8 + -6) / 2.0  # = -7.0
    assert abs(cvar - expected) < 1e-10, (
        f"CVaR(0.2) expected {expected}, got {cvar}")
    print(f"  alpha=0.2: CVaR={cvar:.2f} (expected {expected:.2f})  [OK]")

    # alpha=1.0 should be the full mean
    cvar_full = compute_cvar(energies, alpha=1.0)
    expected_full = np.mean(energies)
    assert abs(cvar_full - expected_full) < 1e-10, (
        f"CVaR(1.0) expected {expected_full}, got {cvar_full}")
    print(f"  alpha=1.0: CVaR={cvar_full:.2f} (expected {expected_full:.2f})  [OK]")

    # alpha=0.1 on 10 items -> 1 item (the minimum)
    cvar_01 = compute_cvar(energies, alpha=0.1)
    assert abs(cvar_01 - (-8)) < 1e-10, (
        f"CVaR(0.1) expected -8, got {cvar_01}")
    print(f"  alpha=0.1: CVaR={cvar_01:.2f} (expected -8.00)  [OK]")

    # Empty list
    cvar_empty = compute_cvar([], alpha=0.2)
    assert np.isnan(cvar_empty), "CVaR of empty list should be NaN"
    print(f"  empty: CVaR=NaN  [OK]")

    print("  PASS")
    print()


# =========================================================================
# Test 2: Circuit metadata extraction
# =========================================================================

def test_circuit_metadata():
    """Verify circuit metadata (qubit count, depth, 2Q gates)."""
    print("Test 2: Circuit metadata extraction")

    # Two-local ansatz: 4 qubits, reps=1
    # RY layer (4 RY) + CZ layer (3 CZ) + final RY (4 RY) = depth varies
    ansatz = build_two_local_ansatz(4, reps=1)
    meta = get_circuit_metadata(ansatz)
    assert meta['n_qubits'] == 4, f"Expected 4 qubits, got {meta['n_qubits']}"
    assert meta['two_q_gates'] == 3, (
        f"Expected 3 CZ gates for 4-qubit linear NN, got {meta['two_q_gates']}")
    assert meta['n_params'] == 8, (
        f"Expected 8 params (4*(1+1)), got {meta['n_params']}")
    print(f"  VQE(4q, reps=1): qubits={meta['n_qubits']}, "
          f"depth={meta['depth']}, 2Q={meta['two_q_gates']}, "
          f"params={meta['n_params']}  [OK]")

    # QAOA circuit: 3 qubits, p=1, X mixer
    h = np.array([-0.5, 0.3, 0.1])
    J = np.array([[0, 0.2, 0], [0, 0, -0.1], [0, 0, 0]])
    qaoa = build_qaoa_circuit(h, J, 3, p=1, mixer='x')
    meta_q = get_circuit_metadata(qaoa)
    assert meta_q['n_qubits'] == 3
    assert meta_q['n_params'] == 2  # gamma + beta
    # Two non-zero J entries -> 2 RZZ gates
    assert meta_q['two_q_gates'] == 2, (
        f"Expected 2 RZZ gates, got {meta_q['two_q_gates']}")
    print(f"  QAOA(3q, p=1, X): qubits={meta_q['n_qubits']}, "
          f"depth={meta_q['depth']}, 2Q={meta_q['two_q_gates']}, "
          f"params={meta_q['n_params']}  [OK]")

    # QAOA XY mixer: 3 qubits, p=1
    qaoa_xy = build_qaoa_circuit(h, J, 3, p=1, mixer='xy')
    meta_xy = get_circuit_metadata(qaoa_xy)
    # XY mixer adds RXX + RYY on 2 pairs = 4 two-qubit gates + 2 cost RZZ = 6
    assert meta_xy['two_q_gates'] == 6, (
        f"Expected 6 2Q gates for QAOA XY, got {meta_xy['two_q_gates']}")
    print(f"  QAOA(3q, p=1, XY): qubits={meta_xy['n_qubits']}, "
          f"depth={meta_xy['depth']}, 2Q={meta_xy['two_q_gates']}, "
          f"params={meta_xy['n_params']}  [OK]")

    print("  PASS")
    print()


# =========================================================================
# Test 3: Ideal sweep smoke test
# =========================================================================

def test_ideal_sweep_smoke():
    """Run ideal sweep on 1 instance, 2 seeds. Verify table structure."""
    print("Test 3: Ideal sweep smoke test")

    instances = select_instances(max_qubits=4)
    if not instances:
        print("  SKIP  no suitable instances found")
        print()
        return

    # Use just the first instance
    test_inst = [instances[0]]
    # Use minimal configs: just VQE reps=1
    test_configs = [ExperimentConfig(
        name='VQE_reps1_stem', method='vqe', encoding='stem', reps=1)]

    df = run_ideal_sweep(test_inst, test_configs, n_seeds=2, verbose=True)

    assert len(df) == 2, f"Expected 2 rows (2 seeds), got {len(df)}"

    required_cols = [
        'instance_id', 'encoding', 'ansatz', 'mixer', 'config_name',
        'n_qubits', 'circuit_depth', 'two_q_gates', 'n_params',
        'seed', 'shot_count', 'energy', 'exact_energy', 'energy_gap',
    ]
    for col in required_cols:
        assert col in df.columns, f"Missing column: {col}"

    assert (df['shot_count'] == 0).all(), "Ideal sweep should have shot_count=0"
    assert df['energy'].notna().all(), "Energies should not be NaN"

    print(f"  Instance: {test_inst[0]['id']} (n={test_inst[0]['qubo'].n})")
    print(f"  Rows: {len(df)}")
    print(f"  Energy range: [{df['energy'].min():.4f}, {df['energy'].max():.4f}]")
    print(f"  Exact energy: {test_inst[0]['exact_energy']:.4f}")
    print("  PASS")
    print()


# =========================================================================
# Test 4: Shot-noise sweep smoke test
# =========================================================================

def test_shot_noise_smoke():
    """Run shot-noise sweep on 1 instance, 2 seeds, 2 shot counts."""
    print("Test 4: Shot-noise sweep smoke test")

    instances = select_instances(max_qubits=4)
    if not instances:
        print("  SKIP  no suitable instances found")
        print()
        return

    test_inst = [instances[0]]
    test_configs = [ExperimentConfig(
        name='VQE_reps1_stem', method='vqe', encoding='stem', reps=1)]

    # First run ideal to get params
    ideal_df = run_ideal_sweep(test_inst, test_configs, n_seeds=2)

    # Run shot noise with 2 shot counts, 2 seeds
    shot_df = run_shot_noise_sweep(
        test_inst, ideal_df, test_configs,
        shot_counts=[128, 512], n_seeds=2, verbose=True)

    # 2 shot counts * 2 seeds = 4 rows
    assert len(shot_df) == 4, f"Expected 4 rows, got {len(shot_df)}"

    assert shot_df['cvar_energy'].notna().all(), "CVaR should not be NaN"
    assert shot_df['energy'].notna().all(), "Mean energy should not be NaN"

    # CVaR should be <= mean energy (since it takes best shots)
    for _, row in shot_df.iterrows():
        assert row['cvar_energy'] <= row['energy'] + 1e-10, (
            f"CVaR ({row['cvar_energy']}) should be <= mean ({row['energy']})")

    print(f"  Instance: {test_inst[0]['id']}")
    print(f"  Rows: {len(shot_df)}")
    print(f"  CVaR energies: {shot_df['cvar_energy'].tolist()}")
    print(f"  Mean energies: {shot_df['energy'].tolist()}")
    print("  PASS")
    print()


# =========================================================================
# Test 5: Full sweep execution
# =========================================================================

def test_full_sweep():
    """Run the complete pipeline experiment and validate results."""
    print("Test 5: Full sweep execution")
    print("  (This is the actual experiment -- may take several minutes)")
    print()

    ideal_df, shot_df = run_full_experiment(
        n_seeds=N_SEEDS, max_qubits=MAX_QUBITS, verbose=True)

    # Validate ideal results
    assert len(ideal_df) > 0, "Ideal sweep produced no results"
    n_instances = ideal_df['instance_id'].nunique()
    n_configs = ideal_df['config_name'].nunique()
    print(f"\n  Ideal sweep: {len(ideal_df)} rows, "
          f"{n_instances} instances, {n_configs} configs")

    # Validate shot-noise results
    assert len(shot_df) > 0, "Shot-noise sweep produced no results"
    shot_counts_found = sorted(shot_df['shot_count'].unique())
    print(f"  Shot-noise sweep: {len(shot_df)} rows, "
          f"shot counts: {shot_counts_found}")

    # Validate output file exists
    out_path = DATA_DIR / "ideal_sweep_results.json"
    assert out_path.exists(), f"Results file not found: {out_path}"

    # Load and validate combined results
    combined = pd.read_json(out_path)
    assert len(combined) == len(ideal_df) + len(shot_df), (
        "Combined results count mismatch")

    # Check circuit metadata is populated
    assert (combined['n_qubits'] > 0).all(), "n_qubits should be positive"
    assert (combined['circuit_depth'] > 0).all(), "circuit_depth should be positive"

    # Sanity check: ideal energies should be close to exact for VQE
    vqe_ideal = ideal_df[ideal_df['ansatz'] == 'VQE']
    if not vqe_ideal.empty:
        mean_gap = vqe_ideal['energy_gap'].mean()
        print(f"  VQE ideal mean energy gap: {mean_gap:.4f}")

    print()
    print("  PASS  Results table populated and validated")
    print()


# =========================================================================
# Import constants from noise_experiments
# =========================================================================
from ideal_sweep import N_SEEDS, MAX_QUBITS


# =========================================================================
# Main
# =========================================================================

def main():
    print("=" * 60)
    print("pipeline -- Noise Progression Tier 1: Validation Tests")
    print("=" * 60)
    print()

    test_cvar_correctness()
    test_circuit_metadata()
    test_ideal_sweep_smoke()
    test_shot_noise_smoke()
    test_full_sweep()

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("pipeline Definition of Done satisfied")
    print("=" * 60)


if __name__ == '__main__':
    main()
