from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from qec_lab.metrics import (
    per_round_logical_error,
)


# ============================================================
# PATHS
# ============================================================

FIG_DIR = Path(
    "results/figures"
)

FIG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# GENERAL HELPERS
# ============================================================


def finish(
    filename: str,
    title: str,
):
    """
    Finalize and save the current Matplotlib figure.
    """

    plt.title(title)
    plt.tight_layout()

    path = (
        FIG_DIR / filename
    )

    plt.savefig(
        path,
        dpi=250,
        bbox_inches="tight",
    )

    plt.close()

    print(
        "Saved:",
        path,
    )


def skip(
    name: str,
    path: Path,
):
    """
    Print a clear message when an optional result file
    does not exist.
    """

    print(
        f"SKIP {name}: "
        f"{path} not found"
    )


def find_column(
    df: pd.DataFrame,
    candidates: list[str],
    required: bool = True,
):
    """
    Find a column even when different package versions
    use slightly different names.

    Matching is case-insensitive.
    """

    normalized = {
        str(column)
        .strip()
        .lower():
        column
        for column
        in df.columns
    }

    for candidate in candidates:
        key = (
            candidate
            .strip()
            .lower()
        )

        if key in normalized:
            return normalized[key]

    if required:
        raise KeyError(
            "\nNone of these columns "
            "were found:\n"
            f"{candidates}\n\n"
            "Actual columns are:\n"
            f"{list(df.columns)}"
        )

    return None


def numeric_column(
    df: pd.DataFrame,
    candidates: list[str],
    required: bool = True,
):
    """
    Locate a candidate column and return a numeric Series.
    """

    column = find_column(
        df,
        candidates,
        required=required,
    )

    if column is None:
        return None

    return pd.to_numeric(
        df[column],
        errors="coerce",
    )


def parse_metadata(
    value,
):
    """
    Safely parse Sinter json_metadata.

    Handles:
    - JSON strings
    - already-decoded dictionaries
    """

    if isinstance(
        value,
        dict,
    ):
        return value

    if pd.isna(value):
        return {}

    try:
        return json.loads(
            str(value)
        )

    except (
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ):
        return {}


def positive_for_log(
    frame: pd.DataFrame,
    column: str,
):
    """
    Filter exact zeros/negative values before plotting on
    logarithmic axes.
    """

    return frame[
        pd.to_numeric(
            frame[column],
            errors="coerce",
        )
        > 0
    ].copy()


# ============================================================
# FIGURE 1
# THRESHOLD CURVES
# ============================================================


def plot_threshold():
    path = Path(
        "results/threshold/"
        "pymatching.csv"
    )

    if not path.exists():
        skip(
            "threshold",
            path,
        )
        return

    print()
    print(
        "Generating threshold plot..."
    )

    df = pd.read_csv(
        path
    )

    print(
        "Threshold CSV columns:",
        list(df.columns),
    )

    metadata_column = (
        find_column(
            df,
            [
                "json_metadata",
                "metadata",
            ],
        )
    )

    shots_column = find_column(
        df,
        [
            "shots",
            "num_shots",
            "shots_completed",
            "shots_collected",
        ],
    )

    errors_column = find_column(
        df,
        [
            "errors",
            "num_errors",
            "logical_errors",
            "errors_observed",
            "error_count",
        ],
    )

    metadata = df[
        metadata_column
    ].map(
        parse_metadata
    )

    df["distance"] = (
        metadata.map(
            lambda x: x.get(
                "d",
                x.get(
                    "distance"
                ),
            )
        )
    )

    df["p"] = (
        metadata.map(
            lambda x: x.get(
                "p"
            )
        )
    )

    df["rounds"] = (
        metadata.map(
            lambda x: x.get(
                "rounds",
                x.get(
                    "d",
                    x.get(
                        "distance"
                    ),
                ),
            )
        )
    )

    df["distance"] = (
        pd.to_numeric(
            df["distance"],
            errors="coerce",
        )
    )

    df["p"] = (
        pd.to_numeric(
            df["p"],
            errors="coerce",
        )
    )

    df["rounds"] = (
        pd.to_numeric(
            df["rounds"],
            errors="coerce",
        )
    )

    df["_plot_shots"] = (
        pd.to_numeric(
            df[shots_column],
            errors="coerce",
        )
    )

    df["_plot_errors"] = (
        pd.to_numeric(
            df[errors_column],
            errors="coerce",
        )
    )

    df = df.dropna(
        subset=[
            "distance",
            "p",
            "rounds",
            "_plot_shots",
            "_plot_errors",
        ]
    ).copy()

    if df.empty:
        print(
            "SKIP threshold: "
            "no usable rows after "
            "parsing."
        )
        return

    # Sinter resume files may contain
    # multiple contributions for the same
    # physical task. Sum them.
    grouped = (
        df.groupby(
            [
                "distance",
                "p",
                "rounds",
            ],
            as_index=False,
        )
        .agg(
            shots=(
                "_plot_shots",
                "sum",
            ),
            errors=(
                "_plot_errors",
                "sum",
            ),
        )
    )

    grouped = grouped[
        grouped["shots"] > 0
    ].copy()

    grouped[
        "shot_error_rate"
    ] = (
        grouped["errors"]
        / grouped["shots"]
    )

    per_round_values = []

    for (
        shot_error_rate,
        rounds,
    ) in zip(
        grouped[
            "shot_error_rate"
        ],
        grouped["rounds"],
    ):
        try:
            value = (
                per_round_logical_error(
                    shot_error_rate=float(
                        shot_error_rate
                    ),
                    rounds=int(
                        rounds
                    ),
                )
            )

        except Exception:
            value = np.nan

        per_round_values.append(
            value
        )

    grouped[
        "logical_per_round"
    ] = per_round_values

    plt.figure(
        figsize=(7.5, 5.2)
    )

    plotted = False

    for distance, group in (
        grouped.groupby(
            "distance"
        )
    ):
        group = (
            group.sort_values(
                "p"
            )
        )

        group = positive_for_log(
            group,
            "logical_per_round",
        )

        if group.empty:
            print(
                "No positive threshold "
                "points for "
                f"d={distance:g}"
            )
            continue

        plt.plot(
            group["p"],
            group[
                "logical_per_round"
            ],
            marker="o",
            label=(
                f"d={int(distance)}"
            ),
        )

        plotted = True

    if not plotted:
        plt.close()

        print(
            "SKIP threshold: "
            "no positive logical-error "
            "points available."
        )
        return

    plt.yscale(
        "log"
    )

    plt.xlabel(
        "Physical error parameter p"
    )

    plt.ylabel(
        "Logical error probability "
        "per round"
    )

    plt.grid(
        True,
        which="both",
        alpha=0.25,
    )

    plt.legend()

    finish(
        "01_threshold_curves.png",
        (
            "Surface-code threshold "
            "behaviour"
        ),
    )


