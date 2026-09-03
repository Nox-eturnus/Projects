from __future__ import annotations

from math import inf

import networkx as nx

from qkd_lab.network.topology import QKDLinkState


def edge_cost(link: QKDLinkState, demand_bits: int) -> float:
    if not link.active or link.key_bits < demand_bits or link.secure_rate_bps <= 0.0:
        return inf
    reserve_penalty = demand_bits / max(link.key_bits, 1)
    rate_penalty = demand_bits / max(link.secure_rate_bps, 1e-9)
    qber_penalty = 10.0 * link.qber
    return 1.0 + reserve_penalty + rate_penalty + qber_penalty


def find_secure_path(graph: nx.Graph, source: str, target: str, demand_bits: int) -> list[str] | None:
    work = nx.Graph()
    for u, v, data in graph.edges(data=True):
        link: QKDLinkState = data["state"]
        cost = edge_cost(link, demand_bits)
        if cost != inf:
            work.add_edge(u, v, weight=cost)
    try:
        return nx.shortest_path(work, source, target, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def path_links(graph: nx.Graph, path: list[str]) -> list[QKDLinkState]:
    return [graph[path[i]][path[i + 1]]["state"] for i in range(len(path) - 1)]