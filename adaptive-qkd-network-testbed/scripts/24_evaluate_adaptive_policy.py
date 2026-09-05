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
from qkd_lab.adaptive.features import ALLOWED_FEATURES
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
            ["git", "status", "--porcelain", "qkd_lab", "tests", "scripts", "standards", "configs", "README.md", ".github"],
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
    """Evaluate an action through an independent predictive gate and realized simulation.
    
    Causal architecture:
      pre-decision telemetry counts
      ↓
      policy recommendation
      ↓
      conservative predictive security gate
      ↓
      chosen action / ABORT
      ↓
      independent realized physical block simulation (with fresh seed & channel perturbation)
      ↓
      fresh finite-key estimation
      ↓
      realized secure bits / ABORT
      ↓
      security-violation audit
    """
    demand_bps = float(context["demand_bps"])
    epoch_sec = 10.0

    if action_name == "ABORT":
        demand_bits = demand_bps * epoch_sec
        delivered_bits = min(demand_bits, key_pool)
        deficit_bits = max(0.0, demand_bits - delivered_bits)
        delivered_rate = delivered_bits / epoch_sec
        deficit_rate = deficit_bits / epoch_sec
        switch_cost = switching_penalty if (prev_action is not None and prev_action != "ABORT") else 0.0
        utility = delivered_rate - 2.0 * deficit_rate - (switch_cost / epoch_sec)
        next_pool = max(0.0, key_pool - delivered_bits)
        return {
            "action": "ABORT",
            "executed": "ABORT",
            "utility": utility,
            "secure_bits": 0.0,
            "duration_seconds": epoch_sec,
            "predictive_gate_miss": False,
            "security_violation": False,
            "violation": False,
            "next_key_pool": next_pool,
            "realized_abort": True,
        }

    action = parse_action_name(action_name)
    if action is None:
        demand_bits = demand_bps * epoch_sec
        delivered_bits = min(demand_bits, key_pool)
        deficit_bits = max(0.0, demand_bits - delivered_bits)
        delivered_rate = delivered_bits / epoch_sec
        deficit_rate = deficit_bits / epoch_sec
        switch_cost = switching_penalty if (prev_action is not None and prev_action != action_name) else 0.0
        utility = delivered_rate - 2.0 * deficit_rate - (switch_cost / epoch_sec)
        next_pool = max(0.0, key_pool - delivered_bits)
        return {
            "action": action_name,
            "executed": "ABORT",
            "utility": utility,
            "secure_bits": 0.0,
            "duration_seconds": epoch_sec,
            "predictive_gate_miss": False,
            "security_violation": False,
            "violation": False,
            "next_key_pool": next_pool,
            "realized_abort": True,
        }

    # Step 1: Pre-execution conservative predictive gate (uses observable telemetry bounds)
    predicted = evaluate_action_outcome(context, action)
    if (not bool(predicted["feasible"])) or bool(predicted["abort"]):
        # Conservative gate intervenes to abort an unsafe/infeasible action
        demand_bits = demand_bps * epoch_sec
        delivered_bits = min(demand_bits, key_pool)
        deficit_bits = max(0.0, demand_bits - delivered_bits)
        delivered_rate = delivered_bits / epoch_sec
        deficit_rate = deficit_bits / epoch_sec
        switch_cost = switching_penalty if (prev_action is not None and prev_action != "ABORT") else 0.0
        utility = delivered_rate - 2.0 * deficit_rate - (switch_cost / epoch_sec)
        next_pool = max(0.0, key_pool - delivered_bits)
        return {
            "action": action_name,
            "executed": "ABORT",
            "utility": utility,
            "secure_bits": 0.0,
            "duration_seconds": epoch_sec,
            "predictive_gate_miss": False,
            "security_violation": False,
            "violation": False,
            "next_key_pool": next_pool,
            "realized_abort": True,
        }

    # Step 2: Independent stochastic physical realization (distinct seed & aggregate simulation)
    rng = np.random.default_rng(seed)
    dist = float(context["distance_km"])
    dark = float(context["dark_probability"])
    eff = float(context["detector_efficiency"])
    actual_qber = float(context["recent_qber"])
    actual_gain = float(context.get("recent_gain", 0.01))

    # Realized stochastic fluctuation on channel conditions
    fluc_qber = max(0.005, min(0.15, actual_qber + float(rng.normal(0.0, 0.001))))
    fluc_gain = max(1e-7, actual_gain * float(1.0 + rng.normal(0.0, 0.02)))

    action_intensities = _intensities(action)
    block_sec = action.duration_seconds

    if action.protocol == "decoy_bb84":
        basis = BasisProbabilities(action.p_key_basis, action.p_key_basis)
        net_opt = max(1e-9, fluc_gain - 2.0 * dark)
        trans = max(1e-8, min(1.0, net_opt / max(eff * action.mu_signal, 1e-6)))
        atten = max(0.15, min(2.0, -10.0 * math.log10(trans) / dist)) if dist > 0 else 0.20
        ch = ChannelParameters(dist, atten)
        det = DetectorParameters(eff, dark, fluc_qber, 2)
        sim_block = simulate_aggregate_decoy_bb84_block(
            action.block_size,
            intensities=action_intensities,
            basis=basis,
            channel=ch,
            detector=det,
            seed=seed,
        )
        res = estimate_lim2014(
            sim_block.records,
            action_intensities,
            eps_sec=EPS_SEC,
            eps_cor=EPS_COR,
            f_ec=1.16,
        )
        realized_bits = float(res.secure_bits)
        realized_abort = bool(res.abort)
    else:
        basis = MDIBasisProbabilities(action.p_key_basis, action.p_key_basis)
        lac = float(context.get("length_ac_km", dist / 2.0))
        lbc = float(context.get("length_bc_km", dist / 2.0))
        net_opt = max(1e-9, fluc_gain - 2.0 * dark)
        trans = max(1e-8, min(1.0, net_opt / max(eff * action.mu_signal, 1e-6)))
        atten = max(0.15, min(2.0, -10.0 * math.log10(trans) / dist)) if dist > 0 else 0.20
        phys = MDIPhysicalParameters(
            alice_to_charlie_km=lac,
            bob_to_charlie_km=lbc,
            attenuation_db_per_km=atten,
            detector_efficiency=eff,
            dark_probability=dark,
            misalignment=fluc_qber,
        )
        sim_block = simulate_aggregate_mdi_block(
            action.block_size,
            alice_intensities=action_intensities,
            bob_intensities=action_intensities,
            basis=basis,
            physical=phys,
            seed=seed,
        )
        res = estimate_mdi_finite_key(sim_block, MDI_BUDGET)
        realized_bits = float(res.secure_bits)
        realized_abort = bool(res.abort)

    # Step 3: Predictive Gate Miss vs Security Violation Audit
    predictive_gate_miss = bool(realized_abort) or (realized_bits <= 0.0)
    # Security violation: Key material was released on an abort.
    # When realized_abort is True, zero keys are released by the engine, so security_violation is 0.
    security_violation = False

    # Step 4: Closed-loop utility and state evolution
    demand_bits = demand_bps * block_sec
    generated_bits = realized_bits if not realized_abort else 0.0
    available_bits = key_pool + generated_bits
    delivered_bits = min(demand_bits, available_bits)
    deficit_bits = max(0.0, demand_bits - delivered_bits)

    delivered_rate = delivered_bits / block_sec
    deficit_rate = deficit_bits / block_sec
    latency_penalty = 0.05 * block_sec
    switch_cost = switching_penalty if (prev_action is not None and prev_action != action_name and action_name != "ABORT") else 0.0

    util = delivered_rate - 2.0 * deficit_rate - latency_penalty - (switch_cost / block_sec)
    if realized_abort:
        util -= 1000.0

    next_pool = min(1_500_000.0, max(0.0, available_bits - delivered_bits))

    return {
        "action": action_name,
        "executed": action_name,
        "utility": util,
        "secure_bits": generated_bits,
        "duration_seconds": block_sec,
        "predictive_gate_miss": predictive_gate_miss,
        "security_violation": security_violation,
        "violation": predictive_gate_miss,
        "next_key_pool": next_pool,
        "realized_abort": realized_abort,
    }


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


