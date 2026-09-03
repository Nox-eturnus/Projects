from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceResult:
    success: bool
    path: tuple[str, ...]
    trusted_intermediate_nodes: tuple[str, ...]
    key_bits_consumed_per_hop: int
    message: str