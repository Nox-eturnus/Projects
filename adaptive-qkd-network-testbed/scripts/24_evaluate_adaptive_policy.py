from __future__ import annotations

import hashlib
import json
import math
import pickle
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from qkd_lab.adaptive.actions import QKDAction, candidate_actions
from qkd_lab.adaptive.dataset import (
    EPS_COR,
    EPS_SEC,
    MDI_BUDGET,
    PULSE_RATE_HZ,
    _intensities,
    evaluate_action_outcome,
)
from qkd_lab.adaptive.execution import execute_action_through_gate
from qkd_lab.adaptive.features import ALLOWED_FEATURES
from qkd_lab.adaptive.utility import compute_service_utility
from qkd_lab.config import load_yaml
from qkd_lab.estimation.finite_key_bb84 import estimate_lim2014
from qkd_lab.estimation.finite_key_mdi import estimate_mdi_finite_key
from qkd_lab.models import (
    BasisProbabilities,
    ChannelParameters,
    DetectorParameters,
)
from qkd_lab.protocols.decoy_bb84 import expected_decoy_bb84_block, simulate_aggregate_decoy_bb84_block
from qkd_lab.protocols.mdi_qkd import (
    MDIBasisProbabilities,
    MDIPhysicalParameters,
    expected_mdi_block,
    simulate_aggregate_mdi_block,
)


def compute_file_hash(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_git_commit() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        return res.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def is_working_tree_clean() -> bool:
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain", "qkd_lab", "tests", "scripts", "standards", "configs", "README.md"],
            capture_output=True,
            text=True,
            check=False,
        )
        return len(res.stdout.strip()) == 0
    except Exception:
        return False


def parse_action_name(action_name: str) -> QKDAction | None:
    if action_name in ("ABORT", "HEURISTIC") or not action_name:
        return None
    try:
        parts = action_name.split("|")
        protocol = parts[0]
        mu = float(parts[1].split("=")[1])
        nu = float(parts[2].split("=")[1])
        p = float(parts[3].split("=")[1])
        n = int(parts[4].split("=")[1])
        return QKDAction(protocol, mu, nu, p, n)
    except Exception:
        return None


def evaluate_decision_independent(
    action_name: str,
    context: dict,
    *,
    key_pool: float,
    prev_action: str | None = None,
    switching_penalty: float = 50.0,
    seed: int = 42,
) -> dict:
    """Evaluate an action through the unified execute_action_through_gate engine."""
    return execute_action_through_gate(
        action_name,
        context,
        key_pool=key_pool,
        prev_action=prev_action,
        switching_penalty=switching_penalty,
        seed=seed,
        latency_weight=0.05,
        deficit_weight=2.0,
        abort_penalty=1000.0,
    )


def evaluate_decision(action_name: str, scenario_data) -> dict:
    """Backward-compatible wrapper supporting DataFrame or dict input."""
    if isinstance(scenario_data, pd.DataFrame):
        if action_name == "ABORT":
            return {
                "action": "ABORT",
                "executed": "ABORT",
                "utility": 0.0,
                "secure_bits": 0.0,
                "predictive_gate_miss": False,
                "security_violation": False,
                "violation": False,
            }
        matches = scenario_data[scenario_data["action_name"] == action_name]
        if matches.empty:
            return {
                "action": action_name,
                "executed": "ABORT",
                "utility": 0.0,
                "secure_bits": 0.0,
                "predictive_gate_miss": False,
                "security_violation": False,
                "violation": False,
            }
        candidate = matches.iloc[0]
        if (not bool(candidate["feasible"])) or bool(candidate["abort"]):
            return {
                "action": action_name,
                "executed": "ABORT",
                "utility": 0.0,
                "secure_bits": 0.0,
                "predictive_gate_miss": False,
                "security_violation": False,
                "violation": False,
            }
        sec_bits = float(candidate["secure_bits"])
        util = float(candidate["service_utility"])
        gate_miss = bool(candidate["abort"]) or (sec_bits <= 0.0)
        return {
            "action": action_name,
            "executed": action_name,
            "utility": util,
            "secure_bits": sec_bits,
            "predictive_gate_miss": gate_miss,
            "security_violation": False,
            "violation": gate_miss,
        }
    return evaluate_decision_independent(action_name, scenario_data, key_pool=500_000.0)


