from __future__ import annotations

from pathlib import Path
from time import perf_counter_ns

import numpy as np
import pandas as pd

from qec_lab.circuits import (
    make_rotated_memory_circuit,
    make_uniform_noise,
)
from qec_lab.decoders import (
    MWPMDecoder,
)
from qec_lab.streaming import (
    CausalPrefixDecoder,
)


OUT_DIR = Path(
    "results/decoder_comparison"
)

SUMMARY_PATH = (
    OUT_DIR
    / "streaming_summary.csv"
)

UPDATE_PATH = (
    OUT_DIR
    / "streaming_updates.csv"
)


DISTANCES = [
    3,
    5,
    7,
    9,
]


UPDATE_STRIDES = [
    1,
    2,
    3,
]


P = 0.005

SHOTS = 2000

WARMUP = 100


def block_decode(
    decoder,
    dets,
    obs,
):
    failures = []
    predictions = []
    latencies = []

    for row in dets[:WARMUP]:
        decoder.decode(row)

    for i in range(
        WARMUP,
        len(dets),
    ):
        start = perf_counter_ns()

        pred = decoder.decode(
            dets[i]
        )

        end = perf_counter_ns()

        pred = np.asarray(
            pred,
            dtype=np.uint8,
        ).reshape(-1)

        predictions.append(pred)

        failures.append(
            int(
                np.any(
                    pred != obs[i]
                )
            )
        )

        latencies.append(
            (end - start)
            / 1000.0
        )

    return {
        "predictions": (
            np.asarray(
                predictions,
                dtype=np.uint8,
            )
        ),
        "failure_rate": float(
            np.mean(failures)
        ),
        "mean_us": float(
            np.mean(latencies)
        ),
        "p99_us": float(
            np.percentile(
                latencies,
                99,
            )
        ),
    }


