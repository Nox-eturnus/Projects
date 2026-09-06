from __future__ import annotations

import math
from typing import Any

import numpy as np

from qkd_lab.adaptive.actions import QKDAction, parse_action_name
from qkd_lab.adaptive.dataset import (
    EPS_COR,
    EPS_SEC,
    MDI_BUDGET,
    _intensities,
    evaluate_action_outcome,
)
from qkd_lab.adaptive.utility import compute_service_utility
from qkd_lab.estimation.finite_key_bb84 import estimate_lim2014
from qkd_lab.estimation.finite_key_mdi import estimate_mdi_finite_key
from qkd_lab.models import (
    BasisProbabilities,
    ChannelParameters,
    DetectorParameters,
)
from qkd_lab.protocols.decoy_bb84 import (
    expected_decoy_bb84_block,
    simulate_aggregate_decoy_bb84_block,
)
from qkd_lab.protocols.mdi_qkd import (
    MDIBasisProbabilities,
    MDIPhysicalParameters,
    expected_mdi_block,
    simulate_aggregate_mdi_block,
)


def execute_action_through_gate(
    action_name: str | QKDAction,
    context: dict[str, Any],
    *,
    key_pool: float = 0.0,
    prev_action: str | None = None,
    switching_penalty: float = 50.0,
    seed: int | None = None,
    latency_weight: float = 0.05,
    deficit_weight: float = 2.0,
    abort_penalty: float = 1000.0,
    max_key_pool: float = 15_000_000.0,
) -> dict[str, Any]:
    """Execute a candidate action through a conservative predictive gate and physical realization.

    Causal architecture:
      pre-decision telemetry counts
      ↓
      policy recommendation
      ↓
      conservative predictive security gate
      ↓
      chosen action / ABORT standby
      ↓
      physical block simulation & finite-key estimation
      ↓
      realized secure bits / ABORT
      ↓
      security-violation audit & closed-loop pool update
    """
    demand_bps = float(context["demand_bps"])
    epoch_sec = 10.0

    if isinstance(action_name, QKDAction):
        action: QKDAction | None = action_name
        action_str = action.name
    elif action_name == "ABORT" or not action_name:
        action = None
        action_str = "ABORT"
    else:
        action = parse_action_name(str(action_name))
        action_str = str(action_name)

    # Standby candidate: ABORT or unparseable action
    if action is None or action_str == "ABORT":
        demand_bits = demand_bps * epoch_sec
        delivered_bits = min(demand_bits, key_pool)
        deficit_bits = max(0.0, demand_bits - delivered_bits)
        # Switching into ABORT incurs zero switching penalty
        switch_cost = 0.0
        utility = compute_service_utility(
            delivered_bits=delivered_bits,
            deficit_bits=deficit_bits,
            duration_seconds=epoch_sec,
            abort=False,
            switch_cost=switch_cost,
            latency_weight=0.0,
            deficit_weight=deficit_weight,
            abort_penalty=abort_penalty,
        )
        next_pool = max(0.0, key_pool - delivered_bits)
        return {
            "action": action_str,
            "executed": "ABORT",
            "utility": utility,
            "secure_bits": 0.0,
            "duration_seconds": epoch_sec,
            "predictive_gate_miss": False,
            "security_violation": False,
            "violation": False,
            "next_key_pool": next_pool,
            "realized_abort": True,
            "demand_bits": demand_bits,
            "delivered_bits": delivered_bits,
            "deficit_bits": deficit_bits,
            "switch_cost": switch_cost,
        }

    # Step 1: Pre-execution conservative predictive gate (uses observable telemetry bounds)
    predicted = evaluate_action_outcome(context, action)
    if (not bool(predicted["feasible"])) or bool(predicted["abort"]):
        # Conservative gate intervenes to safely abort an unsafe/infeasible action
        demand_bits = demand_bps * epoch_sec
        delivered_bits = min(demand_bits, key_pool)
        deficit_bits = max(0.0, demand_bits - delivered_bits)
        switch_cost = 0.0
        utility = compute_service_utility(
            delivered_bits=delivered_bits,
            deficit_bits=deficit_bits,
            duration_seconds=epoch_sec,
            abort=False,
            switch_cost=switch_cost,
            latency_weight=0.0,
            deficit_weight=deficit_weight,
            abort_penalty=abort_penalty,
        )
        next_pool = max(0.0, key_pool - delivered_bits)
        return {
            "action": action_str,
            "executed": "ABORT",
            "utility": utility,
            "secure_bits": 0.0,
            "duration_seconds": epoch_sec,
            "predictive_gate_miss": False,
            "security_violation": False,
            "violation": False,
            "next_key_pool": next_pool,
            "realized_abort": True,
            "demand_bits": demand_bits,
            "delivered_bits": delivered_bits,
            "deficit_bits": deficit_bits,
            "switch_cost": switch_cost,
        }

    # Step 2: Physical block realization & finite-key estimation
    dist = float(context["distance_km"])
    dark = float(context["dark_probability"])
    eff = float(context["detector_efficiency"])
    actual_qber = float(context["recent_qber"])
    actual_gain = float(context.get("recent_gain", 0.01))

    if seed is not None:
        rng = np.random.default_rng(seed)
        fluc_qber = max(0.005, min(0.15, actual_qber + float(rng.normal(0.0, 0.001))))
        fluc_gain = max(1e-7, actual_gain * float(1.0 + rng.normal(0.0, 0.02)))
    else:
        fluc_qber = actual_qber
        fluc_gain = actual_gain

    action_intensities = _intensities(action)
    block_sec = action.duration_seconds

    if action.protocol == "decoy_bb84":
        basis = BasisProbabilities(action.p_key_basis, action.p_key_basis)
        net_opt = max(1e-9, fluc_gain - 2.0 * dark)
        trans = max(1e-8, min(1.0, net_opt / max(eff * action.mu_signal, 1e-6)))
        atten = max(0.15, min(2.0, -10.0 * math.log10(trans) / dist)) if dist > 0 else 0.20
        ch = ChannelParameters(dist, atten)
        det = DetectorParameters(eff, dark, fluc_qber, 2)
        if seed is not None:
            sim_block = simulate_aggregate_decoy_bb84_block(
                action.block_size,
                intensities=action_intensities,
                basis=basis,
                channel=ch,
                detector=det,
                seed=seed,
            )
        else:
            sim_block = expected_decoy_bb84_block(
                action.block_size,
                intensities=action_intensities,
                basis=basis,
                channel=ch,
                detector=det,
            )
        res = estimate_lim2014(
            sim_block.records,
            action_intensities,
            eps_sec=EPS_SEC,
            eps_cor=EPS_COR,
            f_ec=1.16,
        )
        realized_bits = float(res.secure_bits)
        realized_abort = bool(res.abort)
    else:
        basis = MDIBasisProbabilities(action.p_key_basis, action.p_key_basis)
        lac = float(context.get("length_ac_km", dist / 2.0))
        lbc = float(context.get("length_bc_km", dist / 2.0))
        net_opt = max(1e-9, fluc_gain - 2.0 * dark)
        trans = max(1e-8, min(1.0, net_opt / max(eff * action.mu_signal, 1e-6)))
        atten = max(0.15, min(2.0, -10.0 * math.log10(trans) / dist)) if dist > 0 else 0.20
        phys = MDIPhysicalParameters(
            alice_to_charlie_km=lac,
            bob_to_charlie_km=lbc,
            attenuation_db_per_km=atten,
            detector_efficiency=eff,
            dark_probability=dark,
            misalignment=fluc_qber,
        )
        if seed is not None:
            sim_block = simulate_aggregate_mdi_block(
                action.block_size,
                alice_intensities=action_intensities,
                bob_intensities=action_intensities,
                basis=basis,
                physical=phys,
                seed=seed,
            )
        else:
            sim_block = expected_mdi_block(
                action.block_size,
                alice_intensities=action_intensities,
                bob_intensities=action_intensities,
                basis=basis,
                physical=phys,
            )
        res = estimate_mdi_finite_key(sim_block, MDI_BUDGET)
        realized_bits = float(res.secure_bits)
        realized_abort = bool(res.abort)

    # Step 3: Predictive Gate Miss vs Security Violation Audit
    predictive_gate_miss = bool(realized_abort) or (realized_bits <= 0.0)
    generated_bits = realized_bits if not realized_abort else 0.0
    # Security violation: Key material released on an abort
    security_violation = bool(generated_bits > 0.0 and realized_abort)

    # Step 4: Closed-loop utility and state evolution
    demand_bits = demand_bps * block_sec
    available_bits = key_pool + generated_bits
    delivered_bits = min(demand_bits, available_bits)
    deficit_bits = max(0.0, demand_bits - delivered_bits)
    switch_cost = (
        switching_penalty
        if (prev_action is not None and prev_action != action_str and action_str != "ABORT")
        else 0.0
    )

    util = compute_service_utility(
        delivered_bits=delivered_bits,
        deficit_bits=deficit_bits,
        duration_seconds=block_sec,
        abort=realized_abort,
        switch_cost=switch_cost,
        latency_weight=latency_weight,
        deficit_weight=deficit_weight,
        abort_penalty=abort_penalty,
    )

    next_pool = min(max_key_pool, max(0.0, available_bits - delivered_bits))

    return {
        "action": action_str,
        "executed": action_str,
        "utility": util,
        "secure_bits": generated_bits,
        "duration_seconds": block_sec,
        "predictive_gate_miss": predictive_gate_miss,
        "security_violation": security_violation,
        "violation": predictive_gate_miss,
        "next_key_pool": next_pool,
        "realized_abort": realized_abort,
        "demand_bits": demand_bits,
        "delivered_bits": delivered_bits,
        "deficit_bits": deficit_bits,
        "switch_cost": switch_cost,
    }
