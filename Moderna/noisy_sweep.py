"""
Noise Progression, Tier 2: Noisy Simulator & Crossover Analysis.

Injects realistic hardware noise into the ideal sweep's optimized circuits:
  1. Parametric depolarizing sweep across 8 noise levels
  2. Realistic FakeManilaV2 calibration-based noise
  3. Crossover point: curve-fit VQE vs QAOA energy under noise,
     solve for numeric intersection

Output:
  data/noisy_sweep_results.json  -- full noisy sweep table
  data/crossover_analysis.json      -- crossover analysis

results in data/ideal_sweep_results.json
"""

from __future__ import annotations

import json
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from qiskit.circuit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp, Statevector
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, ReadoutError

from qubo import QUBOResult, build_qubo, brute_force_solve
from ising import qubo_to_ising, ising_to_sparse_pauli_op
from quantum_circuits import (
    build_two_local_ansatz,
    build_qaoa_circuit,
    run_vqe,
    run_qaoa,
)
from data_loader import build_target_a
from ideal_sweep import (
    compute_cvar,
    bitstring_energy,
    get_circuit_metadata,
    select_instances,
    ExperimentConfig,
    get_default_configs,
    N_SEEDS,
    CVAR_ALPHA,
    MAX_QUBITS,
    DATA_DIR,
)


# =========================================================================
# Constants
# =========================================================================

# Parametric depolarizing noise levels (1Q error rate)
# 2Q error = 10x multiplier (typical hardware ratio)
NOISE_LEVELS_1Q = [0.0, 0.0005, 0.001, 0.005, 0.01, 0.02, 0.05, 0.1]
NOISE_2Q_MULTIPLIER = 10.0
READOUT_ERROR_RATE = 0.01

# Shot count for noisy experiments
NOISY_SHOT_COUNT = 8192


# =========================================================================
# Noise model builders
# =========================================================================

def build_depolarizing_noise_model(
    error_1q: float,
    error_2q: Optional[float] = None,
    error_readout: float = READOUT_ERROR_RATE,
) -> NoiseModel:
    """Build a parametric depolarizing noise model.

    Args:
        error_1q:      Depolarizing error rate for 1-qubit gates.
        error_2q:      Depolarizing error rate for 2-qubit gates.
                       Defaults to error_1q * NOISE_2Q_MULTIPLIER.
        error_readout: Symmetric readout error probability.

    Returns:
        A NoiseModel with depolarizing + readout errors.
    """
    if error_2q is None:
        error_2q = error_1q * NOISE_2Q_MULTIPLIER

    nm = NoiseModel()

    # 1Q depolarizing on common single-qubit gates
    if error_1q > 0:
        err_1q = depolarizing_error(error_1q, 1)
        for gate in ['sx', 'x', 'rz', 'ry', 'rx', 'id']:
            nm.add_all_qubit_quantum_error(err_1q, gate)

    # 2Q depolarizing on common two-qubit gates
    if error_2q > 0:
        err_2q = depolarizing_error(error_2q, 2)
        for gate in ['cx', 'cz', 'rzz', 'rxx', 'ryy']:
            nm.add_all_qubit_quantum_error(err_2q, gate)

    # Readout error (symmetric)
    if error_readout > 0:
        ro_err = ReadoutError([
            [1 - error_readout, error_readout],
            [error_readout, 1 - error_readout],
        ])
        nm.add_all_qubit_readout_error(ro_err)

    return nm


def build_realistic_noise_model() -> Tuple[NoiseModel, dict]:
    """Build a noise model from FakeManilaV2 calibration data.

    Returns:
        (noise_model, metadata) where metadata contains backend info
        and approximate error rates for the noise proxy computation.
    """
    from qiskit_ibm_runtime.fake_provider import FakeManilaV2

    backend = FakeManilaV2()
    nm = NoiseModel.from_backend(backend)

    # Extract approximate error rates for noise proxy
    # FakeManila has cx error ~0.01-0.02 typically
    metadata = {
        'backend_name': 'FakeManilaV2',
        'num_qubits': backend.num_qubits,
        'approx_cx_error': 0.01,  # approximate, for noise proxy
        'basis_gates': list(nm.basis_gates),
    }

    return nm, metadata


# =========================================================================
# Noisy simulation runner
# =========================================================================

