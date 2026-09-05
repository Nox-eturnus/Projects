from __future__ import annotations

import hashlib
import hmac
import struct

# Prime p = 2^127 - 1 (12th Mersenne prime) for information-theoretic Wegman-Carter hashing
_P127 = (1 << 127) - 1


def authentication_tag(key: bytes, transcript: bytes, tag_bytes: int = 16) -> bytes:
    """HMAC-SHA256 computational authentication tag.
    
    Security note:
        This provides computational security (standard PRF assumption).
        For unconditional information-theoretic security, use wegman_carter_tag().
    """
    if tag_bytes <= 0 or tag_bytes > 32:
        raise ValueError("tag_bytes must lie in 1..32 for HMAC-SHA256")
    return hmac.new(key, transcript, hashlib.sha256).digest()[:tag_bytes]


def verify_authentication_tag(key: bytes, transcript: bytes, tag: bytes) -> bool:
    """Verify HMAC-SHA256 computational authentication tag."""
    expected = authentication_tag(key, transcript, len(tag))
    return hmac.compare_digest(expected, tag)


def wegman_carter_tag(key: bytes, message: bytes, tag_bytes: int = 16) -> bytes:
    """Wegman-Carter information-theoretic authentication tag.
    
    Uses polynomial evaluation over GF(p) with p = 2^127 - 1, masked with a one-time pad:
        Tag = (sum_{i=1}^k m_i * r^i mod p + s) mod 2^(8 * tag_bytes)
        
    Key requirements:
        key must be at least 32 bytes:
        - First 16 bytes: evaluation point r (derived mod p)
        - Next 16 bytes: one-time pad mask s
        
    Security:
        For 16-byte tags (tag_bytes=16), information-theoretic forgery probability is
        bounded by ceil(len(message)/16) / 2^127.
        For 8-byte tags (tag_bytes=8), truncation mod 2^64 increases the collision
        probability to at most ceil(len(message)/16) / 2^64.
        Requires a fresh key (or fresh one-time mask s) for each authenticated message.
    """
    if len(key) < 32:
        raise ValueError("Wegman-Carter key must be at least 32 bytes (16 bytes r + 16 bytes s)")
    if tag_bytes not in (8, 16):
        raise ValueError("tag_bytes must be 8 or 16 for Wegman-Carter tag")

    r = int.from_bytes(key[:16], "big") % _P127
    s = int.from_bytes(key[16:32], "big")

    # Split message into 16-byte blocks
    block_size = 16
    poly_val = 0
    # Append message length as final block to prevent length-extension collisions
    padded_msg = message + struct.pack(">Q", len(message))
    for i in range(0, len(padded_msg), block_size):
        chunk = padded_msg[i : i + block_size]
        coeff = int.from_bytes(chunk, "big") % _P127
        poly_val = ((poly_val + coeff) * r) % _P127

    tag_int = (poly_val + s) % (1 << (8 * tag_bytes))
    return tag_int.to_bytes(tag_bytes, "big")


def verify_wegman_carter_tag(key: bytes, message: bytes, tag: bytes) -> bool:
    """Verify Wegman-Carter information-theoretic authentication tag in constant time."""
    expected = wegman_carter_tag(key, message, len(tag))
    return hmac.compare_digest(expected, tag)