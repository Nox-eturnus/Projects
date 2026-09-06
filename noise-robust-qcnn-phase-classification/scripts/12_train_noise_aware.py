import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from qcnn_lab.config import load_yaml
from qcnn_lab.metrics import binary_metrics
from qcnn_lab.noise.evaluate import noisy_predict
from qcnn_lab.noise.models import build_noise_model, noise_specs_from_config
from qcnn_lab.noise.train import train_noise_aware_spsa
from qcnn_lab.physics.datasets import load_labelled_dataset
from qcnn_lab.qcnn.architecture import get_architecture


def main():
    cfg = load_yaml("configs/project.yaml")
    noise_cfg = load_yaml("configs/noise.yaml")
    specs = noise_specs_from_config(noise_cfg)
    base = np.load("results/ideal/tfim_ideal_model.npz")
    train_idx, val_idx, test_idx = base["train"], base["validation"], base["test"]
    states, meta = load_labelled_dataset("data/processed", "tfim")
    y = meta["label"].to_numpy(dtype=int)
    arch = get_architecture(cfg["qcnn"]["architecture"])
    nt = cfg["noise_training"]
    result = train_noise_aware_spsa(
        states, y, int(cfg["n_qubits"]), arch, train_idx, val_idx,
        [specs["mild_depolarizing"], specs["mixed_training_a"], specs["mixed_training_b"]],
        iterations=int(nt["iterations"]), batch_size=int(nt["batch_size"]), shots=int(nt["shots"]),
        a=float(nt["spsa_a"]), c=float(nt["spsa_c"]), seed=int(cfg["seed"]),
    )
    p = noisy_predict(states[test_idx], result.params, arch, int(cfg["n_qubits"]), build_noise_model(specs["mixed_training_b"]), shots=512, seed=int(cfg["seed"]) + 99)
    metrics = binary_metrics(y[test_idx], p)
    out = Path("results/noise"); out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "tfim_noise_aware_model.npz", params=result.params, train=train_idx, validation=val_idx, test=test_idx)
    pd.DataFrame(result.history).to_csv(out / "tfim_noise_aware_history.csv", index=False)
    summary = {"training_seconds": result.seconds, **asdict(metrics)}
    (out / "tfim_noise_aware_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("Noise-aware training PASSED")


if __name__ == "__main__":
    main()