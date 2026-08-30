from pathlib import Path

import numpy as np
import pandas as pd

from qec_lab.circuits import (
    NoiseParameters,
    make_rotated_memory_circuit,
)
from qec_lab.decoders import (
    CorrelatedMWPMDecoder,
    MWPMDecoder,
)
from qec_lab.noise import (
    replace_depolarize1_with_pauli_channel,
)


CASES = {
    "isotropic": (
        0.002,
        0.002,
        0.002,
    ),
    "z_biased": (
        0.00025,
        0.00025,
        0.0055,
    ),
    "x_biased": (
        0.0055,
        0.00025,
        0.00025,
    ),
    "y_rich": (
        0.0005,
        0.0050,
        0.0005,
    ),
}


def run_case(
    name: str,
    px: float,
    py: float,
    pz: float,
    distance: int,
    basis: str,
    shots: int,
):
    total = px + py + pz

    base = make_rotated_memory_circuit(
        distance=distance,
        rounds=distance,
        noise=NoiseParameters(
            p_gate=0.0,
            p_reset=0.0,
            p_measure=0.0,
            p_idle=total,
        ),
        basis=basis,
    )

    circuit = (
        replace_depolarize1_with_pauli_channel(
            base,
            px=px,
            py=py,
            pz=pz,
        )
    )

    dem = circuit.detector_error_model(
        decompose_errors=True,
        approximate_disjoint_errors=True,
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
        pred = decoder.decode_batch(dets)

        failures = np.any(
            pred != obs,
            axis=1,
        )

        rows.append(
            {
                "noise_case": name,
                "basis": basis,
                "distance": distance,
                "px": px,
                "py": py,
                "pz": pz,
                "decoder": decoder.name,
                "shots": shots,
                "failures": int(
                    failures.sum()
                ),
                "logical_failure_rate": float(
                    failures.mean()
                ),
            }
        )

    return rows


def main():
    output = Path(
        "results/bias/"
        "bias_results.csv"
    )
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = []

    for basis in ["x", "z"]:
        for d in [3, 5, 7]:
            for name, values in (
                CASES.items()
            ):
                rows.extend(
                    run_case(
                        name=name,
                        px=values[0],
                        py=values[1],
                        pz=values[2],
                        distance=d,
                        basis=basis,
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