# ============================================================
# FIGURE 2
# DECODER RELIABILITY
# ============================================================


def plot_decoder_reliability():
    path = Path(
        "results/"
        "decoder_comparison/"
        "decoder_comparison.csv"
    )

    if not path.exists():
        skip(
            "decoder reliability",
            path,
        )
        return

    print()
    print(
        "Generating decoder "
        "reliability plot..."
    )

    df = pd.read_csv(
        path
    )

    print(
        "Decoder comparison columns:",
        list(df.columns),
    )

    metadata_column = (
        find_column(
            df,
            [
                "json_metadata",
                "metadata",
            ],
        )
    )

    decoder_column = find_column(
        df,
        [
            "decoder",
            "decoder_name",
        ],
    )

    shots_column = find_column(
        df,
        [
            "shots",
            "num_shots",
            "shots_completed",
            "shots_collected",
        ],
    )

    errors_column = find_column(
        df,
        [
            "errors",
            "num_errors",
            "logical_errors",
            "errors_observed",
            "error_count",
        ],
    )

    metadata = df[
        metadata_column
    ].map(
        parse_metadata
    )

    df["distance"] = (
        metadata.map(
            lambda x: x.get(
                "d",
                x.get(
                    "distance"
                ),
            )
        )
    )

    df["p"] = metadata.map(
        lambda x: x.get(
            "p"
        )
    )

    df["distance"] = (
        pd.to_numeric(
            df["distance"],
            errors="coerce",
        )
    )

    df["p"] = (
        pd.to_numeric(
            df["p"],
            errors="coerce",
        )
    )

    df["_decoder"] = (
        df[decoder_column]
        .astype(str)
    )

    df["_shots"] = (
        pd.to_numeric(
            df[shots_column],
            errors="coerce",
        )
    )

    df["_errors"] = (
        pd.to_numeric(
            df[errors_column],
            errors="coerce",
        )
    )

    df = df.dropna(
        subset=[
            "distance",
            "p",
            "_shots",
            "_errors",
        ]
    )

    grouped = (
        df.groupby(
            [
                "_decoder",
                "distance",
                "p",
            ],
            as_index=False,
        )
        .agg(
            shots=(
                "_shots",
                "sum",
            ),
            errors=(
                "_errors",
                "sum",
            ),
        )
    )

    grouped = grouped[
        grouped["shots"] > 0
    ].copy()

    grouped[
        "logical_failure_rate"
    ] = (
        grouped["errors"]
        / grouped["shots"]
    )

    if grouped.empty:
        print(
            "SKIP decoder reliability: "
            "no valid rows."
        )
        return

    available_p = sorted(
        grouped[
            "p"
        ].unique()
    )

    # Prefer p=0.006 because it lies
    # inside the calibration sweep.
    target_p = min(
        available_p,
        key=lambda x: abs(
            float(x)
            - 0.006
        ),
    )

    selected = grouped[
        np.isclose(
            grouped["p"],
            target_p,
        )
    ].copy()

    plt.figure(
        figsize=(8, 5.2)
    )

    plotted = False

    for decoder, group in (
        selected.groupby(
            "_decoder"
        )
    ):
        group = group.sort_values(
            "distance"
        )

        group = positive_for_log(
            group,
            "logical_failure_rate",
        )

        if group.empty:
            continue

        plt.plot(
            group["distance"],
            group[
                "logical_failure_rate"
            ],
            marker="o",
            label=decoder,
        )

        plotted = True

    if not plotted:
        plt.close()

        print(
            "SKIP decoder reliability: "
            "all selected values are zero."
        )
        return

    plt.yscale(
        "log"
    )

    plt.xlabel(
        "Code distance"
    )

    plt.ylabel(
        "Logical failure rate"
    )

    plt.grid(
        True,
        which="both",
        alpha=0.25,
    )

    plt.legend(
        fontsize=8
    )

    finish(
        "02_decoder_reliability.png",
        (
            "Decoder reliability "
            f"at p={target_p:g}"
        ),
    )


# ============================================================
# LATENCY JSON LOADER
# ============================================================


