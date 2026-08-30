import numpy as np

from qec_lab.circuits import (
    make_rotated_memory_circuit,
    make_uniform_noise,
)
from qec_lab.decoders import (
    MWPMDecoder,
)
from qec_lab.streaming import (
    CausalPrefixDecoder,
)


def test_final_prefix_matches_block():
    circuit = (
        make_rotated_memory_circuit(
            distance=3,
            rounds=3,
            noise=make_uniform_noise(
                0.003
            ),
            basis="x",
        )
    )

    dem = (
        circuit.detector_error_model(
            decompose_errors=True
        )
    )

    dets, _ = (
        circuit
        .compile_detector_sampler()
        .sample(
            shots=20,
            separate_observables=True,
        )
    )

    block = MWPMDecoder(dem)

    stream = CausalPrefixDecoder(
        decoder=MWPMDecoder(dem),
        circuit=circuit,
        update_stride=1,
    )

    for row in dets:
        expected = block.decode(
            row
        )

        actual = stream.decode(
            row
        ).final_prediction

        assert np.array_equal(
            expected,
            actual,
        )