from pathlib import Path

import pandas as pd

from qkd_lab.config import bb84_objects, load_yaml, mdi_objects
from qkd_lab.estimation.finite_key_bb84 import estimate_lim2014
from qkd_lab.estimation.finite_key_mdi import estimate_mdi_finite_key
from qkd_lab.models import ChannelParameters
from qkd_lab.protocols.decoy_bb84 import expected_decoy_bb84_block
from qkd_lab.protocols.mdi_qkd import MDIPhysicalParameters, expected_mdi_block


def main():
    bb_cfg = load_yaml("configs/baseline.yaml")
    sec = load_yaml("configs/finite_key.yaml")
    intensities, bb_basis, bb_channel0, detector = bb84_objects(bb_cfg)
    mdi_cfg = load_yaml("configs/mdi.yaml")
    ai, bi, mdi_basis, mdi_phys0, mdi_budget = mdi_objects(mdi_cfg)
    pulses = 100_000_000_000
    rows = []
    for d in (20, 50, 80, 100):
        bb_channel = ChannelParameters(d, bb_channel0.attenuation_db_per_km)
        bb_block = expected_decoy_bb84_block(pulses, intensities=intensities, basis=bb_basis, channel=bb_channel, detector=detector)
        bb = estimate_lim2014(bb_block.records, intensities, eps_sec=float(sec["eps_sec"]), eps_cor=float(sec["eps_cor"]))
        rows.append({"distance_km": d, "protocol": "decoy_bb84", "secure_bits": bb.secure_bits, "abort": bb.abort})

        mdi_phys = MDIPhysicalParameters(d / 2, d / 2, mdi_phys0.attenuation_db_per_km, mdi_phys0.detector_efficiency, mdi_phys0.dark_probability, mdi_phys0.misalignment)
        mdi_block = expected_mdi_block(pulses, alice_intensities=ai, bob_intensities=bi, basis=mdi_basis, physical=mdi_phys)
        mdi = estimate_mdi_finite_key(mdi_block, mdi_budget)
        rows.append({"distance_km": d, "protocol": "mdi_qkd", "secure_bits": mdi.secure_bits, "abort": mdi.abort})
    frame = pd.DataFrame(rows)
    Path("results/finite_key").mkdir(parents=True, exist_ok=True)
    frame.to_csv("results/finite_key/protocol_comparison.csv", index=False)
    print(frame.to_string(index=False))
    print("Protocol comparison written")


if __name__ == "__main__":
    main()