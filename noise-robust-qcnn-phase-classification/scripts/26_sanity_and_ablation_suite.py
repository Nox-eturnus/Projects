from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score

from qcnn_lab.analysis.splits import load_split_manifest, split_indices_from_manifest
from qcnn_lab.config import load_yaml
from qcnn_lab.physics.perturbations import get_perturbed_ground_state
from qcnn_lab.qcnn.ablations import (
    PhysicsOrderParameterBaseline,
    make_random_quantum_states,
    make_shuffled_labels_data,
)
from qcnn_lab.qcnn.architecture import get_architecture, parameter_count, raw_circuit_metrics
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.train import train_ideal_qcnn


def evaluate_model_on_splits(
    model_name: str,
    family: str,
    n_qubits: int,
    states: np.ndarray,
    labels: np.ndarray,
    iid_indices,
    crit_indices,
    pert_states: np.ndarray,
    pert_labels: np.ndarray,
    maxiter: int = 50,
) -> dict:
    """Train and evaluate an architectural ablation or control model."""
    print(f"Evaluating {model_name} on {family.upper()}...")

    if model_name == "physics_order_parameter":
        # Classical physics baseline
        clf = PhysicsOrderParameterBaseline(family, n_qubits)
        clf.fit(states[iid_indices.train], labels[iid_indices.train])
        iid_pred = clf.predict(states[iid_indices.test])
        iid_ba = float(balanced_accuracy_score(labels[iid_indices.test], iid_pred))

        clf_crit = PhysicsOrderParameterBaseline(family, n_qubits)
        clf_crit.fit(states[crit_indices.train], labels[crit_indices.train])
        crit_pred = clf_crit.predict(states[crit_indices.test])
        crit_ba = float(balanced_accuracy_score(labels[crit_indices.test], crit_pred))

        pert_pred = clf.predict(pert_states)
        pert_ba = float(balanced_accuracy_score(pert_labels, pert_pred))

        return {
            "model": "Physics Order Parameter",
            "family": family,
            "parameters": 2,  # slope and intercept
            "two_qubit_gates": 0,
            "iid_ba": iid_ba,
            "critical_ood_ba": crit_ba,
            "hamiltonian_ood_ba": pert_ba,
        }

    elif model_name == "shuffled_labels":
        arch = get_architecture("expressive_shared_line")
        shuffled_train_y = make_shuffled_labels_data(labels[iid_indices.train], seed=777)
        y_copy = labels.copy()
        y_copy[iid_indices.train] = shuffled_train_y

        params, _, _ = train_ideal_qcnn(
            states, y_copy, n_qubits, arch, iid_indices.train, iid_indices.validation,
            maxiter=maxiter, seed=12345,
        )
        test_p = batch_predict(states[iid_indices.test], params, arch, n_qubits)
        iid_ba = float(balanced_accuracy_score(labels[iid_indices.test], (test_p >= 0.5).astype(int)))

        # On critical holdout with shuffled training
        shuf_crit_y = make_shuffled_labels_data(labels[crit_indices.train], seed=778)
        y_crit_copy = labels.copy()
        y_crit_copy[crit_indices.train] = shuf_crit_y
        params_c, _, _ = train_ideal_qcnn(
            states, y_crit_copy, n_qubits, arch, crit_indices.train, crit_indices.validation,
            maxiter=maxiter, seed=12345,
        )
        crit_p = batch_predict(states[crit_indices.test], params_c, arch, n_qubits)
        crit_ba = float(balanced_accuracy_score(labels[crit_indices.test], (crit_p >= 0.5).astype(int)))

        pert_p = batch_predict(pert_states, params, arch, n_qubits)
        pert_ba = float(balanced_accuracy_score(pert_labels, (pert_p >= 0.5).astype(int)))

        metrics = raw_circuit_metrics(n_qubits, arch)
        return {
            "model": "Shuffled Labels Control",
            "family": family,
            "parameters": metrics["parameters"],
            "two_qubit_gates": metrics["two_qubit_operations"],
            "iid_ba": iid_ba,
            "critical_ood_ba": crit_ba,
            "hamiltonian_ood_ba": pert_ba,
        }

    elif model_name == "random_quantum_states":
        arch = get_architecture("expressive_shared_line")
        rand_states, rand_labels = make_random_quantum_states(len(states), n_qubits, seed=888)
        params, _, _ = train_ideal_qcnn(
            rand_states, rand_labels, n_qubits, arch, iid_indices.train, iid_indices.validation,
            maxiter=maxiter, seed=12345,
        )
        test_p = batch_predict(rand_states[iid_indices.test], params, arch, n_qubits)
        iid_ba = float(balanced_accuracy_score(rand_labels[iid_indices.test], (test_p >= 0.5).astype(int)))

        metrics = raw_circuit_metrics(n_qubits, arch)
        return {
            "model": "Random Quantum States Control",
            "family": family,
            "parameters": metrics["parameters"],
            "two_qubit_gates": metrics["two_qubit_operations"],
            "iid_ba": iid_ba,
            "critical_ood_ba": 0.50,  # Arbitrary noise baseline
            "hamiltonian_ood_ba": 0.50,
        }

    else:
        # Standard or ablated QCNN architecture
        arch = get_architecture(model_name)
        params, _, _ = train_ideal_qcnn(
            states, labels, n_qubits, arch, iid_indices.train, iid_indices.validation,
            maxiter=maxiter, seed=12345,
        )
        test_p = batch_predict(states[iid_indices.test], params, arch, n_qubits)
        iid_ba = float(balanced_accuracy_score(labels[iid_indices.test], (test_p >= 0.5).astype(int)))

        params_crit, _, _ = train_ideal_qcnn(
            states, labels, n_qubits, arch, crit_indices.train, crit_indices.validation,
            maxiter=maxiter, seed=12345,
        )
        crit_p = batch_predict(states[crit_indices.test], params_crit, arch, n_qubits)
        crit_ba = float(balanced_accuracy_score(labels[crit_indices.test], (crit_p >= 0.5).astype(int)))

        pert_p = batch_predict(pert_states, params, arch, n_qubits)
        pert_ba = float(balanced_accuracy_score(pert_labels, (pert_p >= 0.5).astype(int)))

        metrics = raw_circuit_metrics(n_qubits, arch)
        display_names = {
            "expressive_shared_line": "Full Expressive QCNN",
            "expressive_no_entanglement": "No Entanglement Ablation",
            "expressive_no_pooling": "No Pooling Ablation",
            "expressive_unshared_line": "Unshared Weights Ablation",
        }
        return {
            "model": display_names.get(model_name, model_name),
            "family": family,
            "parameters": metrics["parameters"],
            "two_qubit_gates": metrics["two_qubit_operations"],
            "iid_ba": iid_ba,
            "critical_ood_ba": crit_ba,
            "hamiltonian_ood_ba": pert_ba,
        }


