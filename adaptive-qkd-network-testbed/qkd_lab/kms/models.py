from __future__ import annotations

from dataclasses import dataclass, field, replace
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
    value_b64: str = field(repr=False)
    state: KeyState
    created_at: datetime
    protocol: str
    eps_sec: float
    eps_cor: float
    initiator_sae_id: str | None = None
    target_sae_id: str | None = None
    source: str = "material"

    def __repr__(self) -> str:
        # Never leak raw key bytes or base64 material in logs, exceptions, or debugger reprs
        length_bytes = len(self.value_b64) * 3 // 4 if self.value_b64 else 0
        return (
            f"ManagedKey(key_id={self.key_id!r}, peer_id={self.peer_id!r}, "
            f"bits={self.bits}, value_b64='<REDACTED: {length_bytes} bytes>', "
            f"state={self.state.value!r}, protocol={self.protocol!r}, "
            f"source={self.source!r}, "
            f"initiator_sae_id={self.initiator_sae_id!r}, target_sae_id={self.target_sae_id!r})"
        )

    def with_state(self, state: KeyState) -> "ManagedKey":
        return replace(self, state=state)

    def erase_secret(self) -> "ManagedKey":
        """Wipe secret key material in memory and mark key void."""
        return replace(self, value_b64="", state=KeyState.VOID)

    def consumed_and_erased(self) -> "ManagedKey":
        """Wipe secret key material in memory upon consumption in the KeyStore."""
        return replace(self, value_b64="", state=KeyState.CONSUMED)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)