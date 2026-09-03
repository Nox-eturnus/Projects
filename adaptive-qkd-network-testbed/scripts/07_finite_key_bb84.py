from pathlib import Path

import pandas as pd

from qkd_lab.config import bb84_objects, load_yaml
from qkd_lab.estimation.finite_key_bb84 import estimate_lim2014
from qkd_lab.models import ChannelParameters
from qkd_lab.protocols.decoy_bb84 import expected_decoy_bb84_block


def main():
    cfg = load_yaml("configs/baseline.yaml")
    sec = load_yaml("configs/finite_key.yaml")
    intensities, basis, channel0, detector = bb84_objects(cfg)
    rows = []
    for distance in (0, 25, 50, 75, 100):
        channel = ChannelParameters(distance, channel0.attenuation_db_per_km)
        for pulses in (100_000_000, 1_000_000_000, 10_000_000_000):
            block = expected_decoy_bb84_block(
                pulses,
                intensities=intensities,
                basis=basis,
                channel=channel,
                detector=detector,
            )
            result = estimate_lim2014(
                block.records,
                intensities,
                eps_sec=float(sec["eps_sec"]),
                eps_cor=float(sec["eps_cor"]),
                f_ec=float(cfg["postprocessing"]["f_ec"]),
            )
            rows.append({
                "distance_km": distance,
                "pulses": pulses,
                "secure_bits": result.secure_bits,
                "abort": result.abort,
                "s_x0_lower": result.s_x0_lower,
                "s_x1_lower": result.s_x1_lower,
                "s_z1_lower": result.s_z1_lower,
                "v_z1_upper": result.v_z1_upper,
                "phase_error_upper": result.phase_error_upper,
                "leak_ec": result.leak_ec,
                "eps_sec": result.eps_sec,
                "eps_cor": result.eps_cor,
            })
    frame = pd.DataFrame(rows)
    Path("results/finite_key").mkdir(parents=True, exist_ok=True)
    frame.to_csv("results/finite_key/bb84_finite_key.csv", index=False)
    print(frame.to_string(index=False))
    assert frame["secure_bits"].max() > 0, "baseline sweep should contain at least one positive finite key"
    print("Finite-key BB84 sweep PASSED")


if __name__ == "__main__":
    main()