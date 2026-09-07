from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, f1_score

from qcnn_lab.analysis.calibration import brier_score
from qcnn_lab.analysis.splits import load_split_manifest, split_indices_from_manifest
from qcnn_lab.config import load_yaml
from qcnn_lab.physics.observables import (
    cluster_stabilizer_order,
    tfim_long_range_zz,
    xxz_staggered_structure,
)
from qcnn_lab.qcnn.architecture import get_architecture
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.finite_shots import simulate_finite_shot_observable, simulate_finite_shot_probability
from qcnn_lab.qcnn.train import train_ideal_qcnn


def extract_classical_features(states: np.ndarray, family: str, n_qubits: int) -> np.ndarray:
    """Extract standard Pauli expectation value channels for classical baseline."""
    features = []
    for st in states:
        if family == "tfim":
            f1 = tfim_long_range_zz(st, n_qubits)
            # Local Z and local X features
            features.append([f1, float(np.real(st[0])), float(np.imag(st[0]))])
        elif family == "cluster":
            f1 = cluster_stabilizer_order(st, n_qubits)
            features.append([f1, float(np.real(st[0])), float(np.imag(st[0]))])
        elif family == "xxz":
            f1 = xxz_staggered_structure(st, n_qubits)
            features.append([f1, float(np.real(st[0])), float(np.imag(st[0]))])
        else:
            raise ValueError(f"unknown family {family}")
    return np.asarray(features, dtype=float)


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
                "ba_mean": float(np.mean(bas)),
                "ba_std": float(np.std(bas, ddof=1)),
                "f1_mean": float(np.mean(f1s)),
                "f1_std": float(np.std(f1s, ddof=1)),
                "brier_mean": float(np.mean(bss)),
                "brier_std": float(np.std(bss, ddof=1)),
            })

        # 2. Measurement-budget matched classical baseline comparison
        train_feats = extract_classical_features(states[indices.train], family, n_qubits)
        test_feats = extract_classical_features(test_states, family, n_qubits)
        clf = LogisticRegression()
        clf.fit(train_feats, y[indices.train])

        for b in budgets:
            q_bas = []
            c_bas = []
            k_channels = train_feats.shape[1]
            shots_per_channel = max(1, b // k_channels)

            for seed in range(n_sampling_seeds):
                # QCNN finite shots
                p_hat_q = simulate_finite_shot_probability(exact_p1, shots=b, seed=seed + 2000)
                q_bas.append(balanced_accuracy_score(test_y, (p_hat_q >= 0.5).astype(int)))

                # Classical model with finite shots per observable channel
                noisy_test_feats = np.empty_like(test_feats)
                for ch in range(k_channels):
                    noisy_test_feats[:, ch] = simulate_finite_shot_observable(
                        test_feats[:, ch],
                        shots_per_observable=shots_per_channel,
                        seed=seed + 3000 + ch,
                    )
                c_pred = clf.predict(noisy_test_feats)
                c_bas.append(balanced_accuracy_score(test_y, c_pred))

            budget_records.append({
                "family": family,
                "budget": b,
                "qcnn_ba_mean": float(np.mean(q_bas)),
                "qcnn_ba_std": float(np.std(q_bas, ddof=1)),
                "classical_ba_mean": float(np.mean(c_bas)),
                "classical_ba_std": float(np.std(c_bas, ddof=1)),
            })

    scaling_df = pd.DataFrame(scaling_records)
    scaling_df.to_csv(out_dir / "shot_scaling_metrics.csv", index=False)

    budget_df = pd.DataFrame(budget_records)
    budget_df.to_csv(out_dir / "budget_matched_comparison.csv", index=False)

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

    # Plot 2: Shots vs Brier Score
    plt.figure(figsize=(8, 5))
    for fam, grp in scaling_df.groupby("family"):
        plt.plot(grp["shots"], grp["brier_mean"], marker="s", label=f"{fam.upper()} Brier Score")
    plt.xscale("log", base=2)
    plt.xlabel("Measurement Shots ($S$)")
    plt.ylabel("Brier Score (lower is better)")
    plt.title("Brier Score Scaling with Measurement Shots")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_dir / "shots_vs_brier_score.png", dpi=200)
    plt.close()

    # Plot 3: Budget-matched comparison (QCNN vs Classical)
    plt.figure(figsize=(9, 5))
    for fam, grp in budget_df.groupby("family"):
        plt.plot(grp["budget"], grp["qcnn_ba_mean"], marker="o", label=f"{fam.upper()} QCNN")
        plt.plot(grp["budget"], grp["classical_ba_mean"], marker="^", linestyle="--", label=f"{fam.upper()} Classical (Budget-Matched)")
    plt.xscale("log", base=2)
    plt.xlabel("Total State-Copy Budget ($B$)")
    plt.ylabel("Test Balanced Accuracy")
    plt.title("QCNN vs Measurement-Budget-Matched Classical Baseline")
    plt.ylim(0.4, 1.05)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_dir / "classical_vs_qcnn_budget_matched.png", dpi=200)
    plt.close()

    print(f"Finite-shot benchmarking completed. Results in {out_dir}")
    print("\nBudget Matched Comparison Preview:")
    print(budget_df.head(12).to_string(index=False))


if __name__ == "__main__":
    main()
