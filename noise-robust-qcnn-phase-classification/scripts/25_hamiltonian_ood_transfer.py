from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from qcnn_lab.analysis.calibration import brier_score, expected_calibration_error
from qcnn_lab.analysis.splits import load_split_manifest, split_indices_from_manifest
from qcnn_lab.config import load_yaml
from qcnn_lab.metrics import binary_metrics
from qcnn_lab.physics.datasets import default_specs
from qcnn_lab.physics.perturbations import get_perturbed_ground_state, get_perturbed_state_and_gap
from qcnn_lab.qcnn.ablations import compute_physical_order_parameters
from qcnn_lab.qcnn.architecture import get_architecture
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.train import train_ideal_qcnn


def main():
    parser = argparse.ArgumentParser(
        description="Hamiltonian OOD transfer / microscopic perturbation benchmark under nominal phase boundaries."
    )
    parser.add_argument("--project-config", default="configs/project.yaml", help="Path to project config")
    parser.add_argument("--out-dir", default="results/hamiltonian_ood", help="Output directory")
    parser.add_argument("--fig-dir", default="results/figures", help="Figures output directory")
    args = parser.parse_args()

    proj_cfg = load_yaml(args.project_config)
    n_qubits = int(proj_cfg.get("n_qubits", 8))
    arch = get_architecture(proj_cfg.get("qcnn", {}).get("architecture", "expressive_shared_line"))

    out_dir = Path(args.out_dir)
    fig_dir = Path(args.fig_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    families = ["tfim", "xxz", "cluster"]
    specs = default_specs(n_qubits)
    perturbation_strengths = [0.0, 0.02, 0.05, 0.10, 0.20]

    splits_dir = Path("results/evaluation_splits")
    data_dir = Path("data/processed")

    summary_records = []
    sample_diagnostics = []

    plt.figure(figsize=(8, 5))

    for family in families:
        print(f"Running Hamiltonian OOD Benchmark for {family.upper()}...")
        spec = specs[family]
        h_c = spec.critical_value

        manifest_path = splits_dir / f"{family}_iid_seed11.csv"
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

        test_meta = meta.iloc[indices.test]
        test_params = test_meta["hamiltonian_parameter"].to_numpy(dtype=float)[:20]
        test_labels = (test_params >= h_c).astype(int)

        family_rows = []

        for delta in perturbation_strengths:
            pert_states = []
            fidelities = []
            gaps = []
            order_params = []

            for idx, p in enumerate(test_params):
                _, st_unpert = get_perturbed_ground_state(family, n_qubits, p, 0.0, seed=2026 + idx)
                _, st, gap = get_perturbed_state_and_gap(family, n_qubits, p, delta, seed=2026 + idx)
                fid = float(np.abs(np.vdot(st_unpert, st)) ** 2)
                ord_p = float(compute_physical_order_parameters(np.array([st]), family, n_qubits)[0, 0])

                pert_states.append(st)
                fidelities.append(fid)
                gaps.append(gap)
                order_params.append(ord_p)

            pert_states = np.asarray(pert_states)
            p1 = batch_predict(pert_states, params, arch, n_qubits)
            m = binary_metrics(test_labels, p1)
            bs = brier_score(test_labels, p1)
            ece = expected_calibration_error(test_labels, p1)

            for idx, p in enumerate(test_params):
                sample_diagnostics.append({
                    "family": family,
                    "delta": delta,
                    "parameter": p,
                    "nominal_label": int(test_labels[idx]),
                    "order_parameter": order_params[idx],
                    "spectral_gap": gaps[idx],
                    "fidelity_to_unperturbed": fidelities[idx],
                    "qcnn_probability": float(p1[idx]),
                    "predicted_label": int(p1[idx] >= 0.5),
                })

            rec = {
                "family": family,
                "delta": delta,
                "n_samples": len(test_labels),
                "accuracy": m.accuracy,
                "balanced_accuracy": m.balanced_accuracy,
                "f1": m.f1,
                "roc_auc": m.roc_auc,
                "brier_score": bs,
                "ece": ece,
                "mean_fidelity": float(np.mean(fidelities)),
                "mean_spectral_gap": float(np.mean(gaps)),
            }
            family_rows.append(rec)
            summary_records.append(rec)

        fam_df = pd.DataFrame(family_rows)
        csv_name = f"{family}_disorder.csv" if family == "tfim" else (f"{family}_symmetry_preserving.csv" if family == "cluster" else f"{family}_perturbation.csv")
        fam_df.to_csv(out_dir / csv_name, index=False)

        plt.plot(fam_df["delta"], fam_df["balanced_accuracy"], marker="o", linewidth=2, label=f"{family.upper()} Balanced Accuracy")

    plt.xlabel("Hamiltonian Perturbation / Disorder Strength $\\delta$")
    plt.ylabel("Test Balanced Accuracy (Nominal Labels)")
    plt.title("Robustness to Hamiltonian Perturbations under Nominal Phase Boundaries")
    plt.ylim(0.4, 1.05)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_dir / "hamiltonian_ood_transfer.png", dpi=200)
    plt.close()

    summary_df = pd.DataFrame(summary_records)
    summary_df.to_csv(out_dir / "summary.csv", index=False)

    diag_df = pd.DataFrame(sample_diagnostics)
    diag_df.to_csv(out_dir / "sample_diagnostics.csv", index=False)

    print(f"Hamiltonian OOD benchmark completed. Results in {out_dir}")
    print("\nSummary Results:")
    print(summary_df[["family", "delta", "balanced_accuracy", "f1", "mean_fidelity", "mean_spectral_gap"]].to_string(index=False))


if __name__ == "__main__":
    main()
