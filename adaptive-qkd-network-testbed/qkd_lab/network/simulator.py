from __future__ import annotations

import networkx as nx

from qkd_lab.network.qos import ServiceResult
from qkd_lab.network.routing import find_secure_path, path_links


def generate_keys(graph: nx.Graph, seconds: float) -> None:
    if seconds < 0:
        raise ValueError("seconds must be non-negative")
    for _, _, data in graph.edges(data=True):
        link = data["state"]
        if link.active:
            link.key_bits += int(link.secure_rate_bps * seconds)


def request_end_to_end_key(
    graph: nx.Graph,
    source: str,
    target: str,
    bits: int,
) -> ServiceResult:
    if bits <= 0:
        raise ValueError("bits must be positive")
    path = find_secure_path(graph, source, target, bits)
    if path is None:
        return ServiceResult(False, tuple(), tuple(), 0, "no secure path with sufficient key reserve")
    links = path_links(graph, path)
    for link in links:
        if not link.active or link.key_bits < bits:
            return ServiceResult(False, tuple(path), tuple(path[1:-1]), 0, "path became infeasible")
    for link in links:
        link.key_bits -= bits
    return ServiceResult(True, tuple(path), tuple(path[1:-1]), bits, "trusted-node key relay completed")