def load_latency():
    path = Path(
        "results/"
        "decoder_comparison/"
        "latency.json"
    )

    if not path.exists():
        return (
            None,
            path,
        )

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as f:
            raw = json.load(f)

        if isinstance(
            raw,
            list,
        ):
            df = pd.DataFrame(
                raw
            )

        elif isinstance(
            raw,
            dict,
        ):
            # Support either:
            #
            # {"records": [...]}
            #
            # or a dictionary of rows /
            # dataframe-like content.

            for key in [
                "records",
                "results",
                "benchmarks",
                "data",
            ]:
                if (
                    key in raw
                    and isinstance(
                        raw[key],
                        list,
                    )
                ):
                    df = pd.DataFrame(
                        raw[key]
                    )
                    break

            else:
                try:
                    df = pd.DataFrame(
                        raw
                    )

                except ValueError:
                    df = pd.DataFrame(
                        [raw]
                    )

        else:
            raise ValueError(
                "Unsupported latency.json "
                "structure."
            )

    except Exception as exc:
        print(
            "Could not parse "
            f"{path}: {exc}"
        )

        return (
            None,
            path,
        )

    print(
        "Latency JSON columns:",
        list(df.columns),
    )

    return (
        df,
        path,
    )


# ============================================================
# FIGURE 3
# P99 LATENCY SCALING
# ============================================================


def plot_latency():
    df, path = (
        load_latency()
    )

    if df is None:
        skip(
            "latency scaling",
            path,
        )
        return

    print()
    print(
        "Generating P99 latency "
        "scaling plot..."
    )

    distance_column = (
        find_column(
            df,
            [
                "distance",
                "d",
            ],
        )
    )

    decoder_column = (
        find_column(
            df,
            [
                "decoder",
                "decoder_name",
            ],
        )
    )

    p99_column = find_column(
        df,
        [
            "p99_us",
            "p99_latency_us",
            "single_p99_us",
            "latency_p99_us",
        ],
    )

    work = pd.DataFrame(
        {
            "distance": (
                pd.to_numeric(
                    df[
                        distance_column
                    ],
                    errors="coerce",
                )
            ),
            "decoder": (
                df[
                    decoder_column
                ].astype(str)
            ),
            "p99_us": (
                pd.to_numeric(
                    df[p99_column],
                    errors="coerce",
                )
            ),
        }
    ).dropna()

    plt.figure(
        figsize=(8, 5.2)
    )

    for decoder, group in (
        work.groupby(
            "decoder"
        )
    ):
        group = group.sort_values(
            "distance"
        )

        positive = group[
            group["p99_us"] > 0
        ]

        if positive.empty:
            continue

        plt.plot(
            positive[
                "distance"
            ],
            positive[
                "p99_us"
            ],
            marker="o",
            label=decoder,
        )

    plt.yscale(
        "log"
    )

    plt.xlabel(
        "Code distance"
    )

    plt.ylabel(
        "P99 single-shot "
        "decoding latency (µs)"
    )

    plt.grid(
        True,
        which="both",
        alpha=0.25,
    )

    plt.legend(
        fontsize=8
    )

    finish(
        "03_p99_latency_scaling.png",
        "Decoder tail-latency scaling",
    )


# ============================================================
# FIGURE 4
# THROUGHPUT SCALING
# ============================================================


def plot_throughput():
    df, path = (
        load_latency()
    )

    if df is None:
        skip(
            "throughput",
            path,
        )
        return

    print()
    print(
        "Generating throughput "
        "scaling plot..."
    )

    distance_column = (
        find_column(
            df,
            [
                "distance",
                "d",
            ],
        )
    )

    decoder_column = (
        find_column(
            df,
            [
                "decoder",
                "decoder_name",
            ],
        )
    )

    throughput_column = (
        find_column(
            df,
            [
                "batch_throughput_per_s",
                "throughput_per_s",
                "batch_throughput",
                "shots_per_s",
                "throughput",
            ],
        )
    )

    work = pd.DataFrame(
        {
            "distance": (
                pd.to_numeric(
                    df[
                        distance_column
                    ],
                    errors="coerce",
                )
            ),
            "decoder": (
                df[
                    decoder_column
                ].astype(str)
            ),
            "throughput": (
                pd.to_numeric(
                    df[
                        throughput_column
                    ],
                    errors="coerce",
                )
            ),
        }
    ).dropna()

    plt.figure(
        figsize=(8, 5.2)
    )

    for decoder, group in (
        work.groupby(
            "decoder"
        )
    ):
        group = group.sort_values(
            "distance"
        )

        positive = group[
            group[
                "throughput"
            ]
            > 0
        ]

        if positive.empty:
            continue

        plt.plot(
            positive[
                "distance"
            ],
            positive[
                "throughput"
            ],
            marker="o",
            label=decoder,
        )

    plt.yscale(
        "log"
    )

    plt.xlabel(
        "Code distance"
    )

    plt.ylabel(
        "Batch throughput "
        "(shots/s)"
    )

    plt.grid(
        True,
        which="both",
        alpha=0.25,
    )

    plt.legend(
        fontsize=8
    )

    finish(
        "04_throughput_scaling.png",
        "Decoder throughput scaling",
    )


# ============================================================
# FIGURE 5
# NOISE MISMATCH
# ============================================================


