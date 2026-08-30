from pathlib import Path

import numpy as np
import pandas as pd

from qec_lab.circuits import (
    NoiseParameters,
    make_rotated_memory_circuit,
)
from qec_lab.decoders import MWPMDecoder


def run_proxy(
    distance: int,
    baseline_idle: float,
    elevated_idle: float,
    shots: int,
):
    rows = []

    for label, p_idle in [
        (
            "baseline",
            baseline_idle,
        ),
        (
            "persistent_error_proxy",
            elevated_idle,
        ),
    ]:
        circuit = (
            make_rotated_memory_circuit(
                distance=distance,
                rounds=distance,
                noise=NoiseParameters(
                    p_gate=0.002,
                    p_reset=0.001,
                    p_measure=0.002,
                    p_idle=p_idle,
                ),
                basis="x",
            )
        )

        dem = (
            circuit
            .detector_error_model(
                decompose_errors=True,
            )
        )

        dets, obs = (
            circuit
            .compile_detector_sampler()
            .sample(
                shots=shots,
                separate_observables=True,
            )
        )

        decoder = MWPMDecoder(dem)
        pred = decoder.decode_batch(dets)

        failures = np.any(
            pred != obs,
            axis=1,
        )

        rows.append(
            {
                "model": label,
                "distance": distance,
                "p_idle": p_idle,
                "shots": shots,
                "logical_failure_rate": float(
                    failures.mean()
                ),
                "mean_syndrome_density": float(
                    dets.mean()
                ),
            }
        )

    return rows


def main():
    output = Path(
        "results/noise_models/"
        "leakage_proxy.csv"
    )
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = []

    for d in [3, 5, 7]:
        rows.extend(
            run_proxy(
                distance=d,
                baseline_idle=0.002,
                elevated_idle=0.010,
                shots=20_000,
            )
        )

    df = pd.DataFrame(rows)
    df.to_csv(
        output,
        index=False,
    )
    print(df)


if __name__ == "__main__":
    main()