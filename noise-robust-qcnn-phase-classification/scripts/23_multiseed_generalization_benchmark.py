from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score

from qcnn_lab.analysis.calibration import (
    brier_score,
    calibration_curve,
    expected_calibration_error,
    negative_log_likelihood,
)
from qcnn_lab.analysis.splits import load_split_manifest, split_indices_from_manifest
from qcnn_lab.analysis.statistics import (
    aggregate_hierarchical_statistics,
    aggregate_statistics,
    bootstrap_metric_ci,
    hierarchical_bootstrap,
)
from qcnn_lab.analysis.thresholds import (
    classify_generalization_regime,
    evaluate_at_threshold,
    find_optimal_threshold,
    score_distribution_summary,
    ValidationCalibrator,
)
from qcnn_lab.config import load_yaml
from qcnn_lab.metrics import binary_metrics
from qcnn_lab.provenance import compute_file_hashes, get_git_provenance
from qcnn_lab.qcnn.architecture import get_architecture
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.train import train_ideal_qcnn


def _run_single_benchmark_task(
    family: str,
    split_type: str,
    s_seed: int,
    opt_seed: int,
    data_dir: Path,
    splits_dir: Path,
    n_qubits: int,
    arch,
    maxiter: int,
) -> tuple[dict, list[dict], list[dict]]:
    states = np.load(data_dir / f"{family}_eval_states.npz")["states"]
    meta = pd.read_csv(data_dir / f"{family}_eval_metadata.csv")
    y = meta["label"].to_numpy(dtype=int)

    prefix = "critical" if "critical" in split_type else ("block" if "block" in split_type else "iid")
    manifest_name = f"{family}_{prefix}_seed{s_seed}.csv"
    manifest_path = splits_dir / manifest_name
    manifest = load_split_manifest(manifest_path)
    indices = split_indices_from_manifest(manifest)

    params, history, sec = train_ideal_qcnn(
        states,
        y,
        n_qubits,
        arch,
        indices.train,
        indices.validation,
        maxiter=maxiter,
        seed=opt_seed,
    )
    last_opt = history[-1]

    # Validation predictions & validation-only threshold selection (Audit Item 5)
    val_p = batch_predict(states[indices.validation], params, arch, n_qubits)
    y_val = y[indices.validation]
    t_star = find_optimal_threshold(y_val, val_p)

    # Test predictions
    test_p = batch_predict(states[indices.test], params, arch, n_qubits)
    y_test = y[indices.test]

    # Standard metrics at fixed 0.5 threshold
    m_fixed = binary_metrics(y_test, test_p)
    nll = negative_log_likelihood(y_test, test_p)
    bs = brier_score(y_test, test_p)
    ece = expected_calibration_error(y_test, test_p)

    # Validation-selected threshold evaluation on untouched test set
    m_val_thresh = evaluate_at_threshold(y_test, test_p, threshold=t_star)

    # Platt recalibration fitted strictly on validation set (Audit Item 6)
    val_cal = ValidationCalibrator().fit(y_val, val_p)
    cal_test_p = val_cal.predict_proba(test_p)
    cal_ba = float(balanced_accuracy_score(y_test, (cal_test_p >= 0.5).astype(int)))

    # Score distribution analysis
    s_dist = score_distribution_summary(y_test, test_p)

    run_record = {
        "family": family,
        "split_type": split_type,
        "split_seed": s_seed,
        "optimizer_seed": opt_seed,
        "accuracy": m_fixed.accuracy,
        "balanced_accuracy": m_fixed.balanced_accuracy,
        "f1": m_fixed.f1,
        "roc_auc": m_fixed.roc_auc,
        "cross_entropy": nll,
        "brier_score": bs,
        "ece": ece,
        "fixed_threshold_ba": m_fixed.balanced_accuracy,
        "validation_selected_threshold": t_star,
        "validation_selected_test_ba": m_val_thresh["balanced_accuracy"],
        "threshold_shift": t_star - 0.5,
        "recalibrated_ba": cal_ba,
        "mean_score_class_0": s_dist["mean_score_class_0"],
        "mean_score_class_1": s_dist["mean_score_class_1"],
        "score_separation": s_dist["score_separation"],
        "optimizer_success": last_opt.get("optimizer_success", False),
        "scipy_optimizer_success": last_opt.get("scipy_optimizer_success", False),
        "optimizer_message": str(last_opt.get("optimizer_message", "")),
        "termination_reason": str(last_opt.get("termination_reason", "")),
        "n_function_evaluations": int(last_opt.get("nfev", 0)),
        "maxiter_budget": int(last_opt.get("maxiter_budget", maxiter if maxiter else 120)),
        "initial_train_loss": float(last_opt.get("initial_train_loss", np.nan)),
        "best_train_loss": float(last_opt.get("best_train_loss", np.nan)),
        "final_train_loss": float(last_opt.get("final_train_loss", np.nan)),
        "validation_loss": float(last_opt.get("validation_loss", np.nan)),
        "loss_improvement": float(last_opt.get("loss_improvement", np.nan)),
        "last_10_eval_improvement": float(last_opt.get("last_10_eval_improvement", np.nan)),
        "evaluation_limit_reached": bool(last_opt.get("evaluation_limit_reached", False)),
        "convergence_plateau_detected": bool(last_opt.get("convergence_plateau_detected", False)),
        "training_time": sec,
    }

    sample_preds = []
    for idx_pos, sample_idx in enumerate(indices.test):
        sample_preds.append({
            "family": family,
            "split_type": split_type,
            "split_seed": s_seed,
            "optimizer_seed": opt_seed,
            "sample_id": int(sample_idx),
            "true_label": int(y_test[idx_pos]),
            "p1": float(test_p[idx_pos]),
            "prediction_at_0_5": int(test_p[idx_pos] >= 0.5),
        })

    calibrations = []
    accs, confs, counts = calibration_curve(y_test, test_p, n_bins=10)
    for b_idx in range(len(counts)):
        calibrations.append({
            "family": family,
            "split_type": split_type,
            "bin": b_idx,
            "accuracy": accs[b_idx],
            "confidence": confs[b_idx],
            "count": counts[b_idx],
        })

    return run_record, sample_preds, calibrations


