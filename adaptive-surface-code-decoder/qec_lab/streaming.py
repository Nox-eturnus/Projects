from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter_ns

import numpy as np
import stim


@dataclass(frozen=True)
class PrefixUpdate:
    group_index: int
    groups_seen: int
    detector_count_seen: int
    latency_us: float
    prediction: np.ndarray


@dataclass(frozen=True)
class PrefixDecodeResult:
    final_prediction: np.ndarray
    updates: tuple[PrefixUpdate, ...]
    total_latency_us: float
    prediction_changes: int


def detector_time_groups(
    circuit: stim.Circuit,
) -> list[np.ndarray]:
    """
    Group detector IDs by their Stim
    detector time coordinate.

    For generated surface-code circuits,
    the final coordinate is the temporal
    coordinate.
    """

    coordinates = (
        circuit.get_detector_coordinates()
    )

    if circuit.num_detectors == 0:
        raise ValueError(
            "Circuit contains no "
            "detectors."
        )

    grouped = {}

    for detector_id in range(
        circuit.num_detectors
    ):
        coord = coordinates.get(
            detector_id,
            [],
        )

        if len(coord) == 0:
            t = 0.0
        else:
            t = float(
                coord[-1]
            )

        grouped.setdefault(
            t,
            [],
        ).append(
            detector_id
        )

    result = []

    for t in sorted(grouped):
        result.append(
            np.asarray(
                grouped[t],
                dtype=int,
            )
        )

    return result


def prefix_endpoints(
    num_groups: int,
    update_stride: int,
) -> list[int]:
    """
    Return inclusive numbers of temporal
    groups available at each decoder update.

    The final full-history update is always
    included.
    """

    if num_groups < 1:
        raise ValueError(
            "num_groups must be >= 1"
        )

    if update_stride < 1:
        raise ValueError(
            "update_stride must be >= 1"
        )

    endpoints = list(
        range(
            update_stride,
            num_groups + 1,
            update_stride,
        )
    )

    if (
        not endpoints
        or endpoints[-1]
        != num_groups
    ):
        endpoints.append(
            num_groups
        )

    return endpoints


class CausalPrefixDecoder:
    """
    Causal replay proxy for streaming QEC.

    At update k, only detector groups that
    have arrived up to k are exposed.

    Future detectors are masked to zero.

    The decoder is rerun from scratch at
    each update; therefore this measures a
    causal software replay baseline, NOT an
    optimized stateful incremental decoder.

    Crucially, the final update contains all
    detector groups and must therefore agree
    with block decoding.
    """

    def __init__(
        self,
        decoder,
        circuit: stim.Circuit,
        update_stride: int = 1,
    ):
        self.decoder = decoder
        self.circuit = circuit
        self.update_stride = (
            update_stride
        )

        self.groups = (
            detector_time_groups(
                circuit
            )
        )

        self.endpoints = (
            prefix_endpoints(
                len(self.groups),
                update_stride,
            )
        )

    def decode(
        self,
        dets: np.ndarray,
    ) -> PrefixDecodeResult:
        dets = np.asarray(
            dets,
            dtype=np.uint8,
        )

        if dets.ndim != 1:
            raise ValueError(
                "Expected one detector "
                "vector."
            )

        if len(dets) != (
            self.circuit.num_detectors
        ):
            raise ValueError(
                "Detector-vector length "
                "does not match circuit."
            )

        updates = []
        previous = None
        changes = 0

        for groups_seen in (
            self.endpoints
        ):
            detector_ids = (
                np.concatenate(
                    self.groups[
                        :groups_seen
                    ]
                )
            )

            masked = np.zeros_like(
                dets
            )

            masked[
                detector_ids
            ] = dets[
                detector_ids
            ]

            start = perf_counter_ns()

            prediction = (
                self.decoder.decode(
                    masked
                )
            )

            end = perf_counter_ns()

            prediction = np.asarray(
                prediction,
                dtype=np.uint8,
            ).reshape(-1)

            if (
                previous is not None
                and np.any(
                    prediction
                    != previous
                )
            ):
                changes += 1

            previous = (
                prediction.copy()
            )

            updates.append(
                PrefixUpdate(
                    group_index=(
                        groups_seen - 1
                    ),
                    groups_seen=(
                        groups_seen
                    ),
                    detector_count_seen=(
                        len(detector_ids)
                    ),
                    latency_us=(
                        (end - start)
                        / 1000.0
                    ),
                    prediction=(
                        prediction.copy()
                    ),
                )
            )

        latencies = [
            update.latency_us
            for update in updates
        ]

        return PrefixDecodeResult(
            final_prediction=(
                updates[-1]
                .prediction
                .copy()
            ),
            updates=tuple(
                updates
            ),
            total_latency_us=float(
                np.sum(latencies)
            ),
            prediction_changes=changes,
        )