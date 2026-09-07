import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from qcnn_lab.metrics import binary_metrics
from qcnn_lab.qcnn.architecture import get_architecture
from qcnn_lab.qcnn.evaluate import batch_predict


def main():
    hw = pd.read_csv("results/hardware/hardware_predictions.csv")
    model = np.load("results/hardware/hardware4_tfim_model.npz")
    states = np.load("data/processed/hardware4/tfim_states.npz")["states"]
    arch = get_architecture("light_shared_line")
    idx = hw["sample_id"].to_numpy(dtype=int)
    ideal_p = batch_predict(states[idx], model["params"], arch, 4)
    y = hw["label"].to_numpy(dtype=int)
    summary = {
        "architecture": "light_shared_line",
        "ideal": asdict(binary_metrics(y, ideal_p)),
        "hardware_raw": asdict(binary_metrics(y, hw["p1_raw"].to_numpy())),
        "hardware_mitigated": asdict(binary_metrics(y, hw["p1_mitigated"].to_numpy())),
        "mean_abs_probability_gap_raw": float(np.mean(np.abs(ideal_p - hw["p1_raw"].to_numpy()))),
        "mean_abs_probability_gap_mitigated": float(np.mean(np.abs(ideal_p - hw["p1_mitigated"].to_numpy()))),
    }
    Path("results/hardware/sim_to_hardware_gap.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("Simulation-to-hardware gap analysis completed")


if __name__ == "__main__":
    main()