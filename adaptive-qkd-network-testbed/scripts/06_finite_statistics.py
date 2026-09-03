from pathlib import Path

import pandas as pd

from qkd_lab.config import bb84_objects, load_yaml
from qkd_lab.estimation.confidence import clopper_pearson_interval
from qkd_lab.protocols.decoy_bb84 import simulate_decoy_bb84_block


def main():
    cfg = load_yaml("configs/baseline.yaml")
    intensities, basis, channel, detector = bb84_objects(cfg)
    rows = []
    for pulses in (100_000, 1_000_000):
        block = simulate_decoy_bb84_block(
            pulses,
            intensities=intensities,
            basis=basis,
            channel=channel,
            detector=detector,
            seed=cfg["seed"] + pulses,
        )
        for (basis_name, intensity), rec in block.records.items():
            if rec.sent == 0:
                continue
            q = clopper_pearson_interval(rec.detected, rec.sent, 1e-6)
            t = clopper_pearson_interval(rec.errors, rec.sent, 1e-6)
            rows.append({
                "pulses": pulses,
                "basis": basis_name,
                "intensity": intensity,
                "sent": rec.sent,
                "detected": rec.detected,
                "errors": rec.errors,
                "gain": rec.gain,
                "gain_low": q.lower,
                "gain_high": q.upper,
                "error_gain": rec.error_gain,
                "error_gain_low": t.lower,
                "error_gain_high": t.upper,
            })
    out = pd.DataFrame(rows)
    Path("results/finite_key").mkdir(parents=True, exist_ok=True)
    out.to_csv("results/finite_key/finite_statistics.csv", index=False)
    print(out.head(8).to_string(index=False))
    print("Finite-statistics output written")


if __name__ == "__main__":
    main()