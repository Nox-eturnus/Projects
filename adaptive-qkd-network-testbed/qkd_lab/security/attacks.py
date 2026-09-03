from __future__ import annotations

from dataclasses import dataclass, replace

from qkd_lab.models import ChannelParameters, DetectorParameters


@dataclass(frozen=True)
class AttackProfile:
    intercept_resend_fraction: float = 0.0
    extra_loss_db: float = 0.0
    dark_count_multiplier: float = 1.0
    misalignment_addition: float = 0.0
    source_intensity_scale: float = 1.0
    z_basis_error_addition: float = 0.0

    def validate(self) -> None:
        if not 0.0 <= self.intercept_resend_fraction <= 1.0:
            raise ValueError("intercept_resend_fraction must lie in [0,1]")
        if self.extra_loss_db < 0.0:
            raise ValueError("extra_loss_db must be non-negative")
        if self.dark_count_multiplier < 0.0:
            raise ValueError("dark_count_multiplier must be non-negative")
        if self.source_intensity_scale <= 0.0:
            raise ValueError("source_intensity_scale must be positive")


def attacked_channel(channel: ChannelParameters, attack: AttackProfile) -> ChannelParameters:
    attack.validate()
    if channel.attenuation_db_per_km == 0.0:
        extra_km = 0.0
    else:
        extra_km = attack.extra_loss_db / channel.attenuation_db_per_km
    return replace(channel, length_km=channel.length_km + extra_km)


def attacked_detector(detector: DetectorParameters, attack: AttackProfile) -> DetectorParameters:
    attack.validate()
    return replace(
        detector,
        dark_probability=min(1.0, detector.dark_probability * attack.dark_count_multiplier),
        misalignment=min(0.5, detector.misalignment + attack.misalignment_addition),
    )