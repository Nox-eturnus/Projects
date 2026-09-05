from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qkd_lab.models import BasisProbabilities, ChannelParameters, CountRecord, DetectorParameters, IntensitySetting
from qkd_lab.physical.detector import combine_independent_bit_error
from qkd_lab.physical.source import coherent_gain, coherent_qber
from qkd_lab.rng import make_rng
from qkd_lab.security.attacks import AttackProfile, attacked_channel, attacked_detector


@dataclass(frozen=True)
class DecoyBB84Block:
    pulses: int
    records: dict[tuple[str, str], CountRecord]
    intensities: tuple[IntensitySetting, ...]
    basis: BasisProbabilities
    channel: ChannelParameters
    detector: DetectorParameters
    attack: AttackProfile

    def basis_total(self, basis: str) -> CountRecord:
        subset = [r for (b, _), r in self.records.items() if b == basis]
        return CountRecord(
            sent=sum(r.sent for r in subset),
            detected=sum(r.detected for r in subset),
            errors=sum(r.errors for r in subset),
        )


def validate_intensities(intensities: tuple[IntensitySetting, ...]) -> None:
    if len(intensities) < 2:
        raise ValueError("at least two intensities are required")
    for item in intensities:
        item.validate()
    total = sum(x.probability for x in intensities)
    if not np.isclose(total, 1.0, atol=1e-12):
        raise ValueError("intensity probabilities must sum to 1")
    if len({x.name for x in intensities}) != len(intensities):
        raise ValueError("intensity names must be unique")


def simulate_decoy_bb84_block(
    pulses: int,
    *,
    intensities: tuple[IntensitySetting, ...],
    basis: BasisProbabilities,
    channel: ChannelParameters,
    detector: DetectorParameters,
    attack: AttackProfile | None = None,
    seed: int | None = None,
) -> DecoyBB84Block:
    if pulses <= 0:
        raise ValueError("pulses must be positive")
    if pulses > 10_000_000:
        return simulate_aggregate_decoy_bb84_block(
            pulses,
            intensities=intensities,
            basis=basis,
            channel=channel,
            detector=detector,
            attack=attack,
            seed=seed,
        )
    validate_intensities(intensities)
    basis.validate()
    channel.validate()
    detector.validate()
    attack = attack or AttackProfile()
    attack.validate()

    rng = make_rng(seed)
    probs = np.asarray([x.probability for x in intensities], dtype=float)
    choice = rng.choice(len(intensities), size=pulses, p=probs)
    alice_x = rng.random(pulses) < basis.p_x_alice
    bob_x = rng.random(pulses) < basis.p_x_bob

    effective_channel = attacked_channel(channel, attack)
    effective_detector = attacked_detector(detector, attack)

    records: dict[tuple[str, str], CountRecord] = {}
    for idx, setting in enumerate(intensities):
        actual_mu = setting.mu * attack.source_intensity_scale
        gain = coherent_gain(actual_mu, effective_channel, effective_detector)
        base_qber = coherent_qber(actual_mu, effective_channel, effective_detector)
        intercept_qber = 0.25 * attack.intercept_resend_fraction

        for basis_name, basis_mask in (
            ("X", alice_x & bob_x),
            ("Z", (~alice_x) & (~bob_x)),
        ):
            mask = (choice == idx) & basis_mask
            sent = int(mask.sum())
            if sent == 0:
                records[(basis_name, setting.name)] = CountRecord(0, 0, 0)
                continue

            detected = int(rng.binomial(sent, gain))
            qber = combine_independent_bit_error(base_qber, intercept_qber)
            if basis_name == "Z":
                qber = combine_independent_bit_error(qber, min(0.5, attack.z_basis_error_addition))
            errors = int(rng.binomial(detected, min(0.5, qber))) if detected else 0
            records[(basis_name, setting.name)] = CountRecord(sent, detected, errors)

    return DecoyBB84Block(
        pulses=pulses,
        records=records,
        intensities=intensities,
        basis=basis,
        channel=channel,
        detector=detector,
        attack=attack,
    )


