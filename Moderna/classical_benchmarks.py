"""
the classical benchmarks — SBM & SA Benchmarking.

Classical optimization baselines for RNA folding QUBOs:
  1. Simulated Bifurcation Machine (SBM) — GPU via PyTorch, CPU fallback
  2. Simulated Annealing (SA) — CPU, Metropolis sampling

Both methods solve the same QUBO instances and use the same 20 seeds
as the ideal sweep, with matched evaluation-count units:
  - SBM: 1 evaluation = 1 full integration time-step
  - SA:  1 evaluation = 1 full sweep (N proposed spin flips)

Output: data/classical_benchmarks_results.json

(exact solver), the ideal sweep (fixed seed count = 20)
"""

from __future__ import annotations

import time
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from qubo import QUBOResult, build_qubo, brute_force_solve
from ising import qubo_to_ising, spins_to_bitstring
from ideal_sweep import select_instances, N_SEEDS, MAX_QUBITS, DATA_DIR


# =========================================================================
# Constants
# =========================================================================

# SBM hyperparameters
SBM_T_STEPS = 1000      # number of integration time-steps
SBM_DT = 0.1            # integration step size
SBM_C0 = 2.0            # coupling strength (>1 to overcome deconfining)
SBM_N_RESTARTS = 5      # internal restarts per solve call

# SA hyperparameters
SA_N_SWEEPS = 1000       # number of full sweeps
SA_T_INIT = 5.0          # initial temperature
SA_T_FINAL = 0.01        # final temperature


# =========================================================================
# 1. Simulated Bifurcation Machine (SBM)
# =========================================================================

def _get_torch_device() -> str:
    """Determine the best available torch device."""
    if not HAS_TORCH:
        raise ImportError(
            "PyTorch is required for SBM. Install with: pip install torch"
        )
    if torch.cuda.is_available():
        return 'cuda'
    return 'cpu'


def _sbm_single_run(
    h_torch: 'torch.Tensor',
    J_torch: 'torch.Tensor',
    Q_np: np.ndarray,
    n: int,
    T_steps: int,
    dt: float,
    c0: float,
    seed: int,
    device: str,
) -> Tuple[np.ndarray, float]:
    """Run one SBM trajectory and return (best_bitstring, best_energy).

    Internal helper — not part of the public API.
    """
    # Wide random initialization to break symmetry between variables
    # that have similar h_i values.  Without this, all variables
    # get identical gradient kicks and bifurcate in the same direction.
    gen = torch.Generator(device=device)
    gen.manual_seed(seed)
    x = torch.zeros(n, dtype=torch.float64, device=device).uniform_(-1.0, 1.0, generator=gen)
    y = torch.zeros(n, dtype=torch.float64, device=device)

    best_energy = float('inf')
    best_bits = None

    for t in range(T_steps):
        a_t = t / T_steps  # pump schedule: 0 -> 1

        # Ising gradient: dE/dx_i = h_i + sum_j J_ij x_j
        # NEGATE for minimization: the gradient points uphill,
        # so we apply -gradient to push toward lower energy.
        grad = h_torch + J_torch @ x

        # Update momentum and position (ballistic SBM)
        y = y + dt * (-(1.0 - a_t) * x - c0 * grad)
        x = x + dt * y
        x = torch.clamp(x, -1.0, 1.0)

        # Check current solution quality every 50 steps
        if (t + 1) % 50 == 0 or t == T_steps - 1:
            spins = torch.sign(x)
            spins[spins == 0] = 1.0
            spins_np = spins.cpu().numpy()
            bits = spins_to_bitstring(spins_np)
            e = float(bits @ Q_np @ bits)
            if e < best_energy:
                best_energy = e
                best_bits = bits.copy()

    if best_bits is None:
        spins_final = torch.sign(x)
        spins_final[spins_final == 0] = 1.0
        best_bits = spins_to_bitstring(spins_final.cpu().numpy())
        best_energy = float(best_bits @ Q_np @ best_bits)

    return best_bits, best_energy


