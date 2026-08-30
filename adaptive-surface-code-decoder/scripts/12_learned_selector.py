from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeRegressor

from qec_lab.adaptive import DensityBinPolicy


OUT_DIR = Path("results/adaptive")

CALIBRATION_PATH = (
    OUT_DIR / "policy_samples.parquet"
)

HELDOUT_PATH = (
    OUT_DIR / "heldout_samples.parquet"
)

POLICY_TABLE_PATH = (
    OUT_DIR / "policy_table.csv"
)

MODEL_PATH = (
    OUT_DIR / "learned_selector.pkl"
)

CONFIG_PATH = (
    OUT_DIR
    / "learned_selector_config.json"
)

DECISIONS_PATH = (
    OUT_DIR
    / "learned_selector_decisions.parquet"
)

SWEEP_PATH = (
    OUT_DIR
    / "learned_selector_budget_sweep.csv"
)

MIX_PATH = (
    OUT_DIR
    / "learned_selector_decoder_mix.csv"
)


# Covers:
# strict real-time regime
# through progressively relaxed regimes.
BUDGETS_US = [
    20.0,
    50.0,
    100.0,
    200.0,
    500.0,
    1000.0,
    5000.0,
    20000.0,
    100000.0,
]


DECODERS = [
    "mwpm",
    "mwpm_correlated",
    "union_find",
    "bp_osd",
]


FEATURE_COLUMNS = [
    "rho",
    "distance",
    "p",
    "rounds",
    "bias_ratio",
]


def prepare_frames(
    calibration: pd.DataFrame,
    heldout: pd.DataFrame,
):
    calibration = calibration.copy()
    heldout = heldout.copy()

    # Phase 16 held-out samples do not
    # necessarily store these because they
    # are fixed by the experimental design.
    if "rounds" not in heldout.columns:
        heldout["rounds"] = (
            heldout["distance"]
        )

    if "bias_ratio" not in heldout.columns:
        heldout["bias_ratio"] = 1.0

    if "rounds" not in calibration.columns:
        calibration["rounds"] = (
            calibration["distance"]
        )

    if (
        "bias_ratio"
        not in calibration.columns
    ):
        calibration["bias_ratio"] = 1.0

    return calibration, heldout


def validate_split(
    calibration: pd.DataFrame,
    heldout: pd.DataFrame,
):
    calibration_p = {
        float(x)
        for x
        in calibration["p"].unique()
    }

    heldout_p = {
        float(x)
        for x
        in heldout["p"].unique()
    }

    overlap = (
        calibration_p
        & heldout_p
    )

    print(
        "Calibration p:",
        sorted(calibration_p),
    )

    print(
        "Held-out p:",
        sorted(heldout_p),
    )

    if overlap:
        raise RuntimeError(
            "TRAIN/TEST LEAKAGE: "
            "overlapping p values: "
            f"{sorted(overlap)}"
        )

    required = {
        "scenario_id",
        "shot_id",
        "rho",
        "distance",
        "p",
        "decoder",
        "latency_us",
        "failure",
    }

    for name, frame in [
        ("calibration", calibration),
        ("heldout", heldout),
    ]:
        missing = (
            required
            - set(frame.columns)
        )

        if missing:
            raise ValueError(
                f"{name} missing: "
                f"{sorted(missing)}"
            )


def build_training_table(
    calibration: pd.DataFrame,
) -> pd.DataFrame:
    """
    Do not train directly on noisy 0/1
    per-shot failure labels.

    Aggregate nearby syndrome workloads and
    predict:
        1. logical failure risk
        2. P99 decoder latency
    """

    df = calibration.copy()

    max_rho = max(
        0.05,
        float(df["rho"].max()),
    )

    bins = np.linspace(
        0.0,
        max_rho,
        21,
    )

    df["rho_bin"] = pd.cut(
        df["rho"],
        bins=bins,
        include_lowest=True,
        duplicates="drop",
    )

    grouped = (
        df.groupby(
            [
                "decoder",
                "distance",
                "p",
                "rounds",
                "bias_ratio",
                "rho_bin",
            ],
            observed=True,
        )
        .agg(
            rho=(
                "rho",
                "mean",
            ),
            failure_risk=(
                "failure",
                "mean",
            ),
            latency_p99_us=(
                "latency_us",
                lambda x: float(
                    np.percentile(
                        x,
                        99,
                    )
                ),
            ),
            samples=(
                "failure",
                "size",
            ),
        )
        .reset_index()
    )

    grouped = grouped[
        grouped["samples"] > 0
    ].copy()

    return grouped


