import json
from dataclasses import asdict
from math import sqrt
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t

from qcnn_lab.config import load_yaml
from qcnn_lab.metrics import binary_metrics
from qcnn_lab.noise.evaluate import noisy_predict
from qcnn_lab.noise.models import build_noise_model, noise_specs_from_config
from qcnn_lab.physics.datasets import load_labelled_dataset
from qcnn_lab.qcnn.architecture import get_architecture
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.train import stratified_splits, train_ideal_qcnn


def mean_ci(
    values: np.ndarray,
    clip_bounds: tuple[float, float] | None = None,
) -> tuple[float, float, float, float]:
    values = np.asarray(values, dtype=float)
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    if len(values) < 2:
        low, high = mean, mean
    else:
        half = float(t.ppf(0.975, df=len(values) - 1) * std / sqrt(len(values)))
        low, high = mean - half, mean + half
    if clip_bounds is not None:
        low = float(np.clip(low, clip_bounds[0], clip_bounds[1]))
        high = float(np.clip(high, clip_bounds[0], clip_bounds[1]))
    return mean, std, low, high


def main():
    cfg = load_yaml("configs/project.yaml")
    n = int(cfg["n_qubits"])
    base_seed = int(cfg["seed"])
    arch = get_architecture(cfg["qcnn"]["architecture"])
    noise_specs = noise_specs_from_config(load_yaml("configs/noise.yaml"))
    mixed_noise = build_noise_model(noise_specs["mixed_training_b"])
    repeats = 5
    rows = []

    for family in ("tfim", "xxz", "cluster"):
        states, meta = load_labelled_dataset("data/processed", family)
        y = meta["label"].to_numpy(dtype=int)
        # Keep the data partition fixed; vary optimizer initialization only.
        splits = stratified_splits(
            y,
            train_fraction=float(cfg["train_fraction"]),
            validation_fraction=float(cfg["validation_fraction"]),
            seed=base_seed,
        )
        for repeat in range(repeats):
            train_seed = base_seed + 100 * repeat
            params, _, seconds = train_ideal_qcnn(
                states,
                y,
                n,
                arch,
                splits.train,
                splits.validation,
                maxiter=int(cfg["qcnn"]["maxiter_ideal"]),
                seed=train_seed,
            )
            ideal_p = batch_predict(states[splits.test], params, arch, n)
            noisy_p = noisy_predict(
                states[splits.test],
                params,
                arch,
                n,
                mixed_noise,
                shots=512,
                seed=train_seed + 7,
            )
            rows.append({
                "family": family,
                "repeat": repeat,
                "training_seed": train_seed,
                "condition": "ideal",
                "training_seconds": seconds,
                **asdict(binary_metrics(y[splits.test], ideal_p)),
            })
            rows.append({
                "family": family,
                "repeat": repeat,
                "training_seed": train_seed,
                "condition": "mixed_training_b_noise",
                "training_seconds": seconds,
                **asdict(binary_metrics(y[splits.test], noisy_p)),
            })

    frame = pd.DataFrame(rows)
    out = Path("results/statistics")
    out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out / "repeated_seed_metrics.csv", index=False)

    summary_rows = []
    for (family, condition), group in frame.groupby(["family", "condition"]):
        row = {"family": family, "condition": condition, "n_repeats": int(group["repeat"].nunique())}
        for metric in ("accuracy", "balanced_accuracy", "f1", "roc_auc", "log_loss"):
            bounds = (0.0, 1.0) if metric != "log_loss" else (0.0, float("inf"))
            mean, std, low, high = mean_ci(group[metric].to_numpy(dtype=float), clip_bounds=bounds)
            row[f"{metric}_mean"] = mean
            row[f"{metric}_std"] = std
            row[f"{metric}_ci95_low"] = low
            row[f"{metric}_ci95_high"] = high
        summary_rows.append(row)
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(out / "repeated_seed_summary.csv", index=False)
    (out / "repeated_seed_summary.json").write_text(
        json.dumps(summary_rows, indent=2), encoding="utf-8"
    )
    print(summary.to_string(index=False))
    print("Repeated-seed statistical benchmarking completed")


if __name__ == "__main__":
    main()