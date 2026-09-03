from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from qkd_lab.adaptive.actions import QKDAction, action_is_feasible
from qkd_lab.estimation.finite_key_bb84 import estimate_lim2014
from qkd_lab.estimation.finite_key_mdi import MDIFiniteKeyBudget, estimate_mdi_finite_key
from qkd_lab.models import BasisProbabilities, ChannelParameters, DetectorParameters, IntensitySetting
from qkd_lab.protocols.decoy_bb84 import expected_decoy_bb84_block
from qkd_lab.protocols.mdi_qkd import MDIBasisProbabilities, MDIPhysicalParameters, expected_mdi_block


EPS_SEC = 1.0e-10
EPS_COR = 1.0e-15
PULSE_RATE_HZ = 1.0e9
MDI_BUDGET = MDIFiniteKeyBudget(
    failure_probability=1.0e-10,
    eps_cor=1.0e-15,
    eps_prime=1.0e-12,
    eps_hat=1.0e-12,
    eps_e=1.0e-12,
    eps_b=1.0e-12,
    eps_0=1.0e-12,
    eps_1=1.0e-12,
    eps_pa=1.0e-12,
)


def _intensities(action: QKDAction) -> tuple[IntensitySetting, ...]:
    return (
        IntensitySetting("signal", action.mu_signal, 0.80),
        IntensitySetting("decoy", action.mu_decoy, 0.15),
        IntensitySetting("vacuum", 0.0002, 0.05),
    )


def evaluate_action_outcome(scenario: dict, action: QKDAction) -> dict:
    """Evaluate a candidate from observable/calibrated scenario quantities.

    This is a deterministic expected-count finite-key evaluation. It does not
    use hidden attack strength, hidden photon numbers, or future measurements.
    """
    feasible = action_is_feasible(action, mdi_capable=bool(scenario["mdi_capable"]))
    if not feasible:
        return {
            "feasible": False,
            "secure_bits": 0.0,
            "abort": True,
            "block_seconds": action.block_size / PULSE_RATE_HZ,
            "demand_bits": 0.0,
            "delivered_bits": 0.0,
            "key_deficit_bits": 0.0,
            "service_utility": -1.0e30,
        }

    distance = float(scenario["distance_km"])
    qber_estimate = min(0.10, max(0.0, float(scenario["recent_qber"])))
    dark = float(scenario["dark_probability"])
    efficiency = float(scenario["detector_efficiency"])
    action_intensities = _intensities(action)

    if action.protocol == "decoy_bb84":
        basis = BasisProbabilities(action.p_key_basis, action.p_key_basis)
        channel = ChannelParameters(distance, 0.20)
        detector = DetectorParameters(efficiency, dark, qber_estimate, 2)
        block = expected_decoy_bb84_block(
            action.block_size,
            intensities=action_intensities,
            basis=basis,
            channel=channel,
            detector=detector,
        )
        result = estimate_lim2014(
            block.records,
            action_intensities,
            eps_sec=EPS_SEC,
            eps_cor=EPS_COR,
        )
        secure_bits = float(result.secure_bits)
        abort = bool(result.abort)
    else:
        basis = MDIBasisProbabilities(action.p_key_basis, action.p_key_basis)
        physical = MDIPhysicalParameters(
            alice_to_charlie_km=distance / 2.0,
            bob_to_charlie_km=distance / 2.0,
            attenuation_db_per_km=0.20,
            detector_efficiency=efficiency,
            dark_probability=dark,
            misalignment=qber_estimate,
        )
        block = expected_mdi_block(
            action.block_size,
            alice_intensities=action_intensities,
            bob_intensities=action_intensities,
            basis=basis,
            physical=physical,
        )
        result = estimate_mdi_finite_key(block, MDI_BUDGET)
        secure_bits = float(result.secure_bits)
        abort = bool(result.abort)

    if abort:
        secure_bits = 0.0

    block_seconds = action.block_size / PULSE_RATE_HZ
    demand_bits = float(scenario["demand_bps"]) * block_seconds
    available_after_generation = float(scenario["key_pool_bits"]) + secure_bits
    delivered = min(demand_bits, available_after_generation)
    deficit = max(0.0, demand_bits - delivered)

    # Security is already a hard gate above. This utility only ranks secure,
    # physically feasible candidates by service value and generation delay.
    utility = delivered - 2.0 * deficit - 100.0 * block_seconds
    if abort:
        utility -= 1.0e9

    return {
        "feasible": True,
        "secure_bits": secure_bits,
        "abort": abort,
        "block_seconds": block_seconds,
        "demand_bits": demand_bits,
        "delivered_bits": delivered,
        "key_deficit_bits": deficit,
        "service_utility": utility,
    }


def build_policy_frame(scenarios: list[dict], actions: list[QKDAction]) -> pd.DataFrame:
    rows = []
    for scenario in scenarios:
        for action in actions:
            outcome = evaluate_action_outcome(scenario, action)
            rows.append({**scenario, **asdict(action), "action_name": action.name, **outcome})
    return pd.DataFrame(rows)