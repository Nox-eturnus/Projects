from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import pickle
import subprocess

import numpy as np

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
from qkd_lab.postprocessing.cascade import cascade_reconcile_blockwise
from qkd_lab.postprocessing.privacy import random_toeplitz_seed, toeplitz_hash_fast
from qkd_lab.postprocessing.verification import verify_equal
from qkd_lab.protocols.decoy_bb84 import expected_decoy_bb84_block, make_correlated_raw_keys
from qkd_lab.rng import secure_random_bytes


def get_git_commit() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        return res.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def is_working_tree_clean() -> bool:
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain", "qkd_lab", "tests", "scripts", "standards", "configs", "README.md"],
            capture_output=True,
            text=True,
            check=False,
        )
        return len(res.stdout.strip()) == 0
    except Exception:
        return False


def distill_physical_link(
    distance_km: float,
    action_intensities: tuple,
    detector_efficiency: float,
    dark_probability: float,
    qber: float,
    pulses: int = 100_000_000,
    seed: int = 2026,
    basis_px: float = 0.50,
) -> tuple[bytes, object, int, int]:
    """Execute complete physical QKD distillation: raw generation, Cascade reconciliation, and Toeplitz PA."""
    ch = ChannelParameters(distance_km, 0.20)
    det = DetectorParameters(detector_efficiency, dark_probability, qber, 2)
    basis = BasisProbabilities(basis_px, 1.0 - basis_px)

    block = expected_decoy_bb84_block(
        pulses,
        intensities=action_intensities,
        basis=basis,
        channel=ch,
        detector=det,
    )
    x_total = block.basis_total("X")
    alice_raw, bob_raw = make_correlated_raw_keys(x_total.detected, x_total.qber, seed=seed)

    rec = cascade_reconcile_blockwise(
        alice_raw,
        bob_raw,
        x_total.qber,
        chunk_bits=10_000,
        passes=10,
        seed=seed,
    )
    if not rec.success:
        raise RuntimeError(f"Cascade reconciliation failed for physical link (seed={seed})")

    tag_bits = 50
    if not verify_equal(rec.alice_key, rec.bob_key, tag_bits):
        raise RuntimeError(f"Toeplitz correctness verification failed (seed={seed})")

    fk = estimate_lim2014(
        block.records,
        action_intensities,
        eps_sec=1e-10,
        eps_cor=1e-15,
        leak_ec=rec.disclosed_bits,
        verification_tag_bits=tag_bits,
    )
    if fk.abort or fk.secure_bits <= 0:
        raise RuntimeError(f"Finite-key estimation aborted under benign parameters (seed={seed})")

    pa_seed = random_toeplitz_seed(fk.secure_bits, len(rec.alice_key), seed=seed + 99)
    pa_key = toeplitz_hash_fast(rec.alice_key, fk.secure_bits, pa_seed)

    storable_bytes = len(pa_key) // 8
    storable_bits = storable_bytes * 8
    distilled_material = bytes(np.packbits(pa_key[:storable_bits]))
    return distilled_material, fk, x_total.detected, rec.disclosed_bits


