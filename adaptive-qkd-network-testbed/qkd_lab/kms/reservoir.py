from __future__ import annotations

import base64
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime

from typing import Any

from qkd_lab.kms.models import KeyState, ManagedKey, SCOPE_HIERARCHY, utcnow
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
    key_material: bytearray | bytes | None = None
    source: str = "budget"  # "material" or "budget"
    security_scope: str = "unverified"  # Fail-closed default: "unverified" < "ideal_simulation" < "engineering_model" < "theorem_composable"


@dataclass
class BlockReservation:
    block: DistilledBlock
    bits: int
    material_slice: bytes | None = None


class ReservoirReservation:
    """Represents a transactional reservation of key bits/material from a KeyReservoir."""

    def __init__(self, reservoir: KeyReservoir, bits: int, segments: list[BlockReservation]) -> None:
        self.reservoir = reservoir
        self.bits = bits
        self.segments = segments
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.committed = True
        # Cryptographic hygiene: wipe sensitive material slices once committed
        for seg in self.segments:
            seg.material_slice = None

    def rollback(self) -> None:
        if self.committed or self.rolled_back:
            return
        self.reservoir._restore_reservation(self.segments)
        self.rolled_back = True

    @property
    def eps_sec(self) -> float | None:
        """Summed composable secrecy parameter across contributing blocks, or None if not composable."""
        if not self.is_composable:
            return None
        return sum(seg.block.eps_sec for seg in self.segments)

    @property
    def eps_cor(self) -> float | None:
        """Summed composable correctness parameter across contributing blocks, or None if not composable."""
        if not self.is_composable:
            return None
        return sum(seg.block.eps_cor for seg in self.segments)

    @property
    def protocols(self) -> list[str]:
        """List of distinct protocols contributing to this reservation."""
        return sorted(set(seg.block.protocol for seg in self.segments))

    @property
    def security_scope(self) -> str:
        """Overall security scope: minimum rank across contributing blocks in SCOPE_HIERARCHY."""
        if not self.segments:
            return "unverified"
        min_rank = min(SCOPE_HIERARCHY.get(seg.block.security_scope, 0) for seg in self.segments)
        rank_to_scope = {v: k for k, v in SCOPE_HIERARCHY.items()}
        return rank_to_scope.get(min_rank, "unverified")

    @property
    def is_composable(self) -> bool:
        """True only if all contributing blocks have theorem-level composability."""
        return self.security_scope == "theorem_composable"

    @property
    def source(self) -> str:
        """'material' if all segments were sliced from physical material blocks, else 'budget_synthetic'."""
        if self.segments and all(seg.block.source == "material" for seg in self.segments):
            return "material"
        return "budget_synthetic"

    @property
    def material(self) -> bytes | None:
        """Concatenated key material bytes across all segments, or None if any segment lacks literal material."""
        if not self.segments:
            return None
        if any(seg.material_slice is None for seg in self.segments):
            return None
        return b"".join(seg.material_slice for seg in self.segments)

    def __enter__(self) -> ReservoirReservation:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None and not self.committed and not self.rolled_back:
            self.rollback()


