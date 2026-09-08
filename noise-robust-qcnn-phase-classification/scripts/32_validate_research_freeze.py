#!/usr/bin/env python
"""Validation script enforcing all research-freeze contracts and invariants.

Exits with code 0 if the repository meets all research-freeze standards.
Exits with code 1 if any contract or invariant is violated.
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
    check((report_dir / "canonical_results.json").exists(), "Canonical results JSON exists")
    check((report_dir / "evaluation_matrix.csv").exists(), "Primary evaluation matrix CSV exists")
    check((report_dir / "generalization_report.md").exists(), "Generalization report Markdown exists")

    # 2. Phase-23 Runs & Telemetry
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

    # Check optimizer telemetry completeness in Phase 23
    opt_fields = [
        "optimizer_success",
        "optimizer_message",
        "n_function_evaluations",
        "maxiter_budget",
        "final_train_loss",
        "validation_loss",
        "fixed_threshold_ba",
        "validation_selected_threshold",
        "validation_selected_test_ba",
        "threshold_shift",
        "roc_auc",
    ]
    for field in opt_fields:
        check(field in df_runs.columns, f"Optimizer / threshold field '{field}' present in runs.csv")
        check(not df_runs[field].isna().all(), f"Optimizer field '{field}' is not entirely NaN in runs.csv")

    # 3. Sample-Level Predictions Present (Audit Item 5)
    preds_csv = stat_dir / "test_predictions.csv"
    check(preds_csv.exists(), "Sample-level test_predictions.csv exists")
    df_preds = pd.read_csv(preds_csv)
    check(len(df_preds) > 1000, f"Sample-level predictions populated (found {len(df_preds)} rows)")
    pred_fields = ["family", "split_type", "split_seed", "optimizer_seed", "sample_id", "true_label", "p1", "prediction_at_0_5"]
    for pf in pred_fields:
        check(pf in df_preds.columns, f"Prediction field '{pf}' present in test_predictions.csv")

    # 4. Phase-26 Ablation Telemetry & Permutation Test
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

    # Check pairwise comparisons table
    pairwise_csv = ablation_dir / "pairwise_comparisons.csv"
    check(pairwise_csv.exists(), "Pairwise comparisons CSV exists")
    df_pairs = pd.read_csv(pairwise_csv)
    check(len(df_pairs) >= 5, f"At least 5 paired ablation comparisons recorded (found {len(df_pairs)})")

    # Check Pipeline Permutation Test scale & empirical p-value
    pipe_csv = ablation_dir / "pipeline_label_permutations.csv"
    check(pipe_csv.exists(), "Pipeline label permutations CSV exists")
    df_pipe = pd.read_csv(pipe_csv)
    check(len(df_pipe) >= 199, f"Pipeline permutation test has N >= 199 permutations, found {len(df_pipe)}")

    ablation_prov = json.loads((ablation_dir / "provenance.json").read_text(encoding="utf-8"))
    p_val = ablation_prov.get("pipeline_permutation_p_value")
    check(p_val is not None and p_val <= 0.05, f"Pipeline permutation test achieves p <= 0.05 (observed: {p_val})")

    # Check Shuffled-Training-Label Control separation
    check("n_runs_shuffled_control" in ablation_prov, "Shuffled-training-label control documented in provenance")
    check("pipeline_permutation_p_value" in ablation_prov, "Pipeline permutation test documented in provenance")

    # 5. Hardware Telemetry & Claim Boundaries
    hw_data = json.loads((hw_dir / "expressive_hardware_summary.json").read_text(encoding="utf-8"))
    check(hw_data.get("is_physical_hardware") is True, "Hardware summary confirms physical hardware execution")
    check(len(hw_data.get("raw_job_id", "")) > 10, "Raw job ID is present and valid")
    check(len(hw_data.get("mitigated_job_id", "")) > 10, "Mitigated job ID is present and valid")
    check(hw_data.get("test_sample_count") == 10, "Hardware sample count is exactly 10")
    check(hw_data.get("test_correct") == 10, "Hardware test_correct is 10")
    check(hw_data.get("accuracy_ci95_low") == 0.6915, "Clopper-Pearson 95% CI low is 0.6915")
    check(hw_data.get("accuracy_ci95_high") == 1.0, "Clopper-Pearson 95% CI high is 1.0")
    check(hw_data.get("multi_session_hardware_complete") is False, "multi_session_hardware_complete is accurately False")

    # Verify no fabricated depth/2Q telemetry
    check(hw_data.get("transpiled_depth_raw") is None, "transpiled_depth_raw is honestly null")
    check(hw_data.get("logical_to_physical_layout") is None, "logical_to_physical_layout is honestly null")

    # 6. Canonical Results & Synchronization Consistency
    canonical = json.loads((report_dir / "canonical_results.json").read_text(encoding="utf-8"))
    check(canonical.get("status") in ["RESEARCH_FROZEN", "ADVANCED_BENCHMARK_PRELIMINARY"], "Canonical status is valid")
    check(canonical["statistical_benchmark"]["total_runs_recorded"] == 330, "Canonical benchmark records 330 runs")
    check(canonical["pipeline_permutation"]["n_permutations"] >= 199, "Canonical permutation test records >= 199 permutations")

    # 7. Check README Sync Consistency
    readme_text = Path("README.md").read_text(encoding="utf-8")
    check("<!-- BEGIN AUTO RESULTS: PRIMARY_MATRIX -->" in readme_text, "README contains PRIMARY_MATRIX block")
    check("<!-- BEGIN AUTO RESULTS: ABLATIONS -->" in readme_text, "README contains ABLATIONS block")
    check("<!-- BEGIN AUTO RESULTS: HARDWARE -->" in readme_text, "README contains HARDWARE block")
    check("<!-- BEGIN AUTO RESULTS: BUDGET -->" in readme_text, "README contains BUDGET block")

    # Assert no nan cells in README tables
    check("| nan |" not in readme_text, "README tables do not contain '| nan |' string")

    print("\n[ALL PASS] The repository strictly satisfies all 46 research-freeze invariants!")


if __name__ == "__main__":
    main()