def train_models(
    training: pd.DataFrame,
):
    models = {}

    for decoder in DECODERS:
        subset = training[
            training["decoder"]
            == decoder
        ].copy()

        if subset.empty:
            print(
                "Skipping:",
                decoder,
            )
            continue

        x = subset[
            FEATURE_COLUMNS
        ]

        failure_model = (
            DecisionTreeRegressor(
                max_depth=6,
                min_samples_leaf=5,
                random_state=7,
            )
        )

        latency_model = (
            DecisionTreeRegressor(
                max_depth=6,
                min_samples_leaf=5,
                random_state=11,
            )
        )

        failure_model.fit(
            x,
            subset[
                "failure_risk"
            ],
        )

        latency_model.fit(
            x,
            subset[
                "latency_p99_us"
            ],
        )

        models[decoder] = {
            "failure": failure_model,
            "latency": latency_model,
        }

        print(
            {
                "decoder": decoder,
                "training_rows": (
                    len(subset)
                ),
            }
        )

    if not models:
        raise RuntimeError(
            "No models trained."
        )

    return models


def make_context(
    heldout: pd.DataFrame,
):
    return (
        heldout[
            [
                "scenario_id",
                "shot_id",
                "rho",
                "distance",
                "p",
                "rounds",
                "bias_ratio",
            ]
        ]
        .drop_duplicates(
            [
                "scenario_id",
                "shot_id",
            ]
        )
        .reset_index(
            drop=True
        )
    )


def learned_decisions(
    context: pd.DataFrame,
    models,
    budget_us: float,
):
    rows = []

    for _, shot in (
        context.iterrows()
    ):
        x = pd.DataFrame(
            [
                {
                    key: shot[key]
                    for key
                    in FEATURE_COLUMNS
                }
            ]
        )

        candidates = []

        for decoder, pair in (
            models.items()
        ):
            risk = float(
                pair[
                    "failure"
                ].predict(x)[0]
            )

            p99 = float(
                pair[
                    "latency"
                ].predict(x)[0]
            )

            candidates.append(
                {
                    "decoder": decoder,
                    "predicted_failure": (
                        risk
                    ),
                    "predicted_p99_us": (
                        p99
                    ),
                }
            )

        feasible = [
            x
            for x in candidates
            if (
                x["predicted_p99_us"]
                <= budget_us
            )
        ]

        if feasible:
            best = min(
                feasible,
                key=lambda x: (
                    x[
                        "predicted_failure"
                    ],
                    x[
                        "predicted_p99_us"
                    ],
                ),
            )

            selected = (
                best["decoder"]
            )

            risk = (
                best[
                    "predicted_failure"
                ]
            )

            predicted_p99 = (
                best[
                    "predicted_p99_us"
                ]
            )

        else:
            selected = (
                "NO_FEASIBLE_DECODER"
            )
            risk = np.nan
            predicted_p99 = np.nan

        rows.append(
            {
                "scenario_id": (
                    shot[
                        "scenario_id"
                    ]
                ),
                "shot_id": (
                    shot["shot_id"]
                ),
                "distance": (
                    shot["distance"]
                ),
                "p": shot["p"],
                "rho": shot["rho"],
                "budget_us": (
                    budget_us
                ),
                "method": "learned",
                "selected_decoder": (
                    selected
                ),
                "predicted_failure": (
                    risk
                ),
                "predicted_p99_us": (
                    predicted_p99
                ),
            }
        )

    return pd.DataFrame(rows)