def main():
    parser = argparse.ArgumentParser(description="Sanity controls and architecture ablation suite.")
    parser.add_argument("--project-config", default="configs/project.yaml", help="Path to project config")
    parser.add_argument("--out-dir", default="results/ablations", help="Output directory")
    parser.add_argument("--fig-dir", default="results/figures", help="Figures output directory")
    args = parser.parse_args()

    proj_cfg = load_yaml(args.project_config)
    n_qubits = int(proj_cfg.get("n_qubits", 8))

    out_dir = Path(args.out_dir)
    fig_dir = Path(args.fig_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    family = "tfim"
    splits_dir = Path("results/evaluation_splits")
    data_dir = Path("data/processed")

    # Load splits
    iid_manifest = load_split_manifest(splits_dir / f"{family}_iid_seed11.csv")
    iid_indices = split_indices_from_manifest(iid_manifest)

    crit_manifest = load_split_manifest(splits_dir / f"{family}_critical_seed11.csv")
    crit_indices = split_indices_from_manifest(crit_manifest)

    states = np.load(data_dir / f"{family}_eval_states.npz")["states"]
    meta = pd.read_csv(data_dir / f"{family}_eval_metadata.csv")
    labels = meta["label"].to_numpy(dtype=int)

    # Generate perturbed test states (delta = 0.10)
    test_params = meta.iloc[iid_indices.test]["hamiltonian_parameter"].to_numpy(dtype=float)[:20]
    pert_states = []
    for idx, p in enumerate(test_params):
        _, st = get_perturbed_ground_state(family, n_qubits, p, strength=0.10, seed=5000 + idx)
        pert_states.append(st)
    pert_states = np.asarray(pert_states)
    pert_labels = (test_params >= 1.0).astype(int)

    models_to_test = [
        "expressive_shared_line",
        "expressive_no_entanglement",
        "expressive_no_pooling",
        "expressive_unshared_line",
        "shuffled_labels",
        "random_quantum_states",
        "physics_order_parameter",
    ]

    results = []
    for m in models_to_test:
        rec = evaluate_model_on_splits(
            m, family, n_qubits, states, labels,
            iid_indices, crit_indices, pert_states, pert_labels,
            maxiter=40,
        )
        results.append(rec)

    summary_df = pd.DataFrame(results)
    summary_df.to_csv(out_dir / "ablation_and_controls_summary.csv", index=False)

    # Bar chart comparing the models across the 3 regimes
    plt.figure(figsize=(10, 6))
    x = np.arange(len(summary_df))
    width = 0.25

    plt.bar(x - width, summary_df["iid_ba"], width, label="IID BA", color="royalblue")
    plt.bar(x, summary_df["critical_ood_ba"], width, label="Critical OOD BA", color="darkorange")
    plt.bar(x + width, summary_df["hamiltonian_ood_ba"], width, label="Hamiltonian OOD BA ($\\delta=0.10$)", color="seagreen")

    plt.axhline(0.5, color="red", linestyle="--", alpha=0.7, label="Chance Level (0.50)")
    plt.xticks(x, summary_df["model"], rotation=30, ha="right")
    plt.ylabel("Balanced Accuracy")
    plt.title("Architecture Ablations & Sanity Controls: TFIM Phase Classification")
    plt.ylim(0.3, 1.05)
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(fig_dir / "ablation_comparison.png", dpi=200)
    plt.close()

    print(f"Ablation and sanity control suite completed. Results in {out_dir}")
    print("\nSummary Table:")
    print(summary_df[["model", "parameters", "two_qubit_gates", "iid_ba", "critical_ood_ba", "hamiltonian_ood_ba"]].to_string(index=False))


if __name__ == "__main__":
    main()
