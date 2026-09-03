from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelParameters:
    length_km: float
    attenuation_db_per_km: float = 0.2

    def validate(self) -> None:
        if self.length_km < 0:
            raise ValueError("length_km must be non-negative")
        if self.attenuation_db_per_km < 0:
            raise ValueError("attenuation must be non-negative")


@dataclass(frozen=True)
class DetectorParameters:
    efficiency: float
    dark_probability: float
    misalignment: float
    n_detectors: int = 2

    def validate(self) -> None:
        for name, value in (
            ("efficiency", self.efficiency),
            ("dark_probability", self.dark_probability),
            ("misalignment", self.misalignment),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie in [0,1]")
        if self.n_detectors < 1:
            raise ValueError("n_detectors must be >= 1")


@dataclass(frozen=True)
class IntensitySetting:
    name: str
    mu: float
    probability: float

    def validate(self) -> None:
        if self.mu < 0:
            raise ValueError("mu must be non-negative")
        if not 0.0 < self.probability <= 1.0:
            raise ValueError("intensity probability must lie in (0,1]")


@dataclass(frozen=True)
class BasisProbabilities:
    p_x_alice: float
    p_x_bob: float

    def validate(self) -> None:
        if not 0.0 < self.p_x_alice < 1.0:
            raise ValueError("p_x_alice must lie in (0,1)")
        if not 0.0 < self.p_x_bob < 1.0:
            raise ValueError("p_x_bob must lie in (0,1)")


@dataclass(frozen=True)
class CountRecord:
    sent: int
    detected: int
    errors: int

    @property
    def gain(self) -> float:
        return self.detected / self.sent if self.sent else 0.0

    @property
    def error_gain(self) -> float:
        return self.errors / self.sent if self.sent else 0.0

    @property
    def qber(self) -> float:
        return self.errors / self.detected if self.detected else 0.0