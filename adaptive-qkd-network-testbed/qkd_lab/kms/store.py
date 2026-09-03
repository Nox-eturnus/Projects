from __future__ import annotations

import base64
import threading
import uuid
from dataclasses import asdict

from qkd_lab.kms.models import KeyState, ManagedKey, utcnow
from qkd_lab.rng import secure_random_bytes


class KeyStore:
    def __init__(self) -> None:
        self._keys: dict[str, ManagedKey] = {}
        self._lock = threading.RLock()

    def add_key(
        self,
        *,
        peer_id: str,
        bits: int,
        protocol: str = "simulated_qkd",
        eps_sec: float = 1e-10,
        eps_cor: float = 1e-15,
        key_id: str | None = None,
        value: bytes | None = None,
    ) -> ManagedKey:
        if bits <= 0 or bits % 8 != 0:
            raise ValueError("bits must be a positive multiple of 8")
        key_id = key_id or str(uuid.uuid4())
        value = value if value is not None else secure_random_bytes(bits // 8)
        if len(value) * 8 != bits:
            raise ValueError("value length does not match bits")
        item = ManagedKey(
            key_id=key_id,
            peer_id=peer_id,
            bits=bits,
            value_b64=base64.b64encode(value).decode("ascii"),
            state=KeyState.AVAILABLE,
            created_at=utcnow(),
            protocol=protocol,
            eps_sec=eps_sec,
            eps_cor=eps_cor,
        )
        with self._lock:
            if key_id in self._keys:
                raise ValueError(f"duplicate key_id {key_id}")
            self._keys[key_id] = item
        return item

    def import_key(self, key: ManagedKey, *, peer_id: str | None = None) -> ManagedKey:
        imported = ManagedKey(
            key_id=key.key_id,
            peer_id=peer_id or key.peer_id,
            bits=key.bits,
            value_b64=key.value_b64,
            state=KeyState.AVAILABLE,
            created_at=key.created_at,
            protocol=key.protocol,
            eps_sec=key.eps_sec,
            eps_cor=key.eps_cor,
        )
        with self._lock:
            if imported.key_id in self._keys:
                raise ValueError(f"duplicate key_id {imported.key_id}")
            self._keys[imported.key_id] = imported
        return imported

    def get(self, key_id: str) -> ManagedKey:
        with self._lock:
            if key_id not in self._keys:
                raise KeyError(key_id)
            return self._keys[key_id]

    def available(self, *, peer_id: str | None = None, bits: int | None = None) -> list[ManagedKey]:
        with self._lock:
            out = [k for k in self._keys.values() if k.state == KeyState.AVAILABLE]
            if peer_id is not None:
                out = [k for k in out if k.peer_id == peer_id]
            if bits is not None:
                out = [k for k in out if k.bits == bits]
            return sorted(out, key=lambda k: k.created_at)

    def consume(self, *, peer_id: str, number: int = 1, bits: int = 256) -> list[ManagedKey]:
        if number <= 0:
            raise ValueError("number must be positive")
        with self._lock:
            candidates = self.available(peer_id=peer_id, bits=bits)
            if len(candidates) < number:
                raise RuntimeError("insufficient key material")
            chosen = candidates[:number]
            for key in chosen:
                self._keys[key.key_id] = key.with_state(KeyState.CONSUMED)
            return chosen

    def consume_by_ids(self, key_ids: list[str], *, peer_id: str | None = None) -> list[ManagedKey]:
        if not key_ids:
            raise ValueError("at least one key ID is required")
        with self._lock:
            chosen: list[ManagedKey] = []
            for key_id in key_ids:
                key = self.get(key_id)
                if key.state != KeyState.AVAILABLE:
                    raise RuntimeError(f"key {key_id} is not available")
                if peer_id is not None and key.peer_id != peer_id:
                    raise PermissionError(f"key {key_id} is not assigned to peer {peer_id}")
                chosen.append(key)
            for key in chosen:
                self._keys[key.key_id] = key.with_state(KeyState.CONSUMED)
            return chosen

    def void(self, key_ids: list[str]) -> list[str]:
        voided: list[str] = []
        with self._lock:
            for key_id in key_ids:
                key = self.get(key_id)
                if key.state == KeyState.CONSUMED:
                    raise RuntimeError(f"cannot void consumed key {key_id}")
                self._keys[key_id] = key.with_state(KeyState.VOID)
                voided.append(key_id)
        return voided

    def metrics(self) -> dict[str, int]:
        with self._lock:
            counts = {state.value: 0 for state in KeyState}
            bits = {f"{state.value}_bits": 0 for state in KeyState}
            for key in self._keys.values():
                counts[key.state.value] += 1
                bits[f"{key.state.value}_bits"] += key.bits
            return {**counts, **bits}

    def safe_metadata(self) -> list[dict]:
        """Return metadata without key material."""
        with self._lock:
            rows = []
            for key in self._keys.values():
                d = asdict(key)
                d.pop("value_b64", None)
                d["state"] = key.state.value
                d["created_at"] = key.created_at.isoformat()
                rows.append(d)
            return rows