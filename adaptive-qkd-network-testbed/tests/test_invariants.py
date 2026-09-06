import base64
import pytest
import numpy as np
import pandas as pd

from qkd_lab.adaptive.features import ALLOWED_FEATURES, validate_feature_columns
from qkd_lab.applications.otp import (
    decrypt_authenticated_otp,
    encrypt_authenticated_otp,
)
from qkd_lab.kms.models import KeyState, ManagedKey, utcnow
from qkd_lab.kms.store import KeyStore
from qkd_lab.postprocessing.verification import (
    generate_verification_seed,
    two_universal_tag,
    verification_length,
    verify_equal,
)


def test_duplicate_key_id_consumption_rejected():
    store = KeyStore()
    k1 = store.add_key(peer_id="SAE_B", bits=256)
    
    # Passing duplicate key IDs in the same request must fail atomically
    with pytest.raises(ValueError, match="duplicate key_ids"):
        store.consume_by_ids([k1.key_id, k1.key_id], peer_id="SAE_B")
    
    # Ensure key was not consumed during the failed atomic check
    assert store.get(k1.key_id).state == KeyState.AVAILABLE


def test_key_resurrection_prevented():
    store = KeyStore()
    k1 = store.add_key(peer_id="SAE_B", bits=256)
    store.consume_by_ids([k1.key_id], peer_id="SAE_B")
    assert store.get(k1.key_id).state == KeyState.CONSUMED

    # Attempting to re-import an already consumed key must raise ValueError
    consumed_key = store.get(k1.key_id)
    with pytest.raises(ValueError, match="cannot import key"):
        store.import_key(consumed_key)

    # Attempting to re-import a voided key must also raise ValueError
    k2 = store.add_key(peer_id="SAE_B", bits=256)
    store.void([k2.key_id])
    assert store.get(k2.key_id).state == KeyState.VOID
    void_key = store.get(k2.key_id)
    with pytest.raises(ValueError, match="cannot import key"):
        store.import_key(void_key)


def test_secret_material_redacted_in_repr():
    secret_bytes = b"\xde\xad\xbe\xef" * 8
    b64_str = base64.b64encode(secret_bytes).decode("ascii")
    key = ManagedKey(
        key_id="secret-test-key",
        peer_id="peer-1",
        bits=256,
        value_b64=b64_str,
        state=KeyState.AVAILABLE,
        created_at=utcnow(),
        protocol="test",
        eps_sec=1e-10,
        eps_cor=1e-15,
    )
    repr_str = repr(key)
    # The secret base64 or raw bytes must NEVER appear in the repr
    assert b64_str not in repr_str
    assert "deadbeef" not in repr_str.lower()
    assert "<REDACTED:" in repr_str


def test_two_universal_verification_properties():
    # eps_cor = 1e-10 -> 34 bits
    assert verification_length(1e-10) == 34
    # eps_cor = 1e-15 -> 50 bits
    assert verification_length(1e-15) == 50
    # eps_cor must be in (0, 1)
    with pytest.raises(ValueError):
        verification_length(0.0)
    with pytest.raises(ValueError):
        verification_length(1.5)

    # Verification tag and equality
    rng = np.random.default_rng(42)
    alice = rng.integers(0, 2, size=512, dtype=np.uint8)
    bob_same = alice.copy()
    bob_diff = alice.copy()
    bob_diff[0] ^= 1

    seed = generate_verification_seed(512, 64, seed=999)
    assert verify_equal(alice, bob_same, tag_bits=64, seed=seed)
    assert not verify_equal(alice, bob_diff, tag_bits=64, seed=seed)


def test_allowlist_feature_validation():
    # Valid allowlist columns
    valid_cols = ["distance_km", "recent_qber", "recent_gain"]
    validate_feature_columns(valid_cols)

    # Disallowed columns must raise ValueError
    with pytest.raises(ValueError, match="not in allowlist"):
        validate_feature_columns(["distance_km", "arbitrary_unapproved_column"])