def main():
    parser = argparse.ArgumentParser(description="Multi-split x multi-optimizer statistical benchmark.")
    parser.add_argument("--fast", action="store_true", help="Run fast 3x3 smoke benchmark")
    parser.add_argument("--config", default="configs/evaluation.yaml", help="Evaluation config path")
    parser.add_argument("--project-config", default="configs/project.yaml", help="Project config path")
    parser.add_argument("--out-dir", default="results/statistical_generalization", help="Output directory")
    parser.add_argument("--fig-dir", default="results/figures", help="Figure output directory")
    parser.add_argument("--maxiter", type=int, default=None, help="Override maxiter for optimization")
    parser.add_argument("--n-jobs", type=int, default=8, help="Number of parallel worker processes")
    args = parser.parse_args()

    eval_cfg = load_yaml(args.config)["evaluation"]
    proj_cfg = load_yaml(args.project_config)

    n_qubits = int(proj_cfg.get("n_qubits", 8))
    arch = get_architecture(proj_cfg.get("qcnn", {}).get("architecture", "expressive_shared_line"))
    # In full benchmark, use adaptive budget from convergence policy if not specified
    maxiter = args.maxiter if args.maxiter is not None else (30 if args.fast else 150)

    if args.fast:
        split_seeds = [11, 23]
        optimizer_seeds = [100, 200]
        split_types = ["iid", "critical_holdout"]
        families = ["tfim"]
    else:
        split_seeds = [int(s) for s in eval_cfg["split_seeds"]]
        optimizer_seeds = [100, 200, 300, 400, 500]
        split_types = ["iid", "parameter_block", "critical_holdout"]
        families = ["tfim", "xxz", "cluster"]

    out_dir = Path(args.out_dir)
    fig_dir = Path(args.fig_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    data_dir = Path("data/processed")
    splits_dir = Path("results/evaluation_splits")

    runs = []
    sample_preds = []
    all_calibrations = []

    tasks = []
    for family in families:
        for split_type in split_types:
            if split_type == "parameter_block":
                split_seeds_to_use = [11]
                opt_seeds_to_use = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000] if not args.fast else [100, 200]
            else:
                split_seeds_to_use = split_seeds
                opt_seeds_to_use = optimizer_seeds

            for s_seed in split_seeds_to_use:
                for opt_seed in opt_seeds_to_use:
                    tasks.append((family, split_type, s_seed, opt_seed))

    print(f"Executing {len(tasks)} benchmark runs with n_jobs={args.n_jobs}...")
    if args.n_jobs > 1:
        from joblib import Parallel, delayed
        results = Parallel(n_jobs=args.n_jobs)(
            delayed(_run_single_benchmark_task)(
                fam, stype, s_seed, opt_seed, data_dir, splits_dir, n_qubits, arch, maxiter
            )
            for fam, stype, s_seed, opt_seed in tasks
        )
    else:
        results = [
            _run_single_benchmark_task(
                fam, stype, s_seed, opt_seed, data_dir, splits_dir, n_qubits, arch, maxiter
            )
            for fam, stype, s_seed, opt_seed in tasks
        ]

    for r_rec, s_preds, c_data in results:
        runs.append(r_rec)
        sample_preds.extend(s_preds)
        all_calibrations.extend(c_data)

    runs_df = pd.DataFrame(runs)
    runs_df.to_csv(out_dir / "runs.csv", index=False)
    print(f"Recorded {len(runs_df)} individual experimental runs.")

    # Save sample-level predictions (Audit Item 5)
    preds_df = pd.DataFrame(sample_preds)
    preds_df.to_csv(out_dir / "test_predictions.csv", index=False)
    print(f"Saved {len(preds_df)} sample-level predictions to {out_dir / 'test_predictions.csv'}")

    # Aggregate summaries across (family, split_type) using Hierarchical Bootstrap (Audit Items 7 & 8)
    agg_rows = []
    ci_dict = {}

    metrics_to_aggregate = [
        "balanced_accuracy",
        "accuracy",
        "f1",
        "roc_auc",
        "fixed_threshold_ba",
        "validation_selected_test_ba",
        "recalibrated_ba",
        "score_separation",
        "mean_score_class_0",
        "mean_score_class_1",
        "brier_score",
        "cross_entropy",
        "ece",
    ]

    for (fam, s_type), grp in runs_df.groupby(["family", "split_type"]):
        key = f"{fam}_{s_type}"
        ci_dict[key] = {}
        n_partitions = int(grp["split_seed"].nunique())
        n_opt_seeds = int(grp["optimizer_seed"].nunique())

        is_single_partition = (n_partitions == 1)
        spatial_note = (
            "optimizer-seed variability on one canonical spatial block"
            if is_single_partition
            else f"hierarchical bootstrap across {n_partitions} spatial partitions"
        )

        row = {
            "family": fam,
            "split_type": s_type,
            "n_partitions": n_partitions,
            "n_spatial_partitions": n_partitions,
            "n_optimizer_seeds": n_opt_seeds,
            "n_runs": len(grp),
            "spatial_uncertainty_note": spatial_note,
        }

        for metric in metrics_to_aggregate:
            h_stats = aggregate_hierarchical_statistics(
                grp,
                partition_col="split_seed",
                optimizer_col="optimizer_seed",
                value_col=metric,
                n_boot=5000,
                confidence=0.95,
            )
            row[f"{metric}_mean"] = h_stats["mean"]
            row[f"{metric}_std"] = h_stats["std"]
            row[f"{metric}_median"] = h_stats["median"]
            row[f"{metric}_ci95_low"] = h_stats["hierarchical_ci_low"]
            row[f"{metric}_ci95_high"] = h_stats["hierarchical_ci_high"]
            row[f"{metric}_flat_ci95_low"] = h_stats["naive_flat_ci_low"]
            row[f"{metric}_flat_ci95_high"] = h_stats["naive_flat_ci_high"]

            ci_dict[key][metric] = {
                "mean": h_stats["mean"],
                "std": h_stats["std"],
                "hierarchical_ci95": [h_stats["hierarchical_ci_low"], h_stats["hierarchical_ci_high"]],
                "naive_flat_ci95": [h_stats["naive_flat_ci_low"], h_stats["naive_flat_ci_high"]],
            }

        # Scientific classification of regime (Audit Item 26)
        auc_m = row.get("roc_auc_mean", 0.5)
        fixed_ba_m = row.get("balanced_accuracy_mean", 0.5)
        adj_ba_m = row.get("validation_selected_test_ba_mean", fixed_ba_m)
        sep_m = row.get("score_separation_mean", 0.0)
        row["generalization_regime"] = classify_generalization_regime(auc_m, fixed_ba_m, adj_ba_m, sep_m)

        agg_rows.append(row)

    agg_df = pd.DataFrame(agg_rows)
    agg_df.to_csv(out_dir / "aggregate.csv", index=False)
    (out_dir / "confidence_intervals.json").write_text(json.dumps(ci_dict, indent=2), encoding="utf-8")

    # Save Provenance JSON (Audit Items 38 & 39)
    git_info = get_git_provenance()
    critical_input_files = [
        "configs/project.yaml",
        "configs/evaluation.yaml",
        "data/processed/tfim_eval_states.npz",
        "data/processed/xxz_eval_states.npz",
        "data/processed/cluster_eval_states.npz",
        "qcnn_lab/qcnn/architecture.py",
        "qcnn_lab/qcnn/train.py",
        "qcnn_lab/qcnn/evaluate.py",
        "scripts/23_multiseed_generalization_benchmark.py",
    ]

    split_design = {}
    for s_type, grp in runs_df.groupby("split_type"):
        split_design[s_type] = {
            "n_partitions": int(grp["split_seed"].nunique()),
            "n_optimizer_seeds": int(grp["optimizer_seed"].nunique()),
            "total_runs": int(len(grp)),
        }

    provenance = {
        "git_provenance": git_info,
        "git_commit": git_info["execution_git_commit"] or git_info["base_commit"],
        "base_commit": git_info["base_commit"],
        "working_tree_dirty": git_info["working_tree_dirty"],
        "input_file_hashes": compute_file_hashes(critical_input_files, full_sha256=True),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execution_mode": "fast" if args.fast else "full",
        "python_version": sys.version,
        "n_qubits": n_qubits,
        "optimizer": "COBYLA",
        "maxiter": maxiter,
        "families": families,
        "split_types": split_types,
        "split_design": split_design,
        "total_runs_recorded": len(runs_df),
        "sample_predictions_path": "results/statistical_generalization/test_predictions.csv",
        "threshold_selection_protocol": "validation-only argmax BA(t) in (0, 1) evaluated on test set",
        "script": "scripts/23_multiseed_generalization_benchmark.py",
    }
    with open(out_dir / "provenance.json", "w") as f:
        json.dump(provenance, f, indent=2)

    cal_df = pd.DataFrame(all_calibrations)
    cal_df.to_csv(out_dir / "calibration.csv", index=False)

    # 1. Boxplot of Balanced Accuracy
    plt.figure(figsize=(9, 5))
    groups = []
    labels_box = []
    for (fam, s_type), grp in runs_df.groupby(["family", "split_type"]):
        groups.append(grp["balanced_accuracy"].to_numpy())
        labels_box.append(f"{fam.upper()}\n{s_type}")
    try:
        plt.boxplot(groups, tick_labels=labels_box, patch_artist=True)
    except TypeError:
        plt.boxplot(groups, labels=labels_box, patch_artist=True)
    plt.title("Multi-Split x Multi-Optimizer Balanced Accuracy Distribution")
    plt.ylabel("Test Balanced Accuracy")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(fig_dir / "multiseed_ba_boxplot.png", dpi=200)
    plt.close()

    # 2. Score Distribution Plot Separated by Class across Splits (Audit Item 5)
    plt.figure(figsize=(10, 5))
    bins = np.linspace(0, 1, 25)
    for (fam, s_type), grp_preds in preds_df.groupby(["family", "split_type"]):
        if s_type in ["iid", "critical_holdout", "parameter_block"] and fam == "tfim":
            p0 = grp_preds[grp_preds["true_label"] == 0]["p1"]
            p1 = grp_preds[grp_preds["true_label"] == 1]["p1"]
            plt.hist(p0, bins=bins, alpha=0.4, label=f"{s_type} (Class 0)")
            plt.hist(p1, bins=bins, alpha=0.4, label=f"{s_type} (Class 1)")
    plt.xlabel("Predicted Positive Probability $p_1$")
    plt.ylabel("Sample Count")
    plt.title("Sample Score Distributions by Physical Regime (TFIM)")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(fig_dir / "score_distributions_by_regime.png", dpi=200)
    plt.close()

    # 3. Confidence Intervals Errorbar Plot (Hierarchical CIs)
    plt.figure(figsize=(9, 5))
    x_positions = np.arange(len(agg_df))
    means = agg_df["balanced_accuracy_mean"].to_numpy()
    err_low = means - agg_df["balanced_accuracy_ci95_low"].to_numpy()
    err_high = agg_df["balanced_accuracy_ci95_high"].to_numpy() - means
    labels_ci = [f"{r['family'].upper()} ({r['split_type']})" for _, r in agg_df.iterrows()]

    plt.errorbar(
        x_positions,
        means,
        yerr=[err_low, err_high],
        fmt="o",
        color="royalblue",
        ecolor="darkorange",
        elinewidth=2,
        capsize=5,
        label="Mean with 95% Hierarchical Clustered CI",
    )
    plt.xticks(x_positions, labels_ci, rotation=25, ha="right")
    plt.ylabel("Balanced Accuracy")
    plt.title("Generalization Benchmark: Hierarchical Partition-Aware 95% CIs")
    plt.ylim(0.4, 1.05)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_dir / "confidence_intervals.png", dpi=200)
    plt.close()

    print(f"Results and figures saved to {out_dir} and {fig_dir}")
    print("\nHeadline Statistical Summary (Hierarchical Clustered Bootstrap):")
    cols_to_print = [
        "family",
        "split_type",
        "n_runs",
        "balanced_accuracy_mean",
        "balanced_accuracy_ci95_low",
        "balanced_accuracy_ci95_high",
        "validation_selected_test_ba_mean",
        "roc_auc_mean",
        "generalization_regime",
    ]
    print(agg_df[[c for c in cols_to_print if c in agg_df.columns]].to_string(index=False))


if __name__ == "__main__":
    main()
