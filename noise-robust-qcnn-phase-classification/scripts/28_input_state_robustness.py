from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score

from qcnn_lab.analysis.splits import load_split_manifest, split_indices_from_manifest
from qcnn_lab.config import load_yaml
from qcnn_lab.noise.evaluate import noisy_predict
from qcnn_lab.noise.models import build_noise_model, noise_specs_from_config
from qcnn_lab.noise.state_preparation import noisy_state_preparation_predict
from qcnn_lab.physics.hamiltonians import cluster_ising_hamiltonian, tfim_hamiltonian, xxz_hamiltonian
from qcnn_lab.physics.thermal_states import compute_thermal_density_matrix, evaluate_qcnn_thermal_state
from qcnn_lab.qcnn.architecture import get_architecture
from qcnn_lab.qcnn.evaluate import batch_predict, predict_p1
from qcnn_lab.qcnn.train import train_ideal_qcnn


def get_hamiltonian(family: str, n_qubits: int, param: float):
    if family == "tfim":
        return tfim_hamiltonian(n_qubits, h=param)
    elif family == "cluster":
        return cluster_ising_hamiltonian(n_qubits, h=param)
    elif family == "xxz":
        return xxz_hamiltonian(n_qubits, delta=param)
    raise ValueError(f"unknown family {family}")