def sbm_solve(
    Q: np.ndarray,
    T_steps: int = SBM_T_STEPS,
    dt: float = SBM_DT,
    c0: float = SBM_C0,
    seed: int = 42,
    n_restarts: int = SBM_N_RESTARTS,
) -> Dict[str, Any]:
    """Solve a QUBO using the ballistic Simulated Bifurcation Machine.

    Algorithm (from plan):
        x, y = random_init(N)
        for t in range(T_steps):
            a_t = t / T_steps                          # pump schedule 0->1
            y += dt * (-(1 - a_t) * x - c0 * grad)    # negated for minimization
            x += dt * y
            x = clip(x, -1, 1)
        solution = sign(x)

    Uses n_restarts independent trajectories with different random
    initializations to break symmetry.  Reports the best solution
    across all restarts.  The evaluation count is T_steps (one per
    integration step), consistent regardless of restart count.

    Args:
        Q:          n x n QUBO matrix.
        T_steps:    Number of integration time-steps (= evaluation count).
        dt:         Integration step size.
        c0:         Coupling strength multiplier.
        seed:       Random seed for initialization.
        n_restarts: Number of independent trajectories to run.

    Returns:
        Dict with keys:
            bitstring:     np.ndarray of {0,1}
            energy:        QUBO energy (x^T Q x)
            wall_clock:    Elapsed time in seconds
            evaluations:   T_steps (matched unit)
            device:        'cuda' or 'cpu'
    """
    if not HAS_TORCH:
        raise ImportError("PyTorch required for SBM")

    device = _get_torch_device()
    n = Q.shape[0]

    # Convert QUBO to Ising for the SBM dynamics
    h_ising, J_ising, const_ising = qubo_to_ising(Q)

    # Build the full symmetric Ising coupling matrix
    J_full = J_ising + J_ising.T

    # Normalize coupling by spectral norm to keep dynamics stable
    # regardless of QUBO energy scale (which varies with exclusivity
    # penalty magnitude).
    norm = np.linalg.norm(J_full, ord=2)
    if norm > 1e-12:
        J_norm = J_full / norm
        h_norm = h_ising / norm
    else:
        J_norm = J_full
        h_norm = h_ising

    # Move to torch tensors (shared across restarts)
    J_torch = torch.tensor(J_norm, dtype=torch.float64, device=device)
    h_torch = torch.tensor(h_norm, dtype=torch.float64, device=device)

    best_energy = float('inf')
    best_bits = None

    t_start = time.perf_counter()

    for restart in range(n_restarts):
        restart_seed = seed * 1000 + restart
        bits, energy = _sbm_single_run(
            h_torch, J_torch, Q, n,
            T_steps, dt, c0, restart_seed, device,
        )
        if energy < best_energy:
            best_energy = energy
            best_bits = bits.copy()

    wall_clock = time.perf_counter() - t_start

    return {
        'bitstring': best_bits,
        'energy': best_energy,
        'wall_clock': wall_clock,
        'evaluations': T_steps,
        'device': device,
    }


# =========================================================================
# 2. Simulated Annealing (SA)
# =========================================================================

def _sa_energy_delta(
    spins: np.ndarray,
    i: int,
    h: np.ndarray,
    J_full: np.ndarray,
) -> float:
    """Compute the energy change from flipping spin i.

    For Ising energy E = Σ h_i z_i + Σ_{i<j} J_ij z_i z_j + const,
    flipping z_i → -z_i changes the energy by:
        ΔE = -2 z_i (h_i + Σ_j J_ij z_j)

    This is O(N) per flip, not O(N²) re-evaluation.

    Args:
        spins:   Current spin configuration {-1, +1}^N.
        i:       Index of the spin to flip.
        h:       Linear Ising coefficients.
        J_full:  Full symmetric coupling matrix.

    Returns:
        Energy change if spin i is flipped.
    """
    local_field = h[i] + J_full[i] @ spins
    return -2.0 * spins[i] * local_field


