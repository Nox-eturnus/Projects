import base64
import json
from pathlib import Path

from qkd_lab.applications.aes_gcm import decrypt_aes_gcm, encrypt_aes_gcm
from qkd_lab.applications.otp import (
    authenticate,
    decrypt_authenticated_otp,
    encrypt_authenticated_otp,
    verify_authentication,
    xor_bytes,
)
from qkd_lab.kms.store import KeyStore


def main():
    store = KeyStore()
    plaintext = b"finite-key QKD application demo: composable, verified, and authenticated."
    pt_len = len(plaintext)
    # Ensure key bit lengths are multiples of 8
    pt_bits = pt_len * 8

    # 1. AES-GCM Key allocation and demo
    aes_item = store.add_key(peer_id="SAE_B", bits=256, protocol="decoy_bb84")
    aes_key = base64.b64decode(store.consume_by_ids([aes_item.key_id], peer_id="SAE_B")[0].value_b64)
    nonce, ciphertext = encrypt_aes_gcm(aes_key, plaintext, aad=b"qkd-demo")
    recovered = decrypt_aes_gcm(aes_key, nonce, ciphertext, aad=b"qkd-demo")
    assert recovered == plaintext

    # 2. OTP and Auth Key allocation from KMS
    otp_item = store.add_key(peer_id="SAE_B", bits=pt_bits, protocol="decoy_bb84")
    auth_item = store.add_key(peer_id="SAE_B", bits=256, protocol="decoy_bb84")

    # Consume both keys atomically from the store
    consumed = store.consume_by_ids([otp_item.key_id, auth_item.key_id], peer_id="SAE_B")
    otp_key = base64.b64decode(consumed[0].value_b64)
    auth_key = base64.b64decode(consumed[1].value_b64)

    assert len(otp_key) == pt_len
    assert len(auth_key) == 32

    # 3. Information-Theoretic Authenticated OTP
    it_cipher, it_tag = encrypt_authenticated_otp(plaintext, otp_key, auth_key, mode="it")
    it_decrypted = decrypt_authenticated_otp(it_cipher, it_tag, otp_key, auth_key, mode="it")
    assert it_decrypted == plaintext

    # Tampering test: ensure modified ciphertext is rejected
    tampered_cipher = bytearray(it_cipher)
    tampered_cipher[0] ^= 0x01
    try:
        decrypt_authenticated_otp(bytes(tampered_cipher), it_tag, otp_key, auth_key, mode="it")
        tamper_caught = False
    except ValueError:
        tamper_caught = True
    assert tamper_caught, "tampered ciphertext must be rejected by IT authenticator"

    # 4. Backward-compatible raw OTP + HMAC check with fresh, separate KMS key material
    # Invariant: Never reuse OTP or authentication key material.
    otp_item_2 = store.add_key(peer_id="SAE_B", bits=pt_bits, protocol="decoy_bb84")
    auth_item_2 = store.add_key(peer_id="SAE_B", bits=256, protocol="decoy_bb84")
    consumed_2 = store.consume_by_ids([otp_item_2.key_id, auth_item_2.key_id], peer_id="SAE_B")
    otp_key_2 = base64.b64decode(consumed_2[0].value_b64)
    auth_key_2 = base64.b64decode(consumed_2[1].value_b64)

    otp_cipher_raw = xor_bytes(plaintext, otp_key_2)
    hmac_tag = authenticate(otp_cipher_raw, auth_key_2)
    assert verify_authentication(otp_cipher_raw, auth_key_2, hmac_tag)
    assert xor_bytes(otp_cipher_raw, otp_key_2) == plaintext

    all_consumed = [aes_item.key_id, otp_item.key_id, auth_item.key_id, otp_item_2.key_id, auth_item_2.key_id]
    assert len(set(all_consumed)) == 5, "all consumed keys must be unique"

    summary = {
        "aes_gcm_roundtrip": True,
        "otp_roundtrip": True,
        "otp_authenticated_it": True,
        "tamper_protection_verified": True,
        "keys_consumed_from_kms": all_consumed,
        "kms_metrics": store.metrics(),
    }
    Path("results/kms").mkdir(parents=True, exist_ok=True)
    Path("results/kms/application_demo.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("Secure application demo PASSED")


if __name__ == "__main__":
    main()