from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from qcnn_lab.baselines.classical import make_svm
from qcnn_lab.baselines.features import flatten_observables, observable_tensor
from qcnn_lab.config import load_yaml
from qcnn_lab.metrics import binary_metrics
from qcnn_lab.physics.datasets import load_labelled_dataset
from qcnn_lab.qcnn.architecture import get_architecture, parameter_count
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.train import stratified_splits, train_ideal_qcnn


def balanced_subset(indices: np.ndarray, labels: np.ndarray, per_class: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    chosen = []
    for label in (0, 1):
        pool = indices[labels[indices] == label]
        if per_class > len(pool):
            raise ValueError(f"requested {per_class} samples for class {label}, only {len(pool)} available")
        chosen.extend(rng.choice(pool, size=per_class, replace=False).tolist())
    return np.asarray(sorted(chosen), dtype=int)


def main():
    cfg = load_yaml("configs/project.yaml")
    family = "tfim"
    states, meta = load_labelled_dataset("data/processed", family)
    y = meta["label"].to_numpy(dtype=int)
    n = int(cfg["n_qubits"])
    seed = int(cfg["seed"])
    splits = stratified_splits(y, train_fraction=float(cfg["train_fraction"]), validation_fraction=float(cfg["validation_fraction"]), seed=seed)
    arch = get_architecture(cfg["qcnn"]["architecture"])
    features = flatten_observables(observable_tensor(states, n))
    rows = []

    for per_class in (4, 8, 16, 24):
        for repeat in range(3):
            subset = balanced_subset(splits.train, y, per_class, seed + 1000 * per_class + repeat)
            params, _, seconds = train_ideal_qcnn(states, y, n, arch, subset, splits.validation, maxiter=90, seed=seed + repeat)
            p_q = batch_predict(states[splits.test], params, arch, n)
            rows.append({"family": family, "model": "qcnn", "samples_per_class": per_class, "repeat": repeat, "access_regime": "direct_quantum_state", "model_complexity": parameter_count(n, arch), "training_seconds": seconds, **asdict(binary_metrics(y[splits.test], p_q))})

            svm = make_svm(seed + repeat)
            import time
            started = time.perf_counter(); svm.fit(features[subset], y[subset]); seconds_svm = time.perf_counter() - started
            p_svm = svm.predict_proba(features[splits.test])[:, 1]
            rows.append({"family": family, "model": "svm_rbf", "samples_per_class": per_class, "repeat": repeat, "access_regime": "local_observable_map", "model_complexity": int(svm.named_steps["svc"].support_.size), "training_seconds": seconds_svm, **asdict(binary_metrics(y[splits.test], p_svm))})

    frame = pd.DataFrame(rows)
    out = Path("results/statistics"); out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out / "sample_efficiency.csv", index=False)
    summary = frame.groupby(["model", "samples_per_class"], as_index=False).agg(
        accuracy_mean=("accuracy", "mean"),
        accuracy_std=("accuracy", "std"),
        balanced_accuracy_mean=("balanced_accuracy", "mean"),
        training_seconds_mean=("training_seconds", "mean"),
    )
    summary.to_csv(out / "sample_efficiency_summary.csv", index=False)
    print(summary.to_string(index=False))
    print("Sample-efficiency sweep PASSED")


if __name__ == "__main__":
    main()