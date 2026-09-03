from pathlib import Path

import pandas as pd

from qkd_lab.config import load_yaml, mdi_objects
from qkd_lab.estimation.finite_key_mdi import estimate_mdi_finite_key
from qkd_lab.protocols.mdi_qkd import MDIPhysicalParameters, expected_mdi_block


def main():
    cfg = load_yaml("configs/mdi.yaml")
    alice, bob, basis, physical0, budget = mdi_objects(cfg)
    rows = []
    for total_distance in (20, 50, 80, 100):
        physical = MDIPhysicalParameters(
            total_distance / 2,
            total_distance / 2,
            physical0.attenuation_db_per_km,
            physical0.detector_efficiency,
            physical0.dark_probability,
            physical0.misalignment,
        )
        for pulses in (1_000_000_000, 10_000_000_000, 100_000_000_000):
            block = expected_mdi_block(
                pulses,
                alice_intensities=alice,
                bob_intensities=bob,
                basis=basis,
                physical=physical,
            )
            result = estimate_mdi_finite_key(block, budget)
            rows.append({
                "total_distance_km": total_distance,
                "pulses": pulses,
                "secure_bits": result.secure_bits,
                "abort": result.abort,
                "y11_lower": result.y11_lower,
                "e11_upper": result.e11_upper,
                "n11_lower": result.n11_lower,
                "phase_error_upper": result.phase_error_upper,
                "leak_ec": result.leak_ec,
                "eps_sec": result.eps_sec,
            })
    frame = pd.DataFrame(rows)
    Path("results/mdi").mkdir(parents=True, exist_ok=True)
    frame.to_csv("results/mdi/finite_key.csv", index=False)
    print(frame.to_string(index=False))
    assert frame["secure_bits"].max() > 0
    print("Finite-key MDI sweep PASSED")


if __name__ == "__main__":
    main()