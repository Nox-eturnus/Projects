from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SecurityAssumptions:
    phase_randomized_wcp: bool = True
    authenticated_classical_channel: bool = True
    trusted_source_model: bool = True
    direct_bb84_detector_trusted: bool = True
    mdi_measurement_station_untrusted: bool = True
    trusted_nodes_for_multihop: bool = True

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)

    def validate_core(self) -> None:
        if not self.phase_randomized_wcp:
            raise ValueError("decoy-state analysis requires the registered phase-randomized WCP assumption")
        if not self.authenticated_classical_channel:
            raise ValueError("QKD requires an authenticated classical channel")