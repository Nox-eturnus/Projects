"""
Noise Progression, Tier 1: Ideal & Shot-Noise Only.

Systematically sweeps VQE/QAOA configurations under:
  1. Ideal statevector (zero shot noise) -- mean/variance of energy
  2. Shot-noise only (ideal unitary, zero gate error) -- CVaR-aggregated cost

Logs per run: qubit count, circuit depth, 2Q gate count, parameter count.

Output: data/ideal_sweep_results.json (DataFrame) ready for the noisy sweep/15.

Fixed seed count: 20 (kept constant through the classical benchmarks).
Shot counts: [128, 512, 2048, 8192].
CVaR alpha: 0.2 (best 20% of shots).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import numpy as np
import pandas as pd

from qiskit.circuit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp, Statevector
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

from qubo import QUBOResult, build_qubo, brute_force_solve
from ising import qubo_to_ising, ising_to_sparse_pauli_op
from quantum_circuits import (
    build_two_local_ansatz,
    build_qaoa_circuit,
    run_vqe,
    run_qaoa,
)
from data_loader import build_target_a, build_target_b


# =========================================================================
# Constants
# =========================================================================

N_SEEDS = 20
SHOT_COUNTS = [128, 512, 2048, 8192]
CVAR_ALPHA = 0.2
MAX_QUBITS = 20  # raised to accommodate Target B pseudoknots (stem: 15-19 qubits)
DATA_DIR = Path(__file__).parent / "data"


# =========================================================================
# Utility functions
# =========================================================================

def get_circuit_metadata(circuit: QuantumCircuit) -> Dict[str, int]:
    """Extract qubit count, circuit depth, and two-qubit gate count.

    Uses a simple transpile pass to decompose into basis gates for
    accurate gate counting.

    Args:
        circuit: A QuantumCircuit (may be parameterized or bound).

    Returns:
        Dict with keys: n_qubits, depth, two_q_gates, n_params.
    """
    n_qubits = circuit.num_qubits
    depth = circuit.depth()
    n_params = circuit.num_parameters

    # Count two-qubit gates
    two_q_gates = 0
    for instruction in circuit.data:
        if instruction.operation.num_qubits == 2:
            two_q_gates += 1

    return {
        'n_qubits': n_qubits,
        'depth': depth,
        'two_q_gates': two_q_gates,
        'n_params': n_params,
    }


def compute_cvar(energies: List[float], alpha: float = 0.2) -> float:
    """Compute CVaR (Conditional Value at Risk) at level alpha.

    CVaR-alpha is the mean of the lowest alpha-fraction of energies.
    For minimization, this focuses on the best (lowest energy) samples.

    Args:
        energies: List of energy values from sampled bitstrings.
        alpha:    Fraction of lowest energies to average (0 < alpha <= 1).

    Returns:
        CVaR energy value.
    """
    if not energies:
        return float('nan')

    sorted_e = sorted(energies)
    k = max(1, int(len(sorted_e) * alpha))
    return float(np.mean(sorted_e[:k]))


def bitstring_energy(bitstring: str, Q: np.ndarray) -> float:
    """Compute QUBO energy for a Qiskit-format bitstring.

    Qiskit returns bitstrings with qubit 0 on the right.
    Our QUBO convention: index 0 = qubit 0.
    So we reverse the string.

    Args:
        bitstring: String of '0' and '1' (Qiskit ordering, MSB first).
        Q:         QUBO matrix.

    Returns:
        QUBO energy as a float.
    """
    # Reverse to match our index-0 = qubit-0 convention
    bits = np.array([int(b) for b in reversed(bitstring)], dtype=np.float64)
    return float(bits @ Q @ bits)


def sample_energies_from_circuit(
    circuit: QuantumCircuit,
    params: np.ndarray,
    Q: np.ndarray,
    n_shots: int,
    seed: int,
) -> List[float]:
    """Sample bitstrings from a bound circuit and compute their QUBO energies.

    Uses Qiskit's Statevector to get probabilities, then multinomial
    sampling to simulate shot noise without needing AerSampler for
    the energy computation.

    Args:
        circuit: Parameterized QuantumCircuit.
        params:  Parameter values to bind.
        Q:       QUBO matrix for energy evaluation.
        n_shots: Number of measurement shots.
        seed:    Random seed for sampling.

    Returns:
        List of QUBO energies, one per shot.
    """
    bound = circuit.assign_parameters(params)
    sv = Statevector(bound)
    probs = sv.probabilities()

    # Sample bitstring indices according to probabilities
    rng = np.random.default_rng(seed)
    n_qubits = circuit.num_qubits
    indices = rng.choice(len(probs), size=n_shots, p=probs)

    energies = []
    for idx in indices:
        # Convert index to bitstring (Qiskit ordering: MSB first)
        bs = format(idx, f'0{n_qubits}b')
        e = bitstring_energy(bs, Q)
        energies.append(e)

    return energies


# =========================================================================
# Experiment configurations
# =========================================================================

@dataclass
class ExperimentConfig:
    """Defines a single ansatz/mixer configuration to sweep."""
    name: str
    method: Literal['vqe', 'qaoa']
    encoding: str
    # VQE params
    reps: int = 1
    # QAOA params
    p: int = 1
    mixer: str = 'x'


def get_default_configs() -> List[ExperimentConfig]:
    """Return the standard set of configurations to sweep."""
    configs = []
    for enc in ['stem']:  # stem for tractable n
        # VQE two-local, reps=1 and reps=2
        configs.append(ExperimentConfig(
            name=f'VQE_reps1_{enc}', method='vqe', encoding=enc, reps=1))
        configs.append(ExperimentConfig(
            name=f'VQE_reps2_{enc}', method='vqe', encoding=enc, reps=2))
        # QAOA Pauli-X mixer, p=1 and p=2
        configs.append(ExperimentConfig(
            name=f'QAOA_X_p1_{enc}', method='qaoa', encoding=enc,
            p=1, mixer='x'))
        configs.append(ExperimentConfig(
            name=f'QAOA_X_p2_{enc}', method='qaoa', encoding=enc,
            p=2, mixer='x'))
        # QAOA XY mixer, p=1 and p=2
        configs.append(ExperimentConfig(
            name=f'QAOA_XY_p1_{enc}', method='qaoa', encoding=enc,
            p=1, mixer='xy'))
        configs.append(ExperimentConfig(
            name=f'QAOA_XY_p2_{enc}', method='qaoa', encoding=enc,
            p=2, mixer='xy'))
    return configs


# =========================================================================
# Instance selection
# =========================================================================

def select_instances(max_qubits: int = MAX_QUBITS) -> List[Dict[str, Any]]:
    """Select Target A + Target B instances within the qubit ceiling.

    Returns list of dicts with keys: id, sequence, encoding, qubo, exact_energy.
    """
    df_a = build_target_a()
    df_b = build_target_b()
    combined = pd.concat([df_a, df_b], ignore_index=True)
    instances = []

    for _, row in combined.iterrows():
        for enc in ['stem']:
            qubo = build_qubo(row['sequence'], encoding=enc)
            if 2 <= qubo.n <= max_qubits:
                bf_bits, bf_energy = brute_force_solve(qubo)
                instances.append({
                    'id': row['id'],
                    'sequence': row['sequence'],
                    'encoding': enc,
                    'qubo': qubo,
                    'exact_energy': bf_energy,
                })

    return instances


# =========================================================================
# Ideal statevector sweep
# =========================================================================

def run_ideal_sweep(
    instances: List[Dict[str, Any]],
    configs: Optional[List[ExperimentConfig]] = None,
    n_seeds: int = N_SEEDS,
    max_iter: int = 500,
    verbose: bool = False,
) -> pd.DataFrame:
    """Sweep 1: Ideal statevector, zero shot noise.

    For each (instance, config, seed), optimize with StatevectorEstimator.
    Records the optimal energy and optimal parameters.

    Args:
        instances: List from select_instances().
        configs:   Experiment configurations; uses defaults if None.
        n_seeds:   Number of random seeds per configuration.
        max_iter:  Max optimizer iterations.
        verbose:   Print progress.

    Returns:
        DataFrame with one row per (instance, config, seed).
    """
    if configs is None:
        configs = get_default_configs()

    rows = []
    total = sum(1 for inst in instances for cfg in configs
                if cfg.encoding == inst['encoding'])
    total *= n_seeds
    done = 0

    for inst in instances:
        qubo = inst['qubo']
        exact_e = inst['exact_energy']

        for cfg in configs:
            if cfg.encoding != inst['encoding']:
                continue

            # Build circuit for metadata
            h, J, const = qubo_to_ising(qubo.Q)

            if cfg.method == 'vqe':
                circuit = build_two_local_ansatz(qubo.n, reps=cfg.reps)
            else:
                circuit = build_qaoa_circuit(h, J, qubo.n, p=cfg.p,
                                             mixer=cfg.mixer)
            meta = get_circuit_metadata(circuit)

            for seed_idx in range(n_seeds):
                seed = 1000 + seed_idx  # deterministic seed sequence
                done += 1

                if verbose and done % 10 == 0:
                    print(f"  Ideal sweep: {done}/{total}")

                try:
                    if cfg.method == 'vqe':
                        result = run_vqe(
                            qubo, reps=cfg.reps,
                            max_iter=max_iter, seed=seed)
                    else:
                        result = run_qaoa(
                            qubo, p=cfg.p, mixer=cfg.mixer,
                            max_iter=max_iter, seed=seed,
                            n_restarts=3)

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
                        'seed': seed,
                        'shot_count': 0,  # 0 = statevector (infinite shots)
                        'energy': result['optimal_energy'],
                        'qubo_energy': result['qubo_energy'],
                        'cvar_energy': float('nan'),  # not applicable
                        'exact_energy': exact_e,
                        'energy_gap': result['optimal_energy'] - exact_e,
                        'converged': result['converged'],
                    })
                except Exception as e:
                    if verbose:
                        print(f"    ERROR {inst['id']} {cfg.name} seed={seed}: {e}")
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
                        'seed': seed,
                        'shot_count': 0,
                        'energy': float('nan'),
                        'qubo_energy': float('nan'),
                        'cvar_energy': float('nan'),
                        'exact_energy': exact_e,
                        'energy_gap': float('nan'),
                        'converged': False,
                    })

    return pd.DataFrame(rows)


# =========================================================================
# Shot-noise sweep
# =========================================================================

def run_shot_noise_sweep(
    instances: List[Dict[str, Any]],
    ideal_results: pd.DataFrame,
    configs: Optional[List[ExperimentConfig]] = None,
    shot_counts: Optional[List[int]] = None,
    n_seeds: int = N_SEEDS,
    alpha: float = CVAR_ALPHA,
    verbose: bool = False,
) -> pd.DataFrame:
    """Sweep 2: Ideal unitary, zero gate error, sweep shot count.

    Takes the best parameters from the ideal sweep and re-evaluates
    using shot-based sampling at each shot count.

    Args:
        instances:     List from select_instances().
        ideal_results: DataFrame from run_ideal_sweep().
        configs:       Experiment configurations; uses defaults if None.
        shot_counts:   List of shot counts to sweep.
        n_seeds:       Number of sampling seeds per (config, shot_count).
        alpha:         CVaR alpha parameter.
        verbose:       Print progress.

    Returns:
        DataFrame with one row per (instance, config, shot_count, seed).
    """
    if configs is None:
        configs = get_default_configs()
    if shot_counts is None:
        shot_counts = SHOT_COUNTS

    rows = []

    for inst in instances:
        qubo = inst['qubo']
        exact_e = inst['exact_energy']

        for cfg in configs:
            if cfg.encoding != inst['encoding']:
                continue

            # Get best ideal result for this (instance, config)
            mask = (
                (ideal_results['instance_id'] == inst['id']) &
                (ideal_results['config_name'] == cfg.name)
            )
            cfg_results = ideal_results[mask]
            if cfg_results.empty:
                continue

            # Use the parameters from the best seed (lowest energy)
            best_row = cfg_results.loc[cfg_results['energy'].idxmin()]

            # We need to re-run the best seed to get optimal_params
            # since we don't store params in the DataFrame
            h, J, const = qubo_to_ising(qubo.Q)
            best_seed = int(best_row['seed'])

            if cfg.method == 'vqe':
                best_result = run_vqe(
                    qubo, reps=cfg.reps,
                    max_iter=500, seed=best_seed)
                circuit = build_two_local_ansatz(qubo.n, reps=cfg.reps)
            else:
                best_result = run_qaoa(
                    qubo, p=cfg.p, mixer=cfg.mixer,
                    max_iter=500, seed=best_seed,
                    n_restarts=3)
                circuit = build_qaoa_circuit(h, J, qubo.n, p=cfg.p,
                                             mixer=cfg.mixer)

            optimal_params = best_result['optimal_params']
            meta = get_circuit_metadata(circuit)

            for n_shots in shot_counts:
                for seed_idx in range(n_seeds):
                    sample_seed = 5000 + seed_idx
                    energies = sample_energies_from_circuit(
                        circuit, optimal_params, qubo.Q,
                        n_shots, sample_seed)

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
                        'energy': mean_e,
                        'qubo_energy': float('nan'),
                        'cvar_energy': cvar_e,
                        'exact_energy': exact_e,
                        'energy_gap': mean_e - exact_e,
                        'energy_var': var_e,
                        'converged': True,
                    })

                if verbose:
                    print(f"  Shot sweep: {inst['id']} {cfg.name} "
                          f"shots={n_shots} done ({n_seeds} seeds)")

    return pd.DataFrame(rows)


# =========================================================================
# Full experiment orchestrator
# =========================================================================

def run_full_experiment(
    n_seeds: int = N_SEEDS,
    max_qubits: int = MAX_QUBITS,
    verbose: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Run the complete the ideal sweep experiment.

    1. Select qualifying instances
    2. Run ideal statevector sweep
    3. Run shot-noise sweep
    4. Save combined results

    Args:
        n_seeds:    Number of seeds (default 20, fixed through the classical benchmarks).
        max_qubits: Maximum qubit count for instance selection.
        verbose:    Print progress.

    Returns:
        (ideal_df, shot_df) DataFrames.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if verbose:
        print("=" * 60)
        print("Noise Progression Tier 1: Ideal & Shot-Noise")
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

    # 2. Ideal sweep
    if verbose:
        print("--- Ideal Statevector Sweep ---")
    t0 = time.time()
    ideal_df = run_ideal_sweep(
        instances, configs, n_seeds=n_seeds, verbose=verbose)
    t_ideal = time.time() - t0
    if verbose:
        print(f"  Completed in {t_ideal:.1f}s, {len(ideal_df)} rows")
        print()

    # 3. Shot-noise sweep
    if verbose:
        print("--- Shot-Noise Sweep ---")
    t0 = time.time()
    shot_df = run_shot_noise_sweep(
        instances, ideal_df, configs, verbose=verbose)
    t_shot = time.time() - t0
    if verbose:
        print(f"  Completed in {t_shot:.1f}s, {len(shot_df)} rows")
        print()

    # 4. Save results
    combined = pd.concat([ideal_df, shot_df], ignore_index=True)
    out_path = DATA_DIR / "ideal_sweep_results.json"
    combined.to_json(out_path, orient='records', indent=2)
    if verbose:
        print(f"Results saved to {out_path}")
        print(f"Total rows: {len(combined)}")
        print()

        # Summary statistics
        print("--- Summary ---")
        for cfg_name in combined['config_name'].unique():
            cfg_data = combined[combined['config_name'] == cfg_name]
            ideal_data = cfg_data[cfg_data['shot_count'] == 0]
            if not ideal_data.empty:
                mean_gap = ideal_data['energy_gap'].mean()
                print(f"  {cfg_name}: ideal mean gap = {mean_gap:.4f}")

    return ideal_df, shot_df


if __name__ == '__main__':
    run_full_experiment()
