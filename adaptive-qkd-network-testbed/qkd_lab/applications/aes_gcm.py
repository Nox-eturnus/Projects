from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt_aes_gcm(key: bytes, plaintext: bytes, aad: bytes = b"") -> tuple[bytes, bytes]:
    if len(key) != 32:
        raise ValueError("AES-256-GCM requires a 32-byte key")
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    return nonce, ciphertext


def decrypt_aes_gcm(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes = b"") -> bytes:
    if len(key) != 32:
        raise ValueError("AES-256-GCM requires a 32-byte key")
    return AESGCM(key).decrypt(nonce, ciphertext, aad)