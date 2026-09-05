from __future__ import annotations

import base64
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime

from qkd_lab.kms.models import KeyState, ManagedKey, utcnow
from qkd_lab.rng import secure_random_bytes


@dataclass
class DistilledBlock:
    block_id: str
    bits: int
    remaining_bits: int
    protocol: str
    eps_sec: float
    eps_cor: float
    created_at: datetime
    initiator_sae_id: str | None = None
    target_sae_id: str | None = None


class KeyReservoir:
    """Manages distilled secure key bit pools per peer link.

    Provides O(1) bit tracking and on-demand atomic slicing of ManagedKeys
    (e.g., 256-bit keys for ETSI GS QKD 014 / 020) without generating
    millions of individual objects up front.
    """

    def __init__(self, peer_id: str, *, max_bits: int | None = None) -> None:
        self.peer_id = peer_id
        self._max_bits = max_bits
        self._lock = threading.RLock()
        self._blocks: list[DistilledBlock] = []

    def deposit_bits(
        self,
        bits: int,
        *,
        protocol: str = "simulated_qkd",
        eps_sec: float = 1e-10,
        eps_cor: float = 1e-15,
        initiator_sae_id: str | None = None,
        target_sae_id: str | None = None,
    ) -> str:
        if bits <= 0:
            raise ValueError("bits must be positive")
        with self._lock:
            if self._max_bits is not None:
                current = sum(b.remaining_bits for b in self._blocks)
                if current + bits > self._max_bits:
                    raise RuntimeError("KeyReservoir maximum bit capacity exceeded")
            block_id = str(uuid.uuid4())
            block = DistilledBlock(
                block_id=block_id,
                bits=bits,
                remaining_bits=bits,
                protocol=protocol,
                eps_sec=eps_sec,
                eps_cor=eps_cor,
                created_at=utcnow(),
                initiator_sae_id=initiator_sae_id,
                target_sae_id=target_sae_id or self.peer_id,
            )
            self._blocks.append(block)
            return block_id

    def available_bits(self, *, initiator_sae_id: str | None = None) -> int:
        with self._lock:
            total = 0
            for b in self._blocks:
                if initiator_sae_id is not None and b.initiator_sae_id is not None:
                    if b.initiator_sae_id != initiator_sae_id:
                        continue
                total += b.remaining_bits
            return total

    def consume_bits(self, bits: int, *, initiator_sae_id: str | None = None) -> int:
        if bits <= 0:
            raise ValueError("bits must be positive")
        with self._lock:
            avail = self.available_bits(initiator_sae_id=initiator_sae_id)
            if avail < bits:
                raise RuntimeError(f"insufficient reservoir bits: requested {bits}, available {avail}")
            remaining_to_consume = bits
            for b in self._blocks:
                if initiator_sae_id is not None and b.initiator_sae_id is not None:
                    if b.initiator_sae_id != initiator_sae_id:
                        continue
                if b.remaining_bits <= 0:
                    continue
                take = min(b.remaining_bits, remaining_to_consume)
                b.remaining_bits -= take
                remaining_to_consume -= take
                if remaining_to_consume == 0:
                    break
            self._blocks = [b for b in self._blocks if b.remaining_bits > 0]
            return bits

    def slice_key(
        self,
        *,
        bits: int = 256,
        initiator_sae_id: str | None = None,
        target_sae_id: str | None = None,
        key_id: str | None = None,
    ) -> ManagedKey:
        if bits <= 0 or bits % 8 != 0:
            raise ValueError("bits must be a positive multiple of 8")
        with self._lock:
            avail = self.available_bits(initiator_sae_id=initiator_sae_id)
            if avail < bits:
                raise RuntimeError(f"insufficient reservoir bits to slice {bits}-bit key")
            self.consume_bits(bits, initiator_sae_id=initiator_sae_id)
            key_bytes = secure_random_bytes(bits // 8)
            key_id = key_id or str(uuid.uuid4())
            return ManagedKey(
                key_id=key_id,
                peer_id=self.peer_id,
                bits=bits,
                value_b64=base64.b64encode(key_bytes).decode("ascii"),
                state=KeyState.AVAILABLE,
                created_at=utcnow(),
                protocol="reservoir_slice",
                eps_sec=1e-10,
                eps_cor=1e-15,
                initiator_sae_id=initiator_sae_id,
                target_sae_id=target_sae_id or self.peer_id,
            )
