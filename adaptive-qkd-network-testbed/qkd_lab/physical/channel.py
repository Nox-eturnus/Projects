from __future__ import annotations

from qkd_lab.models import ChannelParameters, DetectorParameters


def fibre_transmittance(channel: ChannelParameters) -> float:
    channel.validate()
    return 10.0 ** (-channel.attenuation_db_per_km * channel.length_km / 10.0)


def total_efficiency(channel: ChannelParameters, detector: DetectorParameters) -> float:
    detector.validate()
    return fibre_transmittance(channel) * detector.efficiency


def background_yield(detector: DetectorParameters) -> float:
    detector.validate()
    p = detector.dark_probability
    return 1.0 - (1.0 - p) ** detector.n_detectors


def n_photon_yield(n: int, channel: ChannelParameters, detector: DetectorParameters) -> float:
    if n < 0:
        raise ValueError("n must be non-negative")
    eta = total_efficiency(channel, detector)
    y0 = background_yield(detector)
    return 1.0 - (1.0 - y0) * (1.0 - eta) ** n