def sa_solve(
    Q: np.ndarray,
    n_sweeps: int = SA_N_SWEEPS,
    T_init: float = SA_T_INIT,
    T_final: float = SA_T_FINAL,
    seed: int = 42,
) -> Dict[str, Any]:
    """Solve a QUBO using Simulated Annealing.

    Algorithm (from plan):
        spins = random_init(N)
        for sweep in range(n_sweeps):
            T = T_schedule(sweep)
            for i in random_order(N):        # one full sweep = N flips
                dE = energy_delta_if_flipped(spins, i, Q)
                if dE < 0 or random() < exp(-dE/T): spins[i] *= -1

    Temperature schedule: exponential decay
        T(sweep) = T_init * (T_final / T_init) ^ (sweep / (n_sweeps - 1))

    One evaluation = one full sweep (N proposed flips).

    Args:
        Q:        n×n QUBO matrix.
        n_sweeps: Number of full sweeps (= evaluation count).
        T_init:   Initial temperature.
        T_final:  Final temperature.
        seed:     Random seed.

    Returns:
        Dict with keys:
            bitstring:     np.ndarray of {0,1}
            energy:        QUBO energy (x^T Q x)
            wall_clock:    Elapsed time in seconds
            evaluations:   n_sweeps (matched unit)
    """
    n = Q.shape[0]
    rng = np.random.default_rng(seed)

    # Convert QUBO to Ising
    h, J_upper, const = qubo_to_ising(Q)

    # Build full symmetric coupling matrix
    J_full = J_upper + J_upper.T

    # Random initial spins {-1, +1}
    spins = rng.choice([-1.0, 1.0], size=n)

    # Compute initial Ising energy
    current_ising_energy = (
        const + np.dot(h, spins) +
        0.5 * spins @ J_full @ spins  # J_full is symmetric, divide by 2
    )

    # Track best solution
    best_spins = spins.copy()
    bits = spins_to_bitstring(best_spins)
    best_qubo_energy = float(bits @ Q @ bits)

    # Temperature ratio for exponential schedule
    if n_sweeps > 1:
        temp_ratio = T_final / T_init
    else:
        temp_ratio = 1.0

    t_start = time.perf_counter()

    for sweep in range(n_sweeps):
        # Exponential temperature schedule
        if n_sweeps > 1:
            T = T_init * (temp_ratio ** (sweep / (n_sweeps - 1)))
        else:
            T = T_init

        # Random permutation of spin indices for this sweep
        order = rng.permutation(n)

        for i in order:
            dE = _sa_energy_delta(spins, int(i), h, J_full)

            if dE < 0:
                spins[i] *= -1
                current_ising_energy += dE
            elif T > 0 and rng.random() < np.exp(-dE / T):
                spins[i] *= -1
                current_ising_energy += dE

        # Check if current solution is the best (in QUBO space)
        bits = spins_to_bitstring(spins)
        qubo_e = float(bits @ Q @ bits)
        if qubo_e < best_qubo_energy:
            best_qubo_energy = qubo_e
            best_spins = spins.copy()

    wall_clock = time.perf_counter() - t_start

    best_bits = spins_to_bitstring(best_spins)

    return {
        'bitstring': best_bits,
        'energy': best_qubo_energy,
        'wall_clock': wall_clock,
        'evaluations': n_sweeps,
    }


# =========================================================================
# 3. Benchmark Runners
# =========================================================================

def run_sbm_benchmark(
    instances: List[Dict[str, Any]],
    n_seeds: int = N_SEEDS,
    T_steps: int = SBM_T_STEPS,
    dt: float = SBM_DT,
    c0: float = SBM_C0,
    verbose: bool = False,
) -> pd.DataFrame:
    """Run SBM benchmark across all instances with n_seeds runs each.

    Args:
        instances: List from select_instances().
        n_seeds:   Number of random seeds per instance.
        T_steps:   SBM integration steps.
        dt:        SBM step size.
        c0:        SBM coupling strength.
        verbose:   Print progress.

    Returns:
        DataFrame with one row per (instance, seed).
    """
    rows = []
    total = len(instances) * n_seeds
    done = 0

    for inst in instances:
        qubo = inst['qubo']
        exact_e = inst['exact_energy']

        for seed_idx in range(n_seeds):
            seed = 1000 + seed_idx  # Same seed series as the ideal sweep
            done += 1

            if verbose and done % 10 == 0:
                print(f"  SBM: {done}/{total}")

            result = sbm_solve(
                qubo.Q, T_steps=T_steps, dt=dt, c0=c0, seed=seed
            )

            rows.append({
                'instance_id': inst['id'],
                'encoding': inst['encoding'],
                'method': 'SBM',
                'seed': seed,
                'energy': result['energy'],
                'exact_energy': exact_e,
                'energy_gap': result['energy'] - exact_e,
                'wall_clock_sec': result['wall_clock'],
                'evaluations': result['evaluations'],
                'n_variables': qubo.n,
                'device': result.get('device', 'cpu'),
            })

    return pd.DataFrame(rows)


def run_sa_benchmark(
    instances: List[Dict[str, Any]],
    n_seeds: int = N_SEEDS,
    n_sweeps: int = SA_N_SWEEPS,
    T_init: float = SA_T_INIT,
    T_final: float = SA_T_FINAL,
    verbose: bool = False,
) -> pd.DataFrame:
    """Run SA benchmark across all instances with n_seeds runs each.

    Args:
        instances: List from select_instances().
        n_seeds:   Number of random seeds per instance.
        n_sweeps:  SA sweep count.
        T_init:    Initial temperature.
        T_final:   Final temperature.
        verbose:   Print progress.

    Returns:
        DataFrame with one row per (instance, seed).
    """
    rows = []
    total = len(instances) * n_seeds
    done = 0

    for inst in instances:
        qubo = inst['qubo']
        exact_e = inst['exact_energy']

        for seed_idx in range(n_seeds):
            seed = 1000 + seed_idx  # Same seed series as the ideal sweep
            done += 1

            if verbose and done % 10 == 0:
                print(f"  SA: {done}/{total}")

            result = sa_solve(
                qubo.Q, n_sweeps=n_sweeps,
                T_init=T_init, T_final=T_final, seed=seed
            )

            rows.append({
                'instance_id': inst['id'],
                'encoding': inst['encoding'],
                'method': 'SA',
                'seed': seed,
                'energy': result['energy'],
                'exact_energy': exact_e,
                'energy_gap': result['energy'] - exact_e,
                'wall_clock_sec': result['wall_clock'],
                'evaluations': result['evaluations'],
                'n_variables': qubo.n,
                'device': 'cpu',
            })

    return pd.DataFrame(rows)


