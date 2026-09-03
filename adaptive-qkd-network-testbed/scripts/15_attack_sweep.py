from pathlib import Path

import pandas as pd

from qkd_lab.config import bb84_objects, load_yaml
from qkd_lab.estimation.finite_key_bb84 import estimate_lim2014
from qkd_lab.protocols.decoy_bb84 import expected_decoy_bb84_block
from qkd_lab.security.attacks import AttackProfile


def main():
    cfg = load_yaml("configs/baseline.yaml")
    sec = load_yaml("configs/finite_key.yaml")
    intensities, basis, channel, detector = bb84_objects(cfg)
    attacks = [
        ("normal", 0.0, AttackProfile()),
        ("intercept_resend", 0.25, AttackProfile(intercept_resend_fraction=0.25)),
        ("intercept_resend", 0.50, AttackProfile(intercept_resend_fraction=0.50)),
        ("dark_counts", 10.0, AttackProfile(dark_count_multiplier=10.0)),
        ("misalignment", 0.03, AttackProfile(misalignment_addition=0.03)),
        ("extra_loss_db", 3.0, AttackProfile(extra_loss_db=3.0)),
        ("intensity_scale", 1.10, AttackProfile(source_intensity_scale=1.10)),
    ]
    rows = []
    for name, strength, attack in attacks:
        block = expected_decoy_bb84_block(
            10_000_000_000,
            intensities=intensities,
            basis=basis,
            channel=channel,
            detector=detector,
            attack=attack,
        )
        result = estimate_lim2014(block.records, intensities, eps_sec=float(sec["eps_sec"]), eps_cor=float(sec["eps_cor"]))
        x = block.basis_total("X")
        rows.append({"attack": name, "strength": strength, "qber_x": x.qber, "secure_bits": result.secure_bits, "abort": result.abort, "phase_error_upper": result.phase_error_upper})
    frame = pd.DataFrame(rows)
    Path("results/attacks").mkdir(parents=True, exist_ok=True)
    frame.to_csv("results/attacks/attack_sweep.csv", index=False)
    print(frame.to_string(index=False))
    print("Attack sweep written")


if __name__ == "__main__":
    main()