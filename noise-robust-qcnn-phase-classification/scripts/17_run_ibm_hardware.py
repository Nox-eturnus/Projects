import json
from pathlib import Path

import numpy as np
import pandas as pd

from qcnn_lab.hardware.ibm import hardware_estimator_predict, service
from qcnn_lab.qcnn.architecture import get_architecture


def main():
    snapshot = json.loads(Path("results/hardware/backend_snapshot.json").read_text(encoding="utf-8"))
    backend = service().backend(name=snapshot[0]["name"])
    model = np.load("results/hardware/hardware4_tfim_model.npz")
    params, test_idx = model["params"], model["test"]
    states = np.load("data/processed/hardware4/tfim_states.npz")["states"]
    meta = pd.read_csv("data/processed/hardware4/tfim_metadata.csv")
    # Keep the first 8 held-out states for an inexpensive proof-of-hardware pass.
    chosen = test_idx[: min(8, len(test_idx))]
    arch = get_architecture("light_shared_line")
    raw_p, raw_job, raw_metrics = hardware_estimator_predict(states[chosen], params, arch, 4, backend, precision=0.05, resilience_level=0, dynamical_decoupling=False, seed_transpiler=2026)
    mit_p, mit_job, mit_metrics = hardware_estimator_predict(states[chosen], params, arch, 4, backend, precision=0.05, resilience_level=1, dynamical_decoupling=True, seed_transpiler=2026)
    rows = []
    for pos, idx in enumerate(chosen):
        rows.append({
            "backend": backend.name,
            "architecture": "light_shared_line",
            "sample_id": int(idx),
            "parameter": float(meta.iloc[idx]["parameter"]),
            "label": int(meta.iloc[idx]["label"]),
            "p1_raw": float(raw_p[pos]),
            "p1_mitigated": float(mit_p[pos]),
            "raw_depth": raw_metrics[pos]["depth"],
            "raw_two_qubit_operations": raw_metrics[pos]["two_qubit_operations"],
            "mitigated_depth": mit_metrics[pos]["depth"],
            "mitigated_two_qubit_operations": mit_metrics[pos]["two_qubit_operations"],
        })
    out = Path("results/hardware")
    pd.DataFrame(rows).to_csv(out / "hardware_predictions.csv", index=False)
    (out / "hardware_jobs.json").write_text(json.dumps({"backend": backend.name, "architecture": "light_shared_line", "raw_job_id": raw_job, "mitigated_job_id": mit_job}, indent=2), encoding="utf-8")
    print(pd.DataFrame(rows).to_string(index=False))
    print("IBM hardware execution completed")


if __name__ == "__main__":
    main()