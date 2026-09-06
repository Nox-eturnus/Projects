import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from qcnn_lab.config import load_yaml
from qcnn_lab.metrics import binary_metrics
from qcnn_lab.physics.datasets import load_labelled_dataset
from qcnn_lab.qcnn.architecture import get_architecture, raw_circuit_metrics
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.train import stratified_splits, train_ideal_qcnn


def main():
    cfg = load_yaml("configs/project.yaml")
    states, meta = load_labelled_dataset("data/processed", "tfim")
    labels = meta["label"].to_numpy(dtype=int)
    splits = stratified_splits(labels, train_fraction=float(cfg["train_fraction"]), validation_fraction=float(cfg["validation_fraction"]), seed=int(cfg["seed"]))
    arch = get_architecture(cfg["qcnn"]["architecture"])
    params, history, seconds = train_ideal_qcnn(
        states, labels, int(cfg["n_qubits"]), arch, splits.train, splits.validation,
        maxiter=int(cfg["qcnn"]["maxiter_ideal"]), seed=int(cfg["seed"]),
    )
    test_p = batch_predict(states[splits.test], params, arch, int(cfg["n_qubits"]))
    metrics = binary_metrics(labels[splits.test], test_p)
    out = Path("results/ideal"); out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "tfim_ideal_model.npz", params=params, train=splits.train, validation=splits.validation, test=splits.test)
    pd.DataFrame(history).to_csv(out / "tfim_ideal_training_history.csv", index=False)
    pred = meta.iloc[splits.test].copy(); pred["p_class1"] = test_p
    pred.to_csv(out / "tfim_ideal_test_predictions.csv", index=False)
    summary = {"family": "tfim", "architecture": arch.name, "training_seconds": seconds, **raw_circuit_metrics(int(cfg["n_qubits"]), arch), **asdict(metrics)}
    (out / "tfim_ideal_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("Ideal TFIM QCNN training PASSED")


if __name__ == "__main__":
    main()