def plot_mismatch():
    path = Path(
        "results/mismatch/"
        "mismatch.csv"
    )

    if not path.exists():
        skip(
            "noise mismatch",
            path,
        )
        return

    print()
    print(
        "Generating noise-mismatch "
        "plot..."
    )

    df = pd.read_csv(
        path
    )

    print(
        "Mismatch columns:",
        list(df.columns),
    )

    true_column = find_column(
        df,
        [
            "true_p",
        ],
    )

    assumed_column = find_column(
        df,
        [
            "assumed_p",
        ],
    )

    value_columns = [
        column
        for column
        in df.columns
        if column not in {
            true_column,
            assumed_column,
        }
    ]

    usable_columns = []

    for column in value_columns:
        numeric = pd.to_numeric(
            df[column],
            errors="coerce",
        )

        if numeric.notna().any():
            df[column] = numeric
            usable_columns.append(
                column
            )

    if not usable_columns:
        print(
            "SKIP noise mismatch: "
            "no decoder result columns."
        )
        return

    assumed_values = (
        pd.to_numeric(
            df[assumed_column],
            errors="coerce",
        )
    )

    true_values = (
        pd.to_numeric(
            df[true_column],
            errors="coerce",
        )
    )

    plt.figure(
        figsize=(7.5, 5.2)
    )

    for decoder in usable_columns:
        plt.plot(
            assumed_values,
            df[decoder],
            marker="o",
            label=str(decoder),
        )

    finite_true = (
        true_values.dropna()
    )

    if not finite_true.empty:
        true_p = float(
            finite_true.iloc[0]
        )

        plt.axvline(
            true_p,
            linestyle="--",
            label=(
                "Matched calibration"
            ),
        )

    plt.xlabel(
        "Assumed physical error p"
    )

    plt.ylabel(
        "Logical failure rate"
    )

    plt.grid(
        True,
        alpha=0.25,
    )

    plt.legend(
        fontsize=8
    )

    finish(
        "05_noise_mismatch.png",
        (
            "Decoder robustness to "
            "noise-model mismatch"
        ),
    )


# ============================================================
# FIGURE 6
# PAULI BIAS SENSITIVITY
# ============================================================


def plot_bias():
    path = Path(
        "results/bias/"
        "bias_results.csv"
    )

    if not path.exists():
        skip(
            "bias sensitivity",
            path,
        )
        return

    print()
    print(
        "Generating bias "
        "sensitivity plot..."
    )

    df = pd.read_csv(
        path
    )

    print(
        "Bias-result columns:",
        list(df.columns),
    )

    required = [
        "noise_case",
        "basis",
        "distance",
        "decoder",
        "logical_failure_rate",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        print(
            "SKIP bias plot: "
            f"missing columns {missing}"
        )
        return

    df["distance"] = (
        pd.to_numeric(
            df["distance"],
            errors="coerce",
        )
    )

    df[
        "logical_failure_rate"
    ] = pd.to_numeric(
        df[
            "logical_failure_rate"
        ],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "distance",
            "logical_failure_rate",
        ]
    )

    if df.empty:
        print(
            "SKIP bias plot: "
            "no valid rows."
        )
        return

    distance = int(
        df["distance"].max()
    )

    available_decoders = (
        df[
            "decoder"
        ]
        .astype(str)
        .unique()
        .tolist()
    )

    if (
        "mwpm"
        in available_decoders
    ):
        decoder = "mwpm"

    else:
        decoder = (
            available_decoders[0]
        )

    selected = df[
        (
            df["distance"]
            == distance
        )
        & (
            df["decoder"]
            .astype(str)
            == decoder
        )
    ].copy()

    if selected.empty:
        print(
            "SKIP bias plot: "
            "selected dataset empty."
        )
        return

    pivot = (
        selected
        .pivot_table(
            index="noise_case",
            columns="basis",
            values=(
                "logical_failure_rate"
            ),
            aggfunc="mean",
        )
    )

    if pivot.empty:
        print(
            "SKIP bias plot: "
            "pivot table empty."
        )
        return

    ax = pivot.plot(
        kind="bar",
        figsize=(8.5, 5.2),
    )

    # Log scale only if every displayed
    # non-NaN value is positive.
    values = pivot.to_numpy(
        dtype=float
    )

    positive_values = values[
        np.isfinite(values)
    ]

    if (
        len(positive_values)
        and np.all(
            positive_values > 0
        )
    ):
        ax.set_yscale(
            "log"
        )

    plt.xlabel(
        "Noise composition"
    )

    plt.ylabel(
        "Logical failure rate"
    )

    plt.xticks(
        rotation=20,
        ha="right",
    )

    plt.grid(
        True,
        axis="y",
        which="both",
        alpha=0.25,
    )

    finish(
        "06_bias_sensitivity.png",
        (
            "Pauli-bias sensitivity "
            f"at d={distance}"
        ),
    )


# ============================================================
# FIGURE 7
# ORDINARY VS CORRELATED MWPM
# ============================================================


def plot_correlation():
    path = Path(
        "results/"
        "decoder_comparison/"
        "correlation_study.csv"
    )

    if not path.exists():
        skip(
            "correlation study",
            path,
        )
        return

    print()
    print(
        "Generating correlation-aware "
        "decoder plot..."
    )

    df = pd.read_csv(
        path
    )

    required = [
        "distance",
        "p",
        "decoder",
        "logical_failure_rate",
    ]

    missing = [
        x
        for x in required
        if x not in df.columns
    ]

    if missing:
        print(
            "SKIP correlation plot: "
            f"missing columns {missing}"
        )
        return

    for column in [
        "distance",
        "p",
        "logical_failure_rate",
    ]:
        df[column] = (
            pd.to_numeric(
                df[column],
                errors="coerce",
            )
        )

    df = df.dropna(
        subset=[
            "distance",
            "p",
            "logical_failure_rate",
        ]
    )

    if df.empty:
        return

    available_p = sorted(
        df["p"].unique()
    )

    target_p = min(
        available_p,
        key=lambda x: abs(
            float(x)
            - 0.005
        ),
    )

    selected = df[
        np.isclose(
            df["p"],
            target_p,
        )
    ].copy()

    plt.figure(
        figsize=(7.5, 5.2)
    )

    for decoder, group in (
        selected.groupby(
            "decoder"
        )
    ):
        group = (
            group.sort_values(
                "distance"
            )
        )

        group = positive_for_log(
            group,
            "logical_failure_rate",
        )

        if group.empty:
            continue

        plt.plot(
            group["distance"],
            group[
                "logical_failure_rate"
            ],
            marker="o",
            label=str(decoder),
        )

    plt.yscale(
        "log"
    )

    plt.xlabel(
        "Code distance"
    )

    plt.ylabel(
        "Logical failure rate"
    )

    plt.grid(
        True,
        which="both",
        alpha=0.25,
    )

    plt.legend()

    finish(
        "07_correlation_decoding.png",
        (
            "Ordinary vs "
            "correlation-aware MWPM "
            f"at p={target_p:g}"
        ),
    )


