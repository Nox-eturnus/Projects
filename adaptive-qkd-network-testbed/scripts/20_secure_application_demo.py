import base64
import json
from pathlib import Path

from qkd_lab.applications.aes_gcm import decrypt_aes_gcm, encrypt_aes_gcm
from qkd_lab.applications.otp import authenticate, verify_authentication, xor_bytes
from qkd_lab.kms.store import KeyStore


def main():
    store = KeyStore()
    aes_item = store.add_key(peer_id="SAE_B", bits=256, protocol="decoy_bb84")
    aes_key = base64.b64decode(store.consume_by_ids([aes_item.key_id], peer_id="SAE_B")[0].value_b64)
    plaintext = b"finite-key QKD application demo"
    nonce, ciphertext = encrypt_aes_gcm(aes_key, plaintext, aad=b"qkd-demo")
    recovered = decrypt_aes_gcm(aes_key, nonce, ciphertext, aad=b"qkd-demo")
    assert recovered == plaintext

    otp_key = bytes(range(len(plaintext)))
    auth_key = b"B" * 32
    otp_cipher = xor_bytes(plaintext, otp_key)
    tag = authenticate(otp_cipher, auth_key)
    assert verify_authentication(otp_cipher, auth_key, tag)
    assert xor_bytes(otp_cipher, otp_key) == plaintext

    summary = {"aes_gcm_roundtrip": True, "otp_roundtrip": True, "otp_authenticated": True, "kms_metrics": store.metrics()}
    Path("results/kms").mkdir(parents=True, exist_ok=True)
    Path("results/kms/application_demo.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("Secure application demo PASSED")


if __name__ == "__main__":
    main()