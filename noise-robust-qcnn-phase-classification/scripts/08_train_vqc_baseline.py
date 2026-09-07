from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from qcnn_lab.config import load_yaml
from qcnn_lab.metrics import binary_metrics
from qcnn_lab.physics.datasets import load_labelled_dataset
from qcnn_lab.qcnn.train import stratified_splits
from qcnn_lab.qcnn.vqc import train_vqc, vqc_circuit_metrics, vqc_predict


def main():
    cfg = load_yaml("configs/project.yaml")
    rows = []
    out = Path("results/baselines"); out.mkdir(parents=True, exist_ok=True)
    for family in ("tfim", "xxz", "cluster"):
        states, meta = load_labelled_dataset("data/processed", family)
        labels = meta["label"].to_numpy(dtype=int)
        splits = stratified_splits(labels, train_fraction=float(cfg["train_fraction"]), validation_fraction=float(cfg["validation_fraction"]), seed=int(cfg["seed"]))
        params, seconds = train_vqc(states, labels, splits.train, n_qubits=int(cfg["n_qubits"]), layers=2, maxiter=100, seed=int(cfg["seed"]))
        p = vqc_predict(states[splits.test], params, int(cfg["n_qubits"]), layers=2)
        row = {
            "family": family,
            "model": "hardware_efficient_vqc",
            "access_regime": "direct_quantum_state",
            "training_seconds": seconds,
            **vqc_circuit_metrics(int(cfg["n_qubits"]), 2),
            **asdict(binary_metrics(labels[splits.test], p)),
        }
        rows.append(row)
        np.savez_compressed(out / f"{family}_vqc_model.npz", params=params, train=splits.train, validation=splits.validation, test=splits.test)
        print(row)
    pd.DataFrame(rows).to_csv(out / "vqc_baseline.csv", index=False)
    print("VQC baseline completed")


if __name__ == "__main__":
    main()