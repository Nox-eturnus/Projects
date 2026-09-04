from __future__ import annotations

import hashlib
import hmac

from qkd_lab.security.transcript_auth import (
    authentication_tag,
    verify_authentication_tag,
    verify_wegman_carter_tag,
    wegman_carter_tag,
)


def xor_bytes(data: bytes, key: bytes) -> bytes:
    if len(data) != len(key):
        raise ValueError("OTP key length must exactly equal plaintext length")
    return bytes(a ^ b for a, b in zip(data, key))


def authenticate(ciphertext: bytes, auth_key: bytes) -> bytes:
    """Computational authentication tag via HMAC-SHA256."""
    return authentication_tag(auth_key, ciphertext, 32)


def verify_authentication(ciphertext: bytes, auth_key: bytes, tag: bytes) -> bool:
    """Verify computational HMAC-SHA256 tag."""
    return verify_authentication_tag(auth_key, ciphertext, tag)


def authenticate_it(ciphertext: bytes, auth_key: bytes) -> bytes:
    """Information-theoretic Wegman-Carter authentication tag."""
    return wegman_carter_tag(auth_key, ciphertext, 16)


def verify_authentication_it(ciphertext: bytes, auth_key: bytes, tag: bytes) -> bool:
    """Verify information-theoretic Wegman-Carter tag."""
    return verify_wegman_carter_tag(auth_key, ciphertext, tag)


def encrypt_authenticated_otp(
    plaintext: bytes,
    enc_key: bytes,
    auth_key: bytes,
    *,
    mode: str = "it",
) -> tuple[bytes, bytes]:
    """Encrypt plaintext using OTP and compute an authentication tag over the ciphertext.
    
    Parameters:
        plaintext: Secret message to encrypt.
        enc_key: One-time pad key (must equal len(plaintext)).
        auth_key: Authentication key (>= 32 bytes for 'it', >= 16 bytes for 'hmac').
        mode: 'it' for Wegman-Carter information-theoretic security, or 'hmac' for computational PRF security.
        
    Returns:
        (ciphertext, tag)
    """
    ciphertext = xor_bytes(plaintext, enc_key)
    if mode == "it":
        tag = authenticate_it(ciphertext, auth_key)
    elif mode == "hmac":
        tag = authenticate(ciphertext, auth_key)
    else:
        raise ValueError(f"unknown mode {mode!r}; choose 'it' or 'hmac'")
    return ciphertext, tag


def decrypt_authenticated_otp(
    ciphertext: bytes,
    tag: bytes,
    enc_key: bytes,
    auth_key: bytes,
    *,
    mode: str = "it",
) -> bytes:
    """Verify tag and decrypt ciphertext using OTP.
    
    Raises:
        ValueError: If tag verification fails or keys are malformed.
    """
    if mode == "it":
        valid = verify_authentication_it(ciphertext, auth_key, tag)
    elif mode == "hmac":
        valid = verify_authentication(ciphertext, auth_key, tag)
    else:
        raise ValueError(f"unknown mode {mode!r}; choose 'it' or 'hmac'")

    if not valid:
        raise ValueError("OTP authentication verification failed; ciphertext may be tampered")

    return xor_bytes(ciphertext, enc_key)