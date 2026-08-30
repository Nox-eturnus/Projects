from pathlib import Path
from time import perf_counter_ns

import numpy as np
import pandas as pd

from qec_lab.adaptive import (
    make_feature_frame,
)
from qec_lab.circuits import (
    make_rotated_memory_circuit,
    make_uniform_noise,
)
from qec_lab.decoders import (
    BPOSDDecoder,
    CorrelatedMWPMDecoder,
    MWPMDecoder,
    UnionFindSurfaceDecoder,
)


def benchmark_scenario(
    distance: int,
    p: float,
    shots: int = 5000,
):
    circuit = (
        make_rotated_memory_circuit(
            distance=distance,
            rounds=distance,
            noise=make_uniform_noise(
                p
            ),
            basis="x",
        )
    )

    dem = (
        circuit.detector_error_model(
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

    features = make_feature_frame(
        dets=dets,
        distance=distance,
        p=p,
        bias_ratio=1.0,
        rounds=distance,
    )

    decoders = [
        MWPMDecoder(dem),
        CorrelatedMWPMDecoder(
            dem
        ),
        UnionFindSurfaceDecoder(
            dem
        ),
        BPOSDDecoder(dem),
    ]

    records = []

    for decoder in decoders:
        for row in dets[:100]:
            decoder.decode(row)

        for i in range(
            100,
            len(dets),
        ):
            start = perf_counter_ns()

            pred = decoder.decode(
                dets[i]
            )

            end = perf_counter_ns()

            failure = bool(
                np.any(
                    pred != obs[i]
                )
            )

            records.append(
                {
                    **features
                    .iloc[i]
                    .to_dict(),
                    "scenario_id": (
                        f"d{distance}_p{p}"
                    ),
                    "shot_id": i,
                    "decoder": (
                        decoder.name
                    ),
                    "latency_us": (
                        end - start
                    ) / 1000.0,
                    "failure": int(
                        failure
                    ),
                }
            )

    return records


def main():
    output = Path(
        "results/adaptive/"
        "policy_samples.parquet"
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = []

    for d in [
        3,
        5,
        7,
        9,
    ]:
        for p in [
            0.002,
            0.004,
            0.006,
            0.008,
        ]:
            rows.extend(
                benchmark_scenario(
                    distance=d,
                    p=p,
                    shots=5000,
                )
            )

    df = pd.DataFrame(rows)

    df.to_parquet(
        output,
        index=False,
    )

    print(df.head())
    print(
        "Rows:",
        len(df),
    )


if __name__ == "__main__":
    main()