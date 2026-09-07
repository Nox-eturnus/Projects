from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, f1_score

from qcnn_lab.analysis.calibration import brier_score
from qcnn_lab.analysis.splits import load_split_manifest, split_indices_from_manifest
from qcnn_lab.config import load_yaml
from qcnn_lab.measurement.grouped_observables import extract_grouped_classical_features
from qcnn_lab.qcnn.architecture import get_architecture
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.finite_shots import simulate_finite_shot_probability
from qcnn_lab.qcnn.train import train_ideal_qcnn


def get_git_commit() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def main():
    parser = argparse.ArgumentParser(description="Finite-shot and measurement-budget benchmark.")
    parser.add_argument("--project-config", default="configs/project.yaml", help="Path to project config")
    parser.add_argument("--out-dir", default="results/finite_shots", help="Output directory")
    parser.add_argument("--fig-dir", default="results/figures", help="Figures output directory")
    args = parser.parse_args()

    proj_cfg = load_yaml(args.project_config)
    n_qubits = int(proj_cfg.get("n_qubits", 8))
    arch = get_architecture(proj_cfg.get("qcnn", {}).get("architecture", "expressive_shared_line"))

    out_dir = Path(args.out_dir)
    fig_dir = Path(args.fig_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    shot_counts = [128, 256, 512, 1024, 2048, 4096, 8192]
    n_sampling_seeds = 20
    budgets = [128, 256, 512, 1024, 2048, 4096]

    families = ["tfim", "xxz", "cluster"]
    splits_dir = Path("results/evaluation_splits")
    data_dir = Path("data/processed")

    scaling_records = []
    budget_records = []

    for family in families:
        print(f"Running Finite-Shot Benchmark for {family.upper()}...")
        manifest = load_split_manifest(splits_dir / f"{family}_iid_seed11.csv")
        indices = split_indices_from_manifest(manifest)

        states = np.load(data_dir / f"{family}_eval_states.npz")["states"]
        meta = pd.read_csv(data_dir / f"{family}_eval_metadata.csv")
        y = meta["label"].to_numpy(dtype=int)

        params, _, _ = train_ideal_qcnn(
            states,
            y,
            n_qubits,
            arch,
            indices.train,
            indices.validation,
            maxiter=int(proj_cfg.get("qcnn", {}).get("maxiter_ideal", 120)),
            seed=12345,
        )

        test_states = states[indices.test]
        test_y = y[indices.test]
        exact_p1 = batch_predict(test_states, params, arch, n_qubits)

        # 1. Shot scaling evaluation
        for s in shot_counts:
            bas, f1s, bss = [], [], []
            for seed in range(n_sampling_seeds):
                p_hat = simulate_finite_shot_probability(exact_p1, shots=s, seed=seed + 1000)
                pred_labels = (p_hat >= 0.5).astype(int)
                bas.append(balanced_accuracy_score(test_y, pred_labels))
                f1s.append(f1_score(test_y, pred_labels, zero_division=0))
                bss.append(brier_score(test_y, p_hat))

            scaling_records.append({
                "family": family,
                "shots": s,
                "n_test": len(test_y),
                "n_sampling_seeds": n_sampling_seeds,
                "ba_mean": float(np.mean(bas)),
                "ba_std": float(np.std(bas, ddof=1)),
                "f1_mean": float(np.mean(f1s)),
                "f1_std": float(np.std(f1s, ddof=1)),
                "brier_mean": float(np.mean(bss)),
                "brier_std": float(np.std(bss, ddof=1)),
            })

        # 2. Physically faithful measurement-budget matched classical baseline comparison
        # Train classical model on exact expectations
        train_feats, n_groups = extract_grouped_classical_features(
            states[indices.train], family, n_qubits, budget=None
        )
        clf = LogisticRegression()
        clf.fit(train_feats, y[indices.train])

        for b in budgets:
            q_bas = []
            c_bas = []

            for seed in range(n_sampling_seeds):
                # QCNN finite shots: B state copies consumed through QCNN circuit readout
                p_hat_q = simulate_finite_shot_probability(exact_p1, shots=b, seed=seed + 2000)
                q_bas.append(balanced_accuracy_score(test_y, (p_hat_q >= 0.5).astype(int)))

                # Classical model with finite state-copy budget B split across physical bases
                noisy_test_feats, _ = extract_grouped_classical_features(
                    test_states, family, n_qubits, budget=b, seed=seed + 3000
                )
                c_pred = clf.predict(noisy_test_feats)
                c_bas.append(balanced_accuracy_score(test_y, c_pred))

            budget_records.append({
                "family": family,
                "budget": b,
                "n_test": len(test_y),
                "n_sampling_seeds": n_sampling_seeds,
                "n_physical_settings": n_groups,
                "qcnn_ba_mean": float(np.mean(q_bas)),
                "qcnn_ba_std": float(np.std(q_bas, ddof=1)),
                "classical_ba_mean": float(np.mean(c_bas)),
                "classical_ba_std": float(np.std(c_bas, ddof=1)),
            })

    scaling_df = pd.DataFrame(scaling_records)
    scaling_df.to_csv(out_dir / "shot_scaling_metrics.csv", index=False)

    budget_df = pd.DataFrame(budget_records)
    budget_df.to_csv(out_dir / "budget_matched_comparison.csv", index=False)

    # Save Provenance JSON (Priority 14)
    provenance = {
        "git_commit": get_git_commit(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
        "n_qubits": n_qubits,
        "shot_counts": shot_counts,
        "budgets": budgets,
        "n_sampling_seeds": n_sampling_seeds,
        "measurement_simulator": "qcnn_lab.measurement.grouped_observables",
        "description": "Physically faithful Pauli basis sampling for TFIM (Z, X), XXZ (Z, X), and Cluster (Setting A, Setting B).",
        "script": "scripts/27_finite_shot_resource_benchmark.py",
    }
    with open(out_dir / "provenance.json", "w") as f:
        json.dump(provenance, f, indent=2)

    # Plot 1: Shots vs Balanced Accuracy
    plt.figure(figsize=(8, 5))
    for fam, grp in scaling_df.groupby("family"):
        plt.errorbar(grp["shots"], grp["ba_mean"], yerr=grp["ba_std"], marker="o", capsize=4, label=f"{fam.upper()} QCNN")
    plt.xscale("log", base=2)
    plt.xlabel("Measurement Shots ($S$)")
    plt.ylabel("Test Balanced Accuracy")
    plt.title("QCNN Performance Envelope under Finite Measurement Shots")
    plt.ylim(0.4, 1.05)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_dir / "shots_vs_balanced_accuracy.png", dpi=200)
    plt.close()

    # Plot 2: Budget-matched Comparison
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    for idx, (fam, grp) in enumerate(budget_df.groupby("family")):
        ax = axes[idx]
        ax.plot(grp["budget"], grp["qcnn_ba_mean"], marker="o", linewidth=2, label="QCNN Readout", color="royalblue")
        ax.fill_between(grp["budget"], grp["qcnn_ba_mean"] - grp["qcnn_ba_std"], grp["qcnn_ba_mean"] + grp["qcnn_ba_std"], alpha=0.2, color="royalblue")
        ax.plot(grp["budget"], grp["classical_ba_mean"], marker="s", linewidth=2, linestyle="--", label="Classical Pauli Group", color="darkorange")
        ax.fill_between(grp["budget"], grp["classical_ba_mean"] - grp["classical_ba_std"], grp["classical_ba_mean"] + grp["classical_ba_std"], alpha=0.2, color="darkorange")
        ax.set_xscale("log", base=2)
        ax.set_xlabel("State-Copy Budget ($B$)")
        ax.set_title(f"{fam.upper()}: QCNN vs Classical Pauli")
        ax.grid(True, linestyle="--", alpha=0.5)
        if idx == 0:
            ax.set_ylabel("Test Balanced Accuracy")
        ax.legend()
    plt.tight_layout()
    plt.savefig(fig_dir / "classical_vs_qcnn_budget_matched.png", dpi=200)
    plt.close()

    print(f"Finite-shot benchmark completed. Results in {out_dir}")
    print("\nBudget-Matched Comparison (mean BA):")
    piv = budget_df.pivot(index="budget", columns="family", values=["qcnn_ba_mean", "classical_ba_mean"])
    print(piv.round(3))


if __name__ == "__main__":
    main()
