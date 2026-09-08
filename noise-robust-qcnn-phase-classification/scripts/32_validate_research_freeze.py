#!/usr/bin/env python
"""Research-freeze validator: internal-consistency checks for the qcnn benchmark.

Exits with code 0 if all implemented research-freeze checks pass.
Exits with code 1 if any check fails.

Design principle: freeze validation verifies that the statistical
PROCEDURE is correct and that artifacts are internally consistent — it
must never demand a particular favorable scientific OUTCOME (e.g. a
significant p-value or a specific hardware accuracy).
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


def check(condition: bool, message: str) -> None:
    if not condition:
        print(f"[FAIL] {message}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"[PASS] {message}")


def _ci_excludes_zero(lo: float, hi: float) -> bool:
    try:
        lo_f, hi_f = float(lo), float(hi)
    except Exception:
        return False
    if np.isnan(lo_f) or np.isnan(hi_f):
        return False
    return bool((lo_f > 0 and hi_f > 0) or (lo_f < 0 and hi_f < 0))


def main():
    print("=== Commencing Automated Research-Freeze Validation ===")

    # 1. Provenance Files Present
    stat_dir = Path("results/statistical_generalization")
    ablation_dir = Path("results/ablations")
    hw_dir = Path("results/hardware")
    report_dir = Path("results/report")

    check((stat_dir / "provenance.json").exists(), "Statistical benchmark provenance.json exists")
    check((ablation_dir / "provenance.json").exists(), "Ablation suite provenance.json exists")
    check((hw_dir / "expressive_hardware_summary.json").exists(), "Hardware summary JSON exists")
    check((hw_dir / "provenance.json").exists(), "Hardware provenance.json exists")
    check((report_dir / "canonical_results.json").exists(), "Canonical results JSON exists")
    check((report_dir / "evaluation_matrix.csv").exists(), "Primary evaluation matrix CSV exists")
    check((report_dir / "generalization_report.md").exists(), "Generalization report Markdown exists")

    # 2. Phase-23 Runs & Telemetry (existence + convergence QUALITY)
    runs_csv = stat_dir / "runs.csv"
    check(runs_csv.exists(), "Phase-23 runs.csv exists")
    df_runs = pd.read_csv(runs_csv)
    check(len(df_runs) == 330, f"Expected 330 Phase-23 benchmark runs, found {len(df_runs)}")

    families = set(df_runs["family"].unique())
    expected_families = {"tfim", "xxz", "cluster"}
    check(expected_families.issubset(families), f"Expected families {expected_families}, found {families}")

    split_types = set(df_runs["split_type"].unique())
    expected_splits = {"iid", "critical_holdout", "parameter_block"}
    check(expected_splits.issubset(split_types), f"Expected splits {expected_splits}, found {split_types}")

    # Telemetry columns must exist and be populated (quality, not just schema).
    opt_fields = [
        "optimizer_success",
        "scipy_optimizer_success",
        "optimizer_message",
        "n_function_evaluations",
        "maxiter_budget",
        "final_train_loss",
        "validation_loss",
        "evaluation_limit_reached",
        "convergence_plateau_detected",
        "convergence_status",
        "fixed_threshold_ba",
        "validation_selected_threshold",
        "validation_selected_test_ba",
        "threshold_shift",
        "roc_auc",
    ]
    for field in opt_fields:
        check(field in df_runs.columns, f"Optimizer / threshold field '{field}' present in runs.csv")
        check(not df_runs[field].isna().all(), f"Optimizer field '{field}' is not entirely NaN in runs.csv")

    # Convergence quality gates: the benchmark is convergence-controlled only
    # if most runs avoid the evaluation limit and reach a converged status.
    scipy_rate = float(df_runs["scipy_optimizer_success"].fillna(False).astype(bool).mean())
    eval_rate = float(df_runs["evaluation_limit_reached"].fillna(False).astype(bool).mean())
    converged = df_runs["convergence_status"].isin(["scipy_converged", "plateau_converged"]).mean()
    print(f"[INFO] Phase-23 scipy success rate: {scipy_rate:.2%}, "
          f"evaluation-limit rate: {eval_rate:.2%}, converged-status rate: {float(converged):.2%}")
    check(scipy_rate >= 0.50,
          f"Phase-23 scipy convergence rate >= 50% (observed {scipy_rate:.2%}); rerun with adaptive looped budget")
    check(eval_rate <= 0.50,
          f"Phase-23 evaluation-limit rate <= 50% (observed {eval_rate:.2%}); runs are not convergence-controlled")
    check(float(converged) >= 0.50,
          f"Phase-23 converged-status rate >= 50% (observed {float(converged):.2%})")

    # 3. Sample-Level Predictions Present
    preds_csv = stat_dir / "test_predictions.csv"
    check(preds_csv.exists(), "Sample-level test_predictions.csv exists")
    df_preds = pd.read_csv(preds_csv)
    check(len(df_preds) > 1000, f"Sample-level predictions populated (found {len(df_preds)} rows)")
    pred_fields = ["family", "split_type", "split_seed", "optimizer_seed", "sample_id", "true_label", "p1", "prediction_at_0_5"]
    for pf in pred_fields:
        check(pf in df_preds.columns, f"Prediction field '{pf}' present in test_predictions.csv")

    # 4. Phase-26 Ablation Telemetry & Fixed-Split Permutation Test
    ablation_runs_csv = ablation_dir / "ablation_runs.csv"
    check(ablation_runs_csv.exists(), "Ablation runs.csv exists")
    df_ablation = pd.read_csv(ablation_runs_csv)

    ablation_opt_fields = [
        "iid_optimizer_success",
        "iid_optimizer_message",
        "iid_n_function_evaluations",
        "iid_maxiter_budget",
        "iid_final_train_loss",
        "iid_validation_loss",
        "critical_optimizer_success",
        "critical_optimizer_message",
        "critical_n_function_evaluations",
        "critical_maxiter_budget",
        "critical_final_train_loss",
        "critical_validation_loss",
    ]
    for aof in ablation_opt_fields:
        check(aof in df_ablation.columns, f"Ablation telemetry field '{aof}' present in ablation_runs.csv")

    # Ablation convergence quality (informational gate: fail while MAXFUN-heavy).
    iid_eval_limited = None
    if "iid_optimizer_message" in df_ablation.columns:
        iid_eval_limited = float(df_ablation["iid_optimizer_message"].str.contains("MAXFUN", na=False).mean())
        print(f"[INFO] Ablation IID MAXFUN termination rate: {iid_eval_limited:.2%}")
        check(iid_eval_limited <= 0.50,
              f"Ablation IID MAXFUN rate <= 50% (observed {iid_eval_limited:.2%}); rerun with corrected convergence loop")

    # Pairwise comparisons table
    pairwise_csv = ablation_dir / "pairwise_comparisons.csv"
    check(pairwise_csv.exists(), "Pairwise comparisons CSV exists")
    df_pairs = pd.read_csv(pairwise_csv)
    check(len(df_pairs) >= 5, f"At least 5 paired ablation comparisons recorded (found {len(df_pairs)})")

    # Fixed-split permutation test: verify PROCEDURE, not outcome.
    # Valid results include non-significant p-values; we check
    #   0 <= p <= 1, n >= 199, and reported_p == (1 + exceedances) / (1 + n).
    pipe_csv = ablation_dir / "pipeline_label_permutations.csv"
    check(pipe_csv.exists(), "Pipeline label permutations CSV exists")
    df_pipe = pd.read_csv(pipe_csv)
    check(len(df_pipe) >= 199, f"Permutation test has N >= 199 permutations, found {len(df_pipe)}")

    ablation_prov = json.loads((ablation_dir / "provenance.json").read_text(encoding="utf-8"))
    n_perms = int(ablation_prov.get("n_permutations_pipeline_test", len(df_pipe)))
    p_val = ablation_prov.get("pipeline_permutation_p_value")
    check(p_val is not None and 0.0 <= float(p_val) <= 1.0,
          f"Permutation p-value is a valid probability in [0, 1] (observed: {p_val})")
    check(n_perms >= 199, f"Permutation test records >= 199 permutations (observed {n_perms})")
    # Recompute exceedances against the true-label reference BA.
    true_ba = ablation_prov.get("shuffled_control_true_ba")
    perm_col = "test_ba_permuted" if "test_ba_permuted" in df_pipe.columns else None
    check(perm_col is not None, "Permutation CSV records per-permutation test BA")
    if perm_col is not None and true_ba is not None:
        n_exceed = int((df_pipe[perm_col].to_numpy(dtype=float) >= float(true_ba)).sum())
        expected_p = float((1 + n_exceed) / (1 + len(df_pipe)))
        check(abs(float(p_val) - expected_p) < 1e-9,
              f"Reported p == (1 + exceedances)/(1 + n) [{n_exceed}/{len(df_pipe)} -> {expected_p:.4f}] (reported {float(p_val):.4f})")
        print(f"[INFO] Permutation: {n_exceed}/{len(df_pipe)} >= observed; "
              f"+1-corrected p = {float(p_val):.4f} (resolution floor {1.0/(len(df_pipe)+1):.4f})")

    check("n_runs_shuffled_control" in ablation_prov, "Shuffled-training-label control documented in provenance")
    check("pipeline_permutation_p_value" in ablation_prov, "Permutation test documented in provenance")

    # Ablation prose vs paired statistics: the conclusion must not
    # contradict the pairwise CIs (this is what let the false
    # "both ablations reduce performance" claim escape before).
    conclusion = str(ablation_prov.get("scientific_conclusion", ""))
    prov_pairs = ablation_prov.get("pairwise_deltas", {})
    if prov_pairs:
        noconv = prov_pairs.get("no_conv_vs_full", {})
        nopool = prov_pairs.get("no_pool_vs_full", {})
        try:
            nc_m = float(noconv.get("delta_crit_mean", float("nan")))
            nc_ci = noconv.get("delta_crit_ci95", (float("nan"), float("nan")))
            np_m = float(nopool.get("delta_crit_mean", float("nan")))
            np_ci = nopool.get("delta_crit_ci95", (float("nan"), float("nan")))
            nc_resolved_neg = _ci_excludes_zero(nc_ci[0], nc_ci[1]) and nc_m < 0
            np_positive = np_m > 0
            text = conclusion.lower()
            check(not (np_positive and "both entanglement ablations reduce" in text),
                  "Ablation prose does not falsely claim both entanglement ablations reduce performance")
            check(nc_resolved_neg or ("statistically resolved degradation" not in text or "convolutional" not in text),
                  "Ablation prose does not falsely claim resolved conv-entanglement degradation")
        except Exception as e:
            check(False, f"Ablation pairwise statistics parseable ({e})")

    # 5. Hardware Provenance: internal CONSISTENCY, not specific outcomes.
    hw_data = json.loads((hw_dir / "expressive_hardware_summary.json").read_text(encoding="utf-8"))
    hw_prov = json.loads((hw_dir / "provenance.json").read_text(encoding="utf-8"))
    check(hw_data.get("is_physical_hardware") is True, "Hardware summary confirms physical hardware execution")
    check(len(hw_data.get("raw_job_id", "")) > 10, "Raw job ID is present and valid")
    check(len(hw_data.get("mitigated_job_id", "")) > 10, "Mitigated job ID is present and valid")
    check(hw_data.get("multi_session_hardware_complete") is False, "multi_session_hardware_complete is accurately False")

    # Stored CI must equal the recomputed Clopper-Pearson interval for the
    # STORED (k, n) — whatever they are — rather than a hard-coded outcome.
    try:
        from qcnn_lab.analysis.binomial_ci import clopper_pearson_interval
        k = int(hw_data["test_correct"])
        n = int(hw_data["test_sample_count"])
        lo, hi = clopper_pearson_interval(k, n, confidence=0.95)
        check(abs(float(hw_data["accuracy_ci95_low"]) - lo) < 1e-9 and abs(float(hw_data["accuracy_ci95_high"]) - hi) < 1e-9,
              f"Stored hardware CI matches recomputed Clopper-Pearson({k}/{n}) = [{lo}, {hi}]")
    except Exception as e:
        check(False, f"Hardware CI recomputation possible ({e})")

    # No fabricated depth/2Q/layout telemetry; full hashes present.
    check(hw_data.get("transpiled_depth_raw") is None, "transpiled_depth_raw is honestly null")
    check(hw_data.get("transpiled_depth_mitigated") is None, "transpiled_depth_mitigated is honestly null")
    check(hw_data.get("two_qubit_count_raw") is None, "two_qubit_count_raw is honestly null")
    check(hw_data.get("two_qubit_count_mitigated") is None, "two_qubit_count_mitigated is honestly null")
    check(hw_data.get("logical_to_physical_layout") is None, "logical_to_physical_layout is honestly null")
    for hfield in ["dataset_hash", "parameter_hash"]:
        hval = hw_data.get(hfield, "")
        check(isinstance(hval, str) and len(hval) == 64,
              f"Hardware {hfield} is a full SHA-256 hex digest")
    for fpath, hval in (hw_data.get("critical_file_hashes", {}) or {}).items():
        check(isinstance(hval, str) and len(hval) == 64,
              f"Hardware file hash for {fpath} is full SHA-256")
    # provenance.json must agree with the summary (no stale contradiction).
    for field in ["transpiled_depth_raw", "transpiled_depth_mitigated",
                  "two_qubit_count_raw", "two_qubit_count_mitigated",
                  "logical_to_physical_layout", "dataset_hash", "parameter_hash",
                  "backend", "raw_job_id", "mitigated_job_id",
                  "test_sample_count", "test_correct"]:
        check(hw_prov.get(field) == hw_data.get(field),
              f"Hardware provenance.json agrees with summary on '{field}'")

    # 6. Canonical Results & Synchronization Consistency
    canonical = json.loads((report_dir / "canonical_results.json").read_text(encoding="utf-8"))
    check(canonical.get("status") in ["RESEARCH_FROZEN", "ADVANCED_BENCHMARK_PRELIMINARY"], "Canonical status is valid")
    check(canonical["statistical_benchmark"]["total_runs_recorded"] == 330, "Canonical benchmark records 330 runs")
    check(canonical["pipeline_permutation"]["n_permutations"] >= 199, "Canonical permutation test records >= 199 permutations")
    # RESEARCH_FROZEN must mean validated — blockers must be empty.
    if canonical.get("status") == "RESEARCH_FROZEN":
        check(len(canonical.get("freeze_blockers", [])) == 0,
              f"RESEARCH_FROZEN declared with no freeze blockers (found {canonical.get('freeze_blockers')})")

    # 7. README Sync Consistency
    readme_text = Path("README.md").read_text(encoding="utf-8")
    check("<!-- BEGIN AUTO RESULTS: PRIMARY_MATRIX -->" in readme_text, "README contains PRIMARY_MATRIX block")
    check("<!-- BEGIN AUTO RESULTS: ABLATIONS -->" in readme_text, "README contains ABLATIONS block")
    check("<!-- BEGIN AUTO RESULTS: HARDWARE -->" in readme_text, "README contains HARDWARE block")
    check("<!-- BEGIN AUTO RESULTS: BUDGET -->" in readme_text, "README contains BUDGET block")
    check("| nan |" not in readme_text, "README tables do not contain '| nan |' string")
    # No stale hardware claims contradicting the null-telemetry artifact.
    check("depth \u2248119" not in readme_text and "depth ≈119" not in readme_text,
          "README does not claim stale transpiled depth 119 for the historical run")
    check("38 CNOT" not in readme_text, "README does not claim stale 38-CNOT count for the historical run")

    print("\n[ALL PASS] All implemented research-freeze checks passed!")


if __name__ == "__main__":
    main()