# ============================================================
# FIGURE 8
# FINAL LOGICAL X / Z SCALING
# ============================================================


def plot_final_scaling():
    path = Path(
        "results/"
        "decoder_comparison/"
        "final_scaling.csv"
    )

    if not path.exists():
        skip(
            "final scaling",
            path,
        )
        return

    print()
    print(
        "Generating logical-X/Z "
        "scaling plot..."
    )

    df = pd.read_csv(
        path
    )

    required = [
        "distance",
        "basis",
        "decoder",
        "logical_failure_rate",
    ]

    missing = [
        x
        for x in required
        if x not in df.columns
    ]

    if missing:
        print(
            "SKIP final scaling: "
            f"missing columns {missing}"
        )
        return

    df["distance"] = (
        pd.to_numeric(
            df["distance"],
            errors="coerce",
        )
    )

    df[
        "logical_failure_rate"
    ] = pd.to_numeric(
        df[
            "logical_failure_rate"
        ],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "distance",
            "logical_failure_rate",
        ]
    )

    plt.figure(
        figsize=(8.5, 5.4)
    )

    plotted = False

    for (
        decoder,
        basis,
    ), group in df.groupby(
        [
            "decoder",
            "basis",
        ]
    ):
        group = group.sort_values(
            "distance"
        )

        group = positive_for_log(
            group,
            "logical_failure_rate",
        )

        if group.empty:
            continue

        plt.plot(
            group["distance"],
            group[
                "logical_failure_rate"
            ],
            marker="o",
            label=(
                f"{decoder}, "
                f"logical-{str(basis).upper()}"
            ),
        )

        plotted = True

    if not plotted:
        plt.close()

        print(
            "SKIP final scaling: "
            "no positive values."
        )
        return

    plt.yscale(
        "log"
    )

    plt.xlabel(
        "Code distance"
    )

    plt.ylabel(
        "Logical failure rate"
    )

    plt.grid(
        True,
        which="both",
        alpha=0.25,
    )

    plt.legend(
        fontsize=8
    )

    finish(
        "08_logical_xz_scaling.png",
        (
            "Logical-X / logical-Z "
            "scaling"
        ),
    )


# ============================================================
# FIGURE 9
# ORIGINAL LOOKUP POLICY PARETO FRONTIER
# ============================================================


def plot_original_pareto():
    path = Path(
        "results/adaptive/"
        "budget_sweep.csv"
    )

    if not path.exists():
        skip(
            "adaptive Pareto",
            path,
        )
        return

    print()
    print(
        "Generating original adaptive "
        "Pareto plot..."
    )

    df = pd.read_csv(
        path
    )

    logical_column = find_column(
        df,
        [
            "logical_failure_rate",
        ],
        required=False,
    )

    p99_column = find_column(
        df,
        [
            "p99_us",
            "p99_latency_us",
        ],
        required=False,
    )

    budget_column = find_column(
        df,
        [
            "budget_us",
            "budget",
        ],
        required=False,
    )

    if (
        logical_column is None
        or p99_column is None
    ):
        print(
            "SKIP adaptive Pareto: "
            "required columns missing."
        )
        return

    df["_logical"] = (
        pd.to_numeric(
            df[
                logical_column
            ],
            errors="coerce",
        )
    )

    df["_p99"] = (
        pd.to_numeric(
            df[p99_column],
            errors="coerce",
        )
    )

    valid = df.dropna(
        subset=[
            "_logical",
            "_p99",
        ]
    ).copy()

    if valid.empty:
        print(
            "SKIP adaptive Pareto: "
            "no feasible rows."
        )
        return

    valid = valid.sort_values(
        "_p99"
    )

    plt.figure(
        figsize=(7.5, 5.2)
    )

    plt.plot(
        valid["_p99"],
        valid["_logical"],
        marker="o",
    )

    if (
        budget_column
        is not None
    ):
        for _, row in (
            valid.iterrows()
        ):
            try:
                label = (
                    f"{float(row[budget_column]):g}"
                )

                plt.annotate(
                    label,
                    (
                        row["_p99"],
                        row["_logical"],
                    ),
                    fontsize=7,
                )

            except (
                ValueError,
                TypeError,
            ):
                pass

    plt.xlabel(
        "Observed P99 decoder "
        "latency (µs)"
    )

    plt.ylabel(
        "Held-out logical "
        "failure rate"
    )

    plt.grid(
        True,
        alpha=0.25,
    )

    finish(
        "09_adaptive_pareto.png",
        (
            "Reliability–latency "
            "Pareto frontier"
        ),
    )


# ============================================================
# LEARNED SELECTOR DATA
# ============================================================


def load_learned_sweep():
    path = Path(
        "results/adaptive/"
        "learned_selector_"
        "budget_sweep.csv"
    )

    if not path.exists():
        return (
            None,
            path,
        )

    df = pd.read_csv(
        path
    )

    return (
        df,
        path,
    )


# ============================================================
# FIGURE 10
# LEARNED VS LOOKUP COVERAGE
# ============================================================


