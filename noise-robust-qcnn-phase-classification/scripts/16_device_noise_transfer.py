import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from qcnn_lab.hardware.ibm import device_noise_predict, service
from qcnn_lab.metrics import binary_metrics
from qcnn_lab.qcnn.architecture import get_architecture


def main():
    snapshot = json.loads(Path("results/hardware/backend_snapshot.json").read_text(encoding="utf-8"))
    svc = service()
    model = np.load("results/hardware/hardware4_tfim_model.npz")
    params, test_idx = model["params"], model["test"]
    states = np.load("data/processed/hardware4/tfim_states.npz")["states"]
    meta = pd.read_csv("data/processed/hardware4/tfim_metadata.csv")
    y = meta["label"].to_numpy(dtype=int)
    arch = get_architecture("light_shared_line")
    rows = []
    circuit_rows = []
    for snap in snapshot[:2]:
        backend = svc.backend(name=snap["name"])
        p, metrics = device_noise_predict(states[test_idx], params, arch, 4, backend, shots=1024, seed=2026)
        rows.append({"backend": backend.name, **asdict(binary_metrics(y[test_idx], p))})
        for idx, m in zip(test_idx, metrics):
            circuit_rows.append({"backend": backend.name, "sample_id": int(idx), **m})
    out = Path("results/hardware")
    pd.DataFrame(rows).to_csv(out / "device_noise_transfer.csv", index=False)
    pd.DataFrame(circuit_rows).to_csv(out / "device_noise_circuit_metrics.csv", index=False)
    print(pd.DataFrame(rows).to_string(index=False))
    print("Device-derived noise transfer PASSED")


if __name__ == "__main__":
    main()