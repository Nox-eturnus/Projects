from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QKDAction:
    protocol: str
    mu_signal: float
    mu_decoy: float
    p_key_basis: float
    block_size: int

    @property
    def name(self) -> str:
        return (
            f"{self.protocol}|mu={self.mu_signal:.2f}|nu={self.mu_decoy:.2f}"
            f"|p={self.p_key_basis:.2f}|N={self.block_size}"
        )

    @property
    def duration_seconds(self) -> float:
        """Physical accumulation time in seconds assuming a 1 GHz source clock."""
        return self.block_size / 1.0e9


def candidate_actions() -> list[QKDAction]:
    actions: list[QKDAction] = []
    for protocol in ("decoy_bb84", "mdi_qkd"):
        for mu in (0.40, 0.55):
            for nu in (0.05, 0.10):
                if nu >= mu:
                    continue
                for p in (0.80, 0.90):
                    for n in (10_000_000_000, 100_000_000_000):
                        actions.append(QKDAction(protocol, mu, nu, p, n))
    return actions


def action_is_feasible(action: QKDAction, *, mdi_capable: bool = True, has_charlie: bool = True) -> bool:
    if action.protocol == "mdi_qkd":
        if not mdi_capable or not has_charlie:
            return False
    return action.protocol in {"decoy_bb84", "mdi_qkd"}


def parse_action_name(action_name: str) -> QKDAction | None:
    if action_name in ("ABORT", "HEURISTIC") or not action_name:
        return None
    try:
        parts = action_name.split("|")
        protocol = parts[0]
        mu = float(parts[1].split("=")[1])
        nu = float(parts[2].split("=")[1])
        p = float(parts[3].split("=")[1])
        n = int(parts[4].split("=")[1])
        return QKDAction(protocol, mu, nu, p, n)
    except Exception:
        return None