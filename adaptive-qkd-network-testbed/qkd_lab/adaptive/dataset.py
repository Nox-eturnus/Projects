import math
from dataclasses import asdict

import pandas as pd

from qkd_lab.adaptive.actions import QKDAction, action_is_feasible
from qkd_lab.estimation.confidence import conservative_telemetry_bounds
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
    recent_qber = float(scenario["recent_qber"])
    recent_gain = float(scenario.get("recent_gain", 0.01))
    observed_err = int(scenario["observed_errors"]) if "observed_errors" in scenario else None
    detected_cnt = int(scenario["detected_counts"]) if "detected_counts" in scenario else None
    sent_pulses = int(scenario["sent_pulses"]) if "sent_pulses" in scenario else None
    qber_estimate, gain_estimate = conservative_telemetry_bounds(
        recent_qber,
        recent_gain,
        observed_errors=observed_err,
        detected_counts=detected_cnt,
        sent_pulses=sent_pulses,
    )

    dark = float(scenario["dark_probability"])
    efficiency = float(scenario["detector_efficiency"])
    action_intensities = _intensities(action)

    # Derive effective channel attenuation from conservative gain bound
    mu_sig = action.mu_signal
    if distance > 0.0 and mu_sig > 0.0:
        net_opt_gain = max(1e-9, gain_estimate - 2.0 * dark)
        transmittance_est = max(1e-8, min(1.0, net_opt_gain / max(efficiency * mu_sig, 1e-6)))
        atten_db_km = max(0.15, min(2.0, -10.0 * math.log10(transmittance_est) / distance))
    else:
        atten_db_km = 0.20

    if action.protocol == "decoy_bb84":
        basis = BasisProbabilities(action.p_key_basis, action.p_key_basis)
        channel = ChannelParameters(distance, atten_db_km)
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
            f_ec=1.16,
        )
        secure_bits = float(result.secure_bits)
        abort = bool(result.abort)
    else:
        basis = MDIBasisProbabilities(action.p_key_basis, action.p_key_basis)
        lac = float(scenario.get("length_ac_km", distance / 2.0))
        lbc = float(scenario.get("length_bc_km", distance / 2.0))
        physical = MDIPhysicalParameters(
            alice_to_charlie_km=lac,
            bob_to_charlie_km=lbc,
            attenuation_db_per_km=atten_db_km,
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

    # Time-normalized utility (Finding 14):
    # Evaluates service rate performance (bps) and generation latency penalty
    # so that 100s actions do not artificially earn 10x more utility than 10s actions.
    delivered_rate_bps = delivered / block_seconds
    deficit_rate_bps = deficit / block_seconds
    latency_penalty = 10.0 * block_seconds

    utility = delivered_rate_bps - 2.0 * deficit_rate_bps - latency_penalty
    if abort:
        utility -= 1.0e6

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