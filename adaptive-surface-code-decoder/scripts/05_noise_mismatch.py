import numpy as np

from qec_lab.circuits import (
    make_rotated_memory_circuit,
    make_uniform_noise,
)
from qec_lab.decoders import (
    CorrelatedMWPMDecoder,
    MWPMDecoder,
)


def logical_failure_rate(
    true_p: float,
    assumed_p: float,
    distance: int = 7,
    shots: int = 100_000,
):
    true_circuit = (
        make_rotated_memory_circuit(
            distance=distance,
            rounds=distance,
            noise=make_uniform_noise(
                true_p
            ),
            basis="x",
        )
    )

    assumed_circuit = (
        make_rotated_memory_circuit(
            distance=distance,
            rounds=distance,
            noise=make_uniform_noise(
                assumed_p
            ),
            basis="x",
        )
    )

    assumed_dem = (
        assumed_circuit
        .detector_error_model(
            decompose_errors=True,
        )
    )

    dets, obs = (
        true_circuit
        .compile_detector_sampler()
        .sample(
            shots=shots,
            separate_observables=True,
        )
    )

    results = {}

    for decoder in [
        MWPMDecoder(
            assumed_dem
        ),
        CorrelatedMWPMDecoder(
            assumed_dem
        ),
    ]:
        pred = decoder.decode_batch(
            dets
        )

        failures = np.any(
            pred != obs,
            axis=1,
        )

        results[
            decoder.name
        ] = float(
            failures.mean()
        )

    return results


def main():
    import pandas as pd
    from pathlib import Path

    output = Path(
        "results/mismatch/"
        "mismatch.csv"
    )
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = []
    true_p = 0.006

    for assumed_p in [
        0.002,
        0.004,
        0.006,
        0.008,
        0.010,
    ]:
        result = logical_failure_rate(
            true_p=true_p,
            assumed_p=assumed_p,
        )

        row = {
            "true_p": true_p,
            "assumed_p": assumed_p,
            **result,
        }

        rows.append(row)
        print(row)

    pd.DataFrame(rows).to_csv(
        output,
        index=False,
    )


if __name__ == "__main__":
    main()