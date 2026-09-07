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
    arch_light = get_architecture("light_shared_line")
    params_light, history_light, seconds_light = train_ideal_qcnn(states, y, 4, arch_light, splits.train, splits.validation, maxiter=100, seed=2026)
    p_light = batch_predict(states[splits.test], params_light, arch_light, 4)
    metrics_light = binary_metrics(y[splits.test], p_light)

    # Comparison benchmark with expressive_shared_line at N=4
    arch_expr = get_architecture("expressive_shared_line")
    params_expr, history_expr, seconds_expr = train_ideal_qcnn(states, y, 4, arch_expr, splits.train, splits.validation, maxiter=100, seed=2026)
    p_expr = batch_predict(states[splits.test], params_expr, arch_expr, 4)
    metrics_expr = binary_metrics(y[splits.test], p_expr)

    summary = {"n_qubits": 4, "architecture": "light_shared_line", "training_seconds": seconds_light, **asdict(metrics_light)}
    out = Path("results/hardware"); out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "hardware4_tfim_model.npz", params=params_light, train=splits.train, validation=splits.validation, test=splits.test)
    pd.DataFrame(history_light).to_csv(out / "hardware4_training_history.csv", index=False)
    (out / "hardware4_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    comparison = {
        "n_qubits": 4,
        "architectures": {
            "light_shared_line": {"architecture": "light_shared_line", "training_seconds": seconds_light, **asdict(metrics_light)},
            "expressive_shared_line": {"architecture": "expressive_shared_line", "training_seconds": seconds_expr, **asdict(metrics_expr)},
        },
    }
    (out / "hardware4_comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    print("Light model summary:", json.dumps(summary, indent=2))
    print("N=4 architecture comparison:", json.dumps(comparison, indent=2))
    print("Hardware-scale model preparation PASSED")


if __name__ == "__main__":
    main()