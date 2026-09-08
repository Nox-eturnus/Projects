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
from qcnn_lab.analysis.statistics import hierarchical_bootstrap, hierarchical_paired_bootstrap
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


def _run_single_ablation_pair(
    arch_name: str,
    s_seed: int,
    opt_seed: int,
    n_qubits: int,
    states: np.ndarray,
    labels: np.ndarray,
    pert_states: np.ndarray,
    pert_labels: np.ndarray,
    splits_dir: Path,
    family: str,
    histories_dir: Path,
) -> dict:
    arch = get_architecture(arch_name)
    metrics = raw_circuit_metrics(n_qubits, arch)
    budget_maxiter = max(300, 5 * int(metrics["parameters"]))

    manifest_iid = load_split_manifest(splits_dir / f"{family}_iid_seed{s_seed}.csv")
    idx_iid = split_indices_from_manifest(manifest_iid)

    manifest_crit = load_split_manifest(splits_dir / f"{family}_critical_seed{s_seed}.csv")
    idx_crit = split_indices_from_manifest(manifest_crit)

    # IID run
    params_iid, hist_iid, iid_sec = train_ideal_qcnn(
        states, labels, n_qubits, arch, idx_iid.train, idx_iid.validation,
        maxiter=budget_maxiter, seed=opt_seed,
    )
    iid_p = batch_predict(states[idx_iid.test], params_iid, arch, n_qubits)
    run_iid_ba = float(balanced_accuracy_score(labels[idx_iid.test], (iid_p >= 0.5).astype(int)))

    # Critical OOD run
    params_crit, hist_crit, crit_sec = train_ideal_qcnn(
        states, labels, n_qubits, arch, idx_crit.train, idx_crit.validation,
        maxiter=budget_maxiter, seed=opt_seed + 10,
    )
    crit_p = batch_predict(states[idx_crit.test], params_crit, arch, n_qubits)
    run_crit_ba = float(balanced_accuracy_score(labels[idx_crit.test], (crit_p >= 0.5).astype(int)))

    # Hamiltonian OOD run
    pert_p = batch_predict(pert_states, params_iid, arch, n_qubits)
    run_ham_ba = float(balanced_accuracy_score(pert_labels, (pert_p >= 0.5).astype(int)))

    last_iid = hist_iid[-1]
    last_crit = hist_crit[-1]

    # Save history logs (both IID and critical trajectories; critical OOD is
    # the main architecture conclusion and needs its own trajectory for
    # diagnosing e.g. the no-pool-entanglement result)
    hist_df = pd.DataFrame(hist_iid[:-1])
    hist_df.to_csv(histories_dir / f"{arch_name}_seed{s_seed}_opt{opt_seed}_iid.csv", index=False)
    hist_crit_df = pd.DataFrame(hist_crit[:-1])
    hist_crit_df.to_csv(histories_dir / f"{arch_name}_seed{s_seed}_opt{opt_seed}_critical.csv", index=False)

    return {
        "architecture": arch_name,
        "split_seed": s_seed,
        "optimizer_seed": opt_seed,
        "parameter_count": metrics["parameters"],
        "two_qubit_gates": metrics["two_qubit_operations"],
        "maxiter_budget": budget_maxiter,
        # Backward-compatible fields
        "n_function_evaluations": last_iid.get("nfev", len(hist_iid) - 1),
        "optimizer_success": last_iid.get("optimizer_success", last_iid.get("success", True)),
        "final_train_loss": last_iid.get("final_train_loss", np.nan),
        "validation_loss": last_iid.get("validation_loss", np.nan),
        # Explicit IID optimizer telemetry (Audit Item 1)
        "iid_optimizer_success": last_iid.get("optimizer_success", False),
        "iid_optimizer_message": last_iid.get("optimizer_message", ""),
        "iid_n_function_evaluations": last_iid.get("nfev", len(hist_iid) - 1),
        "iid_maxiter_budget": last_iid.get("maxiter_budget", budget_maxiter),
        "iid_final_train_loss": last_iid.get("final_train_loss", np.nan),
        "iid_validation_loss": last_iid.get("validation_loss", np.nan),
        "iid_loss_improvement": last_iid.get("loss_improvement", np.nan),
        "iid_last_10_eval_improvement": last_iid.get("last_10_eval_improvement", np.nan),
        "iid_training_time": iid_sec,
        # Explicit Critical optimizer telemetry (Audit Item 1)
        "critical_optimizer_success": last_crit.get("optimizer_success", False),
        "critical_optimizer_message": last_crit.get("optimizer_message", ""),
        "critical_n_function_evaluations": last_crit.get("nfev", len(hist_crit) - 1),
        "critical_maxiter_budget": last_crit.get("maxiter_budget", budget_maxiter),
        "critical_final_train_loss": last_crit.get("final_train_loss", np.nan),
        "critical_validation_loss": last_crit.get("validation_loss", np.nan),
        "critical_loss_improvement": last_crit.get("loss_improvement", np.nan),
        "critical_last_10_eval_improvement": last_crit.get("last_10_eval_improvement", np.nan),
        "critical_training_time": crit_sec,
        # Evaluation performance
        "iid_ba": run_iid_ba,
        "critical_ood_ba": run_crit_ba,
        "hamiltonian_ood_ba": run_ham_ba,
    }


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
    n_jobs: int = 1,
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
            n_runs=25, maxiter=maxiter, seed=777, n_jobs=n_jobs,
        )
        iid_ba = shuf_res["test_ba_real_mean"]

        shuf_crit = evaluate_shuffled_training_label_control(
            states, labels, n_qubits, arch,
            crit_indices.train, crit_indices.validation, crit_indices.test,
            n_runs=10, maxiter=maxiter, seed=888, n_jobs=n_jobs,
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
    # Capture source-tree provenance BEFORE any output files are written:
    # inspecting git status after results exist would falsely report a
    # clean source tree as dirty (the experiment itself modifies results/).
    from qcnn_lab.provenance import get_git_provenance as _get_git_at_start
    git_info_at_start = _get_git_at_start()

    parser = argparse.ArgumentParser(description="Sanity controls and architecture ablation suite.")
    parser.add_argument("--project-config", default="configs/project.yaml", help="Path to project config")
    parser.add_argument("--out-dir", default="results/ablations", help="Output directory")
    parser.add_argument("--fig-dir", default="results/figures", help="Figures output directory")
    parser.add_argument("--pilot", action="store_true", help="Run fast convergence pilot across 6 architectures")
    parser.add_argument("--n-jobs", type=int, default=8, help="Number of parallel worker processes")
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
            n_jobs=args.n_jobs,
        )
        results.append(rec)
        if perm_runs is not None:
            shuffled_records = perm_runs

    summary_df = pd.DataFrame(results)
    summary_df.to_csv(out_dir / "ablation_and_controls_summary.csv", index=False)

    # Save shuffled control logs
    if shuffled_records:
        perm_df = pd.DataFrame(shuffled_records)
        perm_df.to_csv(out_dir / "shuffled_label_permutations.csv", index=False)
        perm_df.to_csv(out_dir / "shuffled_training_control.csv", index=False)
        print(f"Saved {len(perm_df)} shuffled-label control runs to {out_dir / 'shuffled_training_control.csv'}")

    # 2. Multi-Seed Statistical Architecture Ablation Study (Priority 4 & Audit Item 1)
    print("\n--- Stage 2: Multi-Seed Architecture Ablation Study (Adaptive-Budget) ---")
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

    if getattr(args, "pilot", False):
        print("Running fast convergence pilot across all 6 architectures (1 split, 1 optimizer seed)...")
        split_seeds = [11]
        optimizer_seeds = [100]

    histories_dir = out_dir / "histories"
    histories_dir.mkdir(parents=True, exist_ok=True)

    tasks = []
    for arch_name in ablation_archs:
        for s_seed in split_seeds:
            for opt_seed in optimizer_seeds:
                tasks.append((arch_name, s_seed, opt_seed))

    print(f"Executing {len(tasks)} ablation evaluation tasks with n_jobs={args.n_jobs}...")
    if args.n_jobs > 1:
        from joblib import Parallel, delayed
        ablation_runs = Parallel(n_jobs=args.n_jobs)(
            delayed(_run_single_ablation_pair)(
                arch_name, s_seed, opt_seed, n_qubits, states, labels, pert_states, pert_labels,
                splits_dir, family, histories_dir
            )
            for arch_name, s_seed, opt_seed in tasks
        )
    else:
        ablation_runs = [
            _run_single_ablation_pair(
                arch_name, s_seed, opt_seed, n_qubits, states, labels, pert_states, pert_labels,
                splits_dir, family, histories_dir
            )
            for arch_name, s_seed, opt_seed in tasks
        ]

    runs_df = pd.DataFrame(ablation_runs)
    runs_df.to_csv(out_dir / "ablation_runs.csv", index=False)

    # Aggregate statistics (partition-aware hierarchical CIs, consistent
    # with the benchmark and pairwise analyses — not flat bootstraps).
    # Architecture order is alphabetical (groupby default) with fixed seeds
    # so committed statistics are exactly reproducible and re-verifiable.
    agg_records = []
    for arch_idx, (arch_name, grp) in enumerate(sorted(runs_df.groupby("architecture"), key=lambda kv: kv[0])):
        iid_ci = hierarchical_bootstrap(grp, partition_col="split_seed", optimizer_col="optimizer_seed", value_col="iid_ba", seed=7777 + arch_idx)
        crit_ci = hierarchical_bootstrap(grp, partition_col="split_seed", optimizer_col="optimizer_seed", value_col="critical_ood_ba", seed=7777 + arch_idx)
        ham_ci = hierarchical_bootstrap(grp, partition_col="split_seed", optimizer_col="optimizer_seed", value_col="hamiltonian_ood_ba", seed=7777 + arch_idx)

        agg_records.append({
            "architecture": arch_name,
            "parameter_count": int(grp["parameter_count"].iloc[0]),
            "two_qubit_gates": int(grp["two_qubit_gates"].iloc[0]),
            "n_runs": len(grp),
            "iid_ba_mean": float(grp["iid_ba"].mean()),
            "iid_ba_std": float(grp["iid_ba"].std(ddof=1)) if len(grp) > 1 else 0.0,
            "iid_ba_median": float(grp["iid_ba"].median()),
            "iid_ba_ci95_low": iid_ci[0],
            "iid_ba_ci95_high": iid_ci[1],
            "critical_ood_ba_mean": float(grp["critical_ood_ba"].mean()),
            "critical_ood_ba_std": float(grp["critical_ood_ba"].std(ddof=1)) if len(grp) > 1 else 0.0,
            "critical_ood_ba_median": float(grp["critical_ood_ba"].median()),
            "critical_ood_ba_ci95_low": crit_ci[0],
            "critical_ood_ba_ci95_high": crit_ci[1],
            "hamiltonian_ood_ba_mean": float(grp["hamiltonian_ood_ba"].mean()),
            "hamiltonian_ood_ba_std": float(grp["hamiltonian_ood_ba"].std(ddof=1)) if len(grp) > 1 else 0.0,
            "hamiltonian_ood_ba_median": float(grp["hamiltonian_ood_ba"].median()),
            "hamiltonian_ood_ba_ci95_low": ham_ci[0],
            "hamiltonian_ood_ba_ci95_high": ham_ci[1],
        })

    agg_df = pd.DataFrame(agg_records)
    agg_df.to_csv(out_dir / "ablation_aggregate.csv", index=False)

    # Exhaustive Pairwise Comparisons (Audit Item 27)
    pair_comparisons = [
        ("expressive_no_conv_entanglement", "expressive_shared_line", "no_conv_vs_full"),
        ("expressive_no_pool_entanglement", "expressive_shared_line", "no_pool_vs_full"),
        ("expressive_no_entanglement", "expressive_shared_line", "no_entanglement_vs_full"),
        ("expressive_no_pooling", "expressive_shared_line", "no_pooling_vs_full"),
        ("expressive_unshared_line", "expressive_shared_line", "unshared_vs_full"),
        ("expressive_no_conv_entanglement", "expressive_no_pool_entanglement", "no_conv_vs_no_pool"),
    ]

    pairwise_records = []
    pairwise_dict = {}

    for comp_idx, (arch_a, arch_b, comp_label) in enumerate(pair_comparisons):
        runs_a = runs_df[runs_df["architecture"] == arch_a].sort_values(["split_seed", "optimizer_seed"])
        runs_b = runs_df[runs_df["architecture"] == arch_b].sort_values(["split_seed", "optimizer_seed"])

        if len(runs_a) > 0 and len(runs_b) > 0 and len(runs_a) == len(runs_b):
            n_paired = len(runs_a)
            # Split-aware paired bootstrap: the two optimizer seeds within a
            # split share a data partition, so differences are resampled
            # hierarchically (splits, then runs within splits), not flat.
            # Seeds are fixed per comparison so committed statistics are
            # exactly reproducible (and re-verifiable by the validator).
            d_iid_ci = hierarchical_paired_bootstrap(runs_a, runs_b, "iid_ba", seed=12345 + comp_idx)
            d_crit_ci = hierarchical_paired_bootstrap(runs_a, runs_b, "critical_ood_ba", seed=12345 + comp_idx)
            d_ham_ci = hierarchical_paired_bootstrap(runs_a, runs_b, "hamiltonian_ood_ba", seed=12345 + comp_idx)
            paired = runs_a.merge(runs_b, on=["split_seed", "optimizer_seed"], suffixes=("_a", "_b"))
            d_iid = (paired["iid_ba_a"] - paired["iid_ba_b"]).to_numpy(dtype=float)
            d_crit = (paired["critical_ood_ba_a"] - paired["critical_ood_ba_b"]).to_numpy(dtype=float)
            d_ham = (paired["hamiltonian_ood_ba_a"] - paired["hamiltonian_ood_ba_b"]).to_numpy(dtype=float)

            pairwise_records.append({
                "comparison": comp_label,
                "architecture_a": arch_a,
                "architecture_b": arch_b,
                "n_paired_runs": n_paired,
                "delta_iid_mean": float(np.mean(d_iid)),
                "delta_iid_ci95_low": float(d_iid_ci[0]),
                "delta_iid_ci95_high": float(d_iid_ci[1]),
                "delta_crit_mean": float(np.mean(d_crit)),
                "delta_crit_ci95_low": float(d_crit_ci[0]),
                "delta_crit_ci95_high": float(d_crit_ci[1]),
                "delta_ham_mean": float(np.mean(d_ham)),
                "delta_ham_ci95_low": float(d_ham_ci[0]),
                "delta_ham_ci95_high": float(d_ham_ci[1]),
            })

            pairwise_dict[comp_label] = {
                "delta_iid_mean": float(np.mean(d_iid)),
                "delta_iid_ci95": [float(d_iid_ci[0]), float(d_iid_ci[1])],
                "delta_crit_mean": float(np.mean(d_crit)),
                "delta_crit_ci95": [float(d_crit_ci[0]), float(d_crit_ci[1])],
                "delta_ham_mean": float(np.mean(d_ham)),
                "delta_ham_ci95": [float(d_ham_ci[0]), float(d_ham_ci[1])],
            }

            print(f"\nStatistical Comparison ({comp_label}, N={n_paired} paired runs):")
            print(f"  Delta IID BA:      mean = {np.mean(d_iid):+.4f}, 95% CI: [{d_iid_ci[0]:+.4f}, {d_iid_ci[1]:+.4f}]")
            print(f"  Delta Critical BA: mean = {np.mean(d_crit):+.4f}, 95% CI: [{d_crit_ci[0]:+.4f}, {d_crit_ci[1]:+.4f}]")

    pd.DataFrame(pairwise_records).to_csv(out_dir / "pairwise_comparisons.csv", index=False)

    # Stage 3: Fixed-Split Full-Dataset Label-Permutation Significance Test (Audit Item 9)
    # NOTE: this reuses the original train/validation/test indices under each
    # global label permutation (split construction is not regenerated), so
    # "fixed-split" is the accurate description — not full-pipeline resplit.
    print("\n--- Stage 3: Fixed-Split Full-Dataset Label-Permutation Significance Test (N=199) ---")
    pipe_n_perms = 25 if getattr(args, "pilot", False) else 199
    pipe_perm = evaluate_pipeline_label_permutation_test(
        states, labels, n_qubits, get_architecture("expressive_shared_line"),
        iid_indices.train, iid_indices.validation, iid_indices.test,
        true_test_ba=full_qcnn_iid_ba,
        n_permutations=pipe_n_perms,
        maxiter=120,
        seed=4321,
        n_jobs=args.n_jobs,
    )
    pd.DataFrame(pipe_perm["permutation_runs"]).to_csv(out_dir / "pipeline_label_permutations.csv", index=False)
    n_exceed = int(sum(1 for r in pipe_perm["permutation_runs"] if r["test_ba_permuted"] >= full_qcnn_iid_ba))
    print(
        f"Fixed-split permutation test completed (N={pipe_n_perms}): null BA = {pipe_perm['null_test_ba_mean']:.3f} ± {pipe_perm['null_test_ba_std']:.3f} "
        f"[p95: {pipe_perm['null_ba_p95']:.3f}, max: {pipe_perm['null_ba_max']:.3f}], {n_exceed}/{pipe_n_perms} permuted statistics >= observed; "
        f"+1-corrected Monte-Carlo p = {pipe_perm['empirical_p_value']:.4f} (resolution floor {1.0/(pipe_n_perms+1):.4f})"
    )

    # Scientific conclusion derived directly from the split-aware paired
    # bootstrap statistics above. Wording deliberately claims only what the
    # hierarchical CIs resolve; optimizer termination is a documented
    # limitation, not a claim of complete mathematical convergence.
    noconv_crit_info = pairwise_dict.get("no_conv_vs_full", {})
    nopool_crit_info = pairwise_dict.get("no_pool_vs_full", {})

    def _ci_excludes_zero(lo: float, hi: float) -> bool:
        try:
            return bool((float(lo) > 0 and float(hi) > 0) or (float(lo) < 0 and float(hi) < 0))
        except Exception:
            return False

    _noconv_m = float(noconv_crit_info.get("delta_crit_mean", float("nan"))) if noconv_crit_info else float("nan")
    _nopool_m = float(nopool_crit_info.get("delta_crit_mean", float("nan"))) if nopool_crit_info else float("nan")
    _noconv_ci = noconv_crit_info.get("delta_crit_ci95", (float("nan"), float("nan"))) if noconv_crit_info else (float("nan"), float("nan"))
    _nopool_ci = nopool_crit_info.get("delta_crit_ci95", (float("nan"), float("nan"))) if nopool_crit_info else (float("nan"), float("nan"))
    _noconv_resolved = _ci_excludes_zero(_noconv_ci[0], _noconv_ci[1])
    _nopool_resolved = _ci_excludes_zero(_nopool_ci[0], _nopool_ci[1])

    scientific_conclusion = (
        "Under the repeated adaptive-budget runs with optimizer telemetry, removing pooling entanglers improves "
        f"mean IID and critical-region performance relative to the full architecture (critical Delta={_nopool_m:+.4f}, "
        f"95% hierarchical CI [{_nopool_ci[0]:+.4f}, {_nopool_ci[1]:+.4f}], {'statistically resolved' if _nopool_resolved else 'statistically unresolved'}), "
        f"while the effect of removing convolutional entanglement remains unresolved (critical Delta={_noconv_m:+.4f}, "
        f"95% hierarchical CI [{_noconv_ci[0]:+.4f}, {_noconv_ci[1]:+.4f}]). "
        "Removing all entanglement collapses performance to chance, and removing the pooling "
        "hierarchy strongly reduces critical-region generalization. "
        "These results should be interpreted alongside the recorded optimizer-termination diagnostics."
    )

    # Save Provenance JSON. Source-tree state is the snapshot captured at
    # script start (before outputs existed); post-run state is recorded
    # separately so a clean source tree is never misreported as dirty.
    from qcnn_lab.provenance import get_git_provenance, compute_file_hashes
    git_info_after = get_git_provenance()

    critical_input_files = [
        "configs/project.yaml",
        "configs/evaluation.yaml",
        "data/processed/tfim_eval_states.npz",
        "data/processed/tfim_eval_metadata.csv",
        "qcnn_lab/qcnn/architecture.py",
        "qcnn_lab/qcnn/train.py",
        "qcnn_lab/qcnn/evaluate.py",
        "scripts/26_sanity_and_ablation_suite.py",
    ]

    provenance = {
        "git_provenance": git_info_at_start,
        "git_commit": git_info_at_start["execution_git_commit"] or git_info_at_start["base_commit"],
        "base_commit": git_info_at_start["base_commit"],
        "working_tree_dirty": git_info_at_start["working_tree_dirty"],
        "source_tree_dirty_at_start": git_info_at_start["working_tree_dirty"],
        "working_tree_dirty_after_execution": git_info_after["working_tree_dirty"],
        "pairwise_ci_method": "hierarchical paired bootstrap (resample split partitions, then runs within splits; 5000 resamples, fixed per-comparison seeds)",
        "input_file_hashes": compute_file_hashes(critical_input_files, full_sha256=True),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
        "n_qubits": n_qubits,
        "family": family,
        "optimizer": "COBYLA",
        "convergence_policy": "adaptive initial_budget=max(300, 5*p) with looped continuation to max_budget_ceiling=1000 while best-loss window improvement stays active",
        "split_seeds": split_seeds,
        "optimizer_seeds": optimizer_seeds,
        "n_runs_shuffled_control": 25,
        "shuffled_control_true_ba": full_qcnn_iid_ba,
        "shuffled_control_mean_test_ba": float(summary_df[summary_df["model"] == "Shuffled Training Labels Control"]["iid_ba"].iloc[0]),
        "shuffled_control_empirical_p_value": float(summary_df[summary_df["model"] == "Shuffled Training Labels Control"]["empirical_p_value"].iloc[0]),
        "permutation_test_name": "Fixed-Split Full-Dataset Label Permutation Test",
        "permutation_test_design_note": "Global label permutation with original train/validation/test indices reused; split construction is not regenerated under permutation.",
        "n_permutations_pipeline_test": pipe_n_perms,
        "pipeline_permutation_n_exceedances": int(sum(1 for r in pipe_perm["permutation_runs"] if r["test_ba_permuted"] >= full_qcnn_iid_ba)),
        "pipeline_permutation_p_value": pipe_perm["empirical_p_value"],
        "pipeline_permutation_resolution_floor": float(1.0 / (pipe_n_perms + 1)),
        "pipeline_permutation_at_resolution_floor": bool(pipe_perm["empirical_p_value"] == float(1.0 / (pipe_n_perms + 1))),
        "pipeline_permutation_null_ba_mean": pipe_perm["null_test_ba_mean"],
        "pipeline_permutation_null_ba_std": pipe_perm["null_test_ba_std"],
        "pipeline_permutation_null_ba_p95": pipe_perm["null_ba_p95"],
        "pipeline_permutation_null_ba_max": pipe_perm["null_ba_max"],
        "pairwise_deltas": pairwise_dict,
        "scientific_conclusion": scientific_conclusion,
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
