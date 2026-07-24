"""
the genus penalty module — Genus Penalty Calibration.

Adds a topological crossing penalty to the the QUBO module QUBO, calibrated
to steer the solver toward biologically correct pseudoknotted
structures (Target B) without breaking nested solutions (Target A).

Two paths:
  - Path A (stem-level, single-crossing topologies): if the crossing-
    pairs-to-genus ratio is exactly 1:1, apply mu = 1.5 (TT2NE-anchored).
  - Path B (quartet/pair-level, or any multi-crossing topology): sweep
    mu over [0.1, 5.0] and lock mu* at the accuracy-maximizing value.

The calibration sweep uses the CP-SAT solver as a subroutine.
"""

from __future__ import annotations

import json
import os
import numpy as np
from typing import List, Tuple, Optional, Dict, Any

from qubo import (
    QUBOResult, build_qubo,
    _get_pairs, _get_positions,
)
from genus import pairs_cross, compute_genus, parse_dotbracket
from classical_solvers import cpsat_solve, SolverResult


# --------------------------------------------------------------------------
# Stored calibration constant
# --------------------------------------------------------------------------

_MU_STAR_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'data', 'mu_star.json'
)

_mu_star_cache: Optional[float] = None


def get_mu_star() -> Optional[float]:
    """Load the locked mu* constant, or None if not yet calibrated."""
    global _mu_star_cache
    if _mu_star_cache is not None:
        return _mu_star_cache
    if os.path.exists(_MU_STAR_FILE):
        with open(_MU_STAR_FILE, 'r') as f:
            data = json.load(f)
        _mu_star_cache = float(data['mu_star'])
        return _mu_star_cache
    return None


def _save_mu_star(mu_star: float, sweep_results: Dict[str, Any]) -> None:
    """Save mu* and sweep metadata to disk."""
    global _mu_star_cache
    os.makedirs(os.path.dirname(_MU_STAR_FILE), exist_ok=True)
    data = {
        'mu_star': mu_star,
        'sweep_min': sweep_results.get('mu_min'),
        'sweep_max': sweep_results.get('mu_max'),
        'sweep_steps': sweep_results.get('n_steps'),
        'best_accuracy': sweep_results.get('best_accuracy'),
        'accuracies': sweep_results.get('accuracies'),
    }
    with open(_MU_STAR_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    _mu_star_cache = mu_star


# --------------------------------------------------------------------------
# Crossing-pair detection
# --------------------------------------------------------------------------

def get_crossing_candidate_pairs(
    candidates: list,
    encoding: str,
) -> List[Tuple[int, int]]:
    """Find all crossing (candidate_index_a, candidate_index_b) pairs.

    Two candidates cross if any of their base pairs cross each other.
    Returns pairs of indices into the candidates list.

    Args:
        candidates: List of pair tuples, Stems, or Quartets.
        encoding:   One of 'pair', 'stem', 'quartet'.

    Returns:
        List of (i, j) index pairs where i < j and candidates[i]
        crosses candidates[j].
    """
    n = len(candidates)
    crossing_pairs: List[Tuple[int, int]] = []

    for i in range(n):
        pairs_i = _get_pairs(candidates[i], encoding)
        for j in range(i + 1, n):
            pairs_j = _get_pairs(candidates[j], encoding)
            # Check if any pair from i crosses any pair from j
            found_crossing = False
            for pi in pairs_i:
                for pj in pairs_j:
                    if pairs_cross(pi, pj):
                        found_crossing = True
                        break
                if found_crossing:
                    break
            if found_crossing:
                crossing_pairs.append((i, j))

    return crossing_pairs


def count_crossing_pairs_in_solution(
    bitstring: np.ndarray,
    candidates: list,
    encoding: str,
) -> int:
    """Count how many crossing candidate-pairs are selected in a solution."""
    selected_indices = [i for i, b in enumerate(bitstring) if b == 1]
    count = 0
    for a in range(len(selected_indices)):
        for b in range(a + 1, len(selected_indices)):
            idx_a = selected_indices[a]
            idx_b = selected_indices[b]
            pairs_a = _get_pairs(candidates[idx_a], encoding)
            pairs_b = _get_pairs(candidates[idx_b], encoding)
            for pa in pairs_a:
                for pb in pairs_b:
                    if pairs_cross(pa, pb):
                        count += 1
                        break
                else:
                    continue
                break
    return count


# --------------------------------------------------------------------------
# Path A: stem-level, mu = 1.5 for 1:1 crossing-to-genus ratio
# --------------------------------------------------------------------------

TT2NE_MU = 1.5  # TT2NE-anchored genus penalty for Path A


def check_path_a_applicability(
    candidates: list,
    encoding: str,
    known_pairs: List[Tuple[int, int]],
) -> bool:
    """Check if Path A is applicable for this instance.

    Path A applies iff:
      1. Encoding is 'stem'
      2. The crossing-pairs-to-genus ratio is exactly 1:1

    This means the number of crossing candidate-pairs in the known
    structure equals the genus of the known structure.

    Args:
        candidates:  Stem candidates.
        encoding:    Must be 'stem'.
        known_pairs: Known base pairs of the true structure.

    Returns:
        True if Path A applies.
    """
    if encoding != 'stem':
        return False

    genus = compute_genus(known_pairs)
    if genus == 0:
        # No crossings -- Path A trivially applies (no penalty needed)
        return True

    # Count crossing pairs among the known structure's stems
    # For this check, we count how many candidate stem pairs actually
    # cross in the known structure.
    crossing_count = len(get_crossing_candidate_pairs(candidates, encoding))

    # We want crossing_count : genus == 1:1
    # But "crossing_count" here is from ALL candidates, not just
    # the ones in the known structure.  We need the ratio for the
    # known structure specifically.
    #
    # More precisely: genus of the known structure vs number of
    # crossing pairs of base-pair groups in the known structure.
    # For a simple H-type PK: 1 crossing pair -> genus 1 -> ratio 1:1.
    # For kissing hairpin: may have multiple crossings -> genus 1 -> ratio != 1:1.

    # Compute from the known pairs directly
    n_crossing = 0
    for i in range(len(known_pairs)):
        for j in range(i + 1, len(known_pairs)):
            if pairs_cross(known_pairs[i], known_pairs[j]):
                n_crossing += 1

    if n_crossing == 0:
        return True  # nested, no penalty needed

    return n_crossing == genus


# --------------------------------------------------------------------------
# QUBO with genus penalty
# --------------------------------------------------------------------------

def inject_genus_penalty(
    qubo: QUBOResult,
    mu: float,
    crossing_pairs: Optional[List[Tuple[int, int]]] = None,
) -> QUBOResult:
    """Inject genus penalty terms into a copy of the QUBO.

    For every pair of candidates (i, j) that cross, add mu to
    Q[i][j] and Q[j][i] (symmetric).

    Args:
        qubo:           Base QUBOResult (NOT modified).
        mu:             Genus penalty weight.
        crossing_pairs: Pre-computed crossing pairs.  If None,
                        computed internally.

    Returns:
        New QUBOResult with genus penalty injected.
    """
    result = qubo.copy()

    if crossing_pairs is None:
        crossing_pairs = get_crossing_candidate_pairs(
            result.candidates, result.encoding
        )

    for i, j in crossing_pairs:
        result.Q[i, j] += mu / 2.0
        result.Q[j, i] += mu / 2.0

    return result


def build_qubo_with_genus_penalty(
    sequence: str,
    encoding: str = 'pair',
    mu: Optional[float] = None,
    min_stem_len: int = 2,
    excl_multiplier: float = 10.0,
    known_pairs: Optional[List[Tuple[int, int]]] = None,
) -> QUBOResult:
    """Build a QUBO with genus penalty (the QUBO module + the genus penalty module combined).

    If mu is None:
      - For stem encoding with 1:1 crossing-to-genus ratio (Path A):
        uses TT2NE_MU = 1.5.
      - Otherwise (Path B): uses the locked mu_star if available,
        raises ValueError if not calibrated yet.

    Args:
        sequence:        RNA sequence string.
        encoding:        One of 'pair', 'stem', 'quartet'.
        mu:              Explicit genus penalty weight.  If None,
                         auto-selects via Path A/B logic.
        min_stem_len:    Min stem length for stem encoding.
        excl_multiplier: Exclusivity penalty multiplier.
        known_pairs:     Known structure pairs (needed for Path A
                         applicability check; if None, Path B is used).

    Returns:
        QUBOResult with genus penalty injected.
    """
    base_qubo = build_qubo(
        sequence,
        encoding=encoding,
        min_stem_len=min_stem_len,
        excl_multiplier=excl_multiplier,
    )

    # Compute crossing pairs for this candidate set
    crossing_pairs = get_crossing_candidate_pairs(
        base_qubo.candidates, encoding
    )

    if not crossing_pairs:
        # No crossings possible -- return base QUBO unchanged
        return base_qubo

    # Determine mu
    if mu is not None:
        effective_mu = mu
    elif (
        encoding == 'stem'
        and known_pairs is not None
        and check_path_a_applicability(
            base_qubo.candidates, encoding, known_pairs
        )
    ):
        # Path A: TT2NE-anchored mu = 1.5
        effective_mu = TT2NE_MU
    else:
        # Path B: use locked mu_star
        mu_star = get_mu_star()
        if mu_star is None:
            raise ValueError(
                "Path B requires a calibrated mu_star, but none is "
                "locked.  Run calibrate_mu() first."
            )
        effective_mu = mu_star

    return inject_genus_penalty(base_qubo, effective_mu, crossing_pairs)


# --------------------------------------------------------------------------
# Calibration sweep
# --------------------------------------------------------------------------

def calibrate_mu(
    calibration_set: List[Dict[str, Any]],
    encoding: str = 'pair',
    mu_min: float = -3.0,
    mu_max: float = 5.0,
    n_steps: int = 80,
    min_stem_len: int = 2,
    excl_multiplier: float = 10.0,
    cpsat_time_limit: float = 30.0,
    verbose: bool = True,
) -> Tuple[float, Dict[str, Any]]:
    """Sweep mu to find the accuracy-maximizing genus penalty.

    The sweep range includes negative values (crossing bonus) because
    the base QUBO energy model cannot capture pseudoknot stabilization:
    one-body energies are computed as isolated hairpins, and stacking
    bonuses apply only to non-crossing adjacent pairs.  Without a
    crossing bonus (negative mu), the solver always prefers nested
    solutions.  Negative mu compensates by rewarding co-selection of
    crossing candidates.

    For each mu candidate:
      1. Build QUBO with that mu
      2. Solve exactly via CP-SAT
      3. Check classification:
         - Pseudoknotted instance -> solution must have a crossing pair
         - Nested instance -> solution must NOT have a crossing pair
      4. Record accuracy = fraction correctly classified

    Args:
        calibration_set: List of dicts, each with keys:
            'sequence': RNA sequence string,
            'known_structure_dotbracket': dot-bracket string,
            'topology_class': 'nested' or 'pseudoknotted',
            'id': instance identifier.
        encoding:        'pair', 'stem', or 'quartet'.
        mu_min, mu_max:  Sweep range.  Negative mu_min enables
                         crossing-bonus territory.
        n_steps:         Number of mu values to try.
        min_stem_len:    Min stem length for stem encoding.
        excl_multiplier: Exclusivity penalty multiplier.
        cpsat_time_limit: CP-SAT time limit per instance per mu.
        verbose:         Print progress.

    Returns:
        (mu_star, sweep_metadata) -- mu_star is the locked optimal mu.
    """
    mu_values = np.linspace(mu_min, mu_max, n_steps)
    accuracies = []

    n_instances = len(calibration_set)

    if verbose:
        print(f"Calibration sweep: mu in [{mu_min}, {mu_max}], "
              f"{n_steps} steps, {n_instances} instances", flush=True)

    for step_idx, mu in enumerate(mu_values):
        correct = 0

        for inst in calibration_set:
            seq = inst['sequence']
            topo = inst['topology_class']

            # Build QUBO with this mu
            base_qubo = build_qubo(
                seq,
                encoding=encoding,
                min_stem_len=min_stem_len,
                excl_multiplier=excl_multiplier,
            )

            crossing_pairs = get_crossing_candidate_pairs(
                base_qubo.candidates, encoding
            )

            if crossing_pairs:
                penalized_qubo = inject_genus_penalty(
                    base_qubo, mu, crossing_pairs
                )
            else:
                penalized_qubo = base_qubo

            # Solve
            result = cpsat_solve(penalized_qubo, time_limit_sec=cpsat_time_limit)

            if not result.is_optimal:
                # Can't classify reliably -- treat as wrong
                continue

            # Check classification
            has_crossing = result.has_crossing_pair()

            if topo == 'pseudoknotted' and has_crossing:
                correct += 1
            elif topo == 'nested' and not has_crossing:
                correct += 1

        accuracy = correct / n_instances if n_instances > 0 else 0.0
        accuracies.append(accuracy)

        if verbose and (step_idx % 2 == 0 or step_idx == n_steps - 1):
            print(f"  mu={mu:.3f}  accuracy={accuracy:.2%}  "
                  f"({correct}/{n_instances})", flush=True)

    # Find best mu
    accuracies_arr = np.array(accuracies)
    best_idx = int(np.argmax(accuracies_arr))
    mu_star = float(mu_values[best_idx])
    best_accuracy = float(accuracies_arr[best_idx])

    if verbose:
        print(f"\nBest: mu*={mu_star:.3f}  accuracy={best_accuracy:.2%}")

    # Check that mu_star is strictly inside the range
    at_boundary = (best_idx == 0 or best_idx == n_steps - 1)
    if at_boundary:
        print(f"  WARNING: mu* is at the sweep boundary "
              f"(idx={best_idx}/{n_steps-1}). "
              f"Consider widening the range.")

    sweep_results = {
        'mu_min': mu_min,
        'mu_max': mu_max,
        'n_steps': n_steps,
        'best_accuracy': best_accuracy,
        'best_idx': best_idx,
        'at_boundary': at_boundary,
        'accuracies': [float(a) for a in accuracies],
        'mu_values': [float(m) for m in mu_values],
    }

    # Lock mu*
    _save_mu_star(mu_star, sweep_results)

    if verbose:
        print(f"  mu*={mu_star:.3f} locked to {_MU_STAR_FILE}")

    return mu_star, sweep_results
