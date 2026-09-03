from pathlib import Path

import pandas as pd

from qkd_lab.config import load_yaml, mdi_physical_objects
from qkd_lab.protocols.mdi_qkd import MDIPhysicalParameters, mdi_coherent_gain, mdi_coherent_qber


def main():
    cfg = load_yaml("configs/mdi.yaml")
    alice, bob, basis, physical0 = mdi_physical_objects(cfg)
    a_sig = max(alice, key=lambda x: x.mu)
    b_sig = max(bob, key=lambda x: x.mu)
    rows = []
    for total_distance in (0, 25, 50, 75, 100, 125, 150):
        p = MDIPhysicalParameters(
            alice_to_charlie_km=total_distance / 2,
            bob_to_charlie_km=total_distance / 2,
            attenuation_db_per_km=physical0.attenuation_db_per_km,
            detector_efficiency=physical0.detector_efficiency,
            dark_probability=physical0.dark_probability,
            misalignment=physical0.misalignment,
        )
        rows.append({
            "total_distance_km": total_distance,
            "gain": mdi_coherent_gain(a_sig.mu, b_sig.mu, p),
            "qber": mdi_coherent_qber(a_sig.mu, b_sig.mu, p),
        })
    frame = pd.DataFrame(rows)
    Path("results/mdi").mkdir(parents=True, exist_ok=True)
    frame.to_csv("results/mdi/physical_sweep.csv", index=False)
    print(frame.to_string(index=False))
    print("MDI physical sweep written")


if __name__ == "__main__":
    main()