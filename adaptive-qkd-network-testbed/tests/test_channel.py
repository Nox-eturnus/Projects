import numpy as np

from qkd_lab.models import ChannelParameters, DetectorParameters
from qkd_lab.physical.channel import fibre_transmittance
from qkd_lab.physical.source import coherent_gain, coherent_qber


def test_fibre_transmission_monotone():
    vals = [fibre_transmittance(ChannelParameters(d, 0.2)) for d in (0, 25, 50, 100)]
    assert all(a > b for a, b in zip(vals, vals[1:]))


def test_gain_decreases_with_distance():
    det = DetectorParameters(0.25, 1e-7, 0.015)
    q0 = coherent_gain(0.5, ChannelParameters(0), det)
    q100 = coherent_gain(0.5, ChannelParameters(100), det)
    assert q0 > q100 > 0


def test_qber_is_probability():
    det = DetectorParameters(0.25, 1e-7, 0.015)
    qber = coherent_qber(0.5, ChannelParameters(25), det)
    assert 0 <= qber <= 0.5