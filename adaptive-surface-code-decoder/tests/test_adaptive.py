import numpy as np

from qec_lab.adaptive import (
    make_feature_frame,
    syndrome_density,
    syndrome_event_count,
)


def test_syndrome_features():
    dets = np.asarray(
        [
            [0, 0, 0, 0],
            [1, 0, 1, 0],
        ],
        dtype=np.uint8,
    )

    rho = syndrome_density(dets)
    count = syndrome_event_count(dets)

    assert np.allclose(
        rho,
        [0.0, 0.5],
    )

    assert np.array_equal(
        count,
        [0, 2],
    )

    frame = make_feature_frame(
        dets=dets,
        distance=3,
        p=0.005,
        bias_ratio=1.0,
        rounds=3,
    )

    assert len(frame) == 2
    assert "rho" in frame.columns
    assert "event_count" in frame.columns