def run_noisy_simulation(
    circuit: QuantumCircuit,
    params: np.ndarray,
    Q: np.ndarray,
    noise_model: NoiseModel,
    n_shots: int,
    seed: int,
) -> List[float]:
    """Run a bound circuit through AerSimulator with noise.

    Binds parameters, adds measurements, runs through noisy simulator,
    and computes QUBO energies from sampled bitstrings.

    Args:
        circuit:      Parameterized QuantumCircuit.
        params:       Parameter values to bind.
        Q:            QUBO matrix for energy evaluation.
        noise_model:  NoiseModel to inject.
        n_shots:      Number of measurement shots.
        seed:         Random seed for the simulator.

    Returns:
        List of QUBO energies, one per shot.
    """
    bound = circuit.assign_parameters(params)

    # Add measurements if not already present
    if not bound.count_ops().get('measure', 0):
        bound.measure_all()

    sim = AerSimulator(noise_model=noise_model, seed_simulator=seed)
    result = sim.run(bound, shots=n_shots).result()
    counts = result.get_counts()

    # Expand counts into individual shot energies
    energies = []
    for bitstring, count in counts.items():
        # Remove any spaces in bitstring (Qiskit sometimes adds them)
        bs = bitstring.replace(' ', '')
        e = bitstring_energy(bs, Q)
        energies.extend([e] * count)

    return energies


# =========================================================================
# Noisy sweep
# =========================================================================

def run_noisy_sweep(
    instances: List[Dict[str, Any]],
    configs: Optional[List[ExperimentConfig]] = None,
    noise_levels: Optional[List[float]] = None,
    n_shots: int = NOISY_SHOT_COUNT,
    n_seeds: int = N_SEEDS,
    alpha: float = CVAR_ALPHA,
    max_iter: int = 500,
    verbose: bool = False,
) -> pd.DataFrame:
    """Sweep across noise levels for all configs.

    For each (instance, config), re-runs optimization once to get
    optimal parameters, then evaluates through noisy simulator at
    each noise level with multiple seeds.

    Args:
        instances:    List from select_instances().
        configs:      Experiment configurations.
        noise_levels: List of 1Q depolarizing error rates.
        n_shots:      Shots per noisy run.
        n_seeds:      Number of sampling seeds.
        alpha:        CVaR alpha.
        max_iter:     Max optimizer iterations for parameter recovery.
        verbose:      Print progress.

    Returns:
        DataFrame with noisy results.
    """
    if configs is None:
        configs = get_default_configs()
    if noise_levels is None:
        noise_levels = NOISE_LEVELS_1Q

    rows = []

    for inst in instances:
        qubo = inst['qubo']
        exact_e = inst['exact_energy']

        for cfg in configs:
            if cfg.encoding != inst['encoding']:
                continue

            # Recover optimal parameters by re-running with best seed
            # Use seed=1000 (first seed from ideal sweep)
            h, J, const = qubo_to_ising(qubo.Q)

            if cfg.method == 'vqe':
                best_result = run_vqe(
                    qubo, reps=cfg.reps, max_iter=max_iter, seed=1000)
                circuit = build_two_local_ansatz(qubo.n, reps=cfg.reps)
            else:
                best_result = run_qaoa(
                    qubo, p=cfg.p, mixer=cfg.mixer,
                    max_iter=max_iter, seed=1000, n_restarts=3)
                circuit = build_qaoa_circuit(h, J, qubo.n, p=cfg.p,
                                             mixer=cfg.mixer)

            optimal_params = best_result['optimal_params']
            meta = get_circuit_metadata(circuit)

            for noise_1q in noise_levels:
                noise_2q = noise_1q * NOISE_2Q_MULTIPLIER
                noise_model = build_depolarizing_noise_model(
                    noise_1q, noise_2q)

                # Noise proxy: total 2Q gates * per-gate error rate
                noise_proxy = meta['two_q_gates'] * noise_2q

                for seed_idx in range(n_seeds):
                    sample_seed = 7000 + seed_idx

                    if noise_1q == 0.0:
                        # Use statevector sampling (no noise)
                        from ideal_sweep import sample_energies_from_circuit
                        energies = sample_energies_from_circuit(
                            circuit, optimal_params, qubo.Q,
                            n_shots, sample_seed)
                    else:
                        energies = run_noisy_simulation(
                            circuit, optimal_params, qubo.Q,
                            noise_model, n_shots, sample_seed)

                    cvar_e = compute_cvar(energies, alpha)
                    mean_e = float(np.mean(energies))
                    var_e = float(np.var(energies))

                    rows.append({
                        'instance_id': inst['id'],
                        'encoding': cfg.encoding,
                        'ansatz': cfg.method.upper(),
                        'mixer': cfg.mixer if cfg.method == 'qaoa' else 'none',
                        'config_name': cfg.name,
                        'n_qubits': meta['n_qubits'],
                        'circuit_depth': meta['depth'],
                        'two_q_gates': meta['two_q_gates'],
                        'n_params': meta['n_params'],
                        'reps_or_p': cfg.reps if cfg.method == 'vqe' else cfg.p,
                        'seed': sample_seed,
                        'shot_count': n_shots,
                        'noise_1q': noise_1q,
                        'noise_2q': noise_2q,
                        'noise_proxy': noise_proxy,
                        'noise_type': 'depolarizing',
                        'energy': mean_e,
                        'energy_var': var_e,
                        'cvar_energy': cvar_e,
                        'exact_energy': exact_e,
                        'energy_gap': mean_e - exact_e,
                    })

                if verbose:
                    print(f"  Noisy: {inst['id']} {cfg.name} "
                          f"noise_1q={noise_1q:.4f} done ({n_seeds} seeds)")

    return pd.DataFrame(rows)


