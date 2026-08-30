import numpy as np
import pandas as pd

from qec_lab.adaptive import (
    DensityBinPolicy,
)


def build_table(
    df: pd.DataFrame,
) -> pd.DataFrame:
    max_rho = max(
        0.05,
        float(df["rho"].max()),
    )

    bins = np.linspace(
        0.0,
        max_rho,
        21,
    )

    df = df.copy()

    df["rho_bin"] = pd.cut(
        df["rho"],
        bins=bins,
        include_lowest=True,
        duplicates="drop",
    )

    grouped = (
        df
        .groupby(
            [
                "distance",
                "decoder",
                "rho_bin",
            ],
            observed=True,
        )
        .agg(
            logical_failure_rate=(
                "failure",
                "mean",
            ),
            p50_us=(
                "latency_us",
                lambda x: np.percentile(
                    x,
                    50,
                ),
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
            samples=(
                "failure",
                "size",
            ),
        )
        .reset_index()
    )

    grouped[
        "rho_mid"
    ] = grouped[
        "rho_bin"
    ].map(
        lambda interval: (
            interval.mid
        )
    )

    return grouped


def main():
    df = pd.read_parquet(
        "results/adaptive/"
        "policy_samples.parquet"
    )

    table = build_table(df)

    table.to_csv(
        "results/adaptive/"
        "policy_table.csv",
        index=False,
    )

    budget_us = 20.0

    policy = DensityBinPolicy(
        table=table,
        budget_us=budget_us,
    )

    for d in [
        3,
        5,
        7,
        9,
    ]:
        for rho in [
            0.001,
            0.005,
            0.010,
            0.020,
        ]:
            try:
                selected = (
                    policy.select(
                        rho=rho,
                        distance=d,
                    )
                )
            except RuntimeError:
                selected = None

            print(
                {
                    "d": d,
                    "rho": rho,
                    "budget_us": (
                        budget_us
                    ),
                    "selected": (
                        selected
                    ),
                }
            )


if __name__ == "__main__":
    main()