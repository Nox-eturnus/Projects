from __future__ import annotations

import hashlib
import hmac


def authentication_tag(key: bytes, transcript: bytes, tag_bytes: int = 16) -> bytes:
    if tag_bytes <= 0 or tag_bytes > 32:
        raise ValueError("tag_bytes must lie in 1..32 for HMAC-SHA256 demo")
    return hmac.new(key, transcript, hashlib.sha256).digest()[:tag_bytes]


def verify_authentication_tag(key: bytes, transcript: bytes, tag: bytes) -> bool:
    expected = authentication_tag(key, transcript, len(tag))
    return hmac.compare_digest(expected, tag)