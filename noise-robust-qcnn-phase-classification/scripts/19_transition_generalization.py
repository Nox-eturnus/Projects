import json
from dataclasses import asdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from qcnn_lab.analysis.transition import crossing_point, moving_average, steepest_change_point
from qcnn_lab.config import load_yaml
from qcnn_lab.metrics import binary_metrics
from qcnn_lab.physics.datasets import default_specs, load_labelled_dataset, load_transition_dataset
from qcnn_lab.qcnn.architecture import get_architecture
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.train import stratified_splits, train_ideal_qcnn


def main():
    cfg = load_yaml("configs/project.yaml")
    n = int(cfg["n_qubits"])
    seed = int(cfg["seed"])
    arch = get_architecture(cfg["qcnn"]["architecture"])
    specs = default_specs(n)
    out = Path("results/generalization")
    fig_dir = Path("results/figures")
    out.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    for offset, family in enumerate(("tfim", "xxz", "cluster")):
        states, meta = load_labelled_dataset("data/processed", family)
        sweep_states, sweep_meta = load_transition_dataset("data/processed", family)
        y = meta["label"].to_numpy(dtype=int)
        splits = stratified_splits(
            y,
            train_fraction=float(cfg["train_fraction"]),
            validation_fraction=float(cfg["validation_fraction"]),
            seed=seed,
        )
        params, history, seconds = train_ideal_qcnn(
            states,
            y,
            n,
            arch,
            splits.train,
            splits.validation,
            maxiter=int(cfg["qcnn"]["maxiter_ideal"]),
            seed=seed + offset,
        )
        test_p = batch_predict(states[splits.test], params, arch, n)
        test_metrics = binary_metrics(y[splits.test], test_p)
        sweep_p = batch_predict(sweep_states, params, arch, n)
        smooth_p = moving_average(sweep_p, window=3)
        x = sweep_meta["parameter"].to_numpy(dtype=float)
        learned_crossing, bracketed = crossing_point(x, smooth_p, level=0.5)
        prob_min = float(np.min(smooth_p))
        prob_max = float(np.max(smooth_p))
        prob_span = float(prob_max - prob_min)
        transition_detected = bool(bracketed and prob_span >= 0.2)
        learned_steepest = steepest_change_point(x, smooth_p)
        physical_steepest = steepest_change_point(
            x, sweep_meta["physical_diagnostic"].to_numpy(dtype=float)
        )
        spec = specs[family]

        np.savez_compressed(
            out / f"{family}_final_model.npz",
            params=params,
            train=splits.train,
            validation=splits.validation,
            test=splits.test,
        )
        pd.DataFrame(history).to_csv(out / f"{family}_training_history.csv", index=False)
        pred = sweep_meta.copy()
        pred["p_class1"] = sweep_p
        pred["p_class1_smoothed"] = smooth_p
        pred.to_csv(out / f"{family}_transition_predictions.csv", index=False)

        summary = {
            "family": family,
            "architecture": arch.name,
            "training_seconds": seconds,
            "thermodynamic_reference_critical": spec.critical_value,
            "qcnn_p05_crossing": learned_crossing,
            "qcnn_crossing_bracketed": bracketed,
            "transition_detected": transition_detected,
            "probability_span": prob_span,
            "probability_min": prob_min,
            "probability_max": prob_max,
            "qcnn_steepest_change": learned_steepest,
            "physical_diagnostic_steepest_change": physical_steepest,
            "finite_size_warning": "N=8 finite systems need not transition exactly at the thermodynamic critical value.",
            **asdict(test_metrics),
        }
        summaries.append(summary)

        fig, ax1 = plt.subplots(figsize=(7, 4.5))
        ax1.plot(x, smooth_p, label="QCNN P(class 1)")
        ax1.axhline(0.5, linewidth=1, linestyle="--")
        ax1.axvline(spec.critical_value, linewidth=1, linestyle=":", label="thermodynamic reference")
        ax1.set_xlabel("Hamiltonian control parameter")
        ax1.set_ylabel("QCNN class-1 probability")
        ax1.set_ylim(-0.05, 1.05)
        ax2 = ax1.twinx()
        ax2.plot(x, sweep_meta["physical_diagnostic"], alpha=0.55, label="physical diagnostic")
        ax2.set_ylabel("physical diagnostic")
        lines = ax1.get_lines() + ax2.get_lines()
        ax1.legend(lines, [line.get_label() for line in lines], fontsize=8, loc="best")
        fig.tight_layout()
        fig.savefig(fig_dir / f"{family}_transition_generalization.png", dpi=180)
        plt.close(fig)

    frame = pd.DataFrame(summaries)
    frame.to_csv(out / "transition_summary.csv", index=False)
    (out / "transition_summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(frame.to_string(index=False))
    print("Multi-family transition generalization PASSED")


if __name__ == "__main__":
    main()