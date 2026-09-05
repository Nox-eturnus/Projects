from __future__ import annotations

import base64
import json
import pickle
from pathlib import Path

from qkd_lab.adaptive.actions import parse_action_name
from qkd_lab.adaptive.dataset import _intensities, evaluate_action_outcome
from qkd_lab.applications.otp import (
    decrypt_authenticated_otp,
    encrypt_authenticated_otp,
)
from qkd_lab.estimation.finite_key_bb84 import estimate_lim2014
from qkd_lab.kms.store import KeyStore
from qkd_lab.models import BasisProbabilities, ChannelParameters, DetectorParameters
from qkd_lab.network.qos import QKDNQoSRequest
from qkd_lab.network.simulator import request_end_to_end_key
from qkd_lab.network.topology import QKDLinkState, build_graph
from qkd_lab.protocols.decoy_bb84 import simulate_aggregate_decoy_bb84_block


def run_closed_loop_pipeline() -> dict:
    """Execute the complete end-to-end QKD -> KMS -> Network -> Application pipeline."""
    audit_trail: dict[str, object] = {
        "status": "in_progress",
        "stages": {},
    }

    # -------------------------------------------------------------------------
    # Stage 1: KMS & Unified Reserve Network Topology Initialization
    # -------------------------------------------------------------------------
    kms_nodes = {node: KeyStore() for node in ("A", "B", "C", "D")}

    # Initial link reserves
    link_ab = QKDLinkState("A", "B", distance_km=25.0, key_bits=5000, secure_rate_bps=2000, key_store=kms_nodes["A"])
    link_bd = QKDLinkState("B", "D", distance_km=25.0, key_bits=5000, secure_rate_bps=2000, key_store=kms_nodes["B"])
    link_ac = QKDLinkState("A", "C", distance_km=40.0, key_bits=2000, secure_rate_bps=1000, key_store=kms_nodes["A"])
    link_cd = QKDLinkState("C", "D", distance_km=40.0, key_bits=2000, secure_rate_bps=1000, key_store=kms_nodes["C"])

    graph = build_graph([link_ab, link_bd, link_ac, link_cd])
    audit_trail["stages"]["topology_init"] = {
        "nodes": list(kms_nodes.keys()),
        "links": [f"{l.u}-{l.v}" for l in (link_ab, link_bd, link_ac, link_cd)],
        "initial_link_ab_bits": link_ab.key_bits,
    }

    # -------------------------------------------------------------------------
    # Stage 2: Telemetry Observation & Adaptive Policy Recommendation
    # -------------------------------------------------------------------------
    recent_qber = 0.015
    det_eff = 0.55
    channel_trans = 10.0 ** (-0.20 * link_ab.distance_km / 10.0)
    recent_gain = det_eff * 0.40 * channel_trans
    sent_pulses = 100_000
    detected_cnt = int(round(recent_gain * sent_pulses))
    observed_err = int(round(recent_qber * detected_cnt))

    telemetry = {
        "scenario_id": 9999,
        "trajectory_id": 999,
        "time_step": 0,
        "distance_km": link_ab.distance_km,
        "recent_qber": recent_qber,
        "recent_gain": recent_gain,
        "observed_errors": observed_err,
        "detected_counts": detected_cnt,
        "sent_pulses": sent_pulses,
        "dark_probability": 1e-7,
        "detector_efficiency": det_eff,
        "key_pool_bits": float(link_ab.key_bits),
        "demand_bps": 5000.0,
        "mdi_capable": False,
        "charlie_node": None,
    }

    policy_path = Path("results/adaptive/policy.pkl")
    if policy_path.exists():
        with open(policy_path, "rb") as f:
            policy = pickle.load(f)
        recommended_action_name = policy.select(telemetry)
    else:
        recommended_action_name = "decoy_bb84|mu=0.55|nu=0.10|p=0.90|N=10000000000"

    action = parse_action_name(recommended_action_name)
    if action is None:
        raise RuntimeError(f"Policy recommended non-executable action: {recommended_action_name}")

    audit_trail["stages"]["policy_recommendation"] = {
        "telemetry_qber": telemetry["recent_qber"],
        "telemetry_distance_km": telemetry["distance_km"],
        "recommended_action": recommended_action_name,
    }

    # -------------------------------------------------------------------------
    # Stage 3: Conservative Pre-Execution Predictive Security Gate
    # -------------------------------------------------------------------------
    gate_eval = evaluate_action_outcome(telemetry, action)
    if not gate_eval["feasible"] or gate_eval["abort"]:
        raise RuntimeError("Predictive security gate rejected the action!")

    audit_trail["stages"]["predictive_gate"] = {
        "feasible": gate_eval["feasible"],
        "predicted_abort": gate_eval["abort"],
        "predicted_secure_bits": gate_eval["secure_bits"],
    }

    # -------------------------------------------------------------------------
    # Stage 4: Stochastic Physical QKD Execution & Finite-Key Distillation
    # -------------------------------------------------------------------------
    action_intensities = _intensities(action)
    ch = ChannelParameters(link_ab.distance_km, 0.20)
    det = DetectorParameters(telemetry["detector_efficiency"], telemetry["dark_probability"], telemetry["recent_qber"], 2)
    basis = BasisProbabilities(action.p_key_basis, action.p_key_basis)

    sim_block = simulate_aggregate_decoy_bb84_block(
        action.block_size,
        intensities=action_intensities,
        basis=basis,
        channel=ch,
        detector=det,
        seed=12345,
    )

    fk_result = estimate_lim2014(
        sim_block.records,
        action_intensities,
        eps_sec=1e-10,
        eps_cor=1e-15,
        f_ec=1.16,
    )
    if fk_result.abort or fk_result.secure_bits <= 0:
        raise RuntimeError("Physical distillation aborted unexpectedly under benign parameters!")

    distilled_bits = int(fk_result.secure_bits)
    audit_trail["stages"]["physical_qkd_distillation"] = {
        "protocol": "decoy_bb84",
        "pulses": action.block_size,
        "distilled_bits": distilled_bits,
        "phase_error_upper": fk_result.phase_error_upper,
        "abort": fk_result.abort,
    }

    # -------------------------------------------------------------------------
    # Stage 5: Deposit Distilled Bits into KMS KeyReservoir
    # -------------------------------------------------------------------------
    storable_bits = (distilled_bits // 8) * 8
    # Deposit directly through link_ab property to test ledger synchronization
    link_ab.key_bits += storable_bits

    assert kms_nodes["A"].available_bits(peer_id="B") == 5000 + storable_bits, "KMS and Link reserve desynchronized!"
    audit_trail["stages"]["kms_deposit"] = {
        "storable_bits": storable_bits,
        "new_link_ab_bits": link_ab.key_bits,
        "kms_a_available_bits": kms_nodes["A"].available_bits(peer_id="B"),
    }

    # -------------------------------------------------------------------------
    # Stage 6: Multi-Hop QoS Routing & Secure Path Key Allocation
    # -------------------------------------------------------------------------
    qos_req = QKDNQoSRequest(
        source="A",
        target="D",
        key_bits=512,
        max_hops=3,
        service_priority=1,
        reserve_threshold_bits=1000,
    )
    service_res = request_end_to_end_key(graph, "A", "D", bits=512, qos=qos_req)
    assert service_res.success, f"Multi-hop QoS routing failed: {service_res.message}"

    audit_trail["stages"]["network_routing"] = {
        "success": service_res.success,
        "path": list(service_res.path),
        "hops": service_res.hops,
        "eps_total": service_res.eps_total,
        "consumed_per_hop": service_res.key_bits_consumed_per_hop,
    }

    # -------------------------------------------------------------------------
    # Stage 7: Application Information-Theoretic Authenticated OTP
    # -------------------------------------------------------------------------
    secret_message = b"CRITICAL MISSION TELEMETRY: ALL QUANTUM SUBSYSTEMS NOMINAL"
    pt_len = len(secret_message)
    pt_bits = pt_len * 8

    # Node A slices exact-length OTP key and 256-bit auth key from its KMS store
    otp_item = kms_nodes["A"].consume(peer_id="B", number=1, bits=pt_bits, initiator_sae_id="A")[0]
    auth_item = kms_nodes["A"].consume(peer_id="B", number=1, bits=256, initiator_sae_id="A")[0]
    otp_key = base64.b64decode(otp_item.value_b64)
    auth_key = base64.b64decode(auth_item.value_b64)

    cipher, tag = encrypt_authenticated_otp(secret_message, otp_key, auth_key, mode="it")

    # Receiver verifies and decrypts
    decrypted = decrypt_authenticated_otp(cipher, tag, otp_key, auth_key, mode="it")
    assert decrypted == secret_message, "Decrypted message mismatch!"

    # Tamper test
    tampered_cipher = bytearray(cipher)
    tampered_cipher[0] ^= 0xFF
    tamper_caught = False
    try:
        decrypt_authenticated_otp(bytes(tampered_cipher), tag, otp_key, auth_key, mode="it")
    except ValueError:
        tamper_caught = True

    assert tamper_caught, "Tampered ciphertext was not caught by IT authenticator!"

    audit_trail["stages"]["application_otp"] = {
        "message_length_bytes": len(secret_message),
        "encryption_mode": "IT-Authenticated-OTP",
        "decryption_verified": True,
        "tamper_protection_verified": True,
        "keys_consumed": [otp_item.key_id, auth_item.key_id],
    }

    # -------------------------------------------------------------------------
    # Final Validation & Provenance
    # -------------------------------------------------------------------------
    audit_trail["status"] = "PASSED"
    audit_trail["security_violations"] = 0
    audit_trail["predictive_gate_misses"] = 0

    out_file = Path("results/network/end_to_end_closed_loop.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(audit_trail, indent=2), encoding="utf-8")

    return audit_trail


def main():
    print("Executing complete end-to-end closed-loop pipeline...")
    result = run_closed_loop_pipeline()
    print(json.dumps(result, indent=2))
    print("\nEnd-to-end closed loop test PASSED successfully!")


if __name__ == "__main__":
    main()
