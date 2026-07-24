"""
Multi-Tier Performance Evaluation.

Comprehensive comparison of all methods across energy and structural accuracy:

  Tier 1:   Energy comparison (QUBO objective) across exact/VQE/QAOA/SBM/SA
  Tier 2a:  Exact QUBO solution vs ViennaRNA baseline (isolates QUBO approx error)
  Tier 2b:  Structural accuracy -- Sensitivity, PPV, MCC per method (headline result)
  Cross-encoding: agreement/disagreement table (single encoding baseline)

Output: data/evaluation_results.json


"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from qubo import QUBOResult, build_qubo, brute_force_solve, _get_pairs
from genus import pairs_cross, parse_dotbracket
from classical_solvers import cpsat_solve, vienna_mfe
from ising import qubo_to_ising, spins_to_bitstring
from quantum_circuits import run_vqe, run_qaoa
from classical_benchmarks import sbm_solve, sa_solve
from ideal_sweep import select_instances, N_SEEDS, MAX_QUBITS, DATA_DIR
from data_loader import build_target_a, build_target_b


# =========================================================================
# Constants
# =========================================================================

BRACKET_PAIRS = [('(', ')'), ('[', ']'), ('{', '}'), ('<', '>')]


# =========================================================================
# 1. bitstring_to_dotbracket
# =========================================================================

def bitstring_to_dotbracket(
    bitstring: np.ndarray,
    candidates: list,
    encoding: str,
    seq_len: int,
) -> str:
    """Convert a QUBO bitstring to multi-level dot-bracket notation.

    Algorithm (from plan):
        1. Mark each "1" candidate's positions as paired
        2. Assign bracket type by crossing depth: a pair gets bracket-type k
           if it crosses exactly k already-assigned lower-type pairs
           (reuses the genus interlacement logic)
        3. Return dot-bracket string

    Args:
        bitstring:   Binary array of length n_candidates.
        candidates:  List of candidates (pairs/stems/quartets).
        encoding:    One of 'pair', 'stem', 'quartet'.
        seq_len:     Length of the RNA sequence.

    Returns:
        Dot-bracket string with multi-level brackets for crossings.
    """
    # 1. Collect all selected base pairs
    selected_pairs: List[Tuple[int, int]] = []
    for idx, bit in enumerate(bitstring):
        if bit == 1:
            pairs = _get_pairs(candidates[idx], encoding)
            selected_pairs.extend(pairs)

    # Deduplicate and sort
    selected_pairs = sorted(set(selected_pairs))

    if not selected_pairs:
        return '.' * seq_len

    # 2. Assign bracket types by crossing depth
    # For each pair, count how many already-assigned pairs it crosses
    # that have a LOWER bracket type. Process pairs in order, assigning
    # types greedily.
    pair_types: Dict[Tuple[int, int], int] = {}

    for pair in selected_pairs:
        # Count crossings with already-assigned pairs at each level
        crossing_count = 0
        for assigned_pair, _ in pair_types.items():
            if pairs_cross(pair, assigned_pair):
                crossing_count += 1

        # Bracket type = number of crossing pairs
        # (a pair crosses k already-assigned pairs -> type k)
        pair_types[pair] = min(crossing_count, len(BRACKET_PAIRS) - 1)

    # 3. Build the dot-bracket string
    db = ['.'] * seq_len
    for (i, j), btype in pair_types.items():
        opener, closer = BRACKET_PAIRS[btype]
        db[i] = opener
        db[j] = closer

    return ''.join(db)


# =========================================================================
# 2. Structure Metrics (Tier 2b)
# =========================================================================

def compute_structure_metrics(
    predicted_pairs: List[Tuple[int, int]],
    true_pairs: List[Tuple[int, int]],
    seq_len: int,
) -> Dict[str, float]:
    """Compute structural accuracy metrics.

    Confusion matrix over all C(N,2) position-pairs:
        TP = predicted pairs matching true
        FP = predicted-not-true
        FN = true-not-predicted
        TN = everything else

    Args:
        predicted_pairs: List of (i, j) predicted base pairs.
        true_pairs:      List of (i, j) true base pairs.
        seq_len:         Sequence length.

    Returns:
        Dict with TP, FP, FN, TN, sensitivity, ppv, mcc, f1.
    """
    pred_set = set((min(i, j), max(i, j)) for i, j in predicted_pairs)
    true_set = set((min(i, j), max(i, j)) for i, j in true_pairs)

    tp = len(pred_set & true_set)
    fp = len(pred_set - true_set)
    fn = len(true_set - pred_set)

    # Total possible pairs = C(N, 2)
    total_pairs = seq_len * (seq_len - 1) // 2
    tn = total_pairs - tp - fp - fn

    # Sensitivity (recall) = TP / (TP + FN)
    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    # Positive Predictive Value (precision) = TP / (TP + FP)
    ppv = tp / (tp + fp) if (tp + fp) > 0 else 0.0

    # F1 score
    f1 = (2.0 * tp / (2.0 * tp + fp + fn)) if (2 * tp + fp + fn) > 0 else 0.0

    # Matthews Correlation Coefficient
    numerator = tp * tn - fp * fn
    denominator = math.sqrt(
        (tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)
    ) if (tp + fp) * (tp + fn) * (tn + fp) * (tn + fn) > 0 else 1.0
    mcc = numerator / denominator if denominator != 0 else 0.0

    return {
        'tp': tp,
        'fp': fp,
        'fn': fn,
        'tn': tn,
        'sensitivity': sensitivity,
        'ppv': ppv,
        'f1': f1,
        'mcc': mcc,
        'n_predicted': len(pred_set),
        'n_true': len(true_set),
    }


# =========================================================================
# 3. Instance Preparation
# =========================================================================

def prepare_instances(
    max_qubits: int = MAX_QUBITS,
) -> List[Dict[str, Any]]:
    """Prepare instances with QUBOs, exact solutions, and known structures.

    Extends select_instances() with:
        - exact bitstring from brute-force/CP-SAT
        - known dot-bracket structure from datasets
        - ViennaRNA MFE baseline

    Returns:
        List of dicts with keys: id, sequence, encoding, qubo,
        exact_energy, exact_bitstring, known_structure, vienna_structure,
        vienna_energy.
    """
    base_instances = select_instances(max_qubits)
    target_a = build_target_a()
    target_b = build_target_b()
    all_targets = pd.concat([target_a, target_b], ignore_index=True)

    enriched = []
    for inst in base_instances:
        qubo = inst['qubo']

        # Get exact bitstring
        bf_bits, bf_energy = brute_force_solve(qubo)

        # Look up known structure from datasets (Target A or B)
        row = all_targets[all_targets['id'] == inst['id']]
        known_structure = None
        if not row.empty:
            known_structure = row.iloc[0]['known_structure_dotbracket']

        # ViennaRNA MFE baseline
        vienna_struct, vienna_energy = vienna_mfe(inst['sequence'])

        enriched.append({
            'id': inst['id'],
            'sequence': inst['sequence'],
            'encoding': inst['encoding'],
            'qubo': qubo,
            'exact_energy': bf_energy,
            'exact_bitstring': bf_bits,
            'known_structure': known_structure,
            'vienna_structure': vienna_struct,
            'vienna_energy': vienna_energy,
        })

    return enriched


# =========================================================================
# 4. Method Re-Solvers (get bitstrings, not just energies)
# =========================================================================

def _get_best_quantum_bitstring(
    qubo: QUBOResult,
    method: str,
    config_name: str,
    part11_df: pd.DataFrame,
    instance_id: str,
) -> Tuple[Optional[np.ndarray], float, Dict[str, Any]]:
    """Re-run the best quantum seed to extract the actual bitstring.

    the ideal sweep logged energies but not bitstrings, so we re-run the best
    seed to recover the solution.

    Args:
        qubo:        QUBOResult for this instance.
        method:      'vqe' or 'qaoa'.
        config_name: e.g. 'VQE_reps1_stem'.
        part11_df:   the ideal sweep results DataFrame.
        instance_id: Instance ID to filter.

    Returns:
        (bitstring, energy, metadata) or (None, nan, {}) if not found.
    """
    # Find ideal (shot_count=0) results for this config
    mask = (
        (part11_df['instance_id'] == instance_id) &
        (part11_df['config_name'] == config_name) &
        (part11_df['shot_count'] == 0)
    )
    cfg_results = part11_df[mask]
    if cfg_results.empty:
        return None, float('nan'), {}

    # Get best seed
    best_row = cfg_results.loc[cfg_results['energy'].idxmin()]
    best_seed = int(best_row['seed'])

    # Parse config to get method parameters
    if method == 'vqe':
        reps = int(best_row['reps_or_p'])
        result = run_vqe(qubo, reps=reps, max_iter=500, seed=best_seed)
    else:
        p = int(best_row['reps_or_p'])
        mixer = best_row['mixer']
        result = run_qaoa(
            qubo, p=p, mixer=mixer,
            max_iter=500, seed=best_seed, n_restarts=3,
        )

    bitstring = result['bitstring']
    energy = result['qubo_energy']

    meta = {
        'seed': best_seed,
        'config_name': config_name,
        'converged': result['converged'],
        'n_qubits': int(best_row['n_qubits']),
        'circuit_depth': int(best_row['circuit_depth']),
        'two_q_gates': int(best_row['two_q_gates']),
    }
    return bitstring, energy, meta


def _get_best_classical_bitstring(
    qubo: QUBOResult,
    method: str,
    part13_df: pd.DataFrame,
    instance_id: str,
) -> Tuple[Optional[np.ndarray], float, Dict[str, Any]]:
    """Re-run the best classical seed to extract the actual bitstring.

    Args:
        qubo:        QUBOResult.
        method:      'SBM' or 'SA'.
        part13_df:   the classical benchmarks results DataFrame.
        instance_id: Instance ID to filter.

    Returns:
        (bitstring, energy, metadata) or (None, nan, {}) if not found.
    """
    mask = (
        (part13_df['instance_id'] == instance_id) &
        (part13_df['method'] == method)
    )
    method_results = part13_df[mask]
    if method_results.empty:
        return None, float('nan'), {}

    best_row = method_results.loc[method_results['energy'].idxmin()]
    best_seed = int(best_row['seed'])

    if method == 'SA':
        result = sa_solve(qubo.Q, seed=best_seed)
    else:
        result = sbm_solve(qubo.Q, seed=best_seed)

    meta = {
        'seed': best_seed,
        'wall_clock_sec': result['wall_clock'],
        'evaluations': result['evaluations'],
    }
    return result['bitstring'], result['energy'], meta


# =========================================================================
# 5. Tier 1 -- Energy Comparison
# =========================================================================

def run_tier1(
    instances: List[Dict[str, Any]],
    part11_df: pd.DataFrame,
    part13_df: pd.DataFrame,
    verbose: bool = False,
) -> pd.DataFrame:
    """Tier 1: compare final objective across all methods.

    Primary metric: evaluation count.
    Secondary: wall-clock (caveated as confounded by queue time for quantum).

    Returns:
        DataFrame with one row per (instance, method).
    """
    rows = []

    for inst in instances:
        inst_id = inst['id']
        exact_e = inst['exact_energy']

        # --- Exact solver ---
        rows.append({
            'instance_id': inst_id,
            'encoding': inst['encoding'],
            'method': 'Exact (CP-SAT)',
            'config': 'brute_force',
            'best_energy': exact_e,
            'exact_energy': exact_e,
            'energy_gap': 0.0,
            'n_variables': inst['qubo'].n,
        })

        # --- Quantum methods (from the ideal sweep ideal sweep) ---
        for config_name in part11_df['config_name'].unique():
            mask = (
                (part11_df['instance_id'] == inst_id) &
                (part11_df['config_name'] == config_name) &
                (part11_df['shot_count'] == 0)
            )
            cfg_results = part11_df[mask]
            if cfg_results.empty:
                continue
            best_energy = cfg_results['energy'].min()
            mean_energy = cfg_results['energy'].mean()
            std_energy = cfg_results['energy'].std()
            method_name = cfg_results.iloc[0]['ansatz']
            mixer = cfg_results.iloc[0]['mixer']

            rows.append({
                'instance_id': inst_id,
                'encoding': inst['encoding'],
                'method': f"{method_name} ({mixer})" if mixer != 'none' else method_name,
                'config': config_name,
                'best_energy': best_energy,
                'mean_energy': mean_energy,
                'std_energy': std_energy,
                'exact_energy': exact_e,
                'energy_gap': best_energy - exact_e,
                'n_seeds': len(cfg_results),
                'n_variables': inst['qubo'].n,
            })

        # --- Classical methods (from the classical benchmarks) ---
        for method in ['SBM', 'SA']:
            mask = (
                (part13_df['instance_id'] == inst_id) &
                (part13_df['method'] == method)
            )
            method_results = part13_df[mask]
            if method_results.empty:
                continue
            best_energy = method_results['energy'].min()
            mean_energy = method_results['energy'].mean()
            std_energy = method_results['energy'].std()
            mean_wall = method_results['wall_clock_sec'].mean()
            evals = method_results['evaluations'].iloc[0]

            rows.append({
                'instance_id': inst_id,
                'encoding': inst['encoding'],
                'method': method,
                'config': method.lower(),
                'best_energy': best_energy,
                'mean_energy': mean_energy,
                'std_energy': std_energy,
                'exact_energy': exact_e,
                'energy_gap': best_energy - exact_e,
                'n_seeds': len(method_results),
                'evaluations': evals,
                'wall_clock_sec': mean_wall,
                'n_variables': inst['qubo'].n,
            })

    df = pd.DataFrame(rows)
    if verbose:
        print("--- Tier 1: Energy Comparison ---")
        for inst_id in df['instance_id'].unique():
            inst_rows = df[df['instance_id'] == inst_id]
            print(f"\n  {inst_id}:")
            for _, r in inst_rows.iterrows():
                gap = r.get('energy_gap', 0)
                print(f"    {r['method']:30s}  best={r['best_energy']:8.3f}  "
                      f"gap={gap:8.4f}")
        print()

    return df


# =========================================================================
# 6. Tier 2a -- QUBO Solution vs ViennaRNA
# =========================================================================

def run_tier2a(
    instances: List[Dict[str, Any]],
    verbose: bool = False,
) -> pd.DataFrame:
    """Tier 2a: exact QUBO solution vs ViennaRNA/known biology.

    Mismatches isolate error to QUBO/genus penalty's QUBO approximation,
    not the optimizer.
    """
    rows = []

    for inst in instances:
        qubo = inst['qubo']
        exact_bits = inst['exact_bitstring']
        seq = inst['sequence']
        known_struct = inst['known_structure']

        # Convert exact QUBO solution to dot-bracket
        qubo_db = bitstring_to_dotbracket(
            exact_bits, qubo.candidates, qubo.encoding, len(seq)
        )
        qubo_pairs = set(
            (min(i, j), max(i, j))
            for i, j in qubo.selected_pairs(exact_bits)
        )

        # ViennaRNA prediction
        vienna_struct = inst['vienna_structure']
        vienna_pairs = set(
            (min(i, j), max(i, j))
            for i, j in parse_dotbracket(vienna_struct)
        )

        # Known structure
        known_pairs = set()
        if known_struct:
            known_pairs = set(
                (min(i, j), max(i, j))
                for i, j in parse_dotbracket(known_struct)
            )

        # Compare QUBO vs ViennaRNA
        qubo_vs_vienna = {
            'agree': len(qubo_pairs & vienna_pairs),
            'qubo_only': len(qubo_pairs - vienna_pairs),
            'vienna_only': len(vienna_pairs - qubo_pairs),
        }

        # Compare QUBO vs known biology
        qubo_vs_known = {}
        if known_pairs:
            qubo_vs_known = {
                'agree': len(qubo_pairs & known_pairs),
                'qubo_only': len(qubo_pairs - known_pairs),
                'known_only': len(known_pairs - qubo_pairs),
            }

        # Compare ViennaRNA vs known biology
        vienna_vs_known = {}
        if known_pairs:
            vienna_vs_known = {
                'agree': len(vienna_pairs & known_pairs),
                'vienna_only': len(vienna_pairs - known_pairs),
                'known_only': len(known_pairs - vienna_pairs),
            }

        rows.append({
            'instance_id': inst['id'],
            'sequence_length': len(seq),
            'qubo_dotbracket': qubo_db,
            'vienna_dotbracket': vienna_struct,
            'known_dotbracket': known_struct or '',
            'qubo_n_pairs': len(qubo_pairs),
            'vienna_n_pairs': len(vienna_pairs),
            'known_n_pairs': len(known_pairs),
            'qubo_energy': inst['exact_energy'],
            'vienna_energy': inst['vienna_energy'],
            'qubo_vs_vienna_agree': qubo_vs_vienna['agree'],
            'qubo_vs_vienna_qubo_only': qubo_vs_vienna['qubo_only'],
            'qubo_vs_vienna_vienna_only': qubo_vs_vienna['vienna_only'],
            'qubo_vs_known_agree': qubo_vs_known.get('agree', 0),
            'qubo_vs_known_qubo_only': qubo_vs_known.get('qubo_only', 0),
            'qubo_vs_known_known_only': qubo_vs_known.get('known_only', 0),
            'vienna_vs_known_agree': vienna_vs_known.get('agree', 0),
        })

    df = pd.DataFrame(rows)
    if verbose:
        print("--- Tier 2a: QUBO Solution vs ViennaRNA ---")
        for _, r in df.iterrows():
            print(f"\n  {r['instance_id']}:")
            print(f"    QUBO:    {r['qubo_dotbracket']}")
            print(f"    Vienna:  {r['vienna_dotbracket']}")
            if r['known_dotbracket']:
                print(f"    Known:   {r['known_dotbracket']}")
            print(f"    QUBO vs Vienna: {r['qubo_vs_vienna_agree']} agree, "
                  f"{r['qubo_vs_vienna_qubo_only']} QUBO-only, "
                  f"{r['qubo_vs_vienna_vienna_only']} Vienna-only")
            if r['known_dotbracket']:
                print(f"    QUBO vs Known:  {r['qubo_vs_known_agree']} agree, "
                      f"{r['qubo_vs_known_qubo_only']} QUBO-only, "
                      f"{r['qubo_vs_known_known_only']} Known-only")
        print()

    return df


# =========================================================================
# 7. Tier 2b -- Structural Accuracy (Headline Result)
# =========================================================================

def run_tier2b(
    instances: List[Dict[str, Any]],
    part11_df: pd.DataFrame,
    part13_df: pd.DataFrame,
    verbose: bool = False,
) -> pd.DataFrame:
    """Tier 2b: structural accuracy per method.

    Re-runs the best seed from each method to extract the actual bitstring,
    converts to pairs, computes Sensitivity/PPV/MCC against known structure.

    This is the HEADLINE RESULT per the plan.
    """
    rows = []

    # Quantum configs to evaluate (best of each type)
    quantum_configs = [
        ('vqe', 'VQE_reps1_stem'),
        ('vqe', 'VQE_reps2_stem'),
        ('qaoa', 'QAOA_X_p1_stem'),
        ('qaoa', 'QAOA_X_p2_stem'),
        ('qaoa', 'QAOA_XY_p1_stem'),
        ('qaoa', 'QAOA_XY_p2_stem'),
    ]

    total = len(instances) * (len(quantum_configs) + 3)  # +3: exact, SBM, SA
    done = 0

    for inst in instances:
        qubo = inst['qubo']
        seq = inst['sequence']
        known_struct = inst['known_structure']

        if not known_struct:
            continue

        true_pairs = parse_dotbracket(known_struct)

        # --- Exact solver ---
        done += 1
        exact_pairs = qubo.selected_pairs(inst['exact_bitstring'])
        exact_db = bitstring_to_dotbracket(
            inst['exact_bitstring'], qubo.candidates,
            qubo.encoding, len(seq)
        )
        metrics = compute_structure_metrics(exact_pairs, true_pairs, len(seq))
        rows.append({
            'instance_id': inst['id'],
            'method': 'Exact (CP-SAT)',
            'config': 'brute_force',
            'predicted_dotbracket': exact_db,
            'energy': inst['exact_energy'],
            **metrics,
        })

        if verbose and done % 5 == 0:
            print(f"  Tier 2b: {done}/{total}")

        # --- Quantum methods ---
        for method, config_name in quantum_configs:
            done += 1
            try:
                bits, energy, meta = _get_best_quantum_bitstring(
                    qubo, method, config_name, part11_df, inst['id']
                )
                if bits is None:
                    continue

                pred_pairs = qubo.selected_pairs(bits)
                pred_db = bitstring_to_dotbracket(
                    bits, qubo.candidates, qubo.encoding, len(seq)
                )
                metrics = compute_structure_metrics(
                    pred_pairs, true_pairs, len(seq)
                )
                rows.append({
                    'instance_id': inst['id'],
                    'method': config_name.replace('_stem', ''),
                    'config': config_name,
                    'predicted_dotbracket': pred_db,
                    'energy': energy,
                    **metrics,
                    **{f'meta_{k}': v for k, v in meta.items()},
                })
            except Exception as e:
                if verbose:
                    print(f"    WARN: {inst['id']} {config_name}: {e}")

            if verbose and done % 5 == 0:
                print(f"  Tier 2b: {done}/{total}")

        # --- Classical methods ---
        for method in ['SBM', 'SA']:
            done += 1
            try:
                bits, energy, meta = _get_best_classical_bitstring(
                    qubo, method, part13_df, inst['id']
                )
                if bits is None:
                    continue

                pred_pairs = qubo.selected_pairs(bits)
                pred_db = bitstring_to_dotbracket(
                    bits, qubo.candidates, qubo.encoding, len(seq)
                )
                metrics = compute_structure_metrics(
                    pred_pairs, true_pairs, len(seq)
                )
                rows.append({
                    'instance_id': inst['id'],
                    'method': method,
                    'config': method.lower(),
                    'predicted_dotbracket': pred_db,
                    'energy': energy,
                    **metrics,
                    **{f'meta_{k}': v for k, v in meta.items()},
                })
            except Exception as e:
                if verbose:
                    print(f"    WARN: {inst['id']} {method}: {e}")

    df = pd.DataFrame(rows)
    if verbose:
        print("\n--- Tier 2b: Structural Accuracy (Headline) ---")
        # Summary per method
        for method_name in df['method'].unique():
            m = df[df['method'] == method_name]
            print(f"\n  {method_name}:")
            print(f"    Sensitivity: {m['sensitivity'].mean():.4f} "
                  f"(+/- {m['sensitivity'].std():.4f})")
            print(f"    PPV:         {m['ppv'].mean():.4f} "
                  f"(+/- {m['ppv'].std():.4f})")
            print(f"    MCC:         {m['mcc'].mean():.4f} "
                  f"(+/- {m['mcc'].std():.4f})")
            print(f"    F1:          {m['f1'].mean():.4f}")
        print()

    return df


# =========================================================================
# 8. Cross-Encoding Consistency
# =========================================================================

def run_cross_encoding(
    instances: List[Dict[str, Any]],
    verbose: bool = False,
) -> pd.DataFrame:
    """Cross-encoding consistency check.

    Since Parts 11/13 only used 'stem' encoding, this reports a
    single-encoding baseline. The logic supports multiple encodings
    for future expansion.
    """
    rows = []

    for inst in instances:
        qubo = inst['qubo']
        seq = inst['sequence']

        exact_pairs = qubo.selected_pairs(inst['exact_bitstring'])
        exact_db = bitstring_to_dotbracket(
            inst['exact_bitstring'], qubo.candidates,
            qubo.encoding, len(seq)
        )

        # Check topological features
        has_crossing = any(
            pairs_cross(exact_pairs[i], exact_pairs[j])
            for i in range(len(exact_pairs))
            for j in range(i + 1, len(exact_pairs))
        )

        rows.append({
            'instance_id': inst['id'],
            'encoding': inst['encoding'],
            'n_pairs_selected': len(exact_pairs),
            'has_crossing': has_crossing,
            'dotbracket': exact_db,
            'energy': inst['exact_energy'],
            'note': 'single encoding (stem) -- cross-encoding comparison '
                    'requires pair/quartet runs at scale',
        })

    df = pd.DataFrame(rows)
    if verbose:
        print("--- Cross-Encoding Consistency ---")
        print(f"  Encodings tested: {sorted(df['encoding'].unique())}")
        print(f"  NOTE: Only stem encoding was used in Parts 11/13.")
        print(f"         Cross-encoding comparison is degenerate.")
        for _, r in df.iterrows():
            print(f"  {r['instance_id']} ({r['encoding']}): "
                  f"{r['n_pairs_selected']} pairs, "
                  f"crossing={r['has_crossing']}")
        print()

    return df


# =========================================================================
# 9. Full the evaluation Orchestrator
# =========================================================================

def run_full_part14(
    max_qubits: int = MAX_QUBITS,
    verbose: bool = True,
) -> Dict[str, pd.DataFrame]:
    """Run the complete the evaluation evaluation.

    1. Prepare instances with exact solutions and known structures
    2. Load the ideal sweep and the classical benchmarks logged results
    3. Run Tier 1 (energy comparison)
    4. Run Tier 2a (QUBO vs ViennaRNA)
    5. Run Tier 2b (structural accuracy -- headline)
    6. Run cross-encoding consistency
    7. Save consolidated results

    Returns:
        Dict of DataFrames: {tier1, tier2a, tier2b, cross_encoding}
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if verbose:
        print("=" * 60)
        print("Multi-Tier Performance Evaluation")
        print("=" * 60)
        print()

    # 1. Prepare instances
    if verbose:
        print("Preparing instances...")
    instances = prepare_instances(max_qubits)
    if verbose:
        print(f"  {len(instances)} instances prepared")
        for inst in instances:
            known = 'yes' if inst['known_structure'] else 'no'
            print(f"    {inst['id']}: n={inst['qubo'].n}, "
                  f"exact_E={inst['exact_energy']:.3f}, "
                  f"known_struct={known}")
        print()

    # 2. Load logged results
    part11_path = DATA_DIR / "ideal_sweep_results.json"
    part13_path = DATA_DIR / "classical_benchmarks_results.json"

    part11_df = pd.read_json(part11_path)
    part13_df = pd.read_json(part13_path)

    if verbose:
        print(f"  the ideal sweep: {len(part11_df)} rows loaded")
        print(f"  the classical benchmarks: {len(part13_df)} rows loaded")
        print()

    # 3. Tier 1
    t0 = time.time()
    tier1_df = run_tier1(instances, part11_df, part13_df, verbose)
    if verbose:
        print(f"  Tier 1 completed in {time.time()-t0:.1f}s, "
              f"{len(tier1_df)} rows\n")

    # 4. Tier 2a
    t0 = time.time()
    tier2a_df = run_tier2a(instances, verbose)
    if verbose:
        print(f"  Tier 2a completed in {time.time()-t0:.1f}s, "
              f"{len(tier2a_df)} rows\n")

    # 5. Tier 2b (headline -- takes longest due to re-solving)
    if verbose:
        print("Running Tier 2b (re-solving for bitstrings)...")
    t0 = time.time()
    tier2b_df = run_tier2b(instances, part11_df, part13_df, verbose)
    if verbose:
        print(f"  Tier 2b completed in {time.time()-t0:.1f}s, "
              f"{len(tier2b_df)} rows\n")

    # 6. Cross-encoding
    cross_df = run_cross_encoding(instances, verbose)

    # 7. Save results
    results = {
        'tier1': tier1_df,
        'tier2a': tier2a_df,
        'tier2b': tier2b_df,
        'cross_encoding': cross_df,
    }

    out_path = DATA_DIR / "evaluation_results.json"
    combined = {}
    for key, df in results.items():
        combined[key] = json.loads(df.to_json(orient='records'))
    with open(out_path, 'w') as f:
        json.dump(combined, f, indent=2)

    if verbose:
        print(f"Results saved to {out_path}")
        print()
        print("=" * 60)
        print("the evaluation Summary")
        print("=" * 60)
        print(f"  Tier 1:  {len(tier1_df)} rows (energy comparison)")
        print(f"  Tier 2a: {len(tier2a_df)} rows (QUBO vs ViennaRNA)")
        print(f"  Tier 2b: {len(tier2b_df)} rows (structural accuracy)")
        print(f"  Cross:   {len(cross_df)} rows (encoding consistency)")
        print()

    return results


# =========================================================================
# Entry point
# =========================================================================

if __name__ == '__main__':
    run_full_part14()
