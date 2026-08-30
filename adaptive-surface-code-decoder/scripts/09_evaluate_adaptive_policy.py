from pathlib import Path
from time import perf_counter_ns

import numpy as np
import pandas as pd

from qec_lab.adaptive import (
    DensityBinPolicy,
    make_feature_frame,
)
from qec_lab.circuits import (
    make_rotated_memory_circuit,
    make_uniform_noise,
)
from qec_lab.decoders import (
    BPOSDDecoder,
    CorrelatedMWPMDecoder,
    MWPMDecoder,
    UnionFindSurfaceDecoder,
)


HELD_OUT_P = [
    0.003,
    0.005,
    0.007,
]

DISTANCES = [
    3,
    5,
    7,
    9,
]


def evaluate_scenario(
    distance: int,
    p: float,
    shots: int,
):
    circuit = make_rotated_memory_circuit(
        distance=distance,
        rounds=distance,
        noise=make_uniform_noise(p),
        basis="x",
    )

    dem = circuit.detector_error_model(
        decompose_errors=True,
    )

    dets, obs = (
        circuit
        .compile_detector_sampler()
        .sample(
            shots=shots,
            separate_observables=True,
        )
    )

    features = make_feature_frame(
        dets=dets,
        distance=distance,
        p=p,
        bias_ratio=1.0,
        rounds=distance,
    )

    decoders = [
        MWPMDecoder(dem),
        CorrelatedMWPMDecoder(dem),
        UnionFindSurfaceDecoder(dem),
        BPOSDDecoder(dem),
    ]

    rows = []

    for decoder in decoders:
        for row in dets[:100]:
            decoder.decode(row)

        for i in range(
            100,
            len(dets),
        ):
            start = perf_counter_ns()
            pred = decoder.decode(
                dets[i]
            )
            end = perf_counter_ns()

            rows.append(
                {
                    "scenario_id": (
                        f"d{distance}_p{p}"
                    ),
                    "shot_id": i,
                    "distance": distance,
                    "p": p,
                    "rho": float(
                        features.iloc[i][
                            "rho"
                        ]
                    ),
                    "decoder": decoder.name,
                    "latency_us": (
                        end - start
                    ) / 1000.0,
                    "failure": int(
                        np.any(
                            pred != obs[i]
                        )
                    ),
                }
            )

    return rows


def summarize_fixed(
    samples: pd.DataFrame,
):
    return (
        samples
        .groupby(
            "decoder",
            as_index=False,
        )
        .agg(
            logical_failure_rate=(
                "failure",
                "mean",
            ),
            mean_us=(
                "latency_us",
                "mean",
            ),
            p95_us=(
                "latency_us",
                lambda x: np.percentile(
                    x,
                    95,
                ),
            ),
            p99_us=(
                "latency_us",
                lambda x: np.percentile(
                    x,
                    99,
                ),
            ),
        )
    )


def apply_adaptive_policy(
    samples: pd.DataFrame,
    policy_table: pd.DataFrame,
    budget_us: float,
):
    policy = DensityBinPolicy(
        table=policy_table,
        budget_us=budget_us,
    )

    selected_rows = []

    grouped = samples.groupby(
        [
            "scenario_id",
            "shot_id",
        ],
        sort=False,
    )

    for _, group in grouped:
        first = group.iloc[0]

        try:
            selected = policy.select(
                rho=float(
                    first["rho"]
                ),
                distance=int(
                    first["distance"]
                ),
            )
        except RuntimeError:
            continue

        chosen = group[
            group["decoder"].eq(
                selected
            )
        ]

        if chosen.empty:
            continue

        selected_rows.append(
            chosen.iloc[0]
        )

    selected_df = pd.DataFrame(
        selected_rows
    )

    if selected_df.empty:
        raise RuntimeError(
            "Adaptive policy selected "
            "no feasible held-out shots."
        )

    return selected_df


