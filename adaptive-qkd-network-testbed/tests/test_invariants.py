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
    evaluate_decision = eval_mod.evaluate_decision

    # Scenario group where action 'action_fail' has abort=True or secure_bits <= 0
    fake_group = pd.DataFrame([
        {
            "action_name": "action_insecure",
            "feasible": True,
            "abort": False,  # Pretend gate let it through
            "secure_bits": 0.0,  # But realized secure bits <= 0
            "service_utility": -100.0,
        }
    ])

    res = evaluate_decision("action_insecure", fake_group)
    assert res["executed"] == "action_insecure"
    # Must flag violation because an action was executed but produced zero secure bits
    assert res["violation"] is True

    # Safe abort
    abort_res = evaluate_decision("ABORT", fake_group)
    assert abort_res["executed"] == "ABORT"
    assert abort_res["violation"] is False


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
