from pathlib import Path
from time import perf_counter_ns

import numpy as np
import pandas as pd

from qec_lab.circuits import (
    make_rotated_memory_circuit,
    make_uniform_noise,
)
from qec_lab.decoders import (
    CorrelatedMWPMDecoder,
    MWPMDecoder,
)


def benchmark_decoder(
    decoder,
    dets,
    obs,
    warmup=100,
):
    for row in dets[:warmup]:
        decoder.decode(row)

    failures = []
    latencies_us = []

    for i in range(
        warmup,
        len(dets),
    ):
        start = perf_counter_ns()
        pred = decoder.decode(dets[i])
        end = perf_counter_ns()

        failures.append(
            int(
                np.any(
                    pred != obs[i]
                )
            )
        )
        latencies_us.append(
            (end - start) / 1000.0
        )

    x = np.asarray(
        latencies_us,
        dtype=float,
    )

    return {
        "decoder": decoder.name,
        "samples": len(x),
        "logical_failure_rate": float(
            np.mean(failures)
        ),
        "mean_us": float(
            np.mean(x)
        ),
        "p95_us": float(
            np.percentile(x, 95)
        ),
        "p99_us": float(
            np.percentile(x, 99)
        ),
        "throughput_per_s": float(
            len(x) / (
                np.sum(x) / 1e6
            )
        ),
    }


def main():
    output = Path(
        "results/decoder_comparison/"
        "correlation_study.csv"
    )
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = []

    for d in [3, 5, 7, 9]:
        for p in [
            0.003,
            0.005,
            0.007,
        ]:
            circuit = (
                make_rotated_memory_circuit(
                    distance=d,
                    rounds=d,
                    noise=make_uniform_noise(
                        p
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
                    shots=5000,
                    separate_observables=True,
                )
            )

            for decoder in [
                MWPMDecoder(dem),
                CorrelatedMWPMDecoder(
                    dem
                ),
            ]:
                result = (
                    benchmark_decoder(
                        decoder,
                        dets,
                        obs,
                    )
                )

                result.update(
                    {
                        "distance": d,
                        "p": p,
                    }
                )

                rows.append(result)
                print(result)

    pd.DataFrame(rows).to_csv(
        output,
        index=False,
    )


if __name__ == "__main__":
    main()