def plot_learned_coverage():
    df, path = (
        load_learned_sweep()
    )

    if df is None:
        skip(
            "learned coverage",
            path,
        )
        return

    print()
    print(
        "Generating learned-policy "
        "coverage plot..."
    )

    required = [
        "budget_us",
        "method",
        "coverage",
    ]

    if any(
        x not in df.columns
        for x in required
    ):
        print(
            "SKIP learned coverage: "
            "required columns missing."
        )
        return

    selected = df[
        df["method"].isin(
            [
                "learned",
                "lookup",
            ]
        )
    ].copy()

    selected["budget_us"] = (
        pd.to_numeric(
            selected[
                "budget_us"
            ],
            errors="coerce",
        )
    )

    selected["coverage"] = (
        pd.to_numeric(
            selected[
                "coverage"
            ],
            errors="coerce",
        )
    )

    selected = selected.dropna(
        subset=[
            "budget_us",
            "coverage",
        ]
    )

    plt.figure(
        figsize=(7.5, 5.2)
    )

    for method, group in (
        selected.groupby(
            "method"
        )
    ):
        group = group.sort_values(
            "budget_us"
        )

        plt.plot(
            group["budget_us"],
            (
                100.0
                * group["coverage"]
            ),
            marker="o",
            label=str(method),
        )

    plt.xscale(
        "log"
    )

    plt.xlabel(
        "Latency budget (µs)"
    )

    plt.ylabel(
        "Feasible held-out "
        "shots (%)"
    )

    plt.ylim(
        -2,
        102,
    )

    plt.grid(
        True,
        which="both",
        alpha=0.25,
    )

    plt.legend()

    finish(
        "10_learned_policy_coverage.png",
        (
            "Adaptive-policy feasibility "
            "vs latency budget"
        ),
    )


# ============================================================
# FIGURE 11
# LEARNED VS LOOKUP RELIABILITY
# ============================================================


def plot_learned_reliability():
    df, path = (
        load_learned_sweep()
    )

    if df is None:
        skip(
            "learned reliability",
            path,
        )
        return

    print()
    print(
        "Generating learned-vs-lookup "
        "reliability plot..."
    )

    required = [
        "budget_us",
        "method",
        "logical_failure_rate",
    ]

    if any(
        x not in df.columns
        for x in required
    ):
        print(
            "SKIP learned reliability: "
            "required columns missing."
        )
        return

    selected = df[
        df["method"].isin(
            [
                "learned",
                "lookup",
            ]
        )
    ].copy()

    selected[
        "budget_us"
    ] = pd.to_numeric(
        selected[
            "budget_us"
        ],
        errors="coerce",
    )

    selected[
        "logical_failure_rate"
    ] = pd.to_numeric(
        selected[
            "logical_failure_rate"
        ],
        errors="coerce",
    )

    plt.figure(
        figsize=(7.5, 5.2)
    )

    plotted = False

    for method, group in (
        selected.groupby(
            "method"
        )
    ):
        group = (
            group.dropna(
                subset=[
                    "budget_us",
                    "logical_failure_rate",
                ]
            )
            .sort_values(
                "budget_us"
            )
        )

        if group.empty:
            continue

        plt.plot(
            group["budget_us"],
            group[
                "logical_failure_rate"
            ],
            marker="o",
            label=str(method),
        )

        plotted = True

    if not plotted:
        plt.close()

        print(
            "SKIP learned reliability: "
            "no feasible rows."
        )
        return

    plt.xscale(
        "log"
    )

    plt.xlabel(
        "Latency budget (µs)"
    )

    plt.ylabel(
        "Logical failure rate "
        "on selected shots"
    )

    plt.grid(
        True,
        which="both",
        alpha=0.25,
    )

    plt.legend()

    finish(
        "11_learned_vs_lookup.png",
        (
            "Learned vs lookup "
            "adaptive reliability"
        ),
    )


# ============================================================
# FIGURE 12
# DEADLINE VIOLATION RATE VS BUDGET
# ============================================================


def plot_learned_deadline_violations():
    df, path = (
        load_learned_sweep()
    )

    if df is None:
        skip(
            "deadline violations",
            path,
        )
        return

    print()
    print(
        "Generating deadline-violation "
        "plot..."
    )

    required = [
        "budget_us",
        "method",
        "deadline_violation_rate",
    ]

    if any(
        x not in df.columns
        for x in required
    ):
        print(
            "SKIP deadline violations: "
            "required columns missing."
        )
        return

    selected = df[
        df["method"].isin(
            [
                "learned",
                "lookup",
            ]
        )
    ].copy()

    selected["budget_us"] = (
        pd.to_numeric(
            selected[
                "budget_us"
            ],
            errors="coerce",
        )
    )

    selected[
        "deadline_violation_rate"
    ] = pd.to_numeric(
        selected[
            "deadline_violation_rate"
        ],
        errors="coerce",
    )

    plt.figure(
        figsize=(7.5, 5.2)
    )

    plotted = False

    for method, group in (
        selected.groupby(
            "method"
        )
    ):
        group = (
            group.dropna(
                subset=[
                    "budget_us",
                    "deadline_violation_rate",
                ]
            )
            .sort_values(
                "budget_us"
            )
        )

        if group.empty:
            continue

        plt.plot(
            group["budget_us"],
            (
                100.0
                * group[
                    "deadline_violation_rate"
                ]
            ),
            marker="o",
            label=str(method),
        )

        plotted = True

    if not plotted:
        plt.close()
        return

    plt.xscale(
        "log"
    )

    plt.xlabel(
        "Latency budget (µs)"
    )

    plt.ylabel(
        "Deadline-violation rate (%)"
    )

    plt.grid(
        True,
        which="both",
        alpha=0.25,
    )

    plt.legend()

    finish(
        "12_deadline_violations.png",
        (
            "Adaptive-policy deadline "
            "violations"
        ),
    )