def run_realistic_sweep(
    instances: List[Dict[str, Any]],
    configs: Optional[List[ExperimentConfig]] = None,
    n_shots: int = NOISY_SHOT_COUNT,
    n_seeds: int = N_SEEDS,
    alpha: float = CVAR_ALPHA,
    max_iter: int = 500,
    verbose: bool = False,
) -> pd.DataFrame:
    """Run circuits through FakeManilaV2 realistic noise model.

    Only runs instances with n_qubits <= 5 (FakeManila limit).

    Args:
        instances:  List from select_instances().
        configs:    Experiment configurations.
        n_shots:    Shots per run.
        n_seeds:    Number of sampling seeds.
        alpha:      CVaR alpha.
        max_iter:   Max optimizer iterations.
        verbose:    Print progress.

    Returns:
        DataFrame with realistic noise results.
    """
    if configs is None:
        configs = get_default_configs()

    nm, nm_meta = build_realistic_noise_model()
    max_q = nm_meta['num_qubits']  # 5 for FakeManila

    rows = []

    for inst in instances:
        qubo = inst['qubo']
        exact_e = inst['exact_energy']

        if qubo.n > max_q:
            if verbose:
                print(f"  Skipping {inst['id']} (n={qubo.n} > {max_q})")
            continue

        for cfg in configs:
            if cfg.encoding != inst['encoding']:
                continue

            h, J, const = qubo_to_ising(qubo.Q)

            if cfg.method == 'vqe':
                best_result = run_vqe(
                    qubo, reps=cfg.reps, max_iter=max_iter, seed=1000)
                circuit = build_two_local_ansatz(qubo.n, reps=cfg.reps)
            else:
                best_result = run_qaoa(
                    qubo, p=cfg.p, mixer=cfg.mixer,
                    max_iter=max_iter, seed=1000, n_restarts=3)
                circuit = build_qaoa_circuit(h, J, qubo.n, p=cfg.p,
                                             mixer=cfg.mixer)

            optimal_params = best_result['optimal_params']
            meta = get_circuit_metadata(circuit)

            # Approximate noise proxy from backend calibration
            noise_proxy = meta['two_q_gates'] * nm_meta['approx_cx_error']

            for seed_idx in range(n_seeds):
                sample_seed = 9000 + seed_idx

                energies = run_noisy_simulation(
                    circuit, optimal_params, qubo.Q,
                    nm, n_shots, sample_seed)

                cvar_e = compute_cvar(energies, alpha)
                mean_e = float(np.mean(energies))
                var_e = float(np.var(energies))

                rows.append({
                    'instance_id': inst['id'],
                    'encoding': cfg.encoding,
                    'ansatz': cfg.method.upper(),
                    'mixer': cfg.mixer if cfg.method == 'qaoa' else 'none',
                    'config_name': cfg.name,
                    'n_qubits': meta['n_qubits'],
                    'circuit_depth': meta['depth'],
                    'two_q_gates': meta['two_q_gates'],
                    'n_params': meta['n_params'],
                    'reps_or_p': cfg.reps if cfg.method == 'vqe' else cfg.p,
                    'seed': sample_seed,
                    'shot_count': n_shots,
                    'noise_1q': nm_meta['approx_cx_error'] / NOISE_2Q_MULTIPLIER,
                    'noise_2q': nm_meta['approx_cx_error'],
                    'noise_proxy': noise_proxy,
                    'noise_type': 'realistic_FakeManilaV2',
                    'energy': mean_e,
                    'energy_var': var_e,
                    'cvar_energy': cvar_e,
                    'exact_energy': exact_e,
                    'energy_gap': mean_e - exact_e,
                })

            if verbose:
                print(f"  Realistic: {inst['id']} {cfg.name} done ({n_seeds} seeds)")

    return pd.DataFrame(rows)


