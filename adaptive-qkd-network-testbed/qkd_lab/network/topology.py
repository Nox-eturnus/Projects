from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


@dataclass
class QKDLinkState:
    u: str
    v: str
    distance_km: float
    key_bits: int
    secure_rate_bps: float
    active: bool = True
    qber: float = 0.02
    mdi_capable: bool = False

    def validate(self) -> None:
        if self.distance_km < 0:
            raise ValueError("distance_km must be non-negative")
        if self.key_bits < 0:
            raise ValueError("key_bits must be non-negative")
        if self.secure_rate_bps < 0:
            raise ValueError("secure_rate_bps must be non-negative")
        if not 0.0 <= self.qber <= 0.5:
            raise ValueError("qber must lie in [0,0.5]")


def build_graph(links: list[QKDLinkState]) -> nx.Graph:
    graph = nx.Graph()
    for link in links:
        link.validate()
        graph.add_edge(link.u, link.v, state=link)
    return graph