from __future__ import annotations

import argparse
import json
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score

from qcnn_lab.analysis.binomial_ci import clopper_pearson_interval
from qcnn_lab.analysis.calibration import brier_score
from qcnn_lab.config import load_yaml
from qcnn_lab.hardware.circuits import classifier_circuit, two_qubit_count
from qcnn_lab.hardware.ibm import (
    choose_backends,
    device_noise_predict,
    hardware_estimator_predict,
    service,
)
from qcnn_lab.metrics import binary_metrics
from qcnn_lab.qcnn.architecture import get_architecture
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.train import stratified_splits, train_ideal_qcnn


def main():
    # Capture source-tree provenance BEFORE any output files are written.
    from qcnn_lab.provenance import get_git_provenance as _get_git_at_start
    git_info_at_start = _get_git_at_start()

    parser = argparse.ArgumentParser(
        description="N=4 expressive QCNN hardware transfer benchmark across 4 execution stages."
    )
    parser.add_argument(
        "--mode",
        choices=["simulate", "hardware"],
        default="simulate",
        help="Execution mode: 'simulate' runs an analytical surrogate study with explicit provenance; 'hardware' executes real IBM EstimatorV2 jobs.",
    )
    parser.add_argument("--backend", default=None, help="Target backend name for real hardware execution")
    parser.add_argument("--shots", type=int, default=1024, help="Measurement shots")
    parser.add_argument("--out-dir", default="results/hardware", help="Output directory")
    parser.add_argument("--fig-dir", default="results/figures", help="Figures output directory")
    args = parser.parse_args()

    n_qubits = 4
    arch = get_architecture("expressive_shared_line")

    out_dir = Path(args.out_dir)
    fig_dir = Path(args.fig_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load N=4 dataset
    data_dir = Path("data/processed/hardware4")
    states = np.load(data_dir / "tfim_states.npz")["states"]
    meta = pd.read_csv(data_dir / "tfim_metadata.csv")
    y = meta["label"].to_numpy(dtype=int)

    splits = stratified_splits(y, train_fraction=0.70, validation_fraction=0.15, seed=12345)

    # 2. Train N=4 expressive QCNN
    print("Training N=4 Expressive QCNN for Hardware Benchmark...")
    params, _, _ = train_ideal_qcnn(
        states, y, n_qubits, arch, splits.train, splits.validation,
        maxiter=60, seed=12345,
    )

    test_states = states[splits.test]
    test_y = y[splits.test]

    # Stage 1: Ideal Simulator
    print("Stage 1: Evaluating Ideal Simulation...")
    ideal_p = batch_predict(test_states, params, arch, n_qubits)
    ideal_ba = float(balanced_accuracy_score(test_y, (ideal_p >= 0.5).astype(int)))

    if args.mode == "hardware":
        print("Initiating Live Physical IBM Hardware Execution...")
        try:
            svc = service()
            if args.backend:
                backend = svc.backend(args.backend)
            else:
                candidates = choose_backends(min_qubits=4, count=1)
                backend = candidates[0]
            backend_name = backend.name
            print(f"Connected to backend: {backend_name}")
        except Exception as e:
            raise RuntimeError(
                f"IBM Quantum hardware connection failed: {e}\n"
                "Please configure QiskitRuntimeService credentials or run with --mode simulate."
            ) from e

        # Stage 2: Device-Derived Aer Simulator
        print(f"Stage 2: Device-Derived Noise Simulator ({backend_name})...")
        noise_p, noise_metrics = device_noise_predict(
            test_states, params, arch, n_qubits, backend, shots=args.shots, seed=12345
        )
        noise_ba = float(balanced_accuracy_score(test_y, (noise_p >= 0.5).astype(int)))

        # Stage 3: Raw Physical Execution (Resilience Level 0)
        print(f"Stage 3: Submitting Raw QPU Job on {backend_name} (Resilience 0)...")
        raw_p, raw_job_id, raw_metrics = hardware_estimator_predict(
            test_states, params, arch, n_qubits, backend,
            precision=1.0 / np.sqrt(args.shots), resilience_level=0, dynamical_decoupling=False, seed_transpiler=12345
        )
        raw_ba = float(balanced_accuracy_score(test_y, (raw_p >= 0.5).astype(int)))

        # Stage 4: Readout & Dynamical Decoupling Mitigated QPU Execution
        print(f"Stage 4: Submitting Mitigated QPU Job on {backend_name} (Resilience 1 + DD)...")
        mit_p, mit_job_id, mit_metrics = hardware_estimator_predict(
            test_states, params, arch, n_qubits, backend,
            precision=1.0 / np.sqrt(args.shots), resilience_level=1, dynamical_decoupling=True, seed_transpiler=12345
        )
        mit_ba = float(balanced_accuracy_score(test_y, (mit_p >= 0.5).astype(int)))

        test_pred_labels = (mit_p >= 0.5).astype(int)
        test_correct = int(np.sum(test_pred_labels == test_y))
        test_sample_count = len(test_y)
        ci_low, ci_high = clopper_pearson_interval(test_correct, test_sample_count, confidence=0.95)

        # Provenance and code snapshot hashing
        critical_files = [
            "scripts/29_run_expressive_hardware_benchmark.py",
            "qcnn_lab/hardware/ibm.py",
            "qcnn_lab/hardware/circuits.py",
            "qcnn_lab/qcnn/architecture.py",
            "qcnn_lab/qcnn/evaluate.py",
        ]
        from qcnn_lab.provenance import compute_file_hashes, get_git_provenance, hash_parameter_vector
        file_hashes = compute_file_hashes(critical_files, full_sha256=True)
        h_all = hashlib.sha256()
        for f in critical_files:
            p = Path(f)
            if p.exists():
                h_all.update(p.read_bytes())
        code_snapshot_hash = h_all.hexdigest()

        ds_path = data_dir / "tfim_states.npz"
        dataset_hash = hashlib.sha256(ds_path.read_bytes()).hexdigest() if ds_path.exists() else "unknown"

        git_prov = git_info_at_start
        git_commit = git_prov["execution_git_commit"]
        working_dirty_at_start = git_prov["working_tree_dirty"]
        base_commit = git_prov["base_commit"]

        # Parse metrics list correctly
        def _summarize_metrics(m_list):
            if isinstance(m_list, list) and len(m_list) > 0:
                d = [int(m["depth"]) for m in m_list if "depth" in m]
                q = [int(m["two_qubit_operations"]) for m in m_list if "two_qubit_operations" in m]
                return {
                    "depth_median": int(np.median(d)) if d else None,
                    "depth_min": int(np.min(d)) if d else None,
                    "depth_max": int(np.max(d)) if d else None,
                    "two_qubit_median": int(np.median(q)) if q else None,
                    "two_qubit_min": int(np.min(q)) if q else None,
                    "two_qubit_max": int(np.max(q)) if q else None,
                }
            elif isinstance(m_list, dict):
                return {
                    "depth_median": m_list.get("transpiled_depth"),
                    "depth_min": m_list.get("transpiled_depth"),
                    "depth_max": m_list.get("transpiled_depth"),
                    "two_qubit_median": m_list.get("two_qubit_count"),
                    "two_qubit_min": m_list.get("two_qubit_count"),
                    "two_qubit_max": m_list.get("two_qubit_count"),
                }
            return {"depth_median": None, "depth_min": None, "depth_max": None, "two_qubit_median": None, "two_qubit_min": None, "two_qubit_max": None}

        raw_summary = _summarize_metrics(raw_metrics)
        mit_summary = _summarize_metrics(mit_metrics)

        # Dynamic backend processor query
        backend_processor = getattr(backend, "processor_type", {}).get("family", None) if hasattr(backend, "processor_type") else None

        execution_meta = {
            "execution_mode": "physical_hardware",
            "is_physical_hardware": True,
            "execution_git_commit": git_commit,
            "working_tree_dirty": working_dirty_at_start,
            "source_tree_dirty_at_start": working_dirty_at_start,
            "base_commit": base_commit,
            "execution_code_snapshot_hash": code_snapshot_hash,
            "provenance_note": (
                "Hardware execution was performed from an uncommitted working tree; exact committed SHA is unavailable."
                if git_commit is None else "Executed from clean commit."
            ),
            "backend": backend_name,
            "backend_processor": backend_processor,
            "raw_job_id": raw_job_id,
            "mitigated_job_id": mit_job_id,
            "target_precision": float(1.0 / np.sqrt(args.shots)),
            "nominal_shot_equivalent": int(args.shots),
            "test_sample_count": test_sample_count,
            "test_correct": test_correct,
            "balanced_accuracy": mit_ba,
            "accuracy_ci95_low": ci_low,
            "accuracy_ci95_high": ci_high,
            "transpiler_seed": 12345,
            "transpiled_depth_raw": raw_summary["depth_median"],
            "transpiled_depth_mitigated": mit_summary["depth_median"],
            "two_qubit_count_raw": raw_summary["two_qubit_median"],
            "two_qubit_count_mitigated": mit_summary["two_qubit_median"],
            "transpiled_metrics_raw": raw_summary,
            "transpiled_metrics_mitigated": mit_summary,
            "logical_to_physical_layout": None,
            "layout_provenance": "not captured by current execution pipeline",
            "dataset_hash": dataset_hash,
            "parameter_hash": hash_parameter_vector(params, full_sha256=True),
            "critical_file_hashes": file_hashes,
            "multi_session_hardware_complete": False,
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "notes": f"Observed {test_correct}/{test_sample_count} correct classifications on held-out N=4 TFIM test states during one {backend_name} hardware session. Multi-session calibration across multiple distinct cooling/calibration windows is pending.",
        }

    else:
        # Explicit analytical / surrogate simulation mode
        print("Stage 2: Analytical Device-Derived Noise Surrogate (Eagle/Heron profile)...")
        backend_name = "analytical_surrogate_ibm_brisbane"
        median_2q_err = 0.012
        median_ro_err = 0.025
        median_t1 = 280.0
        median_t2 = 140.0

        noise_p = np.clip(ideal_p * (1.0 - 2.5 * median_2q_err) + 0.5 * (2.5 * median_2q_err), 0.0, 1.0)
        noise_ba = float(balanced_accuracy_score(test_y, (noise_p >= 0.5).astype(int)))

        print("Stage 3: Raw Surrogate Simulation (gate infidelity + readout noise + finite shots)...")
        raw_p = np.clip(noise_p * (1.0 - median_ro_err) + 0.5 * median_ro_err, 0.0, 1.0)
        rng = np.random.default_rng(2026)
        raw_shots = rng.binomial(args.shots, raw_p) / float(args.shots)
        raw_ba = float(balanced_accuracy_score(test_y, (raw_shots >= 0.5).astype(int)))

        print("Stage 4: Mitigated Surrogate Simulation (readout response inversion)...")
        mit_p = np.clip((raw_shots - 0.5 * median_ro_err) / (1.0 - median_ro_err), 0.0, 1.0)
        mit_ba = float(balanced_accuracy_score(test_y, (mit_p >= 0.5).astype(int)))

        execution_meta = {
            "execution_mode": "surrogate_simulation",
            "is_physical_hardware": False,
            "backend": backend_name,
            "surrogate_target_profile": "ibm_brisbane",
            "median_2q_error": median_2q_err,
            "median_readout_error": median_ro_err,
            "median_t1_us": median_t1,
            "median_t2_us": median_t2,
            "multi_session_hardware_complete": False,
            "notes": "Analytical surrogate study modeling hardware degradation. No live QPU jobs were dispatched.",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # Save per-sample predictions
    pred_rows = []
    p_raw_save = raw_p if args.mode == "hardware" else raw_shots
    for i in range(len(test_y)):
        pred_rows.append({
            "sample_id": int(splits.test[i]),
            "parameter": float(meta.iloc[splits.test[i]]["parameter"]),
            "true_label": int(test_y[i]),
            "ideal_probability": float(ideal_p[i]),
            "noise_model_probability": float(noise_p[i]),
            "raw_probability": float(p_raw_save[i]),
            "mitigated_probability": float(mit_p[i]),
        })
    csv_file = "expressive_hardware_benchmark.csv" if args.mode == "hardware" else "surrogate_hardware_benchmark.csv"
    pd.DataFrame(pred_rows).to_csv(out_dir / csv_file, index=False)

    summary_dict = {
        **execution_meta,
        "n_qubits": n_qubits,
        "architecture": arch.name,
        "parameters": len(params),
        "ideal_balanced_accuracy": ideal_ba,
        "device_noise_balanced_accuracy": noise_ba,
        "raw_hardware_balanced_accuracy": raw_ba,
        "mitigated_hardware_balanced_accuracy": mit_ba,
    }
    summary_file = "expressive_hardware_summary.json" if args.mode == "hardware" else "surrogate_hardware_summary.json"
    (out_dir / summary_file).write_text(json.dumps(summary_dict, indent=2), encoding="utf-8")

    if args.mode == "hardware":
        prov_file = out_dir / "provenance.json"
        prov_dict = {
            "execution_git_commit": execution_meta.get("execution_git_commit"),
            "working_tree_dirty": execution_meta.get("working_tree_dirty"),
            "source_tree_dirty_at_start": execution_meta.get("source_tree_dirty_at_start"),
            "base_commit": execution_meta.get("base_commit"),
            "execution_code_snapshot_hash": execution_meta.get("execution_code_snapshot_hash"),
            "provenance_note": execution_meta.get("provenance_note"),
            "generated_at": execution_meta.get("execution_timestamp"),
            "backend": execution_meta.get("backend"),
            "backend_processor": execution_meta.get("backend_processor"),
            "raw_job_id": execution_meta.get("raw_job_id"),
            "mitigated_job_id": execution_meta.get("mitigated_job_id"),
            "target_precision": execution_meta.get("target_precision"),
            "nominal_shot_equivalent": execution_meta.get("nominal_shot_equivalent"),
            "test_sample_count": execution_meta.get("test_sample_count"),
            "test_correct": execution_meta.get("test_correct"),
            "balanced_accuracy": execution_meta.get("balanced_accuracy"),
            "accuracy_ci95_low": execution_meta.get("accuracy_ci95_low"),
            "accuracy_ci95_high": execution_meta.get("accuracy_ci95_high"),
            "transpiler_seed": execution_meta.get("transpiler_seed"),
            "transpiled_depth_raw": execution_meta.get("transpiled_depth_raw"),
            "transpiled_depth_mitigated": execution_meta.get("transpiled_depth_mitigated"),
            "two_qubit_count_raw": execution_meta.get("two_qubit_count_raw"),
            "two_qubit_count_mitigated": execution_meta.get("two_qubit_count_mitigated"),
            "transpilation_telemetry_note": execution_meta.get("transpilation_telemetry_note"),
            "logical_to_physical_layout": execution_meta.get("logical_to_physical_layout"),
            "layout_provenance": execution_meta.get("layout_provenance"),
            "dataset_hash": execution_meta.get("dataset_hash"),
            "parameter_hash": execution_meta.get("parameter_hash"),
            "multi_session_hardware_complete": execution_meta.get("multi_session_hardware_complete"),
            "critical_file_hashes": execution_meta.get("critical_file_hashes"),
            "script": "scripts/29_run_expressive_hardware_benchmark.py",
        }
        prov_file.write_text(json.dumps(prov_dict, indent=2), encoding="utf-8")

    # Plot 4 stages comparison
    plt.figure(figsize=(7, 5))
    if args.mode == "hardware":
        stages = ["Ideal\nSimulator", "Device Noise\nModel", f"Raw QPU\n({backend_name})", f"Mitigated QPU\n({backend_name})"]
        plot_title = "N=4 Expressive QCNN: Physical QPU Hardware Transfer Progression"
        fig_name = "expressive_hardware_stages.png"
    else:
        stages = ["Ideal\nSimulator", "Device Noise\nSurrogate", "Raw Surrogate\nProgression", "Mitigated Surrogate\nProgression"]
        plot_title = "N=4 Expressive QCNN: Analytical Surrogate Progression"
        fig_name = "surrogate_hardware_stages.png"

    ba_vals = [ideal_ba, noise_ba, raw_ba, mit_ba]
    colors = ["royalblue", "darkorange", "crimson", "forestgreen"]

    bars = plt.bar(stages, ba_vals, color=colors, width=0.55)
    plt.ylabel("Balanced Accuracy")
    plt.title(plot_title)
    plt.ylim(0.4, 1.05)
    plt.grid(True, linestyle="--", alpha=0.5)
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2.0, yval + 0.02, f"{yval:.3f}", ha="center", va="bottom", fontweight="bold")
    plt.tight_layout()
    plt.savefig(fig_dir / fig_name, dpi=200)
    plt.close()

    print(f"Benchmark finished ({args.mode} mode). Results written to {out_dir}")
    print(json.dumps(summary_dict, indent=2))


if __name__ == "__main__":
    main()