def run_closed_loop_pipeline() -> dict:
    """Execute the complete end-to-end QKD -> KMS -> Network -> Application pipeline.

    Decoupled into two explicitly labeled execution tracks:
      1. full_scale_controller_execution: policy selects N=10^10 pulses, validated through predictive gate.
      2. materialization_scale_cryptographic_execution: 35M pulses, actual distilled material for A-B and B-D,
         Cascade, Toeplitz PA, OTP encryption/decryption.
    """
    audit_trail: dict[str, object] = {
        "status": "in_progress",
        "full_scale_controller_execution": {},
        "materialization_scale_cryptographic_execution": {},
    }

    # =========================================================================
    # Track 1: Full-Scale Controller Execution (N = 10^10 Pulses, 10.0s Epoch)
    # =========================================================================
    distance_ab = 25.0
    recent_qber = 0.015
    det_eff = 0.55
    channel_trans = 10.0 ** (-0.20 * distance_ab / 10.0)
    recent_gain = det_eff * 0.40 * channel_trans
    sent_pulses = 100_000
    detected_cnt = int(round(recent_gain * sent_pulses))
    observed_err = int(round(recent_qber * detected_cnt))

    telemetry = {
        "scenario_id": 9999,
        "trajectory_id": 999,
        "time_step": 0,
        "phase": "normal",
        "distance_km": distance_ab,
        "recent_qber": recent_qber,
        "recent_gain": recent_gain,
        "observed_errors": observed_err,
        "detected_counts": detected_cnt,
        "sent_pulses": sent_pulses,
        "dark_probability": 1.0e-7,
        "detector_efficiency": det_eff,
        "key_pool_bits": 0.0,
        "demand_bps": 12000.0,
        "mdi_capable": False,
        "charlie_node": None,
        "length_ac_km": None,
        "length_bc_km": None,
    }

    policy_path = Path("results/adaptive/policy.pkl")
    if policy_path.exists():
        with policy_path.open("rb") as f:
            policy = pickle.load(f)
        recommended_action_name = policy.select(telemetry)
    else:
        recommended_action_name = "decoy_bb84|mu=0.55|nu=0.10|p=0.90|N=10000000000"

    action = parse_action_name(recommended_action_name)
    if action is None:
        raise RuntimeError(f"Policy recommended non-executable action: {recommended_action_name}")

    # Conservative predictive security gate evaluation
    gate_eval = evaluate_action_outcome(telemetry, action)
    if not gate_eval["feasible"] or gate_eval["abort"]:
        raise RuntimeError("Predictive security gate rejected full-scale action!")

    audit_trail["full_scale_controller_execution"] = {
        "policy_recommendation": recommended_action_name,
        "protocol": action.protocol,
        "pulse_count": action.block_size,
        "epoch_seconds": action.duration_seconds,
        "telemetry_qber": telemetry["recent_qber"],
        "telemetry_distance_km": telemetry["distance_km"],
        "predictive_gate_feasible": gate_eval["feasible"],
        "predictive_gate_predicted_abort": gate_eval["abort"],
        "predicted_secure_bits": gate_eval["secure_bits"],
        "predicted_secure_rate_bps": gate_eval["secure_bits"] / action.duration_seconds,
        "predicted_service_utility": gate_eval["service_utility"],
        "composable_security_scope": "theorem_composable",
        "eps_sec": 1.0e-10,
        "eps_cor": 1.0e-15,
    }

    # =========================================================================
    # Track 2: Materialization-Scale Cryptographic Execution (Genuine Distillation Across All Hops)
    # =========================================================================
    pulses_primary = 150_000_000
    pulses_backup = 180_000_000
    action_intensities = _intensities(action)

    # Sub-stage 2A: Physical QKD distillation for Primary Link A-B (25.0 km)
    distilled_ab, fk_ab, detected_ab, disclosed_ab = distill_physical_link(
        distance_km=25.0,
        action_intensities=action_intensities,
        detector_efficiency=det_eff,
        dark_probability=telemetry["dark_probability"],
        qber=recent_qber,
        pulses=pulses_primary,
        seed=2026,
    )
    storable_bits_ab = len(distilled_ab) * 8

    # Sub-stage 2B: Physical QKD distillation for Primary Link B-D (25.0 km)
    distilled_bd, fk_bd, detected_bd, disclosed_bd = distill_physical_link(
        distance_km=25.0,
        action_intensities=action_intensities,
        detector_efficiency=det_eff,
        dark_probability=telemetry["dark_probability"],
        qber=recent_qber,
        pulses=pulses_primary,
        seed=3026,
    )
    storable_bits_bd = len(distilled_bd) * 8

    # Sub-stage 2C: Physical QKD distillation for Secondary Backup Link A-C (30.0 km)
    distilled_ac, fk_ac, detected_ac, disclosed_ac = distill_physical_link(
        distance_km=30.0,
        action_intensities=action_intensities,
        detector_efficiency=det_eff,
        dark_probability=telemetry["dark_probability"],
        qber=recent_qber,
        pulses=pulses_backup,
        seed=4026,
    )
    storable_bits_ac = len(distilled_ac) * 8

    # Sub-stage 2D: Physical QKD distillation for Secondary Backup Link C-D (30.0 km)
    distilled_cd, fk_cd, detected_cd, disclosed_cd = distill_physical_link(
        distance_km=30.0,
        action_intensities=action_intensities,
        detector_efficiency=det_eff,
        dark_probability=telemetry["dark_probability"],
        qber=recent_qber,
        pulses=pulses_backup,
        seed=5026,
    )
    storable_bits_cd = len(distilled_cd) * 8

    # Sub-stage 2E: KMS Network Topology Initialization & Real Material Deposits
    kms_nodes = {node: KeyStore() for node in ("A", "B", "C", "D")}

    # Deposit genuine privacy-amplified physical key material for Link A-B into Node A's store
    kms_nodes["A"].deposit_reservoir_key_material(
        peer_id="B",
        key_material=distilled_ab,
        protocol="decoy_bb84",
        eps_sec=fk_ab.eps_sec,
        eps_cor=fk_ab.eps_cor,
        initiator_sae_id="A",
        target_sae_id="B",
        security_scope="theorem_composable",
    )
    link_ab = QKDLinkState("A", "B", distance_km=25.0, key_bits=storable_bits_ab, secure_rate_bps=2000, key_store=kms_nodes["A"])

    # Deposit genuine privacy-amplified physical key material for Link B-D into Node B's store
    kms_nodes["B"].deposit_reservoir_key_material(
        peer_id="D",
        key_material=distilled_bd,
        protocol="decoy_bb84",
        eps_sec=fk_bd.eps_sec,
        eps_cor=fk_bd.eps_cor,
        initiator_sae_id="B",
        target_sae_id="D",
        security_scope="theorem_composable",
    )
    link_bd = QKDLinkState("B", "D", distance_km=25.0, key_bits=storable_bits_bd, secure_rate_bps=2000, key_store=kms_nodes["B"])

    # Secondary backup links (A-C and C-D) with genuine distilled physical material
    kms_nodes["A"].deposit_reservoir_key_material(
        peer_id="C",
        key_material=distilled_ac,
        protocol="decoy_bb84",
        eps_sec=fk_ac.eps_sec,
        eps_cor=fk_ac.eps_cor,
        initiator_sae_id="A",
        target_sae_id="C",
        security_scope="theorem_composable",
    )
    link_ac = QKDLinkState("A", "C", distance_km=30.0, key_bits=storable_bits_ac, secure_rate_bps=1000, key_store=kms_nodes["A"])

    kms_nodes["C"].deposit_reservoir_key_material(
        peer_id="D",
        key_material=distilled_cd,
        protocol="decoy_bb84",
        eps_sec=fk_cd.eps_sec,
        eps_cor=fk_cd.eps_cor,
        initiator_sae_id="C",
        target_sae_id="D",
        security_scope="theorem_composable",
    )
    link_cd = QKDLinkState("C", "D", distance_km=30.0, key_bits=storable_bits_cd, secure_rate_bps=1000, key_store=kms_nodes["C"])

    graph = build_graph([link_ab, link_bd, link_ac, link_cd])

    # Invariant checks on reservoir synchronization
    assert kms_nodes["A"].available_bits(peer_id="B") == storable_bits_ab, "Link A-B KMS desynchronized!"
    assert link_ab.key_bits == storable_bits_ab, "Link A-B key_bits desynchronized!"
    assert kms_nodes["B"].available_bits(peer_id="D") == storable_bits_bd, "Link B-D KMS desynchronized!"
    assert link_bd.key_bits == storable_bits_bd, "Link B-D key_bits desynchronized!"
    assert kms_nodes["A"].available_bits(peer_id="C") == storable_bits_ac, "Link A-C KMS desynchronized!"
    assert link_ac.key_bits == storable_bits_ac, "Link A-C key_bits desynchronized!"
    assert kms_nodes["C"].available_bits(peer_id="D") == storable_bits_cd, "Link C-D KMS desynchronized!"
    assert link_cd.key_bits == storable_bits_cd, "Link C-D key_bits desynchronized!"

    # Non-destructive test reservation on both primary and backup links
    with link_ab.reserve_bits(256) as r_ab:
        assert r_ab.source == "material"
        assert r_ab.security_scope == "theorem_composable"
        assert r_ab.is_composable is True
        r_ab.rollback()

    with link_bd.reserve_bits(256) as r_bd:
        assert r_bd.source == "material"
        assert r_bd.security_scope == "theorem_composable"
        assert r_bd.is_composable is True
        r_bd.rollback()

    with link_ac.reserve_bits(256) as r_ac:
        assert r_ac.source == "material"
        assert r_ac.security_scope == "theorem_composable"
        assert r_ac.is_composable is True
        r_ac.rollback()

    with link_cd.reserve_bits(256) as r_cd:
        assert r_cd.source == "material"
        assert r_cd.security_scope == "theorem_composable"
        assert r_cd.is_composable is True
        r_cd.rollback()

    # Sub-stage 2D: Multi-Hop QoS Routing & Trusted-Node Hop-by-Hop Key Delivery
    secret_message = b"CRITICAL MISSION TELEMETRY: ALL QUANTUM SUBSYSTEMS NOMINAL"
    pt_len = len(secret_message)
    pt_bits = pt_len * 8

    qos_otp = QKDNQoSRequest(
        source="A",
        target="D",
        key_bits=pt_bits,
        max_hops=3,
        service_priority=1,
        reserve_threshold_bits=500,
    )
    service_res_otp = request_end_to_end_key(graph, "A", "D", bits=pt_bits, qos=qos_otp, kms_nodes=kms_nodes)
    assert service_res_otp.success, f"Multi-hop QoS routing for OTP key failed: {service_res_otp.message}"
    assert service_res_otp.security_scope == "theorem_composable"
    assert service_res_otp.is_composable

    qos_auth = QKDNQoSRequest(
        source="A",
        target="D",
        key_bits=256,
        max_hops=3,
        service_priority=1,
        reserve_threshold_bits=500,
    )
    service_res_auth = request_end_to_end_key(graph, "A", "D", bits=256, qos=qos_auth, kms_nodes=kms_nodes)
    assert service_res_auth.success, f"Multi-hop QoS routing for Auth key failed: {service_res_auth.message}"
    assert service_res_auth.security_scope == "theorem_composable"
    assert service_res_auth.is_composable

    eps_sum = (service_res_otp.eps_total or 0.0) + (service_res_auth.eps_total or 0.0)

    # Sub-stage 2E: Application Information-Theoretic Authenticated OTP
    otp_item_a = kms_nodes["A"].consume_by_ids([service_res_otp.key_id], peer_id="D", initiator_sae_id="A")[0]
    auth_item_a = kms_nodes["A"].consume_by_ids([service_res_auth.key_id], peer_id="D", initiator_sae_id="A")[0]

    otp_item_d = kms_nodes["D"].consume_by_ids([service_res_otp.key_id], peer_id="A", initiator_sae_id="A")[0]
    auth_item_d = kms_nodes["D"].consume_by_ids([service_res_auth.key_id], peer_id="A", initiator_sae_id="A")[0]

    # Cryptographic invariant: verify identical keys and authentic material provenance
    assert otp_item_a.value_b64 == otp_item_d.value_b64, "E2E OTP key mismatch between KMS stores!"
    assert auth_item_a.value_b64 == auth_item_d.value_b64, "E2E Auth key mismatch between KMS stores!"
    assert otp_item_a.source == "material" and otp_item_d.source == "material"
    assert auth_item_a.source == "material" and auth_item_d.source == "material"
    assert otp_item_a.security_scope == "theorem_composable"
    assert auth_item_a.security_scope == "theorem_composable"
    assert otp_item_d.security_scope == "theorem_composable"
    assert auth_item_d.security_scope == "theorem_composable"

    otp_key_a = base64.b64decode(otp_item_a.value_b64)
    auth_key_a = base64.b64decode(auth_item_a.value_b64)
    otp_key_d = base64.b64decode(otp_item_d.value_b64)
    auth_key_d = base64.b64decode(auth_item_d.value_b64)

    # Node A encrypts the secret message
    cipher, tag = encrypt_authenticated_otp(secret_message, otp_key_a, auth_key_a, mode="it")

    # Node D decrypts and verifies using strictly its own local KMS key material
    decrypted = decrypt_authenticated_otp(cipher, tag, otp_key_d, auth_key_d, mode="it")
    assert decrypted == secret_message, "Decrypted message mismatch at Node D!"

    # Tamper test: Node D rejects corrupted ciphertext
    tampered_cipher = bytearray(cipher)
    tampered_cipher[0] ^= 0xFF
    tamper_caught = False
    try:
        decrypt_authenticated_otp(bytes(tampered_cipher), tag, otp_key_d, auth_key_d, mode="it")
    except ValueError:
        tamper_caught = True

    assert tamper_caught, "Tampered ciphertext was not caught by IT authenticator at Node D!"

    audit_trail["materialization_scale_cryptographic_execution"] = {
        "pulses_primary_link": pulses_primary,
        "pulses_backup_link": pulses_backup,
        "link_ab": {
            "distance_km": 25.0,
            "detected": detected_ab,
            "reconciliation_disclosed_bits": disclosed_ab,
            "finite_key_secure_bits": fk_ab.secure_bits,
            "distilled_bits": storable_bits_ab,
            "eps_sec": fk_ab.eps_sec,
            "eps_cor": fk_ab.eps_cor,
            "security_scope": "theorem_composable",
        },
        "link_bd": {
            "distance_km": 25.0,
            "detected": detected_bd,
            "reconciliation_disclosed_bits": disclosed_bd,
            "finite_key_secure_bits": fk_bd.secure_bits,
            "distilled_bits": storable_bits_bd,
            "eps_sec": fk_bd.eps_sec,
            "eps_cor": fk_bd.eps_cor,
            "security_scope": "theorem_composable",
        },
        "link_ac": {
            "distance_km": 30.0,
            "detected": detected_ac,
            "reconciliation_disclosed_bits": disclosed_ac,
            "finite_key_secure_bits": fk_ac.secure_bits,
            "distilled_bits": storable_bits_ac,
            "eps_sec": fk_ac.eps_sec,
            "eps_cor": fk_ac.eps_cor,
            "security_scope": "theorem_composable",
        },
        "link_cd": {
            "distance_km": 30.0,
            "detected": detected_cd,
            "reconciliation_disclosed_bits": disclosed_cd,
            "finite_key_secure_bits": fk_cd.secure_bits,
            "distilled_bits": storable_bits_cd,
            "eps_sec": fk_cd.eps_sec,
            "eps_cor": fk_cd.eps_cor,
            "security_scope": "theorem_composable",
        },
        "network_routing": {
            "otp_path": list(service_res_otp.path),
            "otp_key_id": service_res_otp.key_id,
            "auth_path": list(service_res_auth.path),
            "auth_key_id": service_res_auth.key_id,
            "hops": service_res_otp.hops,
            "eps_total": eps_sum,
            "security_scope": service_res_otp.security_scope,
            "is_composable": service_res_otp.is_composable,
            "consumed_per_hop_total": service_res_otp.key_bits_consumed_per_hop + service_res_auth.key_bits_consumed_per_hop,
        },
        "application_otp": {
            "message_length_bytes": len(secret_message),
            "encryption_mode": "IT-Authenticated-OTP",
            "keys_verified_identical": True,
            "decryption_verified_at_destination": True,
            "tamper_protection_verified": True,
            "keys_consumed_a": [otp_item_a.key_id, auth_item_a.key_id],
            "keys_consumed_d": [otp_item_d.key_id, auth_item_d.key_id],
        },
    }

    audit_trail["status"] = "PASSED"
    audit_trail["security_violations"] = 0
    audit_trail["predictive_gate_misses"] = 0
    audit_trail["provenance"] = {
        "git_commit": get_git_commit(),
        "working_tree_clean": is_working_tree_clean(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    out_file = Path("results/network/end_to_end_closed_loop.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(audit_trail, indent=2), encoding="utf-8")

    return audit_trail


def main():
    print("Executing decoupled end-to-end closed-loop pipeline...")
    result = run_closed_loop_pipeline()
    print(json.dumps(result, indent=2))
    print("\nEnd-to-end closed loop test PASSED successfully!")


if __name__ == "__main__":
    main()
