from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from qcnn_lab.analysis.calibration import brier_score, calibration_curve, expected_calibration_error, negative_log_likelihood
from qcnn_lab.analysis.splits import load_split_manifest, split_indices_from_manifest
from qcnn_lab.analysis.statistics import aggregate_statistics, bootstrap_metric_ci
from qcnn_lab.config import load_yaml
from qcnn_lab.metrics import binary_metrics
from qcnn_lab.qcnn.architecture import get_architecture
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.train import train_ideal_qcnn


def main():
    parser = argparse.ArgumentParser(description="Multi-split x multi-optimizer statistical benchmark.")
    parser.add_argument("--fast", action="store_true", help="Run fast 3x3 smoke benchmark")
    parser.add_argument("--config", default="configs/evaluation.yaml", help="Evaluation config path")
    parser.add_argument("--project-config", default="configs/project.yaml", help="Project config path")
    parser.add_argument("--out-dir", default="results/statistical_generalization", help="Output directory")
    parser.add_argument("--fig-dir", default="results/figures", help="Figure output directory")
    parser.add_argument("--maxiter", type=int, default=None, help="Override maxiter for optimization")
    args = parser.parse_args()

    eval_cfg = load_yaml(args.config)["evaluation"]
    proj_cfg = load_yaml(args.project_config)

    n_qubits = int(proj_cfg.get("n_qubits", 8))
    arch = get_architecture(proj_cfg.get("qcnn", {}).get("architecture", "expressive_shared_line"))
    maxiter = args.maxiter if args.maxiter is not None else (30 if args.fast else int(proj_cfg.get("qcnn", {}).get("maxiter_ideal", 120)))

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
    all_calibrations = []

    print(f"Starting benchmark: {len(families)} families x {len(split_types)} split types x {len(split_seeds)} split seeds x {len(optimizer_seeds)} optimizer seeds...")

    for family in families:
        states = np.load(data_dir / f"{family}_eval_states.npz")["states"]
        meta = pd.read_csv(data_dir / f"{family}_eval_metadata.csv")
        y = meta["label"].to_numpy(dtype=int)

        for split_type in split_types:
            prefix = "critical" if "critical" in split_type else ("block" if "block" in split_type else "iid")
            for s_seed in split_seeds:
                manifest_name = f"{family}_{prefix}_seed{s_seed}.csv"
                manifest_path = splits_dir / manifest_name
                manifest = load_split_manifest(manifest_path)

                indices = split_indices_from_manifest(manifest)

                for opt_seed in optimizer_seeds:
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
                    test_p = batch_predict(states[indices.test], params, arch, n_qubits)
                    y_test = y[indices.test]

                    m = binary_metrics(y_test, test_p)
                    nll = negative_log_likelihood(y_test, test_p)
                    bs = brier_score(y_test, test_p)
                    ece = expected_calibration_error(y_test, test_p)

                    run_record = {
                        "family": family,
                        "split_type": split_type,
                        "split_seed": s_seed,
                        "optimizer_seed": opt_seed,
                        "accuracy": m.accuracy,
                        "balanced_accuracy": m.balanced_accuracy,
                        "f1": m.f1,
                        "roc_auc": m.roc_auc,
                        "cross_entropy": nll,
                        "brier_score": bs,
                        "ece": ece,
                        "training_time": sec,
                    }
                    runs.append(run_record)

                    # Compute calibration curve for aggregation
                    accs, confs, counts = calibration_curve(y_test, test_p, n_bins=10)
                    for b_idx in range(len(counts)):
                        all_calibrations.append({
                            "family": family,
                            "split_type": split_type,
                            "bin": b_idx,
                            "accuracy": accs[b_idx],
                            "confidence": confs[b_idx],
                            "count": counts[b_idx],
                        })

    runs_df = pd.DataFrame(runs)
    runs_df.to_csv(out_dir / "runs.csv", index=False)
    print(f"Recorded {len(runs_df)} individual experimental runs.")

    # Aggregate summaries across (family, split_type)
    agg_rows = []
    ci_dict = {}

    for (fam, s_type), grp in runs_df.groupby(["family", "split_type"]):
        key = f"{fam}_{s_type}"
        ci_dict[key] = {}
        row = {
            "family": fam,
            "split_type": s_type,
            "n_runs": len(grp),
        }
        for metric in ["balanced_accuracy", "accuracy", "f1", "roc_auc", "brier_score", "cross_entropy", "ece"]:
            stats = aggregate_statistics(grp[metric].to_numpy(dtype=float))
            row[f"{metric}_mean"] = stats["mean"]
            row[f"{metric}_std"] = stats["std"]
            row[f"{metric}_median"] = stats["median"]
            row[f"{metric}_ci95_low"] = stats["ci_low"]
            row[f"{metric}_ci95_high"] = stats["ci_high"]
            ci_dict[key][metric] = {
                "mean": stats["mean"],
                "std": stats["std"],
                "ci95": [stats["ci_low"], stats["ci_high"]],
            }
        agg_rows.append(row)

    agg_df = pd.DataFrame(agg_rows)
    agg_df.to_csv(out_dir / "aggregate.csv", index=False)
    (out_dir / "confidence_intervals.json").write_text(json.dumps(ci_dict, indent=2), encoding="utf-8")

    cal_df = pd.DataFrame(all_calibrations)
    cal_df.to_csv(out_dir / "calibration.csv", index=False)

    # 1. Boxplot of Balanced Accuracy across splits and families
    plt.figure(figsize=(9, 5))
    groups = []
    labels = []
    for (fam, s_type), grp in runs_df.groupby(["family", "split_type"]):
        groups.append(grp["balanced_accuracy"].to_numpy())
        labels.append(f"{fam.upper()}\n{s_type}")
    try:
        plt.boxplot(groups, tick_labels=labels, patch_artist=True)
    except TypeError:
        plt.boxplot(groups, labels=labels, patch_artist=True)
    plt.title("Multi-Split x Multi-Optimizer Balanced Accuracy Distribution")
    plt.ylabel("Test Balanced Accuracy")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(fig_dir / "multiseed_ba_boxplot.png", dpi=200)
    plt.close()

    # 2. Calibration Curve
    plt.figure(figsize=(7, 6))
    plt.plot([0, 1], [0, 1], "k--", label="Perfect Calibration")
    for (fam, s_type), grp in cal_df.groupby(["family", "split_type"]):
        valid = grp.dropna(subset=["accuracy"])
        if len(valid) > 0:
            bin_stats = valid.groupby("bin")[["confidence", "accuracy"]].mean()
            plt.plot(bin_stats["confidence"], bin_stats["accuracy"], marker="o", label=f"{fam.upper()} ({s_type})")
    plt.xlabel("Mean Predicted Confidence")
    plt.ylabel("Fraction of Positives (Accuracy)")
    plt.title("Reliability Diagram / Calibration Curve")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(fig_dir / "calibration_curve.png", dpi=200)
    plt.close()

    # 3. Confidence Intervals Errorbar Plot
    plt.figure(figsize=(9, 5))
    x_positions = np.arange(len(agg_df))
    means = agg_df["balanced_accuracy_mean"].to_numpy()
    err_low = means - agg_df["balanced_accuracy_ci95_low"].to_numpy()
    err_high = agg_df["balanced_accuracy_ci95_high"].to_numpy() - means
    labels = [f"{r['family'].upper()} ({r['split_type']})" for _, r in agg_df.iterrows()]

    plt.errorbar(x_positions, means, yerr=[err_low, err_high], fmt="o", color="royalblue", ecolor="darkorange", elinewidth=2, capsize=5, label="Mean with 95% Bootstrap CI")
    plt.xticks(x_positions, labels, rotation=25, ha="right")
    plt.ylabel("Balanced Accuracy")
    plt.title("Generalization Benchmark: Balanced Accuracy with 95% CIs")
    plt.ylim(0.4, 1.05)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_dir / "confidence_intervals.png", dpi=200)
    plt.close()

    print(f"Results and figures saved to {out_dir} and {fig_dir}")
    print("\nHeadline Statistical Summary:")
    print(agg_df[["family", "split_type", "n_runs", "balanced_accuracy_mean", "balanced_accuracy_std", "balanced_accuracy_ci95_low", "balanced_accuracy_ci95_high", "brier_score_mean", "ece_mean"]].to_string(index=False))


if __name__ == "__main__":
    main()
