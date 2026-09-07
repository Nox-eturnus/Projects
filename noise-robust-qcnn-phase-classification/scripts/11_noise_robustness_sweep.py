import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from qcnn_lab.config import load_yaml
from qcnn_lab.metrics import binary_metrics
from qcnn_lab.noise.evaluate import noisy_predict
from qcnn_lab.noise.models import NoiseSpec, build_noise_model, noise_specs_from_config
from qcnn_lab.noise.robustness import evaluate_robustness_threshold
from qcnn_lab.physics.datasets import load_labelled_dataset
from qcnn_lab.qcnn.architecture import get_architecture


def main():
    cfg = load_yaml("configs/project.yaml")
    arch = get_architecture(cfg["qcnn"]["architecture"])
    model = np.load("results/ideal/tfim_ideal_model.npz")
    params, test_idx = model["params"], model["test"]
    states, meta = load_labelled_dataset("data/processed", "tfim")
    y = meta["label"].to_numpy(dtype=int)
    specs = noise_specs_from_config(load_yaml("configs/noise.yaml"))
    rows = []
    for name in ("mild_depolarizing", "mixed_training_a", "mixed_training_b", "unseen_phase_heavy", "unseen_readout_heavy"):
        p = noisy_predict(states[test_idx], params, arch, int(cfg["n_qubits"]), build_noise_model(specs[name]), shots=512, seed=int(cfg["seed"]))
        rows.append({"profile": name, "sweep_kind": "named_profile", "depolarizing_2q": specs[name].depolarizing_2q, **asdict(binary_metrics(y[test_idx], p))})
    for p2 in cfg["robustness"]["depolarizing_2q_grid"]:
        p2 = float(p2)
        spec = NoiseSpec(name=f"depol2_{p2}", depolarizing_1q=p2 / 10, depolarizing_2q=p2, readout=0.0)
        p = noisy_predict(states[test_idx], params, arch, int(cfg["n_qubits"]), build_noise_model(spec), shots=512, seed=int(cfg["seed"]) + 1)
        rows.append({"profile": spec.name, "sweep_kind": "two_qubit_depolarizing", "depolarizing_2q": p2, **asdict(binary_metrics(y[test_idx], p))})
    out = Path("results/noise"); out.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows); frame.to_csv(out / "ideal_trained_robustness.csv", index=False)
    floor = float(cfg["robustness"]["failure_balanced_accuracy"])
    depol_rows = [r for r in rows if r["sweep_kind"] == "two_qubit_depolarizing"]
    thresh_eval = evaluate_robustness_threshold(depol_rows, floor=floor, noise_key="depolarizing_2q", metric_key="balanced_accuracy")
    summary = {
        "failure_definition": f"first tested 2q depolarizing probability with balanced_accuracy < {floor}",
        "balanced_accuracy_floor": floor,
        "first_tested_failure_probability": thresh_eval["first_tested_failure_probability"],
        "failure_noise_threshold": thresh_eval["failure_noise_threshold"],
        "status": thresh_eval["status"],
        "robustness_threshold_applicable": thresh_eval["robustness_threshold_applicable"],
        "baseline_metric": thresh_eval["baseline_metric"],
        "grid_is_coarse": True,
    }
    (out / "ideal_robustness_threshold.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(frame.to_string(index=False))
    print(json.dumps(summary, indent=2))
    print("Noise robustness sweep completed")


if __name__ == "__main__":
    main()