def lookup_decisions(
    context: pd.DataFrame,
    table: pd.DataFrame,
    budget_us: float,
):
    policy = DensityBinPolicy(
        table=table,
        budget_us=budget_us,
    )

    rows = []

    for _, shot in (
        context.iterrows()
    ):
        try:
            selected = policy.select(
                rho=float(
                    shot["rho"]
                ),
                distance=int(
                    shot["distance"]
                ),
            )

        except RuntimeError:
            selected = (
                "NO_FEASIBLE_DECODER"
            )

        rows.append(
            {
                "scenario_id": (
                    shot[
                        "scenario_id"
                    ]
                ),
                "shot_id": (
                    shot["shot_id"]
                ),
                "distance": (
                    shot["distance"]
                ),
                "p": shot["p"],
                "rho": shot["rho"],
                "budget_us": (
                    budget_us
                ),
                "method": "lookup",
                "selected_decoder": (
                    selected
                ),
                "predicted_failure": (
                    np.nan
                ),
                "predicted_p99_us": (
                    np.nan
                ),
            }
        )

    return pd.DataFrame(rows)


def attach_actual(
    decisions: pd.DataFrame,
    heldout: pd.DataFrame,
):
    actual = heldout[
        [
            "scenario_id",
            "shot_id",
            "decoder",
            "failure",
            "latency_us",
        ]
    ].rename(
        columns={
            "decoder": (
                "selected_decoder"
            ),
            "failure": (
                "actual_failure"
            ),
            "latency_us": (
                "actual_latency_us"
            ),
        }
    )

    merged = decisions.merge(
        actual,
        on=[
            "scenario_id",
            "shot_id",
            "selected_decoder",
        ],
        how="left",
    )

    merged["feasible"] = (
        merged["selected_decoder"]
        != "NO_FEASIBLE_DECODER"
    )

    merged[
        "deadline_violation"
    ] = np.where(
        merged["feasible"],
        (
            merged[
                "actual_latency_us"
            ]
            > merged["budget_us"]
        ),
        np.nan,
    )

    return merged


def summarize_adaptive(
    decisions: pd.DataFrame,
):
    rows = []

    for (
        budget,
        method,
    ), group in decisions.groupby(
        [
            "budget_us",
            "method",
        ]
    ):
        feasible = group[
            group["feasible"]
        ]

        if len(feasible):
            logical_failure = float(
                feasible[
                    "actual_failure"
                ].mean()
            )

            p99 = float(
                np.percentile(
                    feasible[
                        "actual_latency_us"
                    ],
                    99,
                )
            )

            mean_latency = float(
                feasible[
                    "actual_latency_us"
                ].mean()
            )

            violation = float(
                feasible[
                    "deadline_violation"
                ].mean()
            )

        else:
            logical_failure = np.nan
            p99 = np.nan
            mean_latency = np.nan
            violation = np.nan

        rows.append(
            {
                "budget_us": budget,
                "method": method,
                "shots": len(group),
                "feasible_shots": (
                    len(feasible)
                ),
                "coverage": (
                    len(feasible)
                    / len(group)
                ),
                "no_feasible_rate": (
                    1.0
                    - len(feasible)
                    / len(group)
                ),
                "logical_failure_rate": (
                    logical_failure
                ),
                "mean_latency_us": (
                    mean_latency
                ),
                "p99_latency_us": p99,
                "deadline_violation_rate": (
                    violation
                ),
            }
        )

    return pd.DataFrame(rows)


def summarize_fixed(
    heldout: pd.DataFrame,
):
    rows = []

    for budget in BUDGETS_US:
        for decoder, group in (
            heldout.groupby(
                "decoder"
            )
        ):
            rows.append(
                {
                    "budget_us": budget,
                    "method": (
                        f"fixed_{decoder}"
                    ),
                    "shots": (
                        len(group)
                    ),
                    "feasible_shots": (
                        len(group)
                    ),
                    "coverage": 1.0,
                    "no_feasible_rate": (
                        0.0
                    ),
                    "logical_failure_rate": (
                        float(
                            group[
                                "failure"
                            ].mean()
                        )
                    ),
                    "mean_latency_us": (
                        float(
                            group[
                                "latency_us"
                            ].mean()
                        )
                    ),
                    "p99_latency_us": (
                        float(
                            np.percentile(
                                group[
                                    "latency_us"
                                ],
                                99,
                            )
                        )
                    ),
                    "deadline_violation_rate": (
                        float(
                            (
                                group[
                                    "latency_us"
                                ]
                                > budget
                            ).mean()
                        )
                    ),
                }
            )

    return pd.DataFrame(rows)


