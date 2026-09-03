from __future__ import annotations

import hashlib
import hmac
from math import ceil

import numpy as np


def bits_to_bytes(bits: np.ndarray) -> bytes:
    bits = np.asarray(bits, dtype=np.uint8).reshape(-1)
    if len(bits) == 0:
        return b""
    return np.packbits(bits).tobytes()


def verification_tag(bits: np.ndarray, tag_bits: int = 64) -> bytes:
    if not 1 <= tag_bits <= 256:
        raise ValueError("tag_bits must lie in 1..256")
    digest = hashlib.sha256(bits_to_bytes(bits)).digest()
    return digest[: ceil(tag_bits / 8)]


def verify_equal(alice: np.ndarray, bob: np.ndarray, tag_bits: int = 64) -> bool:
    return hmac.compare_digest(verification_tag(alice, tag_bits), verification_tag(bob, tag_bits))