def test_non_tautological_security_violation_check():
    import importlib
    eval_mod = importlib.import_module("scripts.24_evaluate_adaptive_policy")
    evaluate_decision_independent = eval_mod.evaluate_decision_independent
    evaluate_decision = eval_mod.evaluate_decision

    # 1. Conservative predictive gate aborts unsafe high-QBER scenario safely
    insecure_ctx = {
        "distance_km": 95.0,
        "recent_qber": 0.12,
        "recent_gain": 0.0001,
        "dark_probability": 1e-5,
        "detector_efficiency": 0.3,
        "key_pool_bits": 500_000.0,
        "demand_bps": 12000.0,
        "mdi_capable": False,
    }
    action_str = "decoy_bb84|mu=0.55|nu=0.10|p=0.90|N=10000000000"
    gate_res = evaluate_decision_independent(action_str, insecure_ctx, key_pool=500_000.0)
    # The conservative predictive gate correctly intervened and executed ABORT
    assert gate_res["executed"] == "ABORT"
    assert gate_res["violation"] is False

    # 2. Independent realization audit flags violation if an action is executed but fails in physical simulation
    fake_group = pd.DataFrame([
        {
            "action_name": "action_insecure",
            "feasible": True,
            "abort": False,
            "secure_bits": 0.0,
            "service_utility": -100.0,
        }
    ])
    compat_res = evaluate_decision("action_insecure", fake_group)
    assert compat_res["executed"] == "action_insecure"
    assert compat_res["violation"] is True

    # 3. Benign scenario succeeds under independent realization with zero violations
    benign_ctx = {
        "distance_km": 20.0,
        "recent_qber": 0.015,
        "recent_gain": 0.04,
        "dark_probability": 1e-7,
        "detector_efficiency": 0.5,
        "key_pool_bits": 500_000.0,
        "demand_bps": 12000.0,
        "mdi_capable": False,
    }
    benign_res = evaluate_decision_independent(action_str, benign_ctx, key_pool=500_000.0)
    assert benign_res["executed"] == action_str
    assert benign_res["secure_bits"] > 0
    assert benign_res["violation"] is False


def test_it_otp_authentication_and_tamper_detection():
    plaintext = b"top secret message requiring information-theoretic security"
    enc_key = bytes(range(len(plaintext)))
    auth_key = b"\x42" * 32

    cipher, tag = encrypt_authenticated_otp(plaintext, enc_key, auth_key, mode="it")
    decrypted = decrypt_authenticated_otp(cipher, tag, enc_key, auth_key, mode="it")
    assert decrypted == plaintext

    # Flip one bit in ciphertext
    tampered = bytearray(cipher)
    tampered[2] ^= 0x01
    with pytest.raises(ValueError, match="tampered"):
        decrypt_authenticated_otp(bytes(tampered), tag, enc_key, auth_key, mode="it")


def test_kms_rejects_material_release_on_abort():
    """Fault-injection: Ensure aborted realization never deposits or releases key material."""
    from qkd_lab.adaptive.execution import execute_action_through_gate

    # Injected hostile scenario that triggers abort
    hostile_ctx = {
        "distance_km": 80.0,
        "recent_qber": 0.15,
        "recent_gain": 0.0001,
        "dark_probability": 1e-5,
        "detector_efficiency": 0.2,
        "key_pool_bits": 0.0,
        "demand_bps": 10000.0,
        "mdi_capable": False,
    }
    action = "decoy_bb84|mu=0.55|nu=0.10|p=0.90|N=10000000000"
    res = execute_action_through_gate(action, hostile_ctx, key_pool=0.0)

    assert res["executed"] == "ABORT"
    assert res["secure_bits"] == 0.0
    assert res["realized_abort"] is True
    assert res["security_violation"] is False

    # KeyStore must reject depositing 0 bits or material from aborted realization
    store = KeyStore()
    with pytest.raises(ValueError, match="bits must be positive"):
        store.deposit_reservoir_bits(peer_id="B", bits=int(res["secure_bits"]))


def test_unbacked_mdi_link_scope_hierarchy():
    """Verify that unbacked MDI links resolve to engineering_model scope and are not composable."""
    from qkd_lab.network.topology import QKDLinkState

    link_mdi = QKDLinkState(
        u="A",
        v="B",
        distance_km=50.0,
        key_bits=1000,
        secure_rate_bps=500,
        mdi_capable=True,
        charlie_node="C",
    )
    assert link_mdi.protocol == "mdi_qkd"
    res = link_mdi.reserve_bits(256)
    assert res.security_scope == "engineering_model"
    assert res.is_composable is False
    assert res.eps_sec is None
    assert res.eps_cor is None
    res.rollback()


