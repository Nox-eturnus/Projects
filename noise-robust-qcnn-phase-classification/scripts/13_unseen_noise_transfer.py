import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from qcnn_lab.config import load_yaml
from qcnn_lab.metrics import binary_metrics, expected_calibration_error
from qcnn_lab.noise.evaluate import noisy_predict
from qcnn_lab.noise.models import NoiseSpec, build_noise_model, noise_specs_from_config
from qcnn_lab.noise.robustness import evaluate_robustness_threshold
from qcnn_lab.physics.datasets import load_labelled_dataset
from qcnn_lab.qcnn.architecture import get_architecture


def main():
    cfg = load_yaml("configs/project.yaml")
    arch = get_architecture(cfg["qcnn"]["architecture"])
    ideal = np.load("results/ideal/tfim_ideal_model.npz")
    robust = np.load("results/noise/tfim_noise_aware_model.npz")
    test_idx = ideal["test"]
    states, meta = load_labelled_dataset("data/processed", "tfim")
    y = meta["label"].to_numpy(dtype=int)
    specs = noise_specs_from_config(load_yaml("configs/noise.yaml"))
    rows = []

    for profile in ("unseen_phase_heavy", "unseen_readout_heavy"):
        noise = build_noise_model(specs[profile])
        for training, params in (("ideal", ideal["params"]), ("noise_aware", robust["params"])):
            p = noisy_predict(states[test_idx], params, arch, int(cfg["n_qubits"]), noise, shots=1024, seed=int(cfg["seed"]) + 7)
            rows.append({
                "experiment": "unseen_profile",
                "profile": profile,
                "depolarizing_2q": specs[profile].depolarizing_2q,
                "training": training,
                "ece": expected_calibration_error(y[test_idx], p),
                **asdict(binary_metrics(y[test_idx], p)),
            })

    for p2 in cfg["robustness"]["depolarizing_2q_grid"]:
        p2 = float(p2)
        spec = NoiseSpec(name=f"depol2_{p2}", depolarizing_1q=p2 / 10, depolarizing_2q=p2, readout=0.0)
        noise = build_noise_model(spec)
        for training, params in (("ideal", ideal["params"]), ("noise_aware", robust["params"])):
            p = noisy_predict(states[test_idx], params, arch, int(cfg["n_qubits"]), noise, shots=1024, seed=int(cfg["seed"]) + 17)
            rows.append({
                "experiment": "depolarizing_sweep",
                "profile": spec.name,
                "depolarizing_2q": p2,
                "training": training,
                "ece": expected_calibration_error(y[test_idx], p),
                **asdict(binary_metrics(y[test_idx], p)),
            })

    frame = pd.DataFrame(rows)
    out = Path("results/noise"); out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out / "unseen_noise_transfer.csv", index=False)
    floor = float(cfg["robustness"]["failure_balanced_accuracy"])
    depol_frame = frame[frame["experiment"] == "depolarizing_sweep"]
    ideal_eval = evaluate_robustness_threshold(
        depol_frame[depol_frame["training"] == "ideal"].to_dict("records"),
        floor=floor,
        noise_key="depolarizing_2q",
        metric_key="balanced_accuracy",
    )
    noise_aware_eval = evaluate_robustness_threshold(
        depol_frame[depol_frame["training"] == "noise_aware"].to_dict("records"),
        floor=floor,
        noise_key="depolarizing_2q",
        metric_key="balanced_accuracy",
    )
    threshold = {
        "balanced_accuracy_floor": floor,
        "ideal": ideal_eval,
        "noise_aware": noise_aware_eval,
        "ideal_first_tested_failure_probability": ideal_eval["first_tested_failure_probability"],
        "noise_aware_first_tested_failure_probability": noise_aware_eval["first_tested_failure_probability"],
        "ideal_failure_noise_threshold": ideal_eval["failure_noise_threshold"],
        "noise_aware_failure_noise_threshold": noise_aware_eval["failure_noise_threshold"],
        "interpretation": "A higher first-tested failure probability indicates a wider operational robustness envelope on this predefined coarse sweep.",
    }
    (out / "noise_aware_threshold_comparison.json").write_text(json.dumps(threshold, indent=2), encoding="utf-8")
    print(frame.to_string(index=False))
    print(json.dumps(threshold, indent=2))
    print("Unseen-noise transfer PASSED")


if __name__ == "__main__":
    main()