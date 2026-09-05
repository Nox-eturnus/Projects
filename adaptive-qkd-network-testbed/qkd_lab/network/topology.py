from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx


class QKDLinkState:
    u: str
    v: str
    distance_km: float
    secure_rate_bps: float
    active: bool = True
    qber: float = 0.02
    mdi_capable: bool = False
    charlie_node: str | None = None
    length_ac_km: float | None = None
    length_bc_km: float | None = None
    key_store: Any | None = None

    def __init__(
        self,
        u: str,
        v: str,
        distance_km: float,
        key_bits: int,
        secure_rate_bps: float,
        active: bool = True,
        qber: float = 0.02,
        mdi_capable: bool = False,
        charlie_node: str | None = None,
        length_ac_km: float | None = None,
        length_bc_km: float | None = None,
        key_store: Any | None = None,
    ) -> None:
        self.u = u
        self.v = v
        self.distance_km = distance_km
        self.secure_rate_bps = secure_rate_bps
        self.active = active
        self.qber = qber
        self.mdi_capable = mdi_capable
        self.charlie_node = charlie_node
        self.length_ac_km = length_ac_km
        self.length_bc_km = length_bc_km
        self.key_store = key_store
        self._key_bits = 0
        if self.key_store is not None and key_bits > 0:
            if hasattr(self.key_store, "deposit_reservoir_bits"):
                self.key_store.deposit_reservoir_bits(
                    peer_id=self.v,
                    bits=key_bits,
                    initiator_sae_id=self.u,
                    target_sae_id=self.v,
                )
        else:
            self._key_bits = key_bits
        self.__post_init__()

    @property
    def key_bits(self) -> int:
        if self.key_store is not None and hasattr(self.key_store, "available_bits"):
            return self.key_store.available_bits(peer_id=self.v, initiator_sae_id=self.u)
        return self._key_bits

    @key_bits.setter
    def key_bits(self, val: int) -> None:
        if self.key_store is not None and hasattr(self.key_store, "available_bits"):
            current = self.key_store.available_bits(peer_id=self.v, initiator_sae_id=self.u)
            diff = val - current
            if diff > 0:
                self.key_store.deposit_reservoir_bits(
                    peer_id=self.v,
                    bits=diff,
                    initiator_sae_id=self.u,
                    target_sae_id=self.v,
                )
            elif diff < 0:
                self.key_store.consume_bits(
                    peer_id=self.v,
                    bits=-diff,
                    initiator_sae_id=self.u,
                )
        else:
            self._key_bits = val

    def __post_init__(self) -> None:
        if self.charlie_node is not None:
            self.mdi_capable = True
            if self.length_ac_km is None and self.length_bc_km is None:
                self.length_ac_km = self.distance_km / 2.0
                self.length_bc_km = self.distance_km / 2.0
            elif self.length_ac_km is None:
                self.length_ac_km = max(0.0, self.distance_km - (self.length_bc_km or 0.0))
            elif self.length_bc_km is None:
                self.length_bc_km = max(0.0, self.distance_km - (self.length_ac_km or 0.0))
        elif self.mdi_capable:
            if self.length_ac_km is None:
                self.length_ac_km = self.distance_km / 2.0
            if self.length_bc_km is None:
                self.length_bc_km = self.distance_km / 2.0

    def validate(self) -> None:
        if self.distance_km < 0:
            raise ValueError("distance_km must be non-negative")
        if self.key_bits < 0:
            raise ValueError("key_bits must be non-negative")
        if self.secure_rate_bps < 0:
            raise ValueError("secure_rate_bps must be non-negative")
        if not 0.0 <= self.qber <= 0.5:
            raise ValueError("qber must lie in [0,0.5]")
        if self.length_ac_km is not None and self.length_ac_km < 0:
            raise ValueError("length_ac_km must be non-negative")
        if self.length_bc_km is not None and self.length_bc_km < 0:
            raise ValueError("length_bc_km must be non-negative")


def build_graph(links: list[QKDLinkState]) -> nx.Graph:
    graph = nx.Graph()
    for link in links:
        link.validate()
        graph.add_edge(link.u, link.v, state=link)
    return graph


def build_physical_topology_graph(links: list[QKDLinkState]) -> nx.Graph:
    """Build a detailed physical graph including untrusted Charlie BSM nodes for MDI links."""
    graph = nx.Graph()
    for link in links:
        link.validate()
        if link.mdi_capable and link.charlie_node:
            # Physical bipartite fiber links to central untrusted Charlie BSM station
            c = link.charlie_node
            lac = link.length_ac_km if link.length_ac_km is not None else link.distance_km / 2.0
            lbc = link.length_bc_km if link.length_bc_km is not None else link.distance_km / 2.0
            graph.add_node(c, node_type="untrusted_bsm_relay", label=f"Charlie ({c})")
            graph.add_node(link.u, node_type="trusted_endpoint")
            graph.add_node(link.v, node_type="trusted_endpoint")
            graph.add_edge(link.u, c, distance_km=lac, role="alice_arm")
            graph.add_edge(c, link.v, distance_km=lbc, role="bob_arm")
        else:
            graph.add_node(link.u, node_type="trusted_endpoint")
            graph.add_node(link.v, node_type="trusted_endpoint")
            graph.add_edge(link.u, link.v, distance_km=link.distance_km, role="direct_fiber")
    return graph