def test_plain_unbacked_link_scope_hierarchy():
    """Verify that plain unbacked links fail-closed to unverified scope and are not composable."""
    from qkd_lab.network.topology import QKDLinkState

    link_plain = QKDLinkState(
        u="A",
        v="B",
        distance_km=25.0,
        key_bits=1000,
        secure_rate_bps=500,
        mdi_capable=False,
    )
    assert link_plain.protocol == "decoy_bb84"
    res = link_plain.reserve_bits(256)
    assert res.security_scope == "unverified"
    assert res.is_composable is False
    assert res.eps_sec is None
    assert res.eps_cor is None
    res.rollback()


def test_security_scope_hierarchy_composite_resolution():
    """Verify that composite reservations resolve to the minimum rank in SCOPE_HIERARCHY."""
    from qkd_lab.kms.reservoir import KeyReservoir

    # Case 1: theorem_composable + engineering_model -> engineering_model
    res1 = KeyReservoir(peer_id="B")
    res1.deposit_bits(128, security_scope="theorem_composable", eps_sec=1e-10)
    res1.deposit_bits(128, security_scope="engineering_model", eps_sec=2e-10)
    reservation1 = res1.reserve_bits(256)
    assert reservation1.security_scope == "engineering_model"
    assert reservation1.is_composable is False
    assert reservation1.eps_sec is None
    reservation1.rollback()

    # Case 2: theorem_composable + engineering_model + unverified -> unverified
    res2 = KeyReservoir(peer_id="B")
    res2.deposit_bits(128, security_scope="theorem_composable")
    res2.deposit_bits(128, security_scope="engineering_model")
    res2.deposit_bits(128, security_scope="unverified")
    reservation2 = res2.reserve_bits(384)
    assert reservation2.security_scope == "unverified"
    assert reservation2.is_composable is False
    assert reservation2.eps_sec is None
    reservation2.rollback()


def test_key_store_relay_double_deposit_prevention():
    """Ensure QKDLinkState.__init__ diff deposit prevents double-counting existing reservoir bits."""
    from qkd_lab.network.topology import QKDLinkState

    store = KeyStore()
    # Pre-deposit 1000 bits into store
    store.deposit_reservoir_bits(peer_id="B", bits=1000, initiator_sae_id="A")
    assert store.available_bits(peer_id="B", initiator_sae_id="A") == 1000

    # Initializing QKDLinkState with key_bits=1000 must NOT deposit an additional 1000 bits
    link = QKDLinkState("A", "B", distance_km=25.0, key_bits=1000, secure_rate_bps=500, key_store=store)
    assert link.key_bits == 1000
    assert store.available_bits(peer_id="B", initiator_sae_id="A") == 1000


def test_material_slicing_byte_misalignment_enforcement():
    """Enforce that reserve_bits rejects non-multiples of 8 when reserving from material blocks."""
    from qkd_lab.kms.reservoir import KeyReservoir

    res = KeyReservoir(peer_id="B")
    res.deposit_key_material(b"\xaa" * 32)  # 256 bits of material

    # Reserving non-multiple of 8 must raise ValueError to prevent fractional byte misalignment
    with pytest.raises(ValueError, match="multiple of 8"):
        res.reserve_bits(125)

    # Multiples of 8 must succeed cleanly
    r = res.reserve_bits(128)
    assert r.bits == 128
    assert len(r.segments[0].material_slice) == 16
    r.rollback()


def test_import_keys_batch_preserves_security_scope():
    """Verify that import_keys_batch preserves upstream security_scope provenance."""
    from qkd_lab.kms.models import KeyState, ManagedKey, utcnow
    from qkd_lab.kms.store import KeyStore

    store = KeyStore()
    k1 = ManagedKey(
        key_id="k1",
        peer_id="B",
        bits=256,
        value_b64="AAAA",
        state=KeyState.AVAILABLE,
        created_at=utcnow(),
        protocol="decoy_bb84",
        eps_sec=1e-10,
        eps_cor=1e-15,
        security_scope="theorem_composable",
    )
    k2 = ManagedKey(
        key_id="k2",
        peer_id="B",
        bits=256,
        value_b64="BBBB",
        state=KeyState.AVAILABLE,
        created_at=utcnow(),
        protocol="mdi_qkd",
        eps_sec=1e-8,
        eps_cor=1e-15,
        security_scope="engineering_model",
    )

    imported = store.import_keys_batch([k1, k2], peer_id="B")
    assert imported[0].security_scope == "theorem_composable"
    assert imported[1].security_scope == "engineering_model"
    assert store.get("k1").security_scope == "theorem_composable"
    assert store.get("k2").security_scope == "engineering_model"