# ============================================================
# FIGURE 13
# LEARNED DECODER MIX
# ============================================================


def plot_learned_decoder_mix():
    path = Path(
        "results/adaptive/"
        "learned_selector_"
        "decoder_mix.csv"
    )

    if not path.exists():
        skip(
            "learned decoder mix",
            path,
        )
        return

    print()
    print(
        "Generating decoder-mixture "
        "plot..."
    )

    df = pd.read_csv(
        path
    )

    required = [
        "budget_us",
        "method",
        "decoder",
        "fraction",
    ]

    if any(
        x not in df.columns
        for x in required
    ):
        print(
            "SKIP learned decoder mix: "
            "required columns missing."
        )
        return

    # Learned policy is the most useful
    # categorical mix to visualize.
    selected = df[
        df["method"]
        == "learned"
    ].copy()

    selected["budget_us"] = (
        pd.to_numeric(
            selected[
                "budget_us"
            ],
            errors="coerce",
        )
    )

    selected["fraction"] = (
        pd.to_numeric(
            selected[
                "fraction"
            ],
            errors="coerce",
        )
    )

    selected = selected.dropna(
        subset=[
            "budget_us",
            "fraction",
        ]
    )

    if selected.empty:
        print(
            "SKIP learned decoder mix: "
            "no learned-policy rows."
        )
        return

    pivot = (
        selected.pivot_table(
            index="budget_us",
            columns="decoder",
            values="fraction",
            aggfunc="sum",
            fill_value=0.0,
        )
        .sort_index()
    )

    pivot *= 100.0

    ax = pivot.plot(
        kind="bar",
        stacked=True,
        figsize=(9, 5.5),
    )

    plt.xlabel(
        "Latency budget (µs)"
    )

    plt.ylabel(
        "Selected-shot fraction (%)"
    )

    plt.ylim(
        0,
        100,
    )

    plt.xticks(
        rotation=35,
        ha="right",
    )

    plt.grid(
        True,
        axis="y",
        alpha=0.25,
    )

    ax.legend(
        title="Decoder",
        fontsize=8,
    )

    finish(
        "13_learned_decoder_mix.png",
        (
            "Learned selector decoder "
            "mixture"
        ),
    )


# ============================================================
# STREAMING DATA LOADER
# ============================================================


def load_streaming():
    path = Path(
        "results/"
        "decoder_comparison/"
        "streaming_summary.csv"
    )

    if not path.exists():
        return (
            None,
            path,
        )

    df = pd.read_csv(
        path
    )

    return (
        df,
        path,
    )


# ============================================================
# FIGURE 14
# STREAMING UPDATE P99
# ============================================================


def plot_streaming_latency():
    df, path = (
        load_streaming()
    )

    if df is None:
        skip(
            "streaming latency",
            path,
        )
        return

    print()
    print(
        "Generating streaming "
        "update-latency plot..."
    )

    required = [
        "distance",
        "update_stride",
        "p99_update_latency_us",
    ]

    if any(
        x not in df.columns
        for x in required
    ):
        print(
            "SKIP streaming latency: "
            "required columns missing."
        )
        return

    for column in [
        "distance",
        "update_stride",
        "p99_update_latency_us",
    ]:
        df[column] = (
            pd.to_numeric(
                df[column],
                errors="coerce",
            )
        )

    df = df.dropna(
        subset=required
    )

    plt.figure(
        figsize=(7.8, 5.2)
    )

    for stride, group in (
        df.groupby(
            "update_stride"
        )
    ):
        group = group.sort_values(
            "distance"
        )

        positive = group[
            group[
                "p99_update_latency_us"
            ]
            > 0
        ]

        plt.plot(
            positive["distance"],
            positive[
                "p99_update_latency_us"
            ],
            marker="o",
            label=(
                "Update every "
                f"{int(stride)} "
                "temporal group(s)"
            ),
        )

    plt.yscale(
        "log"
    )

    plt.xlabel(
        "Code distance"
    )

    plt.ylabel(
        "P99 causal update "
        "latency (µs)"
    )

    plt.grid(
        True,
        which="both",
        alpha=0.25,
    )

    plt.legend(
        fontsize=8
    )

    finish(
        "14_streaming_update_latency.png",
        "Causal-prefix update latency",
    )


# ============================================================
# FIGURE 15
# STREAMING REPLAY OVERHEAD
# ============================================================


def plot_streaming_overhead():
    df, path = (
        load_streaming()
    )

    if df is None:
        skip(
            "streaming overhead",
            path,
        )
        return

    print()
    print(
        "Generating streaming "
        "replay-overhead plot..."
    )

    required = [
        "distance",
        "update_stride",
        "mean_total_replay_latency_us",
        "block_mean_latency_us",
    ]

    if any(
        x not in df.columns
        for x in required
    ):
        print(
            "SKIP streaming overhead: "
            "required columns missing."
        )
        return

    for column in required:
        df[column] = (
            pd.to_numeric(
                df[column],
                errors="coerce",
            )
        )

    df = df.dropna(
        subset=required
    )

    df = df[
        df[
            "block_mean_latency_us"
        ]
        > 0
    ].copy()

    df[
        "replay_overhead"
    ] = (
        df[
            "mean_total_replay_latency_us"
        ]
        / df[
            "block_mean_latency_us"
        ]
    )

    plt.figure(
        figsize=(7.8, 5.2)
    )

    for stride, group in (
        df.groupby(
            "update_stride"
        )
    ):
        group = group.sort_values(
            "distance"
        )

        plt.plot(
            group["distance"],
            group[
                "replay_overhead"
            ],
            marker="o",
            label=(
                "Update every "
                f"{int(stride)} "
                "group(s)"
            ),
        )

    plt.axhline(
        1.0,
        linestyle="--",
        label="Block MWPM cost",
    )

    plt.xlabel(
        "Code distance"
    )

    plt.ylabel(
        "Total causal replay cost "
        "/ block decode cost"
    )

    plt.grid(
        True,
        alpha=0.25,
    )

    plt.legend(
        fontsize=8
    )

    finish(
        "15_streaming_replay_overhead.png",
        (
            "Computational cost of "
            "causal streaming replay"
        ),
    )


