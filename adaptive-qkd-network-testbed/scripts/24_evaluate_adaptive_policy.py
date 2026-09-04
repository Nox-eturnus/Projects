import hashlib
import json
import pickle
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from qkd_lab.adaptive.features import ALLOWED_FEATURES
from qkd_lab.config import load_yaml


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


def evaluate_decision(
    action_name: str,
    scenario_group: pd.DataFrame,
) -> dict:
    """Evaluate an action through the pre-execution gate and realized block outcome."""
    if action_name == "ABORT":
        return {
            "action": "ABORT",
            "executed": "ABORT",
            "utility": 0.0,
            "secure_bits": 0.0,
            "violation": False,
        }

    matches = scenario_group[scenario_group["action_name"] == action_name]
    if matches.empty:
        return {
            "action": action_name,
            "executed": "ABORT",
            "utility": 0.0,
            "secure_bits": 0.0,
            "violation": False,
        }

    candidate = matches.iloc[0]
    # Pre-execution conservative gate
    if (not bool(candidate["feasible"])) or bool(candidate["abort"]):
        return {
            "action": action_name,
            "executed": "ABORT",
            "utility": 0.0,
            "secure_bits": 0.0,
            "violation": False,
        }

    # Executed action outcome
    sec_bits = float(candidate["secure_bits"])
    util = float(candidate["service_utility"])
    # Independent security violation check:
    # An action was executed, but resulted in an abort or non-positive secure key
    violation = bool(candidate["abort"]) or (sec_bits <= 0.0)

    return {
        "action": action_name,
        "executed": action_name,
        "utility": util,
        "secure_bits": sec_bits,
        "violation": violation,
    }


def heuristic_decision(context: dict) -> str:
    qber = float(context["recent_qber"])
    dist = float(context["distance_km"])
    mdi = bool(context["mdi_capable"])

    if qber > 0.08:
        return "ABORT"
    if mdi and dist >= 50.0:
        return "mdi_qkd|mu=0.40|nu=0.05|p=0.80|N=10000000000"
    if qber < 0.03 and dist < 45.0:
        return "decoy_bb84|mu=0.55|nu=0.10|p=0.90|N=100000000000"
    return "decoy_bb84|mu=0.40|nu=0.05|p=0.80|N=10000000000"


def bootstrap_ci(differences: np.ndarray, n_boot: int = 1000, alpha: float = 0.05, seed: int = 42) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    boot_means = np.empty(n_boot)
    n = len(differences)
    for i in range(n_boot):
        sample = rng.choice(differences, size=n, replace=True)
        boot_means[i] = np.mean(sample)
    lower = float(np.percentile(boot_means, 100 * (alpha / 2.0)))
    upper = float(np.percentile(boot_means, 100 * (1.0 - alpha / 2.0)))
    return lower, upper


