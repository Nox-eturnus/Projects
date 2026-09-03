from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from qkd_lab.config import bb84_objects, load_yaml
from qkd_lab.estimation.decoy_lp import estimate_decoy_bounds, point_intervals
from qkd_lab.math_utils import h2
from qkd_lab.physical.source import coherent_error_gain, coherent_gain


def main():
    config = load_yaml("configs/baseline.yaml")
    intensities, basis, channel0, detector = bb84_objects(config)
    signal = next(x for x in intensities if x.name == "signal")
    rows = []
    for distance in range(0, 181, 5):
        channel = replace(channel0, length_km=float(distance))
        gains = [coherent_gain(x.mu, channel, detector) for x in intensities]
        error_gains = [coherent_error_gain(x.mu, channel, detector) for x in intensities]
        bounds = estimate_decoy_bounds(
            [x.mu for x in intensities],
            point_intervals(gains),
            point_intervals(error_gains),
            n_max=10,
        )
        qmu = coherent_gain(signal.mu, channel, detector)
        emu = coherent_error_gain(signal.mu, channel, detector) / max(qmu, 1e-30)
        q1 = signal.mu * pow(2.718281828459045, -signal.mu) * bounds.y1_lower
        pref = signal.probability * basis.p_x_alice * basis.p_x_bob
        rate = pref * max(0.0, q1 * (1.0 - h2(min(0.5, bounds.e1_upper))) - qmu * 1.16 * h2(min(0.5, emu)))
        rows.append({"distance_km": distance, "y1_lower": bounds.y1_lower, "e1_upper": bounds.e1_upper, "secret_fraction": rate})
    df = pd.DataFrame(rows)
    Path("results/bb84").mkdir(parents=True, exist_ok=True)
    Path("results/figures").mkdir(parents=True, exist_ok=True)
    df.to_csv("results/bb84/asymptotic_decoy.csv", index=False)
    plt.plot(df["distance_km"], df["secret_fraction"], marker="o", markersize=2)
    plt.yscale("log")
    plt.xlabel("Distance (km)")
    plt.ylabel("Asymptotic lower-bound secret bits / emitted pulse")
    plt.tight_layout()
    plt.savefig("results/figures/asymptotic_decoy_rate.png", dpi=180)
    plt.close()
    print(df.head())


if __name__ == "__main__":
    main()