def test_consume_bits_prohibits_non_byte_aligned_material_consumption():
    """Verify that consume_bits prohibits non-byte-aligned partial consumption on material keys."""
    import base64
    from qkd_lab.kms.store import KeyStore

    store = KeyStore()
    # Add a 256-bit material key
    store.add_key(
        peer_id="B",
        bits=256,
        value=b"\x55" * 32,
        source="material",
        security_scope="theorem_composable",
    )

    # Consuming 125 bits (not multiple of 8) must raise ValueError
    with pytest.raises(ValueError, match="byte-aligned"):
        store.consume_bits(peer_id="B", bits=125)

    # Consuming 128 bits (multiple of 8) succeeds and preserves material on leftover 128 bits
    consumed = store.consume_bits(peer_id="B", bits=128)
    assert consumed == 128
    assert store.available_bits(peer_id="B") == 128
    res = store.get_reservoir("B")
    assert res._blocks[0].source == "material"
    assert res._blocks[0].key_material == b"\x55" * 16
    assert res._blocks[0].security_scope == "theorem_composable"


def test_qkd_link_state_counter_update_defaults_to_ideal_simulation():
    """Verify that generic reserve increases on QKDLinkState default to ideal_simulation, not theorem_composable."""
    from qkd_lab.kms.store import KeyStore
    from qkd_lab.network.topology import QKDLinkState

    store = KeyStore()
    link = QKDLinkState("A", "B", distance_km=25.0, key_bits=0, secure_rate_bps=1000, key_store=store)

    # Increasing key_bits deposits budget into store's reservoir
    link.key_bits += 5000
    assert link.key_bits == 5000
    res = store.get_reservoir("B")
    assert res._blocks[0].security_scope == "ideal_simulation"
    assert res._blocks[0].security_scope != "theorem_composable"


def test_multihop_end_to_end_key_relays_literal_material():
    """Verify that request_end_to_end_key relays literal QKD material across trusted intermediate nodes."""
    from qkd_lab.kms.store import KeyStore
    from qkd_lab.network.qos import QKDNQoSRequest
    from qkd_lab.network.simulator import request_end_to_end_key
    from qkd_lab.network.topology import QKDLinkState, build_graph

    kms = {n: KeyStore() for n in ("A", "B", "D")}

    mat_ab = b"\x11" * 32  # 256 bits of material for Hop A-B
    mat_bd = b"\x22" * 32  # 256 bits of material for Hop B-D

    kms["A"].deposit_reservoir_key_material(peer_id="B", key_material=mat_ab, initiator_sae_id="A", security_scope="theorem_composable")
    link_ab = QKDLinkState("A", "B", distance_km=25.0, key_bits=256, secure_rate_bps=1000, key_store=kms["A"])

    kms["B"].deposit_reservoir_key_material(peer_id="D", key_material=mat_bd, initiator_sae_id="B", security_scope="theorem_composable")
    link_bd = QKDLinkState("B", "D", distance_km=25.0, key_bits=256, secure_rate_bps=1000, key_store=kms["B"])

    graph = build_graph([link_ab, link_bd])
    qos = QKDNQoSRequest(source="A", target="D", key_bits=256, max_hops=2)

    res = request_end_to_end_key(graph, "A", "D", bits=256, qos=qos, kms_nodes=kms)
    assert res.success
    assert res.security_scope == "theorem_composable"
    assert res.is_composable is True

    # Both endpoints received the exact literal material from Hop 0 (mat_ab)
    key_a = kms["A"].get(res.key_id)
    key_d = kms["D"].get(res.key_id)
    assert key_a.source == "material"
    assert key_d.source == "material"
    import base64
    assert base64.b64decode(key_a.value_b64) == mat_ab
    assert base64.b64decode(key_d.value_b64) == mat_ab

