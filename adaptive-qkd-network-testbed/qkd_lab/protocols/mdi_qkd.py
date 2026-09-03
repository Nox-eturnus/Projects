from __future__ import annotations

from dataclasses import dataclass
from math import exp

import numpy as np

from qkd_lab.models import CountRecord, IntensitySetting
from qkd_lab.rng import make_rng


@dataclass(frozen=True)
class MDIPhysicalParameters:
    alice_to_charlie_km: float
    bob_to_charlie_km: float
    attenuation_db_per_km: float
    detector_efficiency: float
    dark_probability: float
    misalignment: float

    def validate(self) -> None:
        if self.alice_to_charlie_km < 0 or self.bob_to_charlie_km < 0:
            raise ValueError("MDI arm lengths must be non-negative")
        if self.attenuation_db_per_km < 0:
            raise ValueError("attenuation must be non-negative")
        for name, value in (
            ("detector_efficiency", self.detector_efficiency),
            ("dark_probability", self.dark_probability),
            ("misalignment", self.misalignment),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie in [0,1]")


@dataclass(frozen=True)
class MDIBasisProbabilities:
    p_z_alice: float
    p_z_bob: float


@dataclass(frozen=True)
class MDIBlock:
    pulses: int
    records: dict[tuple[str, str, str], CountRecord]
    alice_intensities: tuple[IntensitySetting, ...]
    bob_intensities: tuple[IntensitySetting, ...]
    basis: MDIBasisProbabilities
    physical: MDIPhysicalParameters


def arm_efficiency(length_km: float, attenuation_db_per_km: float, detector_efficiency: float) -> float:
    channel = 10.0 ** (-attenuation_db_per_km * length_km / 10.0)
    return channel * detector_efficiency


def mdi_n_m_yield(n: int, m: int, physical: MDIPhysicalParameters) -> float:
    physical.validate()
    if n < 0 or m < 0:
        raise ValueError("photon numbers must be non-negative")
    eta_a = arm_efficiency(physical.alice_to_charlie_km, physical.attenuation_db_per_km, physical.detector_efficiency)
    eta_b = arm_efficiency(physical.bob_to_charlie_km, physical.attenuation_db_per_km, physical.detector_efficiency)
    p_a = 1.0 - (1.0 - eta_a) ** n
    p_b = 1.0 - (1.0 - eta_b) ** m
    signal_bsm = 0.5 * p_a * p_b
    d = physical.dark_probability
    background = min(1.0, 2.0 * d * (1.0 - d) + d * d)
    return min(1.0, background + (1.0 - background) * signal_bsm)


def mdi_n_m_error_yield(n: int, m: int, physical: MDIPhysicalParameters) -> float:
    y = mdi_n_m_yield(n, m, physical)
    d = physical.dark_probability
    background = min(1.0, 2.0 * d * (1.0 - d) + d * d)
    signal = max(0.0, y - background)
    return min(y, 0.5 * background + physical.misalignment * signal)


def mdi_coherent_gain(mu_a: float, mu_b: float, physical: MDIPhysicalParameters) -> float:
    physical.validate()
    eta_a = arm_efficiency(physical.alice_to_charlie_km, physical.attenuation_db_per_km, physical.detector_efficiency)
    eta_b = arm_efficiency(physical.bob_to_charlie_km, physical.attenuation_db_per_km, physical.detector_efficiency)
    p_a = 1.0 - exp(-eta_a * mu_a)
    p_b = 1.0 - exp(-eta_b * mu_b)
    signal_bsm = 0.5 * p_a * p_b
    d = physical.dark_probability
    background = min(1.0, 2.0 * d * (1.0 - d) + d * d)
    return min(1.0, background + (1.0 - background) * signal_bsm)


def mdi_coherent_qber(mu_a: float, mu_b: float, physical: MDIPhysicalParameters) -> float:
    q = mdi_coherent_gain(mu_a, mu_b, physical)
    if q <= 0.0:
        return 0.0
    d = physical.dark_probability
    background = min(1.0, 2.0 * d * (1.0 - d) + d * d)
    signal = max(0.0, q - background)
    t = 0.5 * background + physical.misalignment * signal
    return min(0.5, t / q)


def _validate_intensities(items: tuple[IntensitySetting, ...]) -> None:
    for item in items:
        item.validate()
    if not np.isclose(sum(x.probability for x in items), 1.0, atol=1e-12):
        raise ValueError("intensity probabilities must sum to 1")


def simulate_mdi_block(
    pulses: int,
    *,
    alice_intensities: tuple[IntensitySetting, ...],
    bob_intensities: tuple[IntensitySetting, ...],
    basis: MDIBasisProbabilities,
    physical: MDIPhysicalParameters,
    seed: int | None = None,
) -> MDIBlock:
    if pulses <= 0:
        raise ValueError("pulses must be positive")
    _validate_intensities(alice_intensities)
    _validate_intensities(bob_intensities)
    physical.validate()
    if not (0.0 < basis.p_z_alice < 1.0 and 0.0 < basis.p_z_bob < 1.0):
        raise ValueError("basis probabilities must lie in (0,1)")

    rng = make_rng(seed)
    a_choice = rng.choice(len(alice_intensities), size=pulses, p=[x.probability for x in alice_intensities])
    b_choice = rng.choice(len(bob_intensities), size=pulses, p=[x.probability for x in bob_intensities])
    a_z = rng.random(pulses) < basis.p_z_alice
    b_z = rng.random(pulses) < basis.p_z_bob

    records: dict[tuple[str, str, str], CountRecord] = {}
    for ai, a in enumerate(alice_intensities):
        for bi, b in enumerate(bob_intensities):
            gain = mdi_coherent_gain(a.mu, b.mu, physical)
            qber = mdi_coherent_qber(a.mu, b.mu, physical)
            for basis_name, basis_mask in (("Z", a_z & b_z), ("X", (~a_z) & (~b_z))):
                mask = (a_choice == ai) & (b_choice == bi) & basis_mask
                sent = int(mask.sum())
                detected = int(rng.binomial(sent, gain)) if sent else 0
                errors = int(rng.binomial(detected, qber)) if detected else 0
                records[(basis_name, a.name, b.name)] = CountRecord(sent, detected, errors)

    return MDIBlock(
        pulses=pulses,
        records=records,
        alice_intensities=alice_intensities,
        bob_intensities=bob_intensities,
        basis=basis,
        physical=physical,
    )


def expected_mdi_block(
    pulses: int,
    *,
    alice_intensities: tuple[IntensitySetting, ...],
    bob_intensities: tuple[IntensitySetting, ...],
    basis: MDIBasisProbabilities,
    physical: MDIPhysicalParameters,
) -> MDIBlock:
    """Deterministic expected-count MDI block for large design sweeps."""
    if pulses <= 0:
        raise ValueError("pulses must be positive")
    _validate_intensities(alice_intensities)
    _validate_intensities(bob_intensities)
    physical.validate()
    if not (0.0 < basis.p_z_alice < 1.0 and 0.0 < basis.p_z_bob < 1.0):
        raise ValueError("basis probabilities must lie in (0,1)")

    basis_probability = {
        "Z": basis.p_z_alice * basis.p_z_bob,
        "X": (1.0 - basis.p_z_alice) * (1.0 - basis.p_z_bob),
    }
    records: dict[tuple[str, str, str], CountRecord] = {}
    for a in alice_intensities:
        for b in bob_intensities:
            gain = mdi_coherent_gain(a.mu, b.mu, physical)
            qber = mdi_coherent_qber(a.mu, b.mu, physical)
            for basis_name in ("Z", "X"):
                sent = int(round(pulses * a.probability * b.probability * basis_probability[basis_name]))
                detected = min(sent, int(round(sent * gain)))
                errors = min(detected, int(round(detected * qber)))
                records[(basis_name, a.name, b.name)] = CountRecord(sent, detected, errors)
    return MDIBlock(
        pulses=pulses,
        records=records,
        alice_intensities=alice_intensities,
        bob_intensities=bob_intensities,
        basis=basis,
        physical=physical,
    )