def make_mix(
    decisions: pd.DataFrame,
):
    rows = []

    for (
        budget,
        method,
    ), group in decisions.groupby(
        [
            "budget_us",
            "method",
        ]
    ):
        counts = (
            group[
                "selected_decoder"
            ]
            .value_counts(
                normalize=True
            )
        )

        for decoder, fraction in (
            counts.items()
        ):
            rows.append(
                {
                    "budget_us": budget,
                    "method": method,
                    "decoder": decoder,
                    "fraction": (
                        float(fraction)
                    ),
                }
            )

    return pd.DataFrame(rows)


def main():
    OUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    calibration = (
        pd.read_parquet(
            CALIBRATION_PATH
        )
    )

    heldout = (
        pd.read_parquet(
            HELDOUT_PATH
        )
    )

    table = pd.read_csv(
        POLICY_TABLE_PATH
    )

    calibration, heldout = (
        prepare_frames(
            calibration,
            heldout,
        )
    )

    validate_split(
        calibration,
        heldout,
    )

    training = (
        build_training_table(
            calibration
        )
    )

    print(
        "Aggregated training rows:",
        len(training),
    )

    models = train_models(
        training
    )

    with open(
        MODEL_PATH,
        "wb",
    ) as f:
        pickle.dump(
            models,
            f,
        )

    context = make_context(
        heldout
    )

    all_decisions = []

    for budget in BUDGETS_US:
        print()
        print(
            "Budget:",
            budget,
            "us",
        )

        learned = learned_decisions(
            context,
            models,
            budget,
        )

        lookup = lookup_decisions(
            context,
            table,
            budget,
        )

        all_decisions.extend(
            [
                attach_actual(
                    learned,
                    heldout,
                ),
                attach_actual(
                    lookup,
                    heldout,
                ),
            ]
        )

    decisions = pd.concat(
        all_decisions,
        ignore_index=True,
    )

    decisions.to_parquet(
        DECISIONS_PATH,
        index=False,
    )

    adaptive_summary = (
        summarize_adaptive(
            decisions
        )
    )

    fixed_summary = (
        summarize_fixed(
            heldout
        )
    )

    sweep = pd.concat(
        [
            adaptive_summary,
            fixed_summary,
        ],
        ignore_index=True,
    )

    sweep.to_csv(
        SWEEP_PATH,
        index=False,
    )

    mix = make_mix(
        decisions
    )

    mix.to_csv(
        MIX_PATH,
        index=False,
    )

    config = {
        "model_family": (
            "DecisionTreeRegressor"
        ),
        "selection_objective": (
            "min predicted logical "
            "failure subject to "
            "predicted P99 <= budget"
        ),
        "features": FEATURE_COLUMNS,
        "budgets_us": BUDGETS_US,
        "max_depth": 6,
        "min_samples_leaf": 5,
        "decoders": list(
            models.keys()
        ),
        "calibration_p": sorted(
            float(x)
            for x
            in calibration[
                "p"
            ].unique()
        ),
        "heldout_p": sorted(
            float(x)
            for x
            in heldout[
                "p"
            ].unique()
        ),
    }

    with open(
        CONFIG_PATH,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            config,
            f,
            indent=2,
        )

    print()
    print(
        "=== BUDGET SWEEP ==="
    )

    display = sweep[
        sweep["method"].isin(
            [
                "learned",
                "lookup",
            ]
        )
    ]

    print(
        display.to_string(
            index=False
        )
    )

    print()
    print("Saved:", MODEL_PATH)
    print("Saved:", CONFIG_PATH)
    print("Saved:", DECISIONS_PATH)
    print("Saved:", SWEEP_PATH)
    print("Saved:", MIX_PATH)


if __name__ == "__main__":
    main()