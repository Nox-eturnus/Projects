"""
mRNA Quantum Folding Pipeline — Unified Entry Point.

Orchestrates the complete pipeline from RNA sequence data through
quantum/classical optimization to final evaluation and plotting:

    Data → Candidates → QUBO → Genus Penalty → Classical Ground Truth →
    Quantum Optimization (VQE/QAOA) → Classical Benchmarks (SA/SBM) →
    Evaluation → Plots

Supports incremental execution: instances already present in results
files are skipped unless --force is specified.

Usage:
    python run_pipeline.py                  # full pipeline, skip existing
    python run_pipeline.py --force          # re-run everything
    python run_pipeline.py --validate       # run test suite after pipeline
    python run_pipeline.py --max-qubits 12  # override qubit ceiling
    python run_pipeline.py --quiet          # minimal output
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd


# =========================================================================
# 1. Data Loading
# =========================================================================

def stage_data(verbose: bool = True) -> dict:
    """Build all datasets (Target A, Target B, FSE)."""
    from data_loader import build_all_datasets
    if verbose:
        print("=" * 60)
        print("Stage 1: Data Loading")
        print("=" * 60)
    return build_all_datasets()


# =========================================================================
# 2. Instance Selection & QUBO Construction
# =========================================================================

def stage_instances(max_qubits: int, verbose: bool = True) -> List[Dict]:
    """Select qualifying instances and build QUBOs."""
    from ideal_sweep import select_instances
    if verbose:
        print()
        print("=" * 60)
        print("Stage 2: Instance Selection & QUBO Construction")
        print("=" * 60)
    instances = select_instances(max_qubits)
    if verbose:
        print(f"  Selected {len(instances)} instances (max {max_qubits} qubits)")
        for inst in instances:
            print(f"    {inst['id']:25s}  encoding={inst['encoding']:6s}  "
                  f"n={inst['qubo'].n} qubits")
    return instances


# =========================================================================
# 3. Quantum Optimization (VQE/QAOA) — Ideal Sweep
# =========================================================================

def stage_quantum(
    instances: List[Dict],
    skip_existing: bool = True,
    verbose: bool = True,
) -> None:
    """Run ideal statevector VQE/QAOA sweep for all instances."""
    from quantum_circuits import run_vqe, run_qaoa, build_two_local_ansatz, build_qaoa_circuit
    from ising import qubo_to_ising
    from ideal_sweep import N_SEEDS, DATA_DIR

    if verbose:
        print()
        print("=" * 60)
        print("Stage 3: Quantum Optimization (Ideal Sweep)")
        print("=" * 60)

    out_path = DATA_DIR / "ideal_sweep_results.json"
    existing_data = []
    existing_ids = set()

    if out_path.exists() and skip_existing:
        existing_data = json.load(open(out_path))
        existing_ids = {r['instance_id'] for r in existing_data}

    new_instances = [i for i in instances if i['id'] not in existing_ids]

    if not new_instances:
        if verbose:
            print("  All instances already have ideal sweep results. Skipping.")
        return

    if verbose:
        print(f"  Running {len(new_instances)} new instances...")

    configs = [
        {'ansatz': 'VQE', 'mixer': 'none', 'reps_or_p': 1,
         'config_name': 'VQE_reps1_stem'},
        {'ansatz': 'VQE', 'mixer': 'none', 'reps_or_p': 2,
         'config_name': 'VQE_reps2_stem'},
        {'ansatz': 'QAOA', 'mixer': 'x', 'reps_or_p': 1,
         'config_name': 'QAOA_X_p1_stem'},
        {'ansatz': 'QAOA', 'mixer': 'x', 'reps_or_p': 2,
         'config_name': 'QAOA_X_p2_stem'},
        {'ansatz': 'QAOA', 'mixer': 'xy', 'reps_or_p': 1,
         'config_name': 'QAOA_XY_p1_stem'},
        {'ansatz': 'QAOA', 'mixer': 'xy', 'reps_or_p': 2,
         'config_name': 'QAOA_XY_p2_stem'},
    ]

    results = []
    total = len(new_instances) * len(configs) * N_SEEDS
    done = 0

    for inst in new_instances:
        qubo = inst['qubo']
        n = qubo.n
        exact_energy = inst['exact_energy']

        if verbose:
            print(f"\n  Instance {inst['id']} (n={n} qubits)")

        for cfg in configs:
            for seed in range(N_SEEDS):
                done += 1
                t0 = time.time()

                try:
                    if cfg['ansatz'] == 'VQE':
                        result = run_vqe(
                            qubo, reps=cfg['reps_or_p'],
                            max_iter=500, seed=seed,
                        )
                        method_key = 'VQE'
                    else:
                        result = run_qaoa(
                            qubo, p=cfg['reps_or_p'],
                            mixer=cfg['mixer'],
                            max_iter=500, seed=seed,
                            n_restarts=3,
                        )
                        method_key = 'QAOA'

                    energy = result['optimal_energy']
                    qubo_energy = result['qubo_energy']

                    h, J, constant = qubo_to_ising(qubo.Q)

                    if method_key == 'VQE':
                        circuit = build_two_local_ansatz(n, reps=cfg['reps_or_p'])
                    else:
                        circuit = build_qaoa_circuit(
                            h, J, n, p=cfg['reps_or_p'], mixer=cfg['mixer']
                        )

                    depth = circuit.depth()
                    two_q = sum(
                        1 for instr in circuit.data
                        if instr.operation.num_qubits == 2
                    )

                    row = {
                        'instance_id': inst['id'],
                        'encoding': inst['encoding'],
                        'ansatz': method_key,
                        'mixer': cfg['mixer'],
                        'config_name': cfg['config_name'],
                        'n_qubits': n,
                        'circuit_depth': depth,
                        'two_q_gates': two_q,
                        'n_params': circuit.num_parameters,
                        'reps_or_p': cfg['reps_or_p'],
                        'seed': seed,
                        'shot_count': 0,
                        'energy': energy,
                        'qubo_energy': qubo_energy,
                        'cvar_energy': None,
                        'exact_energy': exact_energy,
                        'energy_gap': qubo_energy - exact_energy,
                        'converged': result['converged'],
                        'energy_var': 0.0,
                    }
                    results.append(row)

                except Exception as e:
                    if verbose:
                        print(f"    WARN: {cfg['config_name']} seed={seed}: {e}")

                elapsed = time.time() - t0
                if verbose and done % 10 == 0:
                    print(f"    [{done}/{total}] {cfg['config_name']} "
                          f"seed={seed} ({elapsed:.1f}s)")

    # Append to existing data
    existing_data.extend(results)
    with open(out_path, 'w') as f:
        json.dump(existing_data, f, indent=2, default=str)
    if verbose:
        print(f"\n  Saved {len(existing_data)} total rows to {out_path}")


# =========================================================================
# 4. Classical Benchmarks (SA/SBM)
# =========================================================================

def stage_classical_benchmarks(
    instances: List[Dict],
    skip_existing: bool = True,
    verbose: bool = True,
) -> None:
    """Run SA and SBM benchmarks for all instances."""
    from classical_benchmarks import sbm_solve, sa_solve
    from ideal_sweep import N_SEEDS, DATA_DIR

    if verbose:
        print()
        print("=" * 60)
        print("Stage 4: Classical Benchmarks (SA/SBM)")
        print("=" * 60)

    out_path = DATA_DIR / "classical_benchmarks_results.json"
    existing_data = []
    existing_ids = set()

    if out_path.exists() and skip_existing:
        existing_data = json.load(open(out_path))
        existing_ids = {r['instance_id'] for r in existing_data}

    new_instances = [i for i in instances if i['id'] not in existing_ids]

    if not new_instances:
        if verbose:
            print("  All instances already have benchmark results. Skipping.")
        return

    if verbose:
        print(f"  Running {len(new_instances)} new instances...")

    results = []

    for inst in new_instances:
        qubo = inst['qubo']
        n = qubo.n
        exact_energy = inst['exact_energy']

        if verbose:
            print(f"\n  Instance {inst['id']} (n={n})")

        for seed in range(N_SEEDS):
            # Simulated Annealing
            t0 = time.time()
            sa_result = sa_solve(qubo.Q, seed=seed)
            sa_wall = time.time() - t0
            results.append({
                'instance_id': inst['id'],
                'encoding': inst['encoding'],
                'method': 'SA',
                'seed': seed,
                'energy': sa_result['energy'],
                'exact_energy': exact_energy,
                'energy_gap': sa_result['energy'] - exact_energy,
                'wall_clock_sec': sa_wall,
                'evaluations': sa_result['evaluations'],
                'n_variables': n,
                'device': 'cpu',
            })

            # Simulated Bifurcation Machine
            t0 = time.time()
            sbm_result = sbm_solve(qubo.Q, seed=seed)
            sbm_wall = time.time() - t0
            results.append({
                'instance_id': inst['id'],
                'encoding': inst['encoding'],
                'method': 'SBM',
                'seed': seed,
                'energy': sbm_result['energy'],
                'exact_energy': exact_energy,
                'energy_gap': sbm_result['energy'] - exact_energy,
                'wall_clock_sec': sbm_wall,
                'evaluations': sbm_result['evaluations'],
                'n_variables': n,
                'device': sbm_result.get('device', 'cpu'),
            })

        if verbose:
            sa_best = min(r['energy'] for r in results
                          if r['instance_id'] == inst['id']
                          and r['method'] == 'SA')
            sbm_best = min(r['energy'] for r in results
                           if r['instance_id'] == inst['id']
                           and r['method'] == 'SBM')
            print(f"    SA best={sa_best:.3f}  SBM best={sbm_best:.3f}  "
                  f"exact={exact_energy:.3f}")

    # Append to existing data
    existing_data.extend(results)
    with open(out_path, 'w') as f:
        json.dump(existing_data, f, indent=2, default=str)
    if verbose:
        print(f"\n  Saved {len(existing_data)} total rows to {out_path}")


# =========================================================================
# 5. Evaluation
# =========================================================================

def stage_evaluate(max_qubits: int, verbose: bool = True) -> None:
    """Run multi-tier performance evaluation."""
    from evaluate import run_full_part14
    if verbose:
        print()
        print("=" * 60)
        print("Stage 5: Multi-Tier Performance Evaluation")
        print("=" * 60)
    run_full_part14(max_qubits=max_qubits, verbose=verbose)


# =========================================================================
# 6. Plots & Scalability Report
# =========================================================================

def stage_plots(verbose: bool = True) -> None:
    """Generate all plots and the scalability report."""
    from plots import run_full_part15
    if verbose:
        print()
        print("=" * 60)
        print("Stage 6: Plots & Scalability Report")
        print("=" * 60)
    run_full_part15(verbose=verbose)


# =========================================================================
# 7. Validation
# =========================================================================

def stage_validate(verbose: bool = True) -> bool:
    """Run the test suite and verify Target B coverage."""
    import subprocess

    if verbose:
        print()
        print("=" * 60)
        print("Stage 7: Validation")
        print("=" * 60)

    # Run pytest
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests/', '-v', '--tb=short'],
        cwd=Path(__file__).parent,
    )

    # Verify Target B instances
    eval_path = Path(__file__).parent / 'data' / 'evaluation_results.json'
    if eval_path.exists():
        data = json.load(open(eval_path))
        if 'tier2b' in data:
            ids = {r['instance_id'] for r in data['tier2b']}
            tb = sorted(i for i in ids if 'pk_' in i)
            if verbose:
                print(f"\n  Target B instances in evaluation: {tb}")
            if len(tb) < 5:
                print(f"  WARNING: Only {len(tb)} Target B instances found "
                      f"(expected >= 5)")
                return False
        else:
            print("  WARNING: No tier2b key in evaluation results")
            return False
    else:
        print(f"  WARNING: {eval_path} not found")
        return False

    return result.returncode == 0


# =========================================================================
# Main
# =========================================================================

def main():
    parser = argparse.ArgumentParser(
        description='mRNA Quantum Folding Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Pipeline stages:
  1. Data Loading      — Build Target A, Target B, and FSE datasets
  2. Instance Selection — Select qualifying instances, build QUBOs
  3. Quantum Sweep     — VQE/QAOA ideal statevector optimization
  4. Classical Bench   — Simulated Annealing & Simulated Bifurcation
  5. Evaluation        — Multi-tier performance metrics (Tier 1/2a/2b)
  6. Plots             — Scaling, wall-clock, headline accuracy charts
  7. Validation        — pytest test suite + Target B coverage check
        """,
    )
    parser.add_argument(
        '--max-qubits', type=int, default=20,
        help='Maximum qubit count for instance selection (default: 20)',
    )
    parser.add_argument(
        '--force', action='store_true',
        help='Re-run all stages even if results exist',
    )
    parser.add_argument(
        '--validate', action='store_true',
        help='Run test suite after pipeline completion',
    )
    parser.add_argument(
        '--quiet', action='store_true',
        help='Minimal output',
    )

    args = parser.parse_args()
    verbose = not args.quiet
    skip_existing = not args.force

    t_start = time.time()

    if verbose:
        print("=" * 60)
        print("  mRNA Quantum Folding Pipeline")
        print("=" * 60)
        print()

    # Stage 1: Data
    stage_data(verbose=verbose)

    # Stage 2: Instances
    instances = stage_instances(args.max_qubits, verbose=verbose)

    # Stage 3: Quantum optimization
    stage_quantum(instances, skip_existing=skip_existing, verbose=verbose)

    # Stage 4: Classical benchmarks
    stage_classical_benchmarks(
        instances, skip_existing=skip_existing, verbose=verbose,
    )

    # Stage 5: Evaluation
    stage_evaluate(max_qubits=args.max_qubits, verbose=verbose)

    # Stage 6: Plots
    stage_plots(verbose=verbose)

    elapsed = time.time() - t_start
    if verbose:
        print()
        print("=" * 60)
        print(f"  Pipeline COMPLETE ({elapsed:.0f}s)")
        print("=" * 60)

    # Stage 7: Validation (optional)
    if args.validate:
        ok = stage_validate(verbose=verbose)
        if not ok:
            sys.exit(1)


if __name__ == '__main__':
    main()
