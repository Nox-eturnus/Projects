from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum


class KeyState(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    CONSUMED = "consumed"
    VOID = "void"


@dataclass(frozen=True)
class ManagedKey:
    key_id: str
    peer_id: str
    bits: int
    value_b64: str
    state: KeyState
    created_at: datetime
    protocol: str
    eps_sec: float
    eps_cor: float

    def with_state(self, state: KeyState) -> "ManagedKey":
        return replace(self, state=state)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)