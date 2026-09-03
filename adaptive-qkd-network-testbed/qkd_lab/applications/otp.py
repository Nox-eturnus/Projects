from __future__ import annotations

import hashlib
import hmac


def xor_bytes(data: bytes, key: bytes) -> bytes:
    if len(data) != len(key):
        raise ValueError("OTP key length must exactly equal plaintext length")
    return bytes(a ^ b for a, b in zip(data, key))


def authenticate(ciphertext: bytes, auth_key: bytes) -> bytes:
    return hmac.new(auth_key, ciphertext, hashlib.sha256).digest()


def verify_authentication(ciphertext: bytes, auth_key: bytes, tag: bytes) -> bool:
    return hmac.compare_digest(authenticate(ciphertext, auth_key), tag)