def run_case(
    distance: int,
    update_stride: int,
):
    circuit = (
        make_rotated_memory_circuit(
            distance=distance,
            rounds=distance,
            noise=make_uniform_noise(
                P
            ),
            basis="x",
        )
    )

    dem = (
        circuit.detector_error_model(
            decompose_errors=True,
        )
    )

    dets, obs = (
        circuit
        .compile_detector_sampler()
        .sample(
            shots=SHOTS,
            separate_observables=True,
        )
    )

    block_decoder = MWPMDecoder(
        dem
    )

    block = block_decode(
        block_decoder,
        dets,
        obs,
    )

    stream_decoder = (
        CausalPrefixDecoder(
            decoder=MWPMDecoder(
                dem
            ),
            circuit=circuit,
            update_stride=(
                update_stride
            ),
        )
    )

    # Warmup
    for i in range(
        min(
            WARMUP,
            len(dets),
        )
    ):
        stream_decoder.decode(
            dets[i]
        )

    failures = []
    final_disagreement = []
    total_latencies = []
    update_latencies = []
    prediction_changes = []
    stability_fraction = []

    update_rows = []

    for local_i, shot_i in (
        enumerate(
            range(
                WARMUP,
                len(dets),
            )
        )
    ):
        result = (
            stream_decoder.decode(
                dets[shot_i]
            )
        )

        final_pred = (
            result.final_prediction
        )

        block_pred = (
            block[
                "predictions"
            ][local_i]
        )

        disagree = int(
            np.any(
                final_pred
                != block_pred
            )
        )

        final_disagreement.append(
            disagree
        )

        failures.append(
            int(
                np.any(
                    final_pred
                    != obs[shot_i]
                )
            )
        )

        total_latencies.append(
            result.total_latency_us
        )

        prediction_changes.append(
            result.prediction_changes
        )

        final_prediction = (
            result.final_prediction
        )

        stable_at = len(
            result.updates
        )

        # Find earliest update from which
        # the predicted logical frame never
        # changes again.
        for j in range(
            len(result.updates)
        ):
            later = (
                result.updates[j:]
            )

            if all(
                np.array_equal(
                    update.prediction,
                    final_prediction,
                )
                for update in later
            ):
                stable_at = j + 1
                break

        stability_fraction.append(
            stable_at
            / len(result.updates)
        )

        for update_number, update in (
            enumerate(
                result.updates,
                start=1,
            )
        ):
            update_latencies.append(
                update.latency_us
            )

            update_rows.append(
                {
                    "distance": (
                        distance
                    ),
                    "p": P,
                    "update_stride": (
                        update_stride
                    ),
                    "shot_id": (
                        shot_i
                    ),
                    "update_number": (
                        update_number
                    ),
                    "groups_seen": (
                        update.groups_seen
                    ),
                    "detectors_seen": (
                        update
                        .detector_count_seen
                    ),
                    "latency_us": (
                        update.latency_us
                    ),
                }
            )

    final_disagreement_rate = float(
        np.mean(
            final_disagreement
        )
    )

    if final_disagreement_rate != 0:
        raise RuntimeError(
            "FINAL PREFIX DOES NOT "
            "MATCH BLOCK MWPM. "
            f"d={distance}, "
            f"stride={update_stride}, "
            "disagreement="
            f"{final_disagreement_rate}"
        )

    failure_rate = float(
        np.mean(failures)
    )

    # Because final prediction is equal to
    # block prediction, these must agree.
    if not np.isclose(
        failure_rate,
        block["failure_rate"],
    ):
        raise RuntimeError(
            "Streaming final logical "
            "failure does not reproduce "
            "block result."
        )

    record = {
        "distance": distance,
        "p": P,
        "decoder": "mwpm",
        "mode": (
            "causal_prefix_replay"
        ),
        "update_stride": (
            update_stride
        ),
        "temporal_groups": len(
            stream_decoder.groups
        ),
        "updates_per_shot": len(
            stream_decoder.endpoints
        ),
        "samples": len(
            failures
        ),
        "logical_failure_rate": (
            failure_rate
        ),
        "block_logical_failure_rate": (
            block["failure_rate"]
        ),
        "final_block_disagreement_rate": (
            final_disagreement_rate
        ),
        "block_mean_latency_us": (
            block["mean_us"]
        ),
        "block_p99_latency_us": (
            block["p99_us"]
        ),
        "mean_update_latency_us": float(
            np.mean(
                update_latencies
            )
        ),
        "p50_update_latency_us": float(
            np.percentile(
                update_latencies,
                50,
            )
        ),
        "p95_update_latency_us": float(
            np.percentile(
                update_latencies,
                95,
            )
        ),
        "p99_update_latency_us": float(
            np.percentile(
                update_latencies,
                99,
            )
        ),
        "mean_total_replay_latency_us": (
            float(
                np.mean(
                    total_latencies
                )
            )
        ),
        "p99_total_replay_latency_us": (
            float(
                np.percentile(
                    total_latencies,
                    99,
                )
            )
        ),
        "mean_prediction_changes": (
            float(
                np.mean(
                    prediction_changes
                )
            )
        ),
        "mean_stability_fraction": (
            float(
                np.mean(
                    stability_fraction
                )
            )
        ),
    }

    return record, update_rows


def main():
    OUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    summaries = []
    update_rows = []

    for distance in DISTANCES:
        for stride in UPDATE_STRIDES:
            record, updates = (
                run_case(
                    distance=distance,
                    update_stride=stride,
                )
            )

            summaries.append(
                record
            )

            update_rows.extend(
                updates
            )

            print(record)

    summary = pd.DataFrame(
        summaries
    )

    summary.to_csv(
        SUMMARY_PATH,
        index=False,
    )

    pd.DataFrame(
        update_rows
    ).to_csv(
        UPDATE_PATH,
        index=False,
    )

    print()
    print(
        "=== STREAMING SUMMARY ==="
    )

    print(
        summary.to_string(
            index=False
        )
    )

    print()
    print("Saved:", SUMMARY_PATH)
    print("Saved:", UPDATE_PATH)


if __name__ == "__main__":
    main()