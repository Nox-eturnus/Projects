from dataclasses import asdict
from pathlib import Path

import pandas as pd

from qcnn_lab.config import load_yaml
from qcnn_lab.metrics import binary_metrics
from qcnn_lab.physics.datasets import load_labelled_dataset
from qcnn_lab.qcnn.architecture import get_architecture, raw_circuit_metrics
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.train import stratified_splits, train_ideal_qcnn


def main():
    cfg = load_yaml("configs/project.yaml")
    rows = []
    names = ("light_shared_line", "light_shared_ring", "expressive_shared_line", "light_unshared_line")
    for family in ("tfim", "xxz", "cluster"):
        states, meta = load_labelled_dataset("data/processed", family)
        labels = meta["label"].to_numpy(dtype=int)
        splits = stratified_splits(labels, train_fraction=float(cfg["train_fraction"]), validation_fraction=float(cfg["validation_fraction"]), seed=int(cfg["seed"]))
        for offset, name in enumerate(names):
            arch = get_architecture(name)
            params, _, seconds = train_ideal_qcnn(states, labels, int(cfg["n_qubits"]), arch, splits.train, splits.validation, maxiter=80, seed=int(cfg["seed"]) + offset)
            p = batch_predict(states[splits.test], params, arch, int(cfg["n_qubits"]))
            row = {"family": family, "architecture": name, "training_seconds": seconds, **raw_circuit_metrics(int(cfg["n_qubits"]), arch), **asdict(binary_metrics(labels[splits.test], p))}
            rows.append(row)
            print(row)
    out = Path("results/architectures"); out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / "architecture_sweep.csv", index=False)
    print("Architecture sweep PASSED")


if __name__ == "__main__":
    main()