def oracle_summary(
    samples: pd.DataFrame,
):
    oracle_rows = []

    grouped = samples.groupby(
        [
            "scenario_id",
            "shot_id",
        ],
        sort=False,
    )

    for _, group in grouped:
        successful = group[
            group["failure"].eq(0)
        ]

        if successful.empty:
            chosen = group.sort_values(
                "latency_us"
            ).iloc[0]
        else:
            chosen = successful.sort_values(
                "latency_us"
            ).iloc[0]

        oracle_rows.append(chosen)

    return pd.DataFrame(
        oracle_rows
    )


def main():
    out_dir = Path(
        "results/adaptive"
    )
    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = []

    for d in DISTANCES:
        for p in HELD_OUT_P:
            rows.extend(
                evaluate_scenario(
                    distance=d,
                    p=p,
                    shots=3000,
                )
            )

    samples = pd.DataFrame(rows)

    samples.to_parquet(
        out_dir
        / "heldout_samples.parquet",
        index=False,
    )

    policy_table = pd.read_csv(
        out_dir
        / "policy_table.csv"
    )

    fixed = summarize_fixed(
        samples
    )
    fixed["strategy"] = (
        "fixed_"
        + fixed["decoder"]
    )

    min_p99_by_distance = (
        policy_table
        .groupby("distance")["p99_us"]
        .min()
    )

    minimum_global_feasible_budget = float(
        min_p99_by_distance.max()
    )

    budget_us = (
        1.25
        * minimum_global_feasible_budget
    )

    print(
        "Minimum P99 by distance:"
    )
    print(min_p99_by_distance)

    print(
        "Minimum globally feasible budget:",
        minimum_global_feasible_budget,
        "us",
    )

    print(
        "Evaluation budget:",
        budget_us,
        "us",
    )

    adaptive = apply_adaptive_policy(
        samples=samples,
        policy_table=policy_table,
        budget_us=budget_us,
    )

    adaptive_summary = pd.DataFrame(
        [
            {
                "strategy": "adaptive",
                "decoder": "mixed",
                "logical_failure_rate": float(
                    adaptive[
                        "failure"
                    ].mean()
                ),
                "mean_us": float(
                    adaptive[
                        "latency_us"
                    ].mean()
                ),
                "p95_us": float(
                    np.percentile(
                        adaptive[
                            "latency_us"
                        ],
                        95,
                    )
                ),
                "p99_us": float(
                    np.percentile(
                        adaptive[
                            "latency_us"
                        ],
                        99,
                    )
                ),
                "deadline_violation_rate": float(
                    (
                        adaptive[
                            "latency_us"
                        ]
                        > budget_us
                    ).mean()
                ),
            }
        ]
    )

    oracle = oracle_summary(
        samples
    )

    oracle_summary_df = pd.DataFrame(
        [
            {
                "strategy": "oracle_hindsight",
                "decoder": "mixed",
                "logical_failure_rate": float(
                    oracle[
                        "failure"
                    ].mean()
                ),
                "mean_us": float(
                    oracle[
                        "latency_us"
                    ].mean()
                ),
                "p95_us": float(
                    np.percentile(
                        oracle[
                            "latency_us"
                        ],
                        95,
                    )
                ),
                "p99_us": float(
                    np.percentile(
                        oracle[
                            "latency_us"
                        ],
                        99,
                    )
                ),
                "deadline_violation_rate": float(
                    (
                        oracle[
                            "latency_us"
                        ]
                        > budget_us
                    ).mean()
                ),
            }
        ]
    )

    fixed["deadline_violation_rate"] = (
        np.nan
    )

    summary = pd.concat(
        [
            fixed,
            adaptive_summary,
            oracle_summary_df,
        ],
        ignore_index=True,
        sort=False,
    )

    summary.to_csv(
        out_dir
        / "heldout_results.csv",
        index=False,
    )

    adaptive[
        "decoder"
    ].value_counts(
        normalize=True
    ).rename(
        "fraction"
    ).to_csv(
        out_dir
        / "adaptive_decoder_mix.csv"
    )

    print(summary)


if __name__ == "__main__":
    main()