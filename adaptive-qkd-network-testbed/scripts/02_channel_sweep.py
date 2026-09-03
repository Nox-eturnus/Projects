from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from qkd_lab.config import bb84_objects, load_yaml
from qkd_lab.physical.channel import fibre_transmittance, total_efficiency
from qkd_lab.physical.source import coherent_gain, coherent_qber
from qkd_lab.rng import make_rng


def main():
    config = load_yaml("configs/baseline.yaml")
    _, _, channel0, detector = bb84_objects(config)
    rng = make_rng(12345)
    rows = []
    for distance in range(0, 201, 10):
        channel = replace(channel0, length_km=float(distance))
        for mu in (0.1, 0.3, 0.5, 0.7):
            q = coherent_gain(mu, channel, detector)
            e = coherent_qber(mu, channel, detector)
            shots = 100_000
            detected = int(rng.binomial(shots, q))
            errors = int(rng.binomial(detected, e)) if detected else 0
            rows.append({
                "distance_km": distance,
                "mu": mu,
                "eta_channel": fibre_transmittance(channel),
                "eta_total": total_efficiency(channel, detector),
                "gain_analytic": q,
                "gain_mc": detected / shots,
                "qber_analytic": e,
                "qber_mc": errors / detected if detected else 0.0,
            })
    df = pd.DataFrame(rows)
    Path("results/channel").mkdir(parents=True, exist_ok=True)
    Path("results/figures").mkdir(parents=True, exist_ok=True)
    df.to_csv("results/channel/channel_sweep.csv", index=False)

    for mu, g in df.groupby("mu"):
        plt.plot(g["distance_km"], g["gain_analytic"], label=f"analytic mu={mu}")
        plt.scatter(g["distance_km"], g["gain_mc"], s=10)
    plt.yscale("log")
    plt.xlabel("Distance (km)")
    plt.ylabel("Gain")
    plt.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig("results/figures/channel_gain_validation.png", dpi=180)
    plt.close()

    for mu, g in df.groupby("mu"):
        plt.plot(g["distance_km"], g["qber_analytic"], label=f"analytic mu={mu}")
        plt.scatter(g["distance_km"], g["qber_mc"], s=10)
    plt.xlabel("Distance (km)")
    plt.ylabel("QBER")
    plt.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig("results/figures/channel_qber_validation.png", dpi=180)
    plt.close()
    print(df.head())
    print("Phase 2 outputs written")


if __name__ == "__main__":
    main()