def simulate_fixed_action_on_trajectories(
    action_name: str,
    trajectories_df: pd.DataFrame,
    switching_penalty: float = 50.0,
) -> float:
    """Simulate candidate fixed action across complete training trajectories with evolving key pool."""
    step_utilities = []
    for traj_id, traj_df in trajectories_df.groupby("trajectory_id"):
        traj_df = traj_df.sort_values("time_step")
        steps = traj_df.drop_duplicates(subset=["time_step"])
        pool = float(steps.iloc[0]["key_pool_bits"])
        prev_act = None
        for _, step_row in steps.iterrows():
            context = step_row.to_dict()
            step_id = int(context["time_step"])
            crn_seed = int(42 + traj_id * 1000 + step_id)
            ctx = dict(context)
            ctx["key_pool_bits"] = pool
            ev = evaluate_decision_independent(
                action_name,
                ctx,
                key_pool=pool,
                prev_action=prev_act,
                switching_penalty=switching_penalty,
                seed=crn_seed,
            )
            pool = ev["next_key_pool"]
            prev_act = ev["executed"]
            step_utilities.append(ev["utility"])
    return float(np.mean(step_utilities)) if step_utilities else -1e6


def heuristic_decision(context: dict) -> str:
    qber = float(context["recent_qber"])
    dist = float(context["distance_km"])
    mdi = bool(context["mdi_capable"])

    if qber > 0.08:
        return "ABORT"
    if mdi and dist >= 50.0:
        return "mdi_qkd|mu=0.40|nu=0.05|p=0.80|N=10000000000"
    if qber < 0.03 and dist < 40.0:
        return "decoy_bb84|mu=0.55|nu=0.10|p=0.90|N=10000000000"
    return "decoy_bb84|mu=0.40|nu=0.05|p=0.80|N=10000000000"


def trajectory_paired_sign_flip_test(
    diffs: np.ndarray,
    n_permutations: int = 10_000,
    seed: int = 42,
) -> tuple[float, str]:
    """Paired trajectory-level sign-flip randomization test (10,000 permutations).

    Null hypothesis H0: Paired trajectory differences D_i are symmetric around 0.
    Returns:
        (p_value_numeric, p_value_display)
    """
    n = len(diffs)
    if n == 0:
        return 1.0, "1.0000"
    t_obs = abs(float(np.mean(diffs)))
    if t_obs == 0.0:
        return 1.0, "1.0000"

    rng = np.random.default_rng(seed)
    # Generate random signs {-1, +1} of shape (n_permutations, n)
    signs = rng.choice(np.array([-1.0, 1.0]), size=(n_permutations, n), replace=True)
    perm_t = np.abs(np.mean(signs * diffs, axis=1))

    # Standard unbiased permutation test formula: (1 + count(T >= T_obs)) / (B + 1)
    count_extreme = int(np.sum(perm_t >= t_obs))
    p_val = float((1 + count_extreme) / (n_permutations + 1))

    if p_val <= 0.0001:
        p_str = "< 0.0001"
    else:
        p_str = f"{p_val:.4f}"

    return p_val, p_str


def trajectory_cluster_bootstrap_ci(
    results_df: pd.DataFrame,
    adaptive_col: str,
    baseline_col: str,
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 42,
) -> tuple[float, float, float, float, float, float, float, str]:
    """Trajectory-level cluster bootstrap for CIs and paired sign-flip test for p-values.
    
    Returns:
        (mean_adaptive, mean_baseline, mean_diff, std_diff, ci_lower, ci_upper, p_val_numeric, p_val_display)
    """
    rng = np.random.default_rng(seed)
    traj_metrics = results_df.groupby("trajectory_id")[[adaptive_col, baseline_col]].mean()
    traj_ids = traj_metrics.index.to_numpy()
    n_trajs = len(traj_ids)

    adapt_vals = traj_metrics[adaptive_col].to_numpy()
    base_vals = traj_metrics[baseline_col].to_numpy()
    diffs = adapt_vals - base_vals
    mean_diff = float(np.mean(diffs))
    std_diff = float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0

    boot_diffs = np.empty(n_boot)
    for b in range(n_boot):
        sample_idx = rng.choice(n_trajs, size=n_trajs, replace=True)
        boot_diffs[b] = np.mean(diffs[sample_idx])

    ci_lower = float(np.percentile(boot_diffs, 100.0 * (alpha / 2.0)))
    ci_upper = float(np.percentile(boot_diffs, 100.0 * (1.0 - alpha / 2.0)))

    # Paired trajectory-level sign-flip test (10,000 permutations)
    p_val, p_str = trajectory_paired_sign_flip_test(diffs, n_permutations=10_000, seed=seed)

    return float(np.mean(adapt_vals)), float(np.mean(base_vals)), mean_diff, std_diff, ci_lower, ci_upper, p_val, p_str


