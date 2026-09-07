from dataclasses import asdict
from pathlib import Path
from time import perf_counter

import joblib
import numpy as np
import pandas as pd

from qcnn_lab.baselines.classical import TorchCNN1D, make_mlp, make_svm, mlp_parameter_count, svm_support_count
from qcnn_lab.baselines.features import flatten_observables, observable_tensor
from qcnn_lab.baselines.mps import fit_mps_prototype, predict_mps_prototype
from qcnn_lab.config import load_yaml
from qcnn_lab.metrics import binary_metrics
from qcnn_lab.physics.datasets import load_labelled_dataset
from qcnn_lab.qcnn.train import stratified_splits


def main():
    cfg = load_yaml("configs/project.yaml")
    out = Path("results/baselines")
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for family in ("tfim", "xxz", "cluster"):
        states, meta = load_labelled_dataset("data/processed", family)
        y = meta["label"].to_numpy(dtype=int)
        splits = stratified_splits(y, train_fraction=float(cfg["train_fraction"]), validation_fraction=float(cfg["validation_fraction"]), seed=int(cfg["seed"]))
        feat = observable_tensor(states, int(cfg["n_qubits"]))
        flat = flatten_observables(feat)

        svm = make_svm(int(cfg["seed"]))
        started = perf_counter(); svm.fit(flat[splits.train], y[splits.train]); seconds = perf_counter() - started
        p = svm.predict_proba(flat[splits.test])[:, 1]
        rows.append({"family": family, "model": "svm_rbf", "access_regime": "local_observable_map", "complexity_name": "support_vectors", "model_complexity": svm_support_count(svm), "training_seconds": seconds, **asdict(binary_metrics(y[splits.test], p))})
        joblib.dump(svm, out / f"{family}_svm.joblib")

        mlp = make_mlp(int(cfg["seed"]))
        started = perf_counter(); mlp.fit(flat[splits.train], y[splits.train]); seconds = perf_counter() - started
        p = mlp.predict_proba(flat[splits.test])[:, 1]
        rows.append({"family": family, "model": "mlp", "access_regime": "local_observable_map", "complexity_name": "trainable_parameters", "model_complexity": mlp_parameter_count(mlp), "training_seconds": seconds, **asdict(binary_metrics(y[splits.test], p))})
        joblib.dump(mlp, out / f"{family}_mlp.joblib")

        cnn = TorchCNN1D(feat.shape[1], seed=int(cfg["seed"]))
        started = perf_counter(); history = cnn.fit(feat, y, splits.train, splits.validation); seconds = perf_counter() - started
        p = cnn.predict_proba(feat[splits.test])
        rows.append({"family": family, "model": "classical_cnn_1d", "access_regime": "local_observable_map", "complexity_name": "trainable_parameters", "model_complexity": cnn.parameter_count, "training_seconds": seconds, **asdict(binary_metrics(y[splits.test], p))})
        cnn.torch.save(cnn.model.state_dict(), out / f"{family}_cnn.pt")
        pd.DataFrame(history).to_csv(out / f"{family}_cnn_history.csv", index=False)

        started = perf_counter(); mps = fit_mps_prototype(states, y, splits.train, n_qubits=int(cfg["n_qubits"]), max_bond=8); seconds = perf_counter() - started
        p = predict_mps_prototype(mps, states[splits.test])
        rows.append({"family": family, "model": "mps_prototype_chi8", "access_regime": "full_simulated_statevector", "complexity_name": "max_bond_dimension", "model_complexity": mps.max_bond, "training_seconds": seconds, **asdict(binary_metrics(y[splits.test], p))})
        np.savez_compressed(out / f"{family}_mps_prototypes.npz", prototype0=mps.prototype0, prototype1=mps.prototype1, max_bond=mps.max_bond)

    frame = pd.DataFrame(rows)
    frame.to_csv(out / "classical_baselines.csv", index=False)
    print(frame.to_string(index=False))
    print("Classical baseline suite completed")


if __name__ == "__main__":
    main()