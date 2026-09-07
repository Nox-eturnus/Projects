from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from qcnn_lab.analysis.critical_generalization import evaluate_distance_bands
from qcnn_lab.analysis.splits import load_split_manifest, split_indices_from_manifest
from qcnn_lab.analysis.transition import crossing_point, moving_average
from qcnn_lab.config import load_yaml
from qcnn_lab.physics.datasets import _state_for, default_specs
from qcnn_lab.qcnn.architecture import get_architecture
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.train import train_ideal_qcnn


def main():
    parser = argparse.ArgumentParser(description="Near-critical OOD stress test on dense unseen grids.")
    parser.add_argument("--config", default="configs/evaluation.yaml", help="Path to evaluation config")
    parser.add_argument("--project-config", default="configs/project.yaml", help="Path to project config")
    parser.add_argument("--out-dir", default="results/near_critical", help="Output directory")
    parser.add_argument("--fig-dir", default="results/figures", help="Figures output directory")
    args = parser.parse_args()

    eval_cfg = load_yaml(args.config)["evaluation"]
    proj_cfg = load_yaml(args.project_config)

    n_qubits = int(proj_cfg.get("n_qubits", 8))
    arch = get_architecture(proj_cfg.get("qcnn", {}).get("architecture", "expressive_shared_line"))
    grid_points = int(eval_cfg.get("near_critical_grid", {}).get("points", 41))

    out_dir = Path(args.out_dir)
    fig_dir = Path(args.fig_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    families = ["tfim", "xxz", "cluster"]
    specs = default_specs(n_qubits)
    splits_dir = Path("results/evaluation_splits")
    data_dir = Path("data/processed")

    all_distance_rows = []
    crossover_summary = {}

    plt.figure(figsize=(10, 6))

    for family in families:
        print(f"Executing Near-Critical Stress Test for {family.upper()}...")
        spec = specs[family]
        h_c = spec.critical_value

        crit_cfg = eval_cfg["critical_holdout"][family]
        test_min = float(crit_cfg["test_min"])
        test_max = float(crit_cfg["test_max"])

        # 1. Train on non-critical data strictly outside [test_min, test_max]
        manifest_path = splits_dir / f"{family}_critical_seed11.csv"
        manifest = load_split_manifest(manifest_path)
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

        # 2. Generate dense unseen grid in the held-out critical region [test_min, test_max]
        grid_params = np.linspace(test_min, test_max, grid_points)
        dense_states = []
        dense_true_labels = []
        dense_diagnostics = []

        for p in grid_params:
            energy, st, diag = _state_for(family, n_qubits, float(p))
            dense_states.append(st)
            dense_diagnostics.append(diag)
            dense_true_labels.append(1 if p >= h_c else 0)

        dense_states = np.asarray(dense_states)
        dense_true_labels = np.asarray(dense_true_labels, dtype=int)

        # 3. Evaluate the already-trained QCNN (no retraining!)
        p1 = batch_predict(dense_states, params, arch, n_qubits)
        pred_labels = (p1 >= 0.5).astype(int)
        distances = np.abs(grid_params - h_c)

        # 4. Record predictions
        grid_df = pd.DataFrame({
            "family": family,
            "parameter": grid_params,
            "true_phase": dense_true_labels,
            "predicted_probability": p1,
            "predicted_label": pred_labels,
            "distance_from_hc": distances,
            "physical_diagnostic": dense_diagnostics,
        })
        grid_df.to_csv(out_dir / f"{family}_near_critical.csv", index=False)

        # 5. Finite-size crossover estimate
        smooth_p1 = moving_average(p1, window=3)
        crossing, bracketed = crossing_point(grid_params, smooth_p1, level=0.5)
        crossover_summary[family] = {
            "thermodynamic_hc": h_c,
            "qcnn_finite_size_crossover": crossing,
            "bracketed": bracketed,
            "test_range": [test_min, test_max],
            "note": "Finite-size N=8 QCNN crossover is not required to match thermodynamic h_c exactly.",
        }

        # 6. Evaluate performance vs critical distance bands
        band_metrics = evaluate_distance_bands(dense_true_labels, p1, distances)
        for bm in band_metrics:
            all_distance_rows.append({
                "family": family,
                **asdict(bm),
            })

        # Add to probability plot
        plt.plot(grid_params, smooth_p1, label=f"{family.upper()} QCNN P(y=1|h)", linewidth=2)
        plt.axvline(h_c, linestyle="--", alpha=0.5, label=f"{family.upper()} $h_c={h_c}$" if family == "tfim" else None)

    plt.axhline(0.5, color="gray", linestyle=":", label="Decision Boundary (0.5)")
    plt.xlabel("Hamiltonian Parameter")
    plt.ylabel("Predicted Probability $P(y=1|h)$")
    plt.title("Near-Critical Generalization: Learned Crossover on Dense Unseen Grid")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(fig_dir / "near_critical_probability_curves.png", dpi=200)
    plt.close()

    # Save summary files
    dist_df = pd.DataFrame(all_distance_rows)
    dist_df.to_csv(out_dir / "distance_binned_metrics.csv", index=False)
    (out_dir / "crossover_estimates.json").write_text(json.dumps(crossover_summary, indent=2), encoding="utf-8")

    # Plot performance vs critical distance
    plt.figure(figsize=(8, 5))
    for fam, grp in dist_df.groupby("family"):
        plt.plot(grp["band_name"], grp["balanced_accuracy"], marker="s", label=f"{fam.upper()} BA", linewidth=2)
    plt.xlabel("Distance Band from Critical Point $|h - h_c|$")
    plt.ylabel("Balanced Accuracy")
    plt.title("Classification Performance vs Distance to Phase Transition")
    plt.ylim(0.4, 1.05)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_dir / "near_critical_distance_performance.png", dpi=200)
    plt.close()

    print(f"Near-critical OOD evaluation completed. Results in {out_dir}")
    print("\nDistance Binned Metrics:")
    print(dist_df[["family", "band_name", "n_samples", "accuracy", "balanced_accuracy", "brier_score", "mean_confidence"]].to_string(index=False))


if __name__ == "__main__":
    main()
