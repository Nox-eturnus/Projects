from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QKDNQoSRequest:
    """Research QoS abstraction aligned with selected ITU-T Y.3806 / Y.3823 concepts."""
    source: str
    target: str
    key_bits: int
    service_priority: int = 1  # 1: High (emergency/critical), 2: Normal, 3: Background
    max_hops: int = 4
    max_eps_total: float = 1.0e-9  # End-to-end multi-hop composed security bound
    reserve_threshold_bits: int = 10_000  # Minimum remaining key pool after consumption


@dataclass(frozen=True)
class ServiceResult:
    success: bool
    path: tuple[str, ...]
    trusted_intermediate_nodes: tuple[str, ...]
    key_bits_consumed_per_hop: int
    message: str
    eps_total: float = 0.0
    hops: int = 0
    key_id: str | None = None