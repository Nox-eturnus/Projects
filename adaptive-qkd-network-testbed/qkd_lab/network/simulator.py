from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
import networkx as nx

from qkd_lab.models import (
    BasisProbabilities,
    ChannelParameters,
    DetectorParameters,
    IntensitySetting,
)
from qkd_lab.network.qos import QKDNQoSRequest, ServiceResult
from qkd_lab.network.routing import find_secure_path, path_links
from qkd_lab.protocols.decoy_bb84 import expected_decoy_bb84_block
from qkd_lab.estimation.finite_key_bb84 import estimate_lim2014
from qkd_lab.protocols.mdi_qkd import (
    MDIBasisProbabilities,
    MDIPhysicalParameters,
    expected_mdi_block,
)
from qkd_lab.estimation.finite_key_mdi import MDIFiniteKeyBudget, estimate_mdi_finite_key


class QKDExecutionStatus(str, Enum):
    SECURE_KEY = "SECURE_KEY"
    SECURITY_ABORT = "SECURITY_ABORT"
    ESTIMATOR_INFEASIBLE = "ESTIMATOR_INFEASIBLE"
    MODEL_ERROR = "MODEL_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"


@dataclass(frozen=True)
class QKDPhysicsOutcome:
    status: QKDExecutionStatus
    secure_bits: int
    protocol: str
    phase_error: float = 0.0
    details: str = ""

    def __int__(self) -> int:
        return self.secure_bits


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
    key_store: Any | None = None,
) -> dict[tuple[str, str], QKDPhysicsOutcome]:
    """Replenish link key pools from physical finite-key QKD block simulation.
    
    Supports both Decoy-BB84 and MDI-QKD based on link topology capabilities.
    Classifies outcomes with explicit status codes rather than silently swallowing errors.
    """
    generated: dict[tuple[str, str], QKDPhysicsOutcome] = {}
    bb84_intensities = (
        IntensitySetting("signal", 0.50, 0.80),
        IntensitySetting("decoy", 0.10, 0.15),
        IntensitySetting("vacuum", 0.0002, 0.05),
    )
    bb84_basis = BasisProbabilities(0.90, 0.90)

    mdi_intensities = (
        IntensitySetting("signal", 0.40, 0.80),
        IntensitySetting("decoy", 0.10, 0.15),
        IntensitySetting("vacuum", 0.0002, 0.05),
    )
    mdi_basis = MDIBasisProbabilities(0.90, 0.90)

    for u, v, data in graph.edges(data=True):
        link = data["state"]
        if not link.active:
            generated[(u, v)] = QKDPhysicsOutcome(
                status=QKDExecutionStatus.SECURITY_ABORT,
                secure_bits=0,
                protocol="none",
                details="link inactive",
            )
            continue

        try:
            if link.mdi_capable and link.charlie_node is not None:
                protocol = "mdi_qkd"
                lac = link.length_ac_km if link.length_ac_km is not None else link.distance_km / 2.0
                lbc = link.length_bc_km if link.length_bc_km is not None else link.distance_km / 2.0
                physical = MDIPhysicalParameters(
                    alice_to_charlie_km=lac,
                    bob_to_charlie_km=lbc,
                    attenuation_db_per_km=0.20,
                    detector_efficiency=0.60,
                    dark_probability=1.0e-7,
                    misalignment=link.qber if link.qber is not None else 0.015,
                )
                block = expected_mdi_block(
                    pulses_per_link,
                    alice_intensities=mdi_intensities,
                    bob_intensities=mdi_intensities,
                    basis=mdi_basis,
                    physical=physical,
                )
                budget = MDIFiniteKeyBudget(
                    failure_probability=eps_sec,
                    eps_cor=eps_cor,
                    eps_prime=eps_sec / 100.0,
                    eps_hat=eps_sec / 100.0,
                    eps_e=eps_sec / 100.0,
                    eps_b=eps_sec / 100.0,
                    eps_0=eps_sec / 100.0,
                    eps_1=eps_sec / 100.0,
                    eps_pa=eps_sec / 100.0,
                )
                mdi_res = estimate_mdi_finite_key(block, budget)
                new_bits = int(mdi_res.secure_bits) if not mdi_res.abort else 0
                phase_err = float(mdi_res.phase_error_upper)
                status = QKDExecutionStatus.SECURE_KEY if new_bits > 0 else QKDExecutionStatus.SECURITY_ABORT
                details = f"MDI via Charlie relay {link.charlie_node}"
            else:
                protocol = "decoy_bb84"
                channel = ChannelParameters(link.distance_km, 0.20)
                detector = DetectorParameters(0.25, 1.0e-7, link.qber if link.qber is not None else 0.015, 2)
                block = expected_decoy_bb84_block(
                    pulses_per_link,
                    intensities=bb84_intensities,
                    basis=bb84_basis,
                    channel=channel,
                    detector=detector,
                )
                fk = estimate_lim2014(
                    block.records,
                    bb84_intensities,
                    eps_sec=eps_sec,
                    eps_cor=eps_cor,
                )
                new_bits = int(fk.secure_bits) if not fk.abort else 0
                phase_err = float(fk.phase_error_upper)
                status = QKDExecutionStatus.SECURE_KEY if new_bits > 0 else QKDExecutionStatus.SECURITY_ABORT
                details = f"BB84 direct fiber {link.distance_km}km"

            outcome = QKDPhysicsOutcome(
                status=status,
                secure_bits=new_bits,
                protocol=protocol,
                phase_error=phase_err,
                details=details,
            )
        except ValueError as exc:
            outcome = QKDPhysicsOutcome(
                status=QKDExecutionStatus.CONFIGURATION_ERROR,
                secure_bits=0,
                protocol="unknown",
                details=str(exc),
            )
        except (ArithmeticError, RuntimeError) as exc:
            outcome = QKDPhysicsOutcome(
                status=QKDExecutionStatus.ESTIMATOR_INFEASIBLE,
                secure_bits=0,
                protocol="unknown",
                details=str(exc),
            )
        except Exception as exc:
            outcome = QKDPhysicsOutcome(
                status=QKDExecutionStatus.MODEL_ERROR,
                secure_bits=0,
                protocol="unknown",
                details=str(exc),
            )

        link.key_bits += outcome.secure_bits
        storable_bits = (outcome.secure_bits // 8) * 8
        if key_store is not None and storable_bits > 0 and getattr(link, "key_store", None) is None:
            if hasattr(key_store, "deposit_reservoir_bits"):
                key_store.deposit_reservoir_bits(
                    peer_id=v,
                    bits=storable_bits,
                    protocol=outcome.protocol,
                    eps_sec=eps_sec,
                    eps_cor=eps_cor,
                    initiator_sae_id=u,
                    target_sae_id=v,
                )
            elif isinstance(key_store, dict) and u in key_store and hasattr(key_store[u], "deposit_reservoir_bits"):
                key_store[u].deposit_reservoir_bits(
                    peer_id=v,
                    bits=storable_bits,
                    protocol=outcome.protocol,
                    eps_sec=eps_sec,
                    eps_cor=eps_cor,
                    initiator_sae_id=u,
                    target_sae_id=v,
                )
            elif hasattr(key_store, "add_key"):
                key_store.add_key(
                    peer_id=v,
                    bits=storable_bits,
                    protocol=outcome.protocol,
                    eps_sec=eps_sec,
                    eps_cor=eps_cor,
                    initiator_sae_id=u,
                    target_sae_id=v,
                )
        generated[(u, v)] = outcome

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