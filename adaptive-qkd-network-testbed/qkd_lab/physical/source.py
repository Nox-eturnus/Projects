from __future__ import annotations

from math import exp

from qkd_lab.math_utils import clamp_probability
from qkd_lab.models import ChannelParameters, DetectorParameters
from qkd_lab.physical.channel import background_yield, total_efficiency


def coherent_gain(mu: float, channel: ChannelParameters, detector: DetectorParameters) -> float:
    if mu < 0:
        raise ValueError("mu must be non-negative")
    eta = total_efficiency(channel, detector)
    y0 = background_yield(detector)
    return clamp_probability(1.0 - (1.0 - y0) * exp(-eta * mu))


def coherent_error_gain(mu: float, channel: ChannelParameters, detector: DetectorParameters) -> float:
    q = coherent_gain(mu, channel, detector)
    y0 = background_yield(detector)
    e0 = 0.5
    ed = detector.misalignment
    return clamp_probability(e0 * y0 + ed * max(0.0, q - y0))


def coherent_qber(mu: float, channel: ChannelParameters, detector: DetectorParameters) -> float:
    q = coherent_gain(mu, channel, detector)
    if q <= 0.0:
        return 0.0
    return min(0.5, coherent_error_gain(mu, channel, detector) / q)