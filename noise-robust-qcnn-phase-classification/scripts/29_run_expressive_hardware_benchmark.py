from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score

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

        execution_meta = {
            "execution_mode": "physical_hardware",
            "is_physical_hardware": True,
            "backend": backend_name,
            "raw_job_id": raw_job_id,
            "mitigated_job_id": mit_job_id,
            "multi_session_hardware_complete": False,
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
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
