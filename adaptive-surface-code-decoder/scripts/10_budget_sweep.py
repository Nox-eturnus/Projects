from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from qec_lab.adaptive import (
    DensityBinPolicy,
)


BUDGETS_US = [
    2.0,
    5.0,
    10.0,
    20.0,
    50.0,
    100.0,
]


def evaluate_budget(
    samples: pd.DataFrame,
    table: pd.DataFrame,
    budget_us: float,
):
    policy = DensityBinPolicy(
        table=table,
        budget_us=budget_us,
    )

    selected = []
    infeasible = 0

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
            decoder_name = (
                policy.select(
                    rho=float(
                        first["rho"]
                    ),
                    distance=int(
                        first["distance"]
                    ),
                )
            )
        except RuntimeError:
            infeasible += 1
            continue

        chosen = group[
            group["decoder"].eq(
                decoder_name
            )
        ]

        if chosen.empty:
            infeasible += 1
            continue

        selected.append(
            chosen.iloc[0]
        )

    if not selected:
        return {
            "budget_us": budget_us,
            "logical_failure_rate": np.nan,
            "mean_us": np.nan,
            "p99_us": np.nan,
            "deadline_violation_rate": np.nan,
            "no_feasible_fraction": 1.0,
        }, {}

    selected_df = pd.DataFrame(
        selected
    )

    total_groups = (
        samples[
            [
                "scenario_id",
                "shot_id",
            ]
        ]
        .drop_duplicates()
        .shape[0]
    )

    mix = (
        selected_df[
            "decoder"
        ]
        .value_counts(
            normalize=True
        )
        .to_dict()
    )

    return {
        "budget_us": budget_us,
        "logical_failure_rate": float(
            selected_df[
                "failure"
            ].mean()
        ),
        "mean_us": float(
            selected_df[
                "latency_us"
            ].mean()
        ),
        "p99_us": float(
            np.percentile(
                selected_df[
                    "latency_us"
                ],
                99,
            )
        ),
        "deadline_violation_rate": float(
            (
                selected_df[
                    "latency_us"
                ]
                > budget_us
            ).mean()
        ),
        "no_feasible_fraction": float(
            infeasible
            / total_groups
        ),
    }, mix


def main():
    out_dir = Path(
        "results/adaptive"
    )
    fig_dir = Path(
        "results/figures"
    )
    fig_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    samples = pd.read_parquet(
        out_dir
        / "heldout_samples.parquet"
    )

    table = pd.read_csv(
        out_dir
        / "policy_table.csv"
    )

    rows = []
    mix_rows = []

    for budget in BUDGETS_US:
        summary, mix = (
            evaluate_budget(
                samples,
                table,
                budget,
            )
        )

        rows.append(summary)

        for decoder, fraction in (
            mix.items()
        ):
            mix_rows.append(
                {
                    "budget_us": budget,
                    "decoder": decoder,
                    "fraction": fraction,
                }
            )

        print(summary)

    df = pd.DataFrame(rows)
    df.to_csv(
        out_dir
        / "budget_sweep.csv",
        index=False,
    )

    pd.DataFrame(
        mix_rows
    ).to_csv(
        out_dir
        / "budget_decoder_mix.csv",
        index=False,
    )

    valid = df.dropna(
        subset=[
            "logical_failure_rate",
            "p99_us",
        ]
    )

    plt.figure()
    plt.plot(
        valid["p99_us"],
        valid[
            "logical_failure_rate"
        ],
        marker="o",
    )
    plt.xlabel(
        "Observed P99 decoder latency (us)"
    )
    plt.ylabel(
        "Held-out logical failure rate"
    )
    plt.tight_layout()
    plt.savefig(
        fig_dir
        / "pareto_frontier.png",
        dpi=200,
    )
    plt.close()


if __name__ == "__main__":
    main()