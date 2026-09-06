import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from qcnn_lab.metrics import binary_metrics
from qcnn_lab.physics.datasets import default_specs, generate_task_dataset
from qcnn_lab.qcnn.architecture import get_architecture
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.train import stratified_splits, train_ideal_qcnn


def main():
    spec = default_specs(4)["tfim"]
    states, meta, sweep_states, sweep_meta = generate_task_dataset(spec, samples_per_class=30, transition_points=41, seed=2026)
    out_data = Path("data/processed/hardware4"); out_data.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_data / "tfim_states.npz", states=states); meta.to_csv(out_data / "tfim_metadata.csv", index=False)
    np.savez_compressed(out_data / "tfim_transition_states.npz", states=sweep_states); sweep_meta.to_csv(out_data / "tfim_transition_metadata.csv", index=False)
    y = meta["label"].to_numpy(dtype=int)
    splits = stratified_splits(y, seed=2026)
    arch = get_architecture("light_shared_line")
    params, history, seconds = train_ideal_qcnn(states, y, 4, arch, splits.train, splits.validation, maxiter=100, seed=2026)
    p = batch_predict(states[splits.test], params, arch, 4)
    summary = {"n_qubits": 4, "training_seconds": seconds, **asdict(binary_metrics(y[splits.test], p))}
    out = Path("results/hardware"); out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "hardware4_tfim_model.npz", params=params, train=splits.train, validation=splits.validation, test=splits.test)
    pd.DataFrame(history).to_csv(out / "hardware4_training_history.csv", index=False)
    (out / "hardware4_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("Hardware-scale model preparation PASSED")


if __name__ == "__main__":
    main()