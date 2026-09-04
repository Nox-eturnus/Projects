from __future__ import annotations

import networkx as nx

from qkd_lab.models import BasisProbabilities, ChannelParameters, DetectorParameters, IntensitySetting
from qkd_lab.network.qos import QKDNQoSRequest, ServiceResult
from qkd_lab.network.routing import find_secure_path, path_links
from qkd_lab.protocols.decoy_bb84 import expected_decoy_bb84_block
from qkd_lab.estimation.finite_key_bb84 import estimate_lim2014


def generate_keys(graph: nx.Graph, seconds: float) -> None:
    """Replenish key pools based on configured link secure_rate_bps."""
    if seconds < 0:
        raise ValueError("seconds must be non-negative")
    for _, _, data in graph.edges(data=True):
        link = data["state"]
        if link.active:
            link.key_bits += int(link.secure_rate_bps * seconds)


def replenish_from_qkd_physics(
    graph: nx.Graph,
    pulses_per_link: int = 50_000_000,
    eps_sec: float = 1.0e-10,
    eps_cor: float = 1.0e-15,
) -> dict[tuple[str, str], int]:
    """Replenish link key pools from physical finite-key QKD block simulation."""
    generated = {}
    intensities = (
        IntensitySetting("signal", 0.45, 0.80),
        IntensitySetting("decoy", 0.10, 0.15),
        IntensitySetting("vacuum", 0.0002, 0.05),
    )
    basis = BasisProbabilities(0.85, 0.85)

    for u, v, data in graph.edges(data=True):
        link = data["state"]
        if not link.active:
            generated[(u, v)] = 0
            continue

        channel = ChannelParameters(link.distance_km, 0.20)
        detector = DetectorParameters(0.20, 1e-6, link.qber, 2)
        try:
            block = expected_decoy_bb84_block(
                pulses_per_link,
                intensities=intensities,
                basis=basis,
                channel=channel,
                detector=detector,
            )
            fk = estimate_lim2014(
                block.records,
                intensities,
                eps_sec=eps_sec,
                eps_cor=eps_cor,
            )
            new_bits = int(fk.secure_bits) if not fk.abort else 0
        except Exception:
            new_bits = 0

        link.key_bits += new_bits
        generated[(u, v)] = new_bits

    return generated


def request_end_to_end_key(
    graph: nx.Graph,
    source: str,
    target: str,
    bits: int,
    qos: QKDNQoSRequest | None = None,
) -> ServiceResult:
    """Request an end-to-end key between source and target across trusted relay nodes."""
    if bits <= 0:
        raise ValueError("bits must be positive")

    qos = qos or QKDNQoSRequest(source=source, target=target, key_bits=bits)
    required_reserve = bits + qos.reserve_threshold_bits

    path = find_secure_path(graph, source, target, required_reserve)
    if path is None:
        # Fall back to minimum required bits if reserve threshold cannot be met
        path = find_secure_path(graph, source, target, bits)
        if path is None:
            return ServiceResult(
                success=False,
                path=tuple(),
                trusted_intermediate_nodes=tuple(),
                key_bits_consumed_per_hop=0,
                message="no secure path with sufficient key reserve",
                eps_total=0.0,
                hops=0,
            )

    hops = len(path) - 1
    if hops > qos.max_hops:
        return ServiceResult(
            success=False,
            path=tuple(path),
            trusted_intermediate_nodes=tuple(path[1:-1]),
            key_bits_consumed_per_hop=0,
            message=f"path length ({hops} hops) exceeds max_hops ({qos.max_hops})",
            eps_total=0.0,
            hops=hops,
        )

    # Multi-hop security composition: sum of epsilon parameters across links
    link_eps = 1.0e-10
    eps_total = hops * link_eps
    if eps_total > qos.max_eps_total:
        return ServiceResult(
            success=False,
            path=tuple(path),
            trusted_intermediate_nodes=tuple(path[1:-1]),
            key_bits_consumed_per_hop=0,
            message=f"composed security epsilon ({eps_total:.2e}) exceeds limit ({qos.max_eps_total:.2e})",
            eps_total=eps_total,
            hops=hops,
        )

    links = path_links(graph, path)
    for link in links:
        if not link.active or link.key_bits < bits:
            return ServiceResult(
                success=False,
                path=tuple(path),
                trusted_intermediate_nodes=tuple(path[1:-1]),
                key_bits_consumed_per_hop=0,
                message="path became infeasible during reservation",
                eps_total=eps_total,
                hops=hops,
            )

    # Atomic consumption across all intermediate trusted hops
    for link in links:
        link.key_bits -= bits

    return ServiceResult(
        success=True,
        path=tuple(path),
        trusted_intermediate_nodes=tuple(path[1:-1]),
        key_bits_consumed_per_hop=bits,
        message="trusted-node key relay completed",
        eps_total=eps_total,
        hops=hops,
    )