# =========================================================================
# 4. Full the classical benchmarks Orchestrator
# =========================================================================

def run_full_part13(
    n_seeds: int = N_SEEDS,
    max_qubits: int = MAX_QUBITS,
    verbose: bool = True,
) -> pd.DataFrame:
    """Run the complete the classical benchmarks experiment.

    1. Select qualifying instances (same as the ideal sweep)
    2. Run SBM benchmark (20 seeds each)
    3. Run SA benchmark (20 seeds each)
    4. Validate statistical parity
    5. Save combined results

    Args:
        n_seeds:    Number of seeds (20, fixed from the ideal sweep).
        max_qubits: Maximum qubit count for instance selection.
        verbose:    Print progress.

    Returns:
        Combined DataFrame with SBM and SA results.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if verbose:
        print("=" * 60)
        print("the classical benchmarks — SBM & SA Benchmarking")
        print("=" * 60)
        print()

    # 1. Select instances (same as the ideal sweep)
    instances = select_instances(max_qubits)
    if verbose:
        print(f"Selected {len(instances)} instances:")
        for inst in instances:
            print(f"  {inst['id']} ({inst['encoding']}, "
                  f"n={inst['qubo'].n}, exact={inst['exact_energy']:.3f})")
        print()

    # 2. SBM benchmark
    if verbose:
        print("--- SBM Benchmark (GPU/CPU) ---")
    t0 = time.time()
    sbm_df = run_sbm_benchmark(instances, n_seeds=n_seeds, verbose=verbose)
    t_sbm = time.time() - t0
    if verbose:
        device_used = sbm_df['device'].iloc[0] if len(sbm_df) > 0 else 'N/A'
        print(f"  Completed in {t_sbm:.1f}s on {device_used}, "
              f"{len(sbm_df)} rows")
        print()

    # 3. SA benchmark
    if verbose:
        print("--- SA Benchmark (CPU) ---")
    t0 = time.time()
    sa_df = run_sa_benchmark(instances, n_seeds=n_seeds, verbose=verbose)
    t_sa = time.time() - t0
    if verbose:
        print(f"  Completed in {t_sa:.1f}s, {len(sa_df)} rows")
        print()

    # 4. Statistical parity check
    combined = pd.concat([sbm_df, sa_df], ignore_index=True)
    _validate_parity(combined, instances, n_seeds, verbose)

    # 5. Save results
    out_path = DATA_DIR / "classical_benchmarks_results.json"
    combined.to_json(out_path, orient='records', indent=2)
    if verbose:
        print(f"Results saved to {out_path}")
        print(f"Total rows: {len(combined)}")
        print()

        # Summary statistics
        print("--- Summary ---")
        for method in ['SBM', 'SA']:
            method_data = combined[combined['method'] == method]
            for inst in instances:
                inst_data = method_data[
                    method_data['instance_id'] == inst['id']
                ]
                if inst_data.empty:
                    continue
                mean_gap = inst_data['energy_gap'].mean()
                best_gap = inst_data['energy_gap'].min()
                mean_wall = inst_data['wall_clock_sec'].mean()
                print(f"  {method} | {inst['id']}: "
                      f"mean_gap={mean_gap:.4f}, best_gap={best_gap:.4f}, "
                      f"mean_wall={mean_wall:.4f}s")
        print()

    return combined


def _validate_parity(
    df: pd.DataFrame,
    instances: List[Dict[str, Any]],
    n_seeds: int,
    verbose: bool = False,
) -> None:
    """Validate statistical parity: exactly n_seeds runs per method per instance.

    The master plan EXPLICITLY flags unequal seed counts as a bug.
    This function raises AssertionError if the parity check fails.
    """
    for inst in instances:
        for method in ['SBM', 'SA']:
            count = len(df[
                (df['instance_id'] == inst['id']) &
                (df['method'] == method)
            ])
            assert count == n_seeds, (
                f"PARITY VIOLATION: {method} on {inst['id']} has "
                f"{count} runs, expected {n_seeds}"
            )
    if verbose:
        print(f"  Statistical parity check: PASS "
              f"(exactly {n_seeds} SBM and {n_seeds} SA runs per instance)")
        print()


# =========================================================================
# Entry point
# =========================================================================

if __name__ == '__main__':
    run_full_part13()
