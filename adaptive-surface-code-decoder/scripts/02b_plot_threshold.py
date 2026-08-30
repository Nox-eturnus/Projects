import json

import matplotlib.pyplot as plt
import pandas as pd

from qec_lab.metrics import (
    per_round_logical_error,
)


def main():
    path = (
        "results/threshold/"
        "pymatching.csv"
    )

    df = pd.read_csv(path)

    metadata = df[
        "json_metadata"
    ].map(json.loads)

    df["d"] = metadata.map(
        lambda x: x["d"]
    )
    df["p"] = metadata.map(
        lambda x: x["p"]
    )
    df["rounds"] = metadata.map(
        lambda x: x["rounds"]
    )

    df["p_shot"] = (
        df["errors"] / df["shots"]
    )

    df["p_round"] = [
        per_round_logical_error(
            shot_error_rate=e / s,
            rounds=r,
        )
        for e, s, r in zip(
            df["errors"],
            df["shots"],
            df["rounds"],
        )
    ]

    for d, group in df.groupby("d"):
        group = group.sort_values("p")

        plt.plot(
            group["p"],
            group["p_round"],
            marker="o",
            label=f"d={d}",
        )

    plt.xlabel(
        "Physical error parameter p"
    )
    plt.ylabel(
        "Logical error probability per round"
    )
    plt.yscale("log")
    plt.grid(
        True,
        which="both",
    )
    plt.legend()
    plt.tight_layout()

    plt.savefig(
        "results/threshold/"
        "threshold.png",
        dpi=200,
    )

    plt.show()


if __name__ == "__main__":
    main()