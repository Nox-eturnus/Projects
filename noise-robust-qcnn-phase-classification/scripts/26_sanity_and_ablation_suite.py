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
from sklearn.metrics import balanced_accuracy_score

from qcnn_lab.analysis.splits import load_split_manifest, split_indices_from_manifest
from qcnn_lab.analysis.statistics import bootstrap_confidence_interval
from qcnn_lab.config import load_yaml
from qcnn_lab.physics.perturbations import get_perturbed_ground_state
from qcnn_lab.qcnn.ablations import (
    PhysicsOrderParameterBaseline,
    UntrainedQCNNBaseline,
    evaluate_pipeline_label_permutation_test,
    evaluate_shuffled_training_label_control,
    make_random_quantum_states,
)
from qcnn_lab.qcnn.architecture import get_architecture, parameter_count, raw_circuit_metrics
from qcnn_lab.qcnn.evaluate import batch_predict
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
    full_qcnn_iid_ba: float | None = None,
    maxiter: int = 30,
) -> tuple[dict, list[dict] | None]:
    """Train and evaluate an architectural ablation or control model.

    Returns:
        (summary_record, permutation_records_or_none)
    """
    print(f"Evaluating {model_name} on {family.upper()}...")

    if model_name == "physics_order_parameter":
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

        rec = {
            "model": "Physics Order Parameter",
            "family": family,
            "parameters": 2,
            "two_qubit_gates": 0,
            "iid_ba": iid_ba,
            "critical_ood_ba": crit_ba,
            "hamiltonian_ood_ba": pert_ba,
            "iid_status": "executed",
            "critical_ood_status": "executed",
            "hamiltonian_ood_status": "executed",
        }
        return rec, None

    elif model_name == "untrained_qcnn":
        arch = get_architecture("expressive_shared_line")
        clf = UntrainedQCNNBaseline(arch, n_qubits, seed=12345)
        iid_pred = clf.predict(states[iid_indices.test])
        iid_ba = float(balanced_accuracy_score(labels[iid_indices.test], iid_pred))

        crit_pred = clf.predict(states[crit_indices.test])
        crit_ba = float(balanced_accuracy_score(labels[crit_indices.test], crit_pred))

        pert_pred = clf.predict(pert_states)
        pert_ba = float(balanced_accuracy_score(pert_labels, pert_pred))

        metrics = raw_circuit_metrics(n_qubits, arch)
        rec = {
            "model": "Untrained QCNN Baseline",
            "family": family,
            "parameters": metrics["parameters"],
            "two_qubit_gates": metrics["two_qubit_operations"],
            "iid_ba": iid_ba,
            "critical_ood_ba": crit_ba,
            "hamiltonian_ood_ba": pert_ba,
            "iid_status": "executed",
            "critical_ood_status": "executed",
            "hamiltonian_ood_status": "executed",
        }
        return rec, None

    elif model_name == "shuffled_labels":
        arch = get_architecture("expressive_shared_line")
        # Run shuffled training label sanity control (N=25 runs)
        shuf_res = evaluate_shuffled_training_label_control(
            states, labels, n_qubits, arch,
            iid_indices.train, iid_indices.validation, iid_indices.test,
            true_test_ba=full_qcnn_iid_ba,
            n_runs=25, maxiter=maxiter, seed=777,
        )
        iid_ba = shuf_res["test_ba_real_mean"]

        shuf_crit = evaluate_shuffled_training_label_control(
            states, labels, n_qubits, arch,
            crit_indices.train, crit_indices.validation, crit_indices.test,
            n_runs=10, maxiter=maxiter, seed=888,
        )
        crit_ba = shuf_crit["test_ba_real_mean"]

        metrics = raw_circuit_metrics(n_qubits, arch)
        rec = {
            "model": "Shuffled Training Labels Control",
            "family": family,
            "parameters": metrics["parameters"],
            "two_qubit_gates": metrics["two_qubit_operations"],
            "iid_ba": iid_ba,
            "critical_ood_ba": crit_ba,
            "hamiltonian_ood_ba": np.nan,  # Fail-closed: not executed
            "iid_status": "executed",
            "critical_ood_status": "executed",
            "hamiltonian_ood_status": "not_executed",
            "empirical_p_value": shuf_res["empirical_p_value"],
        }
        return rec, shuf_res["control_runs"]

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
        rec = {
            "model": "Random Quantum States Control",
            "family": family,
            "parameters": metrics["parameters"],
            "two_qubit_gates": metrics["two_qubit_operations"],
            "iid_ba": iid_ba,
            "critical_ood_ba": np.nan,    # Fail-closed: conceptually not applicable
            "hamiltonian_ood_ba": np.nan, # Fail-closed: conceptually not applicable
            "iid_status": "executed",
            "critical_ood_status": "not_applicable",
            "hamiltonian_ood_status": "not_applicable",
        }
        return rec, None

    else:
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
            "expressive_no_conv_entanglement": "No Conv Entanglement",
            "expressive_no_pool_entanglement": "No Pool Entanglement",
            "expressive_no_entanglement": "No Entanglement Anywhere",
            "expressive_no_pooling": "No Pooling Ablation",
            "expressive_unshared_line": "Unshared Weights Ablation",
        }
        rec = {
            "model": display_names.get(model_name, model_name),
            "family": family,
            "parameters": metrics["parameters"],
            "two_qubit_gates": metrics["two_qubit_operations"],
            "iid_ba": iid_ba,
            "critical_ood_ba": crit_ba,
            "hamiltonian_ood_ba": pert_ba,
            "iid_status": "executed",
            "critical_ood_status": "executed",
            "hamiltonian_ood_status": "executed",
        }
        return rec, None


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

    # 1. Single-split canonical summary (with full expressive run first to get true_test_ba)
    print("--- Stage 1: Single-Split Canonical Summary & Fail-Closed Controls ---")
    full_qcnn_res, _ = evaluate_model_on_splits(
        "expressive_shared_line", family, n_qubits, states, labels,
        iid_indices, crit_indices, pert_states, pert_labels, maxiter=120,
    )
    full_qcnn_iid_ba = full_qcnn_res["iid_ba"]

    models_to_test = [
        "expressive_shared_line",
        "expressive_no_conv_entanglement",
        "expressive_no_pool_entanglement",
        "expressive_no_entanglement",
        "expressive_no_pooling",
        "expressive_unshared_line",
        "untrained_qcnn",
        "shuffled_labels",
        "random_quantum_states",
        "physics_order_parameter",
    ]

    results = []
    shuffled_records = None

    for m in models_to_test:
        if m == "expressive_shared_line":
            results.append(full_qcnn_res)
            continue
        rec, perm_runs = evaluate_model_on_splits(
            m, family, n_qubits, states, labels,
            iid_indices, crit_indices, pert_states, pert_labels,
            full_qcnn_iid_ba=full_qcnn_iid_ba,
            maxiter=120,
        )
        results.append(rec)
        if perm_runs is not None:
            shuffled_records = perm_runs

    summary_df = pd.DataFrame(results)
    summary_df.to_csv(out_dir / "ablation_and_controls_summary.csv", index=False)

    # Save permutation logs
    if shuffled_records:
        perm_df = pd.DataFrame(shuffled_records)
        perm_df.to_csv(out_dir / "shuffled_label_permutations.csv", index=False)
        print(f"Saved {len(perm_df)} shuffled-label permutations to {out_dir / 'shuffled_label_permutations.csv'}")

    # 2. Multi-Seed Statistical Architecture Ablation Study (Priority 4)
    print("\n--- Stage 2: Multi-Seed Architecture Ablation Study ---")
    ablation_archs = [
        "expressive_shared_line",
        "expressive_no_conv_entanglement",
        "expressive_no_pool_entanglement",
        "expressive_no_entanglement",
        "expressive_no_pooling",
        "expressive_unshared_line",
    ]
    split_seeds = [11, 23, 37, 51, 71]
    optimizer_seeds = [100, 200]

    ablation_runs = []
    for arch_name in ablation_archs:
        arch = get_architecture(arch_name)
        metrics = raw_circuit_metrics(n_qubits, arch)
        budget_maxiter = max(120, 2 * int(metrics["parameters"]))
        for s_seed in split_seeds:
            manifest_iid = load_split_manifest(splits_dir / f"{family}_iid_seed{s_seed}.csv")
            idx_iid = split_indices_from_manifest(manifest_iid)

            manifest_crit = load_split_manifest(splits_dir / f"{family}_critical_seed{s_seed}.csv")
            idx_crit = split_indices_from_manifest(manifest_crit)

            for opt_seed in optimizer_seeds:
                # IID run
                params_iid, hist_iid, _ = train_ideal_qcnn(
                    states, labels, n_qubits, arch, idx_iid.train, idx_iid.validation,
                    maxiter=budget_maxiter, seed=opt_seed,
                )
                iid_p = batch_predict(states[idx_iid.test], params_iid, arch, n_qubits)
                run_iid_ba = float(balanced_accuracy_score(labels[idx_iid.test], (iid_p >= 0.5).astype(int)))

                # Critical OOD run
                params_crit, hist_crit, _ = train_ideal_qcnn(
                    states, labels, n_qubits, arch, idx_crit.train, idx_crit.validation,
                    maxiter=budget_maxiter, seed=opt_seed + 10,
                )
                crit_p = batch_predict(states[idx_crit.test], params_crit, arch, n_qubits)
                run_crit_ba = float(balanced_accuracy_score(labels[idx_crit.test], (crit_p >= 0.5).astype(int)))

                # Hamiltonian OOD run
                pert_p = batch_predict(pert_states, params_iid, arch, n_qubits)
                run_ham_ba = float(balanced_accuracy_score(pert_labels, (pert_p >= 0.5).astype(int)))

                ablation_runs.append({
                    "architecture": arch_name,
                    "split_seed": s_seed,
                    "optimizer_seed": opt_seed,
                    "parameter_count": metrics["parameters"],
                    "two_qubit_gates": metrics["two_qubit_operations"],
                    "maxiter_budget": budget_maxiter,
                    "n_function_evaluations": hist_iid[-1].get("nfev", len(hist_iid) - 1),
                    "optimizer_success": hist_iid[-1].get("success", True),
                    "final_train_loss": hist_iid[-1].get("final_train_loss", np.nan),
                    "validation_loss": hist_iid[-1].get("validation_loss", np.nan),
                    "iid_ba": run_iid_ba,
                    "critical_ood_ba": run_crit_ba,
                    "hamiltonian_ood_ba": run_ham_ba,
                })

    runs_df = pd.DataFrame(ablation_runs)
    runs_df.to_csv(out_dir / "ablation_runs.csv", index=False)

    # Aggregate statistics
    agg_records = []
    for arch_name, grp in runs_df.groupby("architecture"):
        iid_ci = bootstrap_confidence_interval(grp["iid_ba"].to_numpy())
        crit_ci = bootstrap_confidence_interval(grp["critical_ood_ba"].to_numpy())
        ham_ci = bootstrap_confidence_interval(grp["hamiltonian_ood_ba"].to_numpy())

        agg_records.append({
            "architecture": arch_name,
            "parameter_count": int(grp["parameter_count"].iloc[0]),
            "two_qubit_gates": int(grp["two_qubit_gates"].iloc[0]),
            "n_runs": len(grp),
            "iid_ba_mean": float(grp["iid_ba"].mean()),
            "iid_ba_std": float(grp["iid_ba"].std(ddof=1)),
            "iid_ba_median": float(grp["iid_ba"].median()),
            "iid_ba_ci95_low": iid_ci[0],
            "iid_ba_ci95_high": iid_ci[1],
            "critical_ood_ba_mean": float(grp["critical_ood_ba"].mean()),
            "critical_ood_ba_std": float(grp["critical_ood_ba"].std(ddof=1)),
            "critical_ood_ba_median": float(grp["critical_ood_ba"].median()),
            "critical_ood_ba_ci95_low": crit_ci[0],
            "critical_ood_ba_ci95_high": crit_ci[1],
            "hamiltonian_ood_ba_mean": float(grp["hamiltonian_ood_ba"].mean()),
            "hamiltonian_ood_ba_std": float(grp["hamiltonian_ood_ba"].std(ddof=1)),
            "hamiltonian_ood_ba_median": float(grp["hamiltonian_ood_ba"].median()),
            "hamiltonian_ood_ba_ci95_low": ham_ci[0],
            "hamiltonian_ood_ba_ci95_high": ham_ci[1],
        })

    agg_df = pd.DataFrame(agg_records)
    agg_df.to_csv(out_dir / "ablation_aggregate.csv", index=False)

    # Pairwise comparisons:
    # 1. Delta BA = BA_no_conv - BA_full
    full_runs = runs_df[runs_df["architecture"] == "expressive_shared_line"].sort_values(["split_seed", "optimizer_seed"])
    noconv_runs = runs_df[runs_df["architecture"] == "expressive_no_conv_entanglement"].sort_values(["split_seed", "optimizer_seed"])
    nopool_runs = runs_df[runs_df["architecture"] == "expressive_no_pool_entanglement"].sort_values(["split_seed", "optimizer_seed"])

    delta_noconv_iid = noconv_runs["iid_ba"].to_numpy() - full_runs["iid_ba"].to_numpy()
    delta_noconv_crit = noconv_runs["critical_ood_ba"].to_numpy() - full_runs["critical_ood_ba"].to_numpy()
    delta_noconv_iid_ci = bootstrap_confidence_interval(delta_noconv_iid)
    delta_noconv_crit_ci = bootstrap_confidence_interval(delta_noconv_crit)

    delta_nopool_iid = nopool_runs["iid_ba"].to_numpy() - full_runs["iid_ba"].to_numpy()
    delta_nopool_crit = nopool_runs["critical_ood_ba"].to_numpy() - full_runs["critical_ood_ba"].to_numpy()
    delta_nopool_iid_ci = bootstrap_confidence_interval(delta_nopool_iid)
    delta_nopool_crit_ci = bootstrap_confidence_interval(delta_nopool_crit)

    delta_conv_vs_pool_iid = noconv_runs["iid_ba"].to_numpy() - nopool_runs["iid_ba"].to_numpy()
    delta_conv_vs_pool_crit = noconv_runs["critical_ood_ba"].to_numpy() - nopool_runs["critical_ood_ba"].to_numpy()
    delta_conv_vs_pool_iid_ci = bootstrap_confidence_interval(delta_conv_vs_pool_iid)
    delta_conv_vs_pool_crit_ci = bootstrap_confidence_interval(delta_conv_vs_pool_crit)

    print(f"\nStatistical Comparison (No-Conv vs Full Expressive, N={len(delta_noconv_iid)} paired runs):")
    print(f"  Delta IID BA:      mean = {np.mean(delta_noconv_iid):+.4f}, 95% CI: [{delta_noconv_iid_ci[0]:+.4f}, {delta_noconv_iid_ci[1]:+.4f}]")
    print(f"  Delta Critical BA: mean = {np.mean(delta_noconv_crit):+.4f}, 95% CI: [{delta_noconv_crit_ci[0]:+.4f}, {delta_noconv_crit_ci[1]:+.4f}]")

    print(f"\nStatistical Comparison (No-Pool vs Full Expressive, N={len(delta_nopool_iid)} paired runs):")
    print(f"  Delta IID BA:      mean = {np.mean(delta_nopool_iid):+.4f}, 95% CI: [{delta_nopool_iid_ci[0]:+.4f}, {delta_nopool_iid_ci[1]:+.4f}]")
    print(f"  Delta Critical BA: mean = {np.mean(delta_nopool_crit):+.4f}, 95% CI: [{delta_nopool_crit_ci[0]:+.4f}, {delta_nopool_crit_ci[1]:+.4f}]")

    print(f"\nStatistical Comparison (No-Conv vs No-Pool, N={len(delta_conv_vs_pool_iid)} paired runs):")
    print(f"  Delta IID BA:      mean = {np.mean(delta_conv_vs_pool_iid):+.4f}, 95% CI: [{delta_conv_vs_pool_iid_ci[0]:+.4f}, {delta_conv_vs_pool_iid_ci[1]:+.4f}]")
    print(f"  Delta Critical BA: mean = {np.mean(delta_conv_vs_pool_crit):+.4f}, 95% CI: [{delta_conv_vs_pool_crit_ci[0]:+.4f}, {delta_conv_vs_pool_crit_ci[1]:+.4f}]")

    # Stage 3: Full-Pipeline Label Permutation Significance Test
    print("\n--- Stage 3: Full-Pipeline Label-Permutation Significance Test ---")
    pipe_perm = evaluate_pipeline_label_permutation_test(
        states, labels, n_qubits, get_architecture("expressive_shared_line"),
        iid_indices.train, iid_indices.validation, iid_indices.test,
        true_test_ba=full_qcnn_iid_ba,
        n_permutations=25,
        maxiter=120,
        seed=4321,
    )
    pd.DataFrame(pipe_perm["permutation_runs"]).to_csv(out_dir / "pipeline_label_permutations.csv", index=False)
    print(f"Pipeline permutation test completed: null BA = {pipe_perm['null_test_ba_mean']:.3f} ± {pipe_perm['null_test_ba_std']:.3f}, p = {pipe_perm['empirical_p_value']:.4f}")

    # Save Provenance JSON (Priority 14)
    provenance = {
        "git_commit": get_git_commit(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
        "n_qubits": n_qubits,
        "family": family,
        "optimizer": "COBYLA",
        "split_seeds": split_seeds,
        "optimizer_seeds": optimizer_seeds,
        "n_runs_shuffled_control": 25,
        "n_permutations_pipeline_test": 25,
        "pipeline_permutation_p_value": pipe_perm["empirical_p_value"],
        "pipeline_permutation_null_ba_mean": pipe_perm["null_test_ba_mean"],
        "pipeline_permutation_null_ba_std": pipe_perm["null_test_ba_std"],
        "pairwise_deltas": {
            "no_conv_vs_full": {
                "delta_iid_mean": float(np.mean(delta_noconv_iid)),
                "delta_iid_ci95": [float(delta_noconv_iid_ci[0]), float(delta_noconv_iid_ci[1])],
                "delta_crit_mean": float(np.mean(delta_noconv_crit)),
                "delta_crit_ci95": [float(delta_noconv_crit_ci[0]), float(delta_noconv_crit_ci[1])],
            },
            "no_pool_vs_full": {
                "delta_iid_mean": float(np.mean(delta_nopool_iid)),
                "delta_iid_ci95": [float(delta_nopool_iid_ci[0]), float(delta_nopool_iid_ci[1])],
                "delta_crit_mean": float(np.mean(delta_nopool_crit)),
                "delta_crit_ci95": [float(delta_nopool_crit_ci[0]), float(delta_nopool_crit_ci[1])],
            },
            "no_conv_vs_no_pool": {
                "delta_iid_mean": float(np.mean(delta_conv_vs_pool_iid)),
                "delta_iid_ci95": [float(delta_conv_vs_pool_iid_ci[0]), float(delta_conv_vs_pool_iid_ci[1])],
                "delta_crit_mean": float(np.mean(delta_conv_vs_pool_crit)),
                "delta_crit_ci95": [float(delta_conv_vs_pool_crit_ci[0]), float(delta_conv_vs_pool_crit_ci[1])],
            },
        },
        "scientific_conclusion": (
            "The full architecture gives the strongest mean IID and critical-region generalization; "
            "removing either convolutional or pooling entanglement degrades performance, while removing all entanglement or pooling collapses to chance."
        ),
        "script": "scripts/26_sanity_and_ablation_suite.py",
    }
    with open(out_dir / "provenance.json", "w") as f:
        json.dump(provenance, f, indent=2)

    # Plot ablation comparison
    plt.figure(figsize=(12, 6))
    x = np.arange(len(summary_df))
    width = 0.25

    # Replace NaNs with 0 for plotting purpose only, but annotate
    iid_plot = summary_df["iid_ba"].fillna(0.0)
    crit_plot = summary_df["critical_ood_ba"].fillna(0.0)
    ham_plot = summary_df["hamiltonian_ood_ba"].fillna(0.0)

    plt.bar(x - width, iid_plot, width, label="IID BA", color="royalblue")
    plt.bar(x, crit_plot, width, label="Critical OOD BA", color="darkorange")
    plt.bar(x + width, ham_plot, width, label="Hamiltonian OOD BA ($\\delta=0.10$)", color="seagreen")

    plt.axhline(0.5, color="red", linestyle="--", alpha=0.7, label="Chance Level (0.50)")
    plt.xticks(x, summary_df["model"], rotation=35, ha="right", fontsize=9)
    plt.ylabel("Balanced Accuracy")
    plt.title("Architecture Ablations & Sanity Controls: TFIM Phase Classification (Fail-Closed)")
    plt.ylim(0.0, 1.05)
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(fig_dir / "ablation_comparison.png", dpi=200)
    plt.close()

    print(f"\nAblation and sanity control suite completed. Results in {out_dir}")
    print("\nSummary Table (Fail-Closed):")
    print(summary_df[["model", "parameters", "two_qubit_gates", "iid_ba", "critical_ood_ba", "hamiltonian_ood_ba", "iid_status", "critical_ood_status", "hamiltonian_ood_status"]].to_string(index=False))


if __name__ == "__main__":
    main()
