import numpy as np

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


def make_problem():
    circuit = make_rotated_memory_circuit(
        distance=3,
        rounds=3,
        noise=make_uniform_noise(
            0.003
        ),
        basis="x",
    )

    dem = circuit.detector_error_model(
        decompose_errors=True,
    )

    dets, obs = (
        circuit
        .compile_detector_sampler()
        .sample(
            shots=100,
            separate_observables=True,
        )
    )

    return dem, dets, obs


def test_mwpm_shapes():
    dem, dets, obs = make_problem()

    decoder = MWPMDecoder(dem)

    pred = decoder.decode_batch(dets)

    assert pred.shape == obs.shape


def test_correlated_mwpm_shapes():
    dem, dets, obs = make_problem()

    decoder = CorrelatedMWPMDecoder(
        dem
    )

    pred = decoder.decode_batch(dets)

    assert pred.shape == obs.shape


def test_bposd_shapes():
    dem, dets, obs = make_problem()

    decoder = BPOSDDecoder(dem)

    pred = decoder.decode_batch(
        dets[:10]
    )

    assert pred.shape == obs[:10].shape


def test_union_find_shapes():
    dem, dets, obs = make_problem()

    decoder = UnionFindSurfaceDecoder(
        dem
    )

    pred = decoder.decode_batch(
        dets[:10]
    )

    assert pred.shape == obs[:10].shape


def test_zero_syndrome_mwpm():
    dem, _, _ = make_problem()

    decoder = MWPMDecoder(dem)

    zero = np.zeros(
        dem.num_detectors,
        dtype=np.uint8,
    )

    pred = decoder.decode(zero)

    assert pred.ndim == 1