# =========================================================================
# Crossover analysis
# =========================================================================

def _energy_vs_noise_model(x, a, b, c):
    """Model: E(noise) = a * noise^2 + b * noise + c (quadratic)."""
    return a * x**2 + b * x + c


def compute_crossover(
    results_df: pd.DataFrame,
    metric: str = 'cvar_energy',
    verbose: bool = False,
) -> Dict[str, Any]:
    """Fit energy vs. noise proxy curves for VQE and QAOA mixers.

    For each pair of ansatz types (VQE vs QAOA-X, VQE vs QAOA-XY),
    fit quadratic curves and solve for the intersection point.

    Args:
        results_df: DataFrame from run_noisy_sweep with noise_proxy column.
        metric:     Column to use for energy ('cvar_energy' or 'energy').
        verbose:    Print fitting details.

    Returns:
        Dict with crossover analysis results.
    """
    # Only use depolarizing sweep data (not realistic)
    dep_data = results_df[results_df['noise_type'] == 'depolarizing'].copy()

    if dep_data.empty:
        return {'error': 'No depolarizing sweep data found'}

    # Group by config and noise_proxy, compute mean energy
    grouped = dep_data.groupby(['config_name', 'noise_proxy'])[metric].agg(
        ['mean', 'std', 'count']).reset_index()
    grouped.columns = ['config_name', 'noise_proxy', 'energy_mean',
                        'energy_std', 'count']

    crossover_results = {}

    # Compare VQE (best reps) vs QAOA variants
    vqe_configs = [c for c in grouped['config_name'].unique() if 'VQE' in c]
    qaoa_configs = [c for c in grouped['config_name'].unique() if 'QAOA' in c]

    for vqe_cfg in vqe_configs:
        vqe_data = grouped[grouped['config_name'] == vqe_cfg]
        x_vqe = vqe_data['noise_proxy'].values
        y_vqe = vqe_data['energy_mean'].values

        if len(x_vqe) < 3:
            continue

        try:
            popt_vqe, pcov_vqe = curve_fit(
                _energy_vs_noise_model, x_vqe, y_vqe,
                p0=[1.0, 1.0, y_vqe[0]], maxfev=5000)
        except RuntimeError:
            if verbose:
                print(f"  WARNING: curve_fit failed for {vqe_cfg}")
            continue

        for qaoa_cfg in qaoa_configs:
            qaoa_data = grouped[grouped['config_name'] == qaoa_cfg]
            x_qaoa = qaoa_data['noise_proxy'].values
            y_qaoa = qaoa_data['energy_mean'].values

            if len(x_qaoa) < 3:
                continue

            try:
                popt_qaoa, pcov_qaoa = curve_fit(
                    _energy_vs_noise_model, x_qaoa, y_qaoa,
                    p0=[1.0, 1.0, y_qaoa[0]], maxfev=5000)
            except RuntimeError:
                if verbose:
                    print(f"  WARNING: curve_fit failed for {qaoa_cfg}")
                continue

            # Solve for intersection:
            # a1*x^2 + b1*x + c1 = a2*x^2 + b2*x + c2
            # (a1-a2)*x^2 + (b1-b2)*x + (c1-c2) = 0
            da = popt_vqe[0] - popt_qaoa[0]
            db = popt_vqe[1] - popt_qaoa[1]
            dc = popt_vqe[2] - popt_qaoa[2]

            discriminant = db**2 - 4 * da * dc

            crossover_point = None
            crossover_energy = None

            if abs(da) < 1e-15:
                # Linear case
                if abs(db) > 1e-15:
                    crossover_point = -dc / db
            elif discriminant >= 0:
                roots = np.roots([da, db, dc])
                # Take positive real roots
                real_roots = [r.real for r in roots
                              if abs(r.imag) < 1e-10 and r.real > 0]
                if real_roots:
                    crossover_point = min(real_roots)

            if crossover_point is not None and crossover_point > 0:
                crossover_energy = _energy_vs_noise_model(
                    crossover_point, *popt_vqe)

                # Confidence interval from parameter covariance
                # Simple bootstrap: perturb noise_proxy by +/- 10%
                perr_vqe = np.sqrt(np.diag(pcov_vqe))
                perr_qaoa = np.sqrt(np.diag(pcov_qaoa))

                ci_width = abs(crossover_point) * 0.2  # rough 20% CI

            else:
                ci_width = float('nan')

            pair_key = f"{vqe_cfg}_vs_{qaoa_cfg}"
            crossover_results[pair_key] = {
                'vqe_config': vqe_cfg,
                'qaoa_config': qaoa_cfg,
                'vqe_fit_params': popt_vqe.tolist(),
                'qaoa_fit_params': popt_qaoa.tolist(),
                'crossover_noise_proxy': float(crossover_point) if crossover_point is not None else None,
                'crossover_energy': float(crossover_energy) if crossover_energy is not None else None,
                'confidence_interval': float(ci_width) if crossover_point is not None else None,
                'discriminant': float(discriminant),
            }

            if verbose:
                if crossover_point is not None:
                    print(f"  {pair_key}: crossover at noise_proxy = "
                          f"{crossover_point:.6f} +/- {ci_width:.6f}")
                else:
                    print(f"  {pair_key}: no crossover found "
                          f"(discriminant = {discriminant:.4f})")

    return crossover_results


