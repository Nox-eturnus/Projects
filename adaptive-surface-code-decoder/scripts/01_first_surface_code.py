import numpy as np
import pymatching

from qec_lab.circuits import (
    make_rotated_memory_circuit,
    make_uniform_noise,
)


def main():
    distance = 3
    rounds = 3
    p = 0.005
    shots = 10_000

    circuit = make_rotated_memory_circuit(
        distance=distance,
        rounds=rounds,
        noise=make_uniform_noise(p),
        basis="x",
    )

    print("Qubits:", circuit.num_qubits)
    print("Detectors:", circuit.num_detectors)
    print(
        "Logical observables:",
        circuit.num_observables,
    )

    dem = circuit.detector_error_model(
        decompose_errors=True,
    )

    matching = (
        pymatching.Matching
        .from_detector_error_model(dem)
    )

    sampler = circuit.compile_detector_sampler()

    dets, actual_observables = sampler.sample(
        shots=shots,
        separate_observables=True,
    )

    predicted_observables = matching.decode_batch(
        dets
    )

    logical_failures = np.any(
        predicted_observables
        != actual_observables,
        axis=1,
    )

    p_logical = logical_failures.mean()

    print("Shots:", shots)
    print(
        "Logical failures:",
        logical_failures.sum(),
    )
    print(
        "Logical failure probability:",
        p_logical,
    )


if __name__ == "__main__":
    main()