def main():
    parser = argparse.ArgumentParser(description="Thermal state and state-preparation robustness benchmark.")
    parser.add_argument("--project-config", default="configs/project.yaml", help="Path to project config")
    parser.add_argument("--out-dir", default="results/thermal_and_prep", help="Output directory")
    parser.add_argument("--fig-dir", default="results/figures", help="Figures output directory")
    args = parser.parse_args()

    proj_cfg = load_yaml(args.project_config)
    n_qubits = int(proj_cfg.get("n_qubits", 8))
    arch = get_architecture(proj_cfg.get("qcnn", {}).get("architecture", "expressive_shared_line"))

    out_dir = Path(args.out_dir)
    fig_dir = Path(args.fig_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    temperatures = [0.0, 0.01, 0.025, 0.05, 0.10, 0.20, 0.40]
    families = ["tfim", "xxz", "cluster"]
    splits_dir = Path("results/evaluation_splits")
    data_dir = Path("data/processed")

    # Load circuit noise models
    noise_specs = noise_specs_from_config(load_yaml("configs/noise.yaml"))

    thermal_rows = []

    print("Running Thermal State Generalization Benchmark...")
    plt.figure(figsize=(8, 5))

    for family in families:
        manifest = load_split_manifest(splits_dir / f"{family}_iid_seed11.csv")
        indices = split_indices_from_manifest(manifest)

        states = np.load(data_dir / f"{family}_eval_states.npz")["states"]
        meta = pd.read_csv(data_dir / f"{family}_eval_metadata.csv")
        y = meta["label"].to_numpy(dtype=int)

        params, _, _ = train_ideal_qcnn(
            states, y, n_qubits, arch, indices.train, indices.validation,
            maxiter=int(proj_cfg.get("qcnn", {}).get("maxiter_ideal", 120)), seed=12345,
        )

        test_meta = meta.iloc[indices.test][:16]  # 16 test points for thermal sweep
        test_params = test_meta["hamiltonian_parameter"].to_numpy(dtype=float)
        test_y = (test_params >= 1.0).astype(int)

        predict_single = lambda st: predict_p1(st, params, arch, n_qubits)

        for T in temperatures:
            thermal_p = []
            for p in test_params:
                H = get_hamiltonian(family, n_qubits, p)
                vecs, weights = compute_thermal_density_matrix(H, T)
                p1_val = evaluate_qcnn_thermal_state(vecs, weights, predict_single)
                thermal_p.append(p1_val)

            thermal_p = np.asarray(thermal_p)
            ba = float(balanced_accuracy_score(test_y, (thermal_p >= 0.5).astype(int)))
            thermal_rows.append({
                "family": family,
                "temperature": T,
                "balanced_accuracy": ba,
            })

    thermal_df = pd.DataFrame(thermal_rows)
    thermal_df.to_csv(out_dir / "thermal_scaling.csv", index=False)

    for fam, grp in thermal_df.groupby("family"):
        plt.plot(grp["temperature"], grp["balanced_accuracy"], marker="o", linewidth=2, label=f"{fam.upper()} QCNN")

    plt.xlabel("Temperature ($T$) in units of $J / k_B$")
    plt.ylabel("Test Balanced Accuracy")
    plt.title("QCNN Robustness to Thermal State Imperfections (Trained at T=0)")
    plt.ylim(0.4, 1.05)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_dir / "thermal_degradation_curve.png", dpi=200)
    plt.close()

    # 2. 2x2 Factorial State vs Circuit Noise Design
    print("Evaluating 2x2 Factorial Noise Design...")
    tfim_manifest = load_split_manifest(splits_dir / "tfim_iid_seed11.csv")
    tfim_idx = split_indices_from_manifest(tfim_manifest)
    tfim_states = np.load(data_dir / "tfim_eval_states.npz")["states"]
    tfim_meta = pd.read_csv(data_dir / "tfim_eval_metadata.csv")
    tfim_y = tfim_meta["label"].to_numpy(dtype=int)

    tfim_params, _, _ = train_ideal_qcnn(
        tfim_states, tfim_y, n_qubits, arch, tfim_idx.train, tfim_idx.validation,
        maxiter=int(proj_cfg.get("qcnn", {}).get("maxiter_ideal", 120)), seed=12345,
    )
    test_sub_states = tfim_states[tfim_idx.test]
    test_sub_y = tfim_y[tfim_idx.test]

    ideal_p = batch_predict(test_sub_states, tfim_params, arch, n_qubits)
    noisy_circuit_model = build_noise_model(noise_specs["mixed_training_b"])
    noisy_circuit_p = noisy_predict(test_sub_states, tfim_params, arch, n_qubits, noisy_circuit_model, shots=512, seed=42)

    p_state_rate = 0.08
    noisy_state_ideal_circ_p = noisy_state_preparation_predict(ideal_p, p_state_rate)
    noisy_state_noisy_circ_p = noisy_state_preparation_predict(noisy_circuit_p, p_state_rate)

    factorial_records = [
        {"input_state": "ideal", "qcnn_circuit": "ideal", "balanced_accuracy": float(balanced_accuracy_score(test_sub_y, (ideal_p >= 0.5).astype(int)))},
        {"input_state": "noisy", "qcnn_circuit": "ideal", "balanced_accuracy": float(balanced_accuracy_score(test_sub_y, (noisy_state_ideal_circ_p >= 0.5).astype(int)))},
        {"input_state": "ideal", "qcnn_circuit": "noisy", "balanced_accuracy": float(balanced_accuracy_score(test_sub_y, (noisy_circuit_p >= 0.5).astype(int)))},
        {"input_state": "noisy", "qcnn_circuit": "noisy", "balanced_accuracy": float(balanced_accuracy_score(test_sub_y, (noisy_state_noisy_circ_p >= 0.5).astype(int)))},
    ]
    factorial_df = pd.DataFrame(factorial_records)
    factorial_df.to_csv(out_dir / "two_by_two_noise_ablation.csv", index=False)

    # 3. 2D Heatmap Grid: BA(p_state, p_circuit) - Analytical Sensitivity Surface
    print("Generating 2D Noise Analytical Surrogate Heatmap Grid...")
    p_state_grid = [0.0, 0.02, 0.05, 0.10, 0.15]
    p_circ_grid = [0.0, 0.01, 0.02, 0.04, 0.08]

    grid_matrix = np.zeros((len(p_state_grid), len(p_circ_grid)))
    grid_rows = []

    for i, p_st in enumerate(p_state_grid):
        for j, p_circ in enumerate(p_circ_grid):
            # Analytical sensitivity surface: models 2Q error degradation and state prep depolarizing noise
            circ_deg = np.clip(ideal_p * (1.0 - 1.5 * p_circ) + 0.5 * (1.5 * p_circ), 0.0, 1.0)
            combined_p = noisy_state_preparation_predict(circ_deg, p_st)
            ba = float(balanced_accuracy_score(test_sub_y, (combined_p >= 0.5).astype(int)))
            grid_matrix[i, j] = ba
            grid_rows.append({
                "p_state": p_st,
                "p_circuit": p_circ,
                "balanced_accuracy": ba,
                "model_type": "analytical_sensitivity_surrogate",
            })

    grid_df = pd.DataFrame(grid_rows)
    grid_df.to_csv(out_dir / "surrogate_noise_heatmap.csv", index=False)

    plt.figure(figsize=(7, 6))
    im = plt.imshow(grid_matrix, origin="lower", cmap="viridis", vmin=0.5, vmax=1.0)
    plt.xticks(range(len(p_circ_grid)), [f"{p:.2f}" for p in p_circ_grid])
    plt.yticks(range(len(p_state_grid)), [f"{p:.2f}" for p in p_state_grid])
    plt.xlabel("Circuit Two-Qubit Noise Rate ($p_{circuit}$)")
    plt.ylabel("State-Preparation Noise Rate ($p_{state}$)")
    plt.title("Analytical Noise Sensitivity Surface: BA($p_{state}, p_{circuit}$)")
    cbar = plt.colorbar(im)
    cbar.set_label("Balanced Accuracy")
    for i in range(len(p_state_grid)):
        for j in range(len(p_circ_grid)):
            plt.text(j, i, f"{grid_matrix[i, j]:.2f}", ha="center", va="center", color="white" if grid_matrix[i, j] < 0.75 else "black")
    plt.tight_layout()
    plt.savefig(fig_dir / "surrogate_noise_sensitivity_surface.png", dpi=200)
    plt.close()

    # Save Provenance JSON (Priority 14)
    import json
    import subprocess
    import sys
    from datetime import datetime, timezone
    def get_commit():
        try:
            return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        except Exception:
            return "unknown"
    prov = {
        "git_commit": get_commit(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
        "n_qubits": n_qubits,
        "temperatures": temperatures,
        "p_state_grid": p_state_grid,
        "p_circuit_grid": p_circ_grid,
        "script": "scripts/28_input_state_robustness.py",
    }
    with open(out_dir / "provenance.json", "w") as f:
        json.dump(prov, f, indent=2)

    print(f"Robustness evaluations saved in {out_dir} and {fig_dir}")
    print("\n2x2 Factorial Design Table (Simulated Aer Noise vs State Prep Noise):")
    print(factorial_df.to_string(index=False))
    print("\nNote: 2D grid saved as surrogate_noise_heatmap.csv (analytical sensitivity model).")



if __name__ == "__main__":
    main()
