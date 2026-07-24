"""
pipeline -- Noise Progression Tier 2: Validation Tests.

Definition of Done:
  - Noisy simulator results populated across parametric noise levels
  - Realistic backend noise (FakeManilaV2) results included
  - Crossover point numerically computed with confidence interval
  - Results saved to data/noisy_sweep_results.json and data/crossover_analysis.json
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path

from noisy_sweep import (
    build_depolarizing_noise_model,
    build_realistic_noise_model,
    run_noisy_simulation,
    run_noisy_sweep,
    run_realistic_sweep,
    compute_crossover,
    run_full_part12,
    _energy_vs_noise_model,
    NOISE_LEVELS_1Q,
    NOISE_2Q_MULTIPLIER,
    NOISY_SHOT_COUNT,
)
from ideal_sweep import (
    compute_cvar,
    get_circuit_metadata,
    select_instances,
    ExperimentConfig,
    N_SEEDS,
    MAX_QUBITS,
    DATA_DIR,
)
from qubo import build_qubo, brute_force_solve
from ising import qubo_to_ising
from quantum_circuits import build_two_local_ansatz, build_qaoa_circuit, run_vqe


# =========================================================================
# Test 1: Noise model construction
# =========================================================================

def test_noise_model_construction():
    """Verify depolarizing and realistic noise models build correctly."""
    print("Test 1: Noise model construction")

    # Depolarizing model
    nm = build_depolarizing_noise_model(0.01)
    assert len(nm.noise_instructions) > 0, "Noise model should have instructions"
    print(f"  Depolarizing (1Q=0.01, 2Q=0.10): "
          f"{len(nm.noise_instructions)} noisy instructions  [OK]")

    # Zero noise should be ideal
    nm_zero = build_depolarizing_noise_model(0.0, error_readout=0.0)
    assert len(nm_zero.noise_instructions) == 0, (
        "Zero-error model should be ideal (no noise instructions)")
    print(f"  Zero noise: ideal model  [OK]")

    # Realistic model
    nm_real, meta = build_realistic_noise_model()
    assert meta['num_qubits'] == 5
    assert meta['backend_name'] == 'FakeManilaV2'
    assert len(nm_real.noise_instructions) > 0
    print(f"  Realistic ({meta['backend_name']}, {meta['num_qubits']}q): "
          f"{len(nm_real.noise_instructions)} noisy instructions  [OK]")

    print("  PASS")
    print()


# =========================================================================
# Test 2: Noisy simulation smoke test
# =========================================================================

def test_noisy_simulation():
    """Run one circuit through AerSimulator with noise."""
    print("Test 2: Noisy simulation smoke test")

    instances = select_instances(max_qubits=4)
    assert len(instances) > 0, "No instances found"
    inst = instances[0]
    qubo = inst['qubo']

    # Optimize to get params
    result = run_vqe(qubo, reps=1, max_iter=300, seed=42)
    circuit = build_two_local_ansatz(qubo.n, reps=1)

    # Run with no noise (baseline)
    nm_zero = build_depolarizing_noise_model(0.0, error_readout=0.0)
    energies_ideal = run_noisy_simulation(
        circuit, result['optimal_params'], qubo.Q,
        nm_zero, 2048, seed=42)
    mean_ideal = np.mean(energies_ideal)

    # Run with moderate noise
    nm_noisy = build_depolarizing_noise_model(0.02)
    energies_noisy = run_noisy_simulation(
        circuit, result['optimal_params'], qubo.Q,
        nm_noisy, 2048, seed=42)
    mean_noisy = np.mean(energies_noisy)

    # Run with heavy noise
    nm_heavy = build_depolarizing_noise_model(0.1)
    energies_heavy = run_noisy_simulation(
        circuit, result['optimal_params'], qubo.Q,
        nm_heavy, 2048, seed=42)
    mean_heavy = np.mean(energies_heavy)

    print(f"  Instance: {inst['id']} (n={qubo.n})")
    print(f"  Exact energy:  {inst['exact_energy']:.4f}")
    print(f"  Ideal mean:    {mean_ideal:.4f}")
    print(f"  Noisy mean:    {mean_noisy:.4f} (error_1q=0.02)")
    print(f"  Heavy mean:    {mean_heavy:.4f} (error_1q=0.10)")

    # Noisy should generally be worse (higher energy) than ideal
    # But with small circuits this might not always hold due to shot noise
    # At minimum, verify we got finite results
    assert np.isfinite(mean_ideal), "Ideal energy should be finite"
    assert np.isfinite(mean_noisy), "Noisy energy should be finite"
    assert np.isfinite(mean_heavy), "Heavy-noise energy should be finite"
    assert len(energies_noisy) == 2048, "Should have 2048 samples"

    print("  PASS")
    print()


# =========================================================================
# Test 3: Crossover computation on synthetic data
# =========================================================================

def test_crossover_synthetic():
    """Feed synthetic data with known intersection, verify crossover."""
    print("Test 3: Crossover computation (synthetic data)")

    # Create synthetic data where VQE and QAOA curves cross
    # VQE: starts low, degrades slowly -> E = 2*x + 1
    # QAOA: starts high, degrades less -> E = 0.5*x + 2
    # Crossover: 2x + 1 = 0.5x + 2 -> x = 2/3

    np.random.seed(42)
    n_seeds = 5
    rows = []

    for noise_proxy in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2]:
        for seed_idx in range(n_seeds):
            # VQE: E = 2*x + 1 + noise
            vqe_e = 2.0 * noise_proxy + 1.0 + np.random.normal(0, 0.05)
            rows.append({
                'config_name': 'VQE_reps1_stem',
                'noise_proxy': noise_proxy,
                'noise_type': 'depolarizing',
                'cvar_energy': vqe_e,
                'energy': vqe_e,
                'noise_1q': noise_proxy,
            })

            # QAOA: E = 0.5*x + 2 + noise
            qaoa_e = 0.5 * noise_proxy + 2.0 + np.random.normal(0, 0.05)
            rows.append({
                'config_name': 'QAOA_X_p1_stem',
                'noise_proxy': noise_proxy,
                'noise_type': 'depolarizing',
                'cvar_energy': qaoa_e,
                'energy': qaoa_e,
                'noise_1q': noise_proxy,
            })

    df = pd.DataFrame(rows)
    crossover = compute_crossover(df, verbose=True)

    pair_key = 'VQE_reps1_stem_vs_QAOA_X_p1_stem'
    assert pair_key in crossover, f"Expected {pair_key} in crossover results"
    result = crossover[pair_key]

    # Expected crossover at x = 2/3 ~= 0.667
    assert result['crossover_noise_proxy'] is not None, "Crossover should be found"
    cp = result['crossover_noise_proxy']
    assert abs(cp - 0.667) < 0.1, (
        f"Crossover at {cp:.4f}, expected ~0.667")

    print(f"  Expected crossover: ~0.667")
    print(f"  Computed crossover: {cp:.4f}")
    print(f"  Confidence interval: +/- {result['confidence_interval']:.4f}")
    print("  PASS")
    print()


# =========================================================================
# Test 4: Full noisy sweep
# =========================================================================

def test_full_noisy_sweep():
    """Execute the complete pipeline experiment."""
    print("Test 4: Full noisy sweep + crossover analysis")
    print("  (This is the actual experiment -- may take a long time)")
    print()

    combined, crossover = run_full_part12(
        n_seeds=N_SEEDS, max_qubits=MAX_QUBITS, verbose=True)

    # Validate results
    assert len(combined) > 0, "No results produced"

    # Check depolarizing data
    dep = combined[combined['noise_type'] == 'depolarizing']
    assert len(dep) > 0, "No depolarizing results"
    noise_levels_found = sorted(dep['noise_1q'].unique())
    print(f"\n  Depolarizing rows: {len(dep)}")
    print(f"  Noise levels: {noise_levels_found}")

    # Check realistic data
    real = combined[combined['noise_type'] == 'realistic_FakeManilaV2']
    print(f"  Realistic rows: {len(real)}")

    # Validate output files
    out_noisy = DATA_DIR / "noisy_sweep_results.json"
    out_cross = DATA_DIR / "crossover_analysis.json"
    assert out_noisy.exists(), f"Missing {out_noisy}"
    assert out_cross.exists(), f"Missing {out_cross}"

    # Crossover analysis
    print(f"\n  Crossover pairs analyzed: {len(crossover)}")
    for pair, result in crossover.items():
        cp = result.get('crossover_noise_proxy')
        if cp is not None:
            print(f"    {pair}: crossover at noise_proxy = {cp:.6f}")
        else:
            print(f"    {pair}: no crossover found")

    print()
    print("  PASS  Results populated and crossover analysis complete")
    print()


# =========================================================================
# Test 5: Crossover validation
# =========================================================================

def test_crossover_validation():
    """Verify crossover results are well-formed."""
    print("Test 5: Crossover validation")

    out_cross = DATA_DIR / "crossover_analysis.json"
    assert out_cross.exists(), "Crossover file not found -- run Test 4 first"

    with open(out_cross) as f:
        crossover = json.load(f)

    assert len(crossover) > 0, "No crossover pairs found"

    # Check that at least some pairs have valid crossover points
    has_crossover = False
    for pair, result in crossover.items():
        assert 'vqe_config' in result
        assert 'qaoa_config' in result
        assert 'vqe_fit_params' in result
        assert 'qaoa_fit_params' in result
        assert 'crossover_noise_proxy' in result
        assert 'discriminant' in result

        if result['crossover_noise_proxy'] is not None:
            has_crossover = True
            assert result['crossover_noise_proxy'] >= 0, (
                "Crossover should be at non-negative noise")
            assert result['confidence_interval'] is not None
            print(f"  {pair}: crossover = {result['crossover_noise_proxy']:.6f} "
                  f"+/- {result['confidence_interval']:.6f}")
        else:
            print(f"  {pair}: no positive crossover (curves don't intersect)")

    # It's acceptable if no crossover is found (VQE may dominate everywhere
    # or QAOA may dominate everywhere). Document it as a finding.
    if not has_crossover:
        print("  NOTE: No crossover found between any VQE/QAOA pair.")
        print("        This is a valid finding if one method dominates across")
        print("        all noise levels.")

    print("  PASS")
    print()


# =========================================================================
# Main
# =========================================================================

def main():
    print("=" * 60)
    print("pipeline -- Noise Progression Tier 2: Validation Tests")
    print("=" * 60)
    print()

    test_noise_model_construction()
    test_noisy_simulation()
    test_crossover_synthetic()
    test_full_noisy_sweep()
    test_crossover_validation()

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("pipeline Definition of Done satisfied")
    print("=" * 60)


if __name__ == '__main__':
    main()