def simulate_aggregate_decoy_bb84_block(
    pulses: int,
    *,
    intensities: tuple[IntensitySetting, ...],
    basis: BasisProbabilities,
    channel: ChannelParameters,
    detector: DetectorParameters,
    attack: AttackProfile | None = None,
    seed: int | None = None,
) -> DecoyBB84Block:
    """Stochastic simulation using aggregate Multinomial/Binomial distributions.

    Runs in O(num_settings) memory and time, enabling exact finite-sample
    stochastic simulations for arbitrarily large pulse counts (e.g., 10^10 - 10^11).
    """
    if pulses <= 0:
        raise ValueError("pulses must be positive")
    validate_intensities(intensities)
    basis.validate()
    channel.validate()
    detector.validate()
    attack = attack or AttackProfile()
    attack.validate()

    rng = make_rng(seed)
    effective_channel = attacked_channel(channel, attack)
    effective_detector = attacked_detector(detector, attack)

    # Sifted match probabilities
    p_x_match = basis.p_x_alice * basis.p_x_bob
    p_z_match = (1.0 - basis.p_x_alice) * (1.0 - basis.p_x_bob)
    p_mismatch = max(0.0, 1.0 - p_x_match - p_z_match)

    categories: list[tuple[IntensitySetting, str]] = []
    probs: list[float] = []
    for setting in intensities:
        categories.append((setting, "X"))
        probs.append(setting.probability * p_x_match)
        categories.append((setting, "Z"))
        probs.append(setting.probability * p_z_match)

    probs.append(p_mismatch)
    prob_arr = np.array(probs, dtype=float)
    prob_arr /= prob_arr.sum()

    multinomial_counts = rng.multinomial(pulses, prob_arr)

    records: dict[tuple[str, str], CountRecord] = {}
    for idx, (setting, basis_name) in enumerate(categories):
        sent = int(multinomial_counts[idx])
        if sent == 0:
            records[(basis_name, setting.name)] = CountRecord(0, 0, 0)
            continue

        actual_mu = setting.mu * attack.source_intensity_scale
        gain = coherent_gain(actual_mu, effective_channel, effective_detector)
        base_qber = coherent_qber(actual_mu, effective_channel, effective_detector)
        intercept_qber = 0.25 * attack.intercept_resend_fraction
        qber = combine_independent_bit_error(base_qber, intercept_qber)
        if basis_name == "Z":
            qber = combine_independent_bit_error(qber, min(0.5, attack.z_basis_error_addition))

        detected = int(rng.binomial(sent, gain))
        errors = int(rng.binomial(detected, min(0.5, qber))) if detected > 0 else 0
        records[(basis_name, setting.name)] = CountRecord(sent, detected, errors)

    return DecoyBB84Block(
        pulses=pulses,
        records=records,
        intensities=intensities,
        basis=basis,
        channel=channel,
        detector=detector,
        attack=attack,
    )


def make_correlated_raw_keys(length: int, qber: float, seed: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    if length < 0:
        raise ValueError("length must be non-negative")
    if not 0.0 <= qber <= 0.5:
        raise ValueError("qber must lie in [0,0.5]")
    rng = make_rng(seed)
    alice = rng.integers(0, 2, size=length, dtype=np.uint8)
    bob = alice.copy()
    flips = rng.random(length) < qber
    bob[flips] ^= 1
    return alice, bob


def expected_decoy_bb84_block(
    pulses: int,
    *,
    intensities: tuple[IntensitySetting, ...],
    basis: BasisProbabilities,
    channel: ChannelParameters,
    detector: DetectorParameters,
    attack: AttackProfile | None = None,
) -> DecoyBB84Block:
    """Deterministic expected-count block for large finite-key design sweeps.

    Counts are rounded expectations rather than a Monte Carlo realization. Use
    simulate_decoy_bb84_block when sampling fluctuations themselves matter.
    """
    if pulses <= 0:
        raise ValueError("pulses must be positive")
    validate_intensities(intensities)
    basis.validate()
    channel.validate()
    detector.validate()
    attack = attack or AttackProfile()
    attack.validate()

    effective_channel = attacked_channel(channel, attack)
    effective_detector = attacked_detector(detector, attack)
    records: dict[tuple[str, str], CountRecord] = {}
    basis_probability = {
        "X": basis.p_x_alice * basis.p_x_bob,
        "Z": (1.0 - basis.p_x_alice) * (1.0 - basis.p_x_bob),
    }

    for setting in intensities:
        actual_mu = setting.mu * attack.source_intensity_scale
        gain = coherent_gain(actual_mu, effective_channel, effective_detector)
        base_qber = coherent_qber(actual_mu, effective_channel, effective_detector)
        intercept_qber = 0.25 * attack.intercept_resend_fraction
        for basis_name in ("X", "Z"):
            sent = int(round(pulses * setting.probability * basis_probability[basis_name]))
            detected = min(sent, int(round(sent * gain)))
            qber = combine_independent_bit_error(base_qber, intercept_qber)
            if basis_name == "Z":
                qber = combine_independent_bit_error(qber, min(0.5, attack.z_basis_error_addition))
            errors = min(detected, int(round(detected * min(0.5, qber))))
            records[(basis_name, setting.name)] = CountRecord(sent, detected, errors)

    return DecoyBB84Block(
        pulses=pulses,
        records=records,
        intensities=intensities,
        basis=basis,
        channel=channel,
        detector=detector,
        attack=attack,
    )