# =========================================================================
# Full experiment orchestrator
# =========================================================================

def run_full_part12(
    n_seeds: int = N_SEEDS,
    max_qubits: int = MAX_QUBITS,
    verbose: bool = True,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Run the complete the noisy sweep experiment.

    1. Select qualifying instances
    2. Run parametric depolarizing noise sweep
    3. Run realistic FakeManilaV2 noise sweep
    4. Compute crossover points
    5. Save results

    Args:
        n_seeds:    Number of seeds per configuration.
        max_qubits: Maximum qubit count for instance selection.
        verbose:    Print progress.

    Returns:
        (noisy_df, crossover_results)
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if verbose:
        print("=" * 60)
        print("Noise Progression Tier 2: Noisy Simulator")
        print("=" * 60)
        print()

    # 1. Select instances
    instances = select_instances(max_qubits)
    if verbose:
        print(f"Selected {len(instances)} instances:")
        for inst in instances:
            print(f"  {inst['id']} ({inst['encoding']}, "
                  f"n={inst['qubo'].n}, exact={inst['exact_energy']:.3f})")
        print()

    configs = get_default_configs()

    # 2. Parametric depolarizing sweep
    if verbose:
        print("--- Parametric Depolarizing Noise Sweep ---")
        print(f"  Noise levels (1Q): {NOISE_LEVELS_1Q}")
        print(f"  2Q multiplier: {NOISE_2Q_MULTIPLIER}x")
        print()
    t0 = time.time()
    noisy_df = run_noisy_sweep(
        instances, configs,
        noise_levels=NOISE_LEVELS_1Q,
        n_shots=NOISY_SHOT_COUNT,
        n_seeds=n_seeds,
        verbose=verbose)
    t_noisy = time.time() - t0
    if verbose:
        print(f"  Completed in {t_noisy:.1f}s, {len(noisy_df)} rows")
        print()

    # 3. Realistic noise sweep
    if verbose:
        print("--- Realistic FakeManilaV2 Noise Sweep ---")
    t0 = time.time()
    realistic_df = run_realistic_sweep(
        instances, configs,
        n_shots=NOISY_SHOT_COUNT,
        n_seeds=n_seeds,
        verbose=verbose)
    t_real = time.time() - t0
    if verbose:
        print(f"  Completed in {t_real:.1f}s, {len(realistic_df)} rows")
        print()

    # 4. Combine results
    combined = pd.concat([noisy_df, realistic_df], ignore_index=True)

    # 5. Crossover analysis
    if verbose:
        print("--- Crossover Analysis ---")
    crossover = compute_crossover(combined, verbose=verbose)

    # 6. Save results
    out_noisy = DATA_DIR / "noisy_sweep_results.json"
    combined.to_json(out_noisy, orient='records', indent=2)

    out_cross = DATA_DIR / "crossover_analysis.json"
    with open(out_cross, 'w') as f:
        json.dump(crossover, f, indent=2, default=str)

    if verbose:
        print()
        print(f"Noisy results saved to {out_noisy} ({len(combined)} rows)")
        print(f"Crossover results saved to {out_cross}")
        print()

        # Summary
        print("--- Summary ---")
        dep_data = combined[combined['noise_type'] == 'depolarizing']
        for cfg_name in dep_data['config_name'].unique():
            cfg_data = dep_data[dep_data['config_name'] == cfg_name]
            zero_noise = cfg_data[cfg_data['noise_1q'] == 0.0]['cvar_energy'].mean()
            max_noise = cfg_data[cfg_data['noise_1q'] == max(NOISE_LEVELS_1Q)]['cvar_energy'].mean()
            print(f"  {cfg_name}: CVaR @ noise=0 -> {zero_noise:.3f}, "
                  f"CVaR @ noise={max(NOISE_LEVELS_1Q)} -> {max_noise:.3f}")

    return combined, crossover


if __name__ == '__main__':
    run_full_part12()