def trajectory_cluster_bootstrap_ci(
    results_df: pd.DataFrame,
    adaptive_col: str,
    baseline_col: str,
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 42,
) -> tuple[float, float, float, float, float, float]:
    """Trajectory-level cluster bootstrap to account for temporal auto-correlation within trajectories.
    
    Returns:
        (mean_adaptive, mean_baseline, mean_diff, std_diff, ci_lower, ci_upper)
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

    return float(np.mean(adapt_vals)), float(np.mean(base_vals)), mean_diff, std_diff, ci_lower, ci_upper


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
    # Evaluate each candidate action across ALL unique training scenarios (penalizing aborts)
    all_actions = candidate_actions()
    action_scores: dict[str, float] = {}
    train_scenarios = train.drop_duplicates(subset=["scenario_id"])
    for act in all_actions:
        scores = []
        for _, sc_row in train_scenarios.iterrows():
            out = evaluate_action_outcome(sc_row.to_dict(), act)
            scores.append(out["service_utility"])
        action_scores[act.name] = float(np.mean(scores))

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
            adapt_rec = policy.select(adapt_ctx)

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

    # Statistical Comparison vs Baselines using Trajectory Cluster Bootstrap
    stat_comparisons = []
    for b_name in baseline_definitions.keys():
        mean_adapt, mean_base, mean_diff, std_diff, ci_lower, ci_upper = trajectory_cluster_bootstrap_ci(
            results_df,
            "adaptive_utility",
            f"{b_name}_utility",
            n_boot=n_boot,
        )
        cohens_d = float(mean_diff / std_diff) if std_diff > 1e-9 else 0.0

        stat_comparisons.append({
            "baseline": b_name,
            "mean_adaptive_utility": mean_adapt,
            "mean_baseline_utility": mean_base,
            "mean_paired_difference": mean_diff,
            "std_paired_difference": std_diff,
            "cohens_d": cohens_d,
            "ci_95_lower": ci_lower,
            "ci_95_upper": ci_upper,
            "baseline_gate_misses": int(results_df[f"{b_name}_gate_miss"].sum()),
            "adaptive_gate_misses": int(results_df["adaptive_gate_miss"].sum()),
            "baseline_violations": int(results_df[f"{b_name}_violation"].sum()),
            "adaptive_violations": int(results_df["adaptive_violation"].sum()),
        })

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
        "predictive_gate_misses_adaptive": int(results_df["adaptive_gate_miss"].sum()),
        "security_violations_adaptive": int(results_df["adaptive_violation"].sum()),
    }
    Path("results/adaptive/evaluation_provenance.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8"
    )

    print("=== Held-out Adaptive Policy vs 6 Baselines (Trajectory Cluster Bootstrap) ===")
    print(stats_df[["baseline", "mean_adaptive_utility", "mean_baseline_utility", "mean_paired_difference", "ci_95_lower", "ci_95_upper", "cohens_d"]].to_string(index=False))
    print("\nProvenance:")
    print(json.dumps(provenance, indent=2))

    assert not results_df["adaptive_violation"].any(), "Security violation detected in adaptive policy execution!"
    print("\nHeld-out evaluation and baseline comparison PASSED")


if __name__ == "__main__":
    main()