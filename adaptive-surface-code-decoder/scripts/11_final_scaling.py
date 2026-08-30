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


def run_case(
    distance: int,
    basis: str,
    p: float,
    shots: int,
):
    circuit = make_rotated_memory_circuit(
        distance=distance,
        rounds=distance,
        noise=make_uniform_noise(p),
        basis=basis,
    )

    dem = circuit.detector_error_model(
        decompose_errors=True,
    )

    dets, obs = (
        circuit
        .compile_detector_sampler()
        .sample(
            shots=shots,
            separate_observables=True,
        )
    )

    rows = []

    for decoder in [
        MWPMDecoder(dem),
        CorrelatedMWPMDecoder(dem),
    ]:
        for row in dets[:100]:
            decoder.decode(row)

        failures = []
        latencies = []

        for i in range(
            100,
            len(dets),
        ):
            start = perf_counter_ns()
            pred = decoder.decode(
                dets[i]
            )
            end = perf_counter_ns()

            failures.append(
                int(
                    np.any(
                        pred != obs[i]
                    )
                )
            )
            latencies.append(
                (end - start) / 1000.0
            )

        x = np.asarray(
            latencies,
            dtype=float,
        )

        rows.append(
            {
                "distance": distance,
                "basis": basis,
                "p": p,
                "decoder": decoder.name,
                "num_qubits": (
                    circuit.num_qubits
                ),
                "num_detectors": (
                    circuit.num_detectors
                ),
                "samples": len(x),
                "logical_failure_rate": float(
                    np.mean(failures)
                ),
                "mean_us": float(
                    np.mean(x)
                ),
                "p95_us": float(
                    np.percentile(
                        x,
                        95,
                    )
                ),
                "p99_us": float(
                    np.percentile(
                        x,
                        99,
                    )
                ),
                "throughput_per_s": float(
                    len(x)
                    / (
                        np.sum(x)
                        / 1e6
                    )
                ),
            }
        )

    return rows


def main():
    output = Path(
        "results/decoder_comparison/"
        "final_scaling.csv"
    )
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = []

    for basis in ["x", "z"]:
        for d in [
            3,
            5,
            7,
            9,
            11,
        ]:
            rows.extend(
                run_case(
                    distance=d,
                    basis=basis,
                    p=0.005,
                    shots=5000,
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