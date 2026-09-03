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


def action_is_feasible(action: QKDAction, *, mdi_capable: bool) -> bool:
    if action.protocol == "mdi_qkd" and not mdi_capable:
        return False
    return action.protocol in {"decoy_bb84", "mdi_qkd"}