def main():
    cfg = load_yaml("configs/adaptive.yaml")
    split_mod = cfg["evaluation"]["train_trajectory_split_modulo"]
    n_boot = cfg["evaluation"]["bootstrap_resamples"]

    frame = pd.read_csv("data/policy/policy_dataset.csv")
    frame["mdi_capable"] = frame["mdi_capable"].astype(bool)

    # Train / Test split by trajectory
    train = frame[frame["trajectory_id"] % split_mod != 0].copy()
    test = frame[frame["trajectory_id"] % split_mod == 0].copy()

    with Path("results/adaptive/policy.pkl").open("rb") as f:
        policy = pickle.load(f)

    # Determine Training-Optimal Fixed Action
    train_feasible = train[train["feasible"] & (~train["abort"])]
    training_optimal_action = str(
        train_feasible.groupby("action_name")["service_utility"]
        .mean()
        .sort_values(ascending=False)
        .index[0]
    )

    baseline_definitions = {
        "fixed_bb84_conservative": "decoy_bb84|mu=0.40|nu=0.05|p=0.80|N=10000000000",
        "fixed_bb84_aggressive": "decoy_bb84|mu=0.55|nu=0.10|p=0.90|N=100000000000",
        "fixed_mdi": "mdi_qkd|mu=0.40|nu=0.05|p=0.80|N=10000000000",
        "training_optimal_fixed": training_optimal_action,
        "heuristic_policy": "HEURISTIC",
        "abort_baseline": "ABORT",
    }

    features = list(ALLOWED_FEATURES)
    per_scenario_rows = []

    for sid, group in test.groupby("scenario_id"):
        context = group.iloc[0][features].to_dict()
        traj_id = int(group.iloc[0]["trajectory_id"])
        step_id = int(group.iloc[0]["time_step"])
        phase = str(group.iloc[0]["phase"])

        # 1. Adaptive Policy Evaluation
        adapt_rec = policy.select(context)
        adapt_eval = evaluate_decision(adapt_rec, group)

        # Oracle Best Available
        oracle_rows = group[group["feasible"] & (~group["abort"])]
        oracle_util = float(oracle_rows["service_utility"].max()) if not oracle_rows.empty else 0.0

        scenario_res = {
            "scenario_id": sid,
            "trajectory_id": traj_id,
            "time_step": step_id,
            "phase": phase,
            "oracle_utility": oracle_util,
            "adaptive_action": adapt_eval["executed"],
            "adaptive_utility": adapt_eval["utility"],
            "adaptive_secure_bits": adapt_eval["secure_bits"],
            "adaptive_violation": adapt_eval["violation"],
        }

        # 2. Baseline Evaluations
        for b_name, b_action in baseline_definitions.items():
            act = heuristic_decision(context) if b_action == "HEURISTIC" else b_action
            b_eval = evaluate_decision(act, group)
            scenario_res[f"{b_name}_utility"] = b_eval["utility"]
            scenario_res[f"{b_name}_bits"] = b_eval["secure_bits"]
            scenario_res[f"{b_name}_violation"] = b_eval["violation"]

        per_scenario_rows.append(scenario_res)

    results_df = pd.DataFrame(per_scenario_rows)
    Path("results/adaptive").mkdir(parents=True, exist_ok=True)
    results_df.to_csv("results/adaptive/heldout_summary.csv", index=False)

    # Statistical Comparison vs Baselines
    stat_comparisons = []
    adapt_utils = results_df["adaptive_utility"].to_numpy()

    for b_name in baseline_definitions.keys():
        b_utils = results_df[f"{b_name}_utility"].to_numpy()
        diffs = adapt_utils - b_utils
        mean_diff = float(np.mean(diffs))
        std_diff = float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0
        cohens_d = float(mean_diff / std_diff) if std_diff > 1e-9 else 0.0
        ci_lower, ci_upper = bootstrap_ci(diffs, n_boot=n_boot)

        stat_comparisons.append({
            "baseline": b_name,
            "mean_adaptive_utility": float(np.mean(adapt_utils)),
            "mean_baseline_utility": float(np.mean(b_utils)),
            "mean_paired_difference": mean_diff,
            "std_paired_difference": std_diff,
            "cohens_d": cohens_d,
            "ci_95_lower": ci_lower,
            "ci_95_upper": ci_upper,
            "baseline_violations": int(results_df[f"{b_name}_violation"].sum()),
            "adaptive_violations": int(results_df["adaptive_violation"].sum()),
        })

    stats_df = pd.DataFrame(stat_comparisons)
    stats_df.to_csv("results/adaptive/baseline_comparisons.csv", index=False)

    # Provenance Logging
    provenance = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": get_git_commit(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "policy_dataset_sha256": compute_file_hash("data/policy/policy_dataset.csv"),
        "features": features,
        "training_optimal_action": training_optimal_action,
        "num_test_scenarios": len(results_df),
        "num_test_trajectories": int(results_df["trajectory_id"].nunique()),
        "security_violations_adaptive": int(results_df["adaptive_violation"].sum()),
    }
    Path("results/adaptive/evaluation_provenance.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8"
    )

    print("=== Held-out Adaptive Policy vs 6 Baselines ===")
    print(stats_df[["baseline", "mean_paired_difference", "ci_95_lower", "ci_95_upper", "cohens_d"]].to_string(index=False))
    print("\nProvenance:")
    print(json.dumps(provenance, indent=2))

    assert not results_df["adaptive_violation"].any(), "Security violation detected in adaptive policy execution!"
    print("\nHeld-out evaluation and baseline comparison PASSED")


if __name__ == "__main__":
    main()