class KeyReservoir:
    """Manages distilled secure key bit pools per peer link.

    Provides O(1) bit tracking and on-demand atomic slicing of ManagedKeys
    (e.g., 256-bit keys for ETSI GS QKD 014 / 020). Supports two modes:
      - "material": stores actual privacy-amplified key bytes and slices them
      - "budget": tracks secure-bit counts and synthesizes CSPRNG keys tagged 'budget_synthetic'
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
        key_material: bytes | bytearray | None = None,
        source: str | None = None,
        security_scope: str = "unverified",
    ) -> str:
        if bits <= 0:
            raise ValueError("bits must be positive")
        if key_material is not None:
            if bits % 8 != 0:
                raise ValueError(f"bits ({bits}) must be a multiple of 8 when key_material is provided")
            if len(key_material) * 8 < bits:
                raise ValueError(
                    f"key_material length ({len(key_material)} bytes = {len(key_material)*8} bits) "
                    f"is less than declared bits ({bits})"
                )
            mat: bytearray | bytes | None = bytearray(key_material[: bits // 8])
            block_source = source or "material"
        else:
            mat = None
            block_source = source or "budget"

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
                key_material=mat,
                source=block_source,
                security_scope=security_scope,
            )
            self._blocks.append(block)
            return block_id

    def deposit_key_material(
        self,
        key_material: bytes | bytearray,
        *,
        protocol: str = "distilled_material",
        eps_sec: float = 1e-10,
        eps_cor: float = 1e-15,
        initiator_sae_id: str | None = None,
        target_sae_id: str | None = None,
        security_scope: str = "unverified",
    ) -> str:
        return self.deposit_bits(
            len(key_material) * 8,
            protocol=protocol,
            eps_sec=eps_sec,
            eps_cor=eps_cor,
            initiator_sae_id=initiator_sae_id,
            target_sae_id=target_sae_id,
            key_material=key_material,
            source="material",
            security_scope=security_scope,
        )

    def available_bits(
        self,
        *,
        initiator_sae_id: str | None = None,
        allow_unbound: bool = False,
    ) -> int:
        with self._lock:
            total = 0
            for b in self._blocks:
                if initiator_sae_id is not None:
                    if allow_unbound:
                        if b.initiator_sae_id is not None and b.initiator_sae_id != initiator_sae_id:
                            continue
                    else:
                        if b.initiator_sae_id != initiator_sae_id:
                            continue
                total += b.remaining_bits
            return total

    def consume_bits(
        self,
        bits: int,
        *,
        initiator_sae_id: str | None = None,
        allow_unbound: bool = False,
    ) -> int:
        if bits <= 0:
            raise ValueError("bits must be positive")
        with self._lock:
            avail = self.available_bits(initiator_sae_id=initiator_sae_id, allow_unbound=allow_unbound)
            if avail < bits:
                raise RuntimeError(f"insufficient reservoir bits: requested {bits}, available {avail}")
            remaining_to_consume = bits
            for b in self._blocks:
                if initiator_sae_id is not None:
                    if allow_unbound:
                        if b.initiator_sae_id is not None and b.initiator_sae_id != initiator_sae_id:
                            continue
                    else:
                        if b.initiator_sae_id != initiator_sae_id:
                            continue
                if b.remaining_bits <= 0:
                    continue
                take = min(b.remaining_bits, remaining_to_consume)
                b.remaining_bits -= take
                if b.key_material is not None:
                    take_bytes = (take + 7) // 8
                    b.key_material = b.key_material[take_bytes:]
                remaining_to_consume -= take
                if remaining_to_consume == 0:
                    break
            self._blocks = [b for b in self._blocks if b.remaining_bits > 0]
            return bits

    def reserve_bits(
        self,
        bits: int,
        *,
        initiator_sae_id: str | None = None,
        allow_unbound: bool = False,
    ) -> ReservoirReservation:
        """Transactionally reserve bits/material from reservoir.

        Returns a ReservoirReservation that can be committed or rolled back.
        If rolled back, the exact blocks and key material slices are restored.
        """
        if bits <= 0:
            raise ValueError("bits must be positive")
        with self._lock:
            avail = self.available_bits(initiator_sae_id=initiator_sae_id, allow_unbound=allow_unbound)
            if avail < bits:
                raise RuntimeError(f"insufficient reservoir bits: requested {bits}, available {avail}")

            # Enforce byte-alignment if reserving from any material-backed block
            if bits % 8 != 0:
                bits_needed = bits
                for b in self._blocks:
                    if initiator_sae_id is not None:
                        if allow_unbound:
                            if b.initiator_sae_id is not None and b.initiator_sae_id != initiator_sae_id:
                                continue
                        else:
                            if b.initiator_sae_id != initiator_sae_id:
                                continue
                    if b.remaining_bits <= 0:
                        continue
                    if b.key_material is not None:
                        raise ValueError(
                            f"bits ({bits}) must be a multiple of 8 when reserving from key material blocks"
                        )
                    bits_needed -= b.remaining_bits
                    if bits_needed <= 0:
                        break

            remaining_to_reserve = bits
            segments: list[BlockReservation] = []
            for b in self._blocks:
                if initiator_sae_id is not None:
                    if allow_unbound:
                        if b.initiator_sae_id is not None and b.initiator_sae_id != initiator_sae_id:
                            continue
                    else:
                        if b.initiator_sae_id != initiator_sae_id:
                            continue
                if b.remaining_bits <= 0:
                    continue
                take = min(b.remaining_bits, remaining_to_reserve)
                b.remaining_bits -= take
                mat_slice: bytes | None = None
                if b.key_material is not None:
                    take_bytes = take // 8
                    mat_slice = bytes(b.key_material[:take_bytes])
                    b.key_material = b.key_material[take_bytes:]
                segments.append(
                    BlockReservation(
                        block=b,
                        bits=take,
                        material_slice=mat_slice,
                    )
                )
                remaining_to_reserve -= take
                if remaining_to_reserve == 0:
                    break

            self._blocks = [b for b in self._blocks if b.remaining_bits > 0]
            return ReservoirReservation(self, bits, segments)

    def _restore_reservation(self, segments: list[BlockReservation]) -> None:
        """Restore previously reserved segments back into reservoir."""
        with self._lock:
            for seg in reversed(segments):
                b = seg.block
                b.remaining_bits += seg.bits
                if seg.material_slice is not None:
                    if b.key_material is None:
                        b.key_material = bytearray(seg.material_slice)
                    else:
                        b.key_material = bytearray(seg.material_slice) + bytearray(b.key_material)
                if b not in self._blocks:
                    self._blocks.append(b)
            self._blocks.sort(key=lambda block: block.created_at)

    def slice_key(
        self,
        *,
        bits: int = 256,
        initiator_sae_id: str | None = None,
        target_sae_id: str | None = None,
        key_id: str | None = None,
        allow_unbound: bool = False,
    ) -> ManagedKey:
        if bits <= 0 or bits % 8 != 0:
            raise ValueError("bits must be a positive multiple of 8")
        with self._lock:
            avail = self.available_bits(initiator_sae_id=initiator_sae_id, allow_unbound=allow_unbound)
            if avail < bits:
                raise RuntimeError(f"insufficient reservoir bits to slice {bits}-bit key")

            remaining_to_slice = bits
            collected_material = bytearray()
            is_material = True
            contributing_protocols: list[str] = []
            contributing_scopes: list[str] = []
            composed_eps_sec = 0.0
            composed_eps_cor = 0.0

            for b in self._blocks:
                if initiator_sae_id is not None:
                    if allow_unbound:
                        if b.initiator_sae_id is not None and b.initiator_sae_id != initiator_sae_id:
                            continue
                    else:
                        if b.initiator_sae_id != initiator_sae_id:
                            continue
                if b.remaining_bits <= 0:
                    continue

                take = min(b.remaining_bits, remaining_to_slice)
                b.remaining_bits -= take
                remaining_to_slice -= take

                contributing_protocols.append(b.protocol)
                contributing_scopes.append(b.security_scope)
                composed_eps_sec += b.eps_sec
                composed_eps_cor += b.eps_cor

                if b.key_material is not None and b.source == "material":
                    take_bytes = take // 8
                    collected_material.extend(b.key_material[:take_bytes])
                    b.key_material = b.key_material[take_bytes:]
                else:
                    is_material = False

                if remaining_to_slice == 0:
                    break

            self._blocks = [b for b in self._blocks if b.remaining_bits > 0]

            bytes_needed = bits // 8
            if is_material and len(collected_material) == bytes_needed:
                key_bytes = bytes(collected_material)
                source_tag = "material"
            else:
                key_bytes = secure_random_bytes(bytes_needed)
                source_tag = "budget_synthetic"

            unique_protocols = sorted(set(contributing_protocols))
            if len(unique_protocols) == 1:
                key_protocol = unique_protocols[0]
            elif len(unique_protocols) > 1:
                key_protocol = f"composite:{'+'.join(unique_protocols)}"
            else:
                key_protocol = "reservoir_slice"

            min_rank = min(SCOPE_HIERARCHY.get(s, 0) for s in contributing_scopes) if contributing_scopes else 0
            rank_to_scope = {v: k for k, v in SCOPE_HIERARCHY.items()}
            key_security_scope = rank_to_scope.get(min_rank, "unverified")

            key_id = key_id or str(uuid.uuid4())
            return ManagedKey(
                key_id=key_id,
                peer_id=self.peer_id,
                bits=bits,
                value_b64=base64.b64encode(key_bytes).decode("ascii"),
                state=KeyState.AVAILABLE,
                created_at=utcnow(),
                protocol=key_protocol,
                eps_sec=composed_eps_sec if composed_eps_sec > 0 else 1e-10,
                eps_cor=composed_eps_cor if composed_eps_cor > 0 else 1e-15,
                initiator_sae_id=initiator_sae_id,
                target_sae_id=target_sae_id or self.peer_id,
                source=source_tag,
                security_scope=key_security_scope,
            )