# ============================================================
# FIGURE 16
# STREAMING FRAME STABILITY
# ============================================================


def plot_streaming_stability():
    df, path = (
        load_streaming()
    )

    if df is None:
        skip(
            "streaming stability",
            path,
        )
        return

    print()
    print(
        "Generating streaming "
        "frame-stability plot..."
    )

    required = [
        "distance",
        "update_stride",
        "mean_prediction_changes",
    ]

    if any(
        x not in df.columns
        for x in required
    ):
        print(
            "SKIP streaming stability: "
            "required columns missing."
        )
        return

    for column in required:
        df[column] = (
            pd.to_numeric(
                df[column],
                errors="coerce",
            )
        )

    df = df.dropna(
        subset=required
    )

    plt.figure(
        figsize=(7.8, 5.2)
    )

    for stride, group in (
        df.groupby(
            "update_stride"
        )
    ):
        group = group.sort_values(
            "distance"
        )

        plt.plot(
            group["distance"],
            group[
                "mean_prediction_changes"
            ],
            marker="o",
            label=(
                "Update every "
                f"{int(stride)} "
                "group(s)"
            ),
        )

    plt.xlabel(
        "Code distance"
    )

    plt.ylabel(
        "Mean logical-frame "
        "prediction changes / shot"
    )

    plt.grid(
        True,
        alpha=0.25,
    )

    plt.legend(
        fontsize=8
    )

    finish(
        "16_streaming_frame_stability.png",
        (
            "Logical-frame stability "
            "during causal decoding"
        ),
    )


# ============================================================
# FIGURE 17
# FINAL SYSTEMS RELIABILITY / LATENCY
# ============================================================


def plot_final_system_tradeoff():
    path = Path(
        "results/"
        "decoder_comparison/"
        "final_scaling.csv"
    )

    if not path.exists():
        skip(
            "final systems tradeoff",
            path,
        )
        return

    print()
    print(
        "Generating final systems "
        "trade-off plot..."
    )

    df = pd.read_csv(
        path
    )

    required = [
        "logical_failure_rate",
        "p99_us",
        "decoder",
        "distance",
        "basis",
    ]

    if any(
        x not in df.columns
        for x in required
    ):
        print(
            "SKIP final systems "
            "tradeoff: required "
            "columns missing."
        )
        return

    for column in [
        "logical_failure_rate",
        "p99_us",
        "distance",
    ]:
        df[column] = (
            pd.to_numeric(
                df[column],
                errors="coerce",
            )
        )

    df = df.dropna(
        subset=[
            "logical_failure_rate",
            "p99_us",
            "distance",
        ]
    )

    df = df[
        (
            df[
                "logical_failure_rate"
            ]
            > 0
        )
        & (
            df["p99_us"] > 0
        )
    ].copy()

    if df.empty:
        print(
            "SKIP final systems "
            "tradeoff: no usable rows."
        )
        return

    plt.figure(
        figsize=(8, 5.5)
    )

    for decoder, group in (
        df.groupby(
            "decoder"
        )
    ):
        plt.scatter(
            group["p99_us"],
            group[
                "logical_failure_rate"
            ],
            label=str(decoder),
        )

        for _, row in (
            group.iterrows()
        ):
            plt.annotate(
                (
                    f"d={int(row['distance'])}"
                    f",{str(row['basis']).upper()}"
                ),
                (
                    row["p99_us"],
                    row[
                        "logical_failure_rate"
                    ],
                ),
                fontsize=6,
            )

    plt.xscale(
        "log"
    )

    plt.yscale(
        "log"
    )

    plt.xlabel(
        "P99 decoder latency (µs)"
    )

    plt.ylabel(
        "Logical failure rate"
    )

    plt.grid(
        True,
        which="both",
        alpha=0.25,
    )

    plt.legend(
        fontsize=8
    )

    finish(
        "17_final_reliability_latency.png",
        (
            "Final reliability–latency "
            "trade-off"
        ),
    )


# ============================================================
# MAIN
# ============================================================


def main():
    print(
        "=" * 70
    )

    print(
        "Generating all available "
        "project result figures"
    )

    print(
        "=" * 70
    )

    plot_threshold()

    plot_decoder_reliability()

    plot_latency()

    plot_throughput()

    plot_mismatch()

    plot_bias()

    plot_correlation()

    plot_final_scaling()

    plot_original_pareto()

    plot_learned_coverage()

    plot_learned_reliability()

    plot_learned_deadline_violations()

    plot_learned_decoder_mix()

    plot_streaming_latency()

    plot_streaming_overhead()

    plot_streaming_stability()

    plot_final_system_tradeoff()

    print()
    print(
        "=" * 70
    )

    print(
        "Plot generation complete."
    )

    print(
        "Available figures are in:"
    )

    print(
        FIG_DIR.resolve()
    )

    print(
        "=" * 70
    )


if __name__ == "__main__":
    main()