def main():
    cfg = load_yaml("configs/adaptive.yaml")
    split_mod = cfg["evaluation"]["train_trajectory_split_modulo"]
    n_boot = cfg["evaluation"]["bootstrap_resamples"]
    switching_penalty = cfg["trajectories"].get("switching_penalty_utility", 50.0)

    frame = pd.read_csv("data/policy/policy_dataset.csv")
    frame["mdi_capable"] = frame["mdi_capable"].astype(bool)

    # Train / Test split by trajectory
    train = frame[frame["trajectory_id"] % split_mod != 0].copy()
    test = frame[frame["trajectory_id"] % split_mod == 0].copy()

    with Path("results/adaptive/policy.pkl").open("rb") as f:
        policy = pickle.load(f)

    # Determine Training-Optimal Fixed Action:
    # Closed-loop trajectory simulation across all training trajectories with dynamic key-pool evolution
    all_actions = candidate_actions()
    action_scores: dict[str, float] = {}
    for act in all_actions:
        action_scores[act.name] = simulate_fixed_action_on_trajectories(
            act.name,
            train,
            switching_penalty=switching_penalty,
        )

    training_optimal_action = max(action_scores, key=action_scores.get)

    baseline_definitions = {
        "fixed_bb84_conservative": "decoy_bb84|mu=0.40|nu=0.05|p=0.80|N=10000000000",
        "fixed_bb84_aggressive": "decoy_bb84|mu=0.55|nu=0.10|p=0.90|N=10000000000",
        "fixed_mdi": "mdi_qkd|mu=0.40|nu=0.05|p=0.80|N=10000000000",
        "training_optimal_fixed": training_optimal_action,
        "heuristic_policy": "HEURISTIC",
        "abort_baseline": "ABORT",
    }

    per_scenario_rows = []

    # Closed-loop trajectory evaluation:
    # Each policy advances its own state (key_pool and previous action) step by step
    for traj_id, traj_df in test.groupby("trajectory_id"):
        traj_df = traj_df.sort_values("time_step")
        steps = traj_df.drop_duplicates(subset=["time_step"])
        init_pool = float(steps.iloc[0]["key_pool_bits"])

        adaptive_key_pool = init_pool
        adaptive_prev_act = None

        baseline_pools = {b_name: init_pool for b_name in baseline_definitions}
        baseline_prev_acts = {b_name: None for b_name in baseline_definitions}

        for _, step_row in steps.iterrows():
            context = step_row.to_dict()
            step_id = int(context["time_step"])
            phase = str(context["phase"])
            sid = int(context["scenario_id"])

            # Common Random Number (CRN) seed for this exact trajectory step:
            # BOTH adaptive and all baselines receive the IDENTICAL physical realization!
            crn_seed = int(42 + traj_id * 1000 + step_id)

            # 1. Adaptive Policy Step (closed-loop with its own key pool)
            adapt_ctx = dict(context)
            adapt_ctx["key_pool_bits"] = adaptive_key_pool
            adapt_rec = policy.select(
                adapt_ctx,
                prev_action=adaptive_prev_act,
                switching_penalty=switching_penalty,
            )

            adapt_eval = evaluate_decision_independent(
                adapt_rec,
                adapt_ctx,
                key_pool=adaptive_key_pool,
                prev_action=adaptive_prev_act,
                switching_penalty=switching_penalty,
                seed=crn_seed,
            )
            adaptive_key_pool = adapt_eval["next_key_pool"]
            adaptive_prev_act = adapt_eval["executed"]

            scenario_res = {
                "scenario_id": sid,
                "trajectory_id": traj_id,
                "time_step": step_id,
                "phase": phase,
                "adaptive_action": adapt_eval["executed"],
                "adaptive_utility": adapt_eval["utility"],
                "adaptive_secure_bits": adapt_eval["secure_bits"],
                "adaptive_gate_miss": adapt_eval["predictive_gate_miss"],
                "adaptive_violation": adapt_eval["security_violation"],
            }

            # 2. Baseline Evaluations (closed-loop on identical physical realization)
            for b_name, b_action in baseline_definitions.items():
                b_ctx = dict(context)
                b_ctx["key_pool_bits"] = baseline_pools[b_name]
                act = heuristic_decision(b_ctx) if b_action == "HEURISTIC" else b_action

                b_eval = evaluate_decision_independent(
                    act,
                    b_ctx,
                    key_pool=baseline_pools[b_name],
                    prev_action=baseline_prev_acts[b_name],
                    switching_penalty=switching_penalty,
                    seed=crn_seed,
                )
                baseline_pools[b_name] = b_eval["next_key_pool"]
                baseline_prev_acts[b_name] = b_eval["executed"]

                scenario_res[f"{b_name}_action"] = b_eval["executed"]
                scenario_res[f"{b_name}_utility"] = b_eval["utility"]
                scenario_res[f"{b_name}_bits"] = b_eval["secure_bits"]
                scenario_res[f"{b_name}_gate_miss"] = b_eval["predictive_gate_miss"]
                scenario_res[f"{b_name}_violation"] = b_eval["security_violation"]

            per_scenario_rows.append(scenario_res)

    results_df = pd.DataFrame(per_scenario_rows)
    Path("results/adaptive").mkdir(parents=True, exist_ok=True)
    results_df.to_csv("results/adaptive/heldout_summary.csv", index=False)

    # Statistical Comparison vs Baselines using Trajectory Cluster Bootstrap & Paired Sign-Flip Permutation Test
    stat_comparisons = []
    for b_name in baseline_definitions.keys():
        mean_adapt, mean_base, mean_diff, std_diff, ci_lower, ci_upper, p_val, p_str = trajectory_cluster_bootstrap_ci(
            results_df,
            "adaptive_utility",
            f"{b_name}_utility",
            n_boot=n_boot,
        )
        cohens_d = float(mean_diff / std_diff) if std_diff > 1e-9 else 0.0

        stat_comparisons.append({
            "baseline": b_name,
            "hypothesis_tier": "primary" if b_name == "training_optimal_fixed" else "secondary",
            "mean_adaptive_utility": mean_adapt,
            "mean_baseline_utility": mean_base,
            "mean_paired_difference": mean_diff,
            "std_paired_difference": std_diff,
            "cohens_d": cohens_d,
            "ci_95_lower": ci_lower,
            "ci_95_upper": ci_upper,
            "p_value_raw": p_val,
            "p_value_display": p_str,
            "p_value_adjusted": p_val,
            "p_value_adjusted_display": p_str,
            "baseline_gate_misses": int(results_df[f"{b_name}_gate_miss"].sum()),
            "adaptive_gate_misses": int(results_df["adaptive_gate_miss"].sum()),
            "baseline_violations": int(results_df[f"{b_name}_violation"].sum()),
            "adaptive_violations": int(results_df["adaptive_violation"].sum()),
        })

    # Holm-Bonferroni step-down adjustment on the 5 secondary baselines
    secondary = [r for r in stat_comparisons if r["hypothesis_tier"] == "secondary"]
    secondary.sort(key=lambda r: r["p_value_raw"])
    m = len(secondary)
    cum_max = 0.0
    for i, r in enumerate(secondary):
        adj = min(1.0, (m - i) * r["p_value_raw"])
        cum_max = max(cum_max, adj)
        r["p_value_adjusted"] = cum_max
        r["p_value_adjusted_display"] = "< 0.0001" if cum_max <= 0.0001 else f"{cum_max:.4f}"

    stats_df = pd.DataFrame(stat_comparisons)
    stats_df.to_csv("results/adaptive/baseline_comparisons.csv", index=False)

    # Provenance Logging
    clean_tree = is_working_tree_clean()
    provenance = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": get_git_commit(),
        "working_tree_clean": clean_tree,
        "python_version": sys.version,
        "platform": platform.platform(),
        "policy_dataset_sha256": compute_file_hash("data/policy/policy_dataset.csv"),
        "features": list(ALLOWED_FEATURES),
        "training_optimal_action": training_optimal_action,
        "num_test_scenarios": len(results_df),
        "num_test_trajectories": int(results_df["trajectory_id"].nunique()),
        "bootstrap_method": "trajectory_cluster_bootstrap",
        "p_value_method": "paired_trajectory_sign_flip_permutation_10000",
        "multiple_testing_adjustment": "holm_bonferroni_secondary_baselines",
        "predictive_gate_misses_adaptive": int(results_df["adaptive_gate_miss"].sum()),
        "security_violations_adaptive": int(results_df["adaptive_violation"].sum()),
    }
    Path("results/adaptive/evaluation_provenance.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8"
    )

    print("=== Held-out Adaptive Policy vs 6 Baselines (Cluster Bootstrap CI + 10k Sign-Flip Test) ===")
    print(stats_df[["baseline", "hypothesis_tier", "mean_adaptive_utility", "mean_baseline_utility", "mean_paired_difference", "ci_95_lower", "ci_95_upper", "p_value_display", "p_value_adjusted_display", "cohens_d"]].to_string(index=False))
    print("\nProvenance:")
    print(json.dumps(provenance, indent=2))

    assert not results_df["adaptive_violation"].any(), "Security violation detected in adaptive policy execution!"
    print("\nHeld-out evaluation and baseline comparison PASSED")


if __name__ == "__main__":
    main()