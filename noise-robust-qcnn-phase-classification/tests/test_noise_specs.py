import pytest

from qcnn_lab.noise.models import NoiseSpec


def test_invalid_noise_probability_rejected():
    with pytest.raises(ValueError):
        NoiseSpec("bad", readout=1.0).validate()