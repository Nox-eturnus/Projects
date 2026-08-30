from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def syndrome_density(
    dets: np.ndarray,
) -> np.ndarray:
    return np.mean(
        dets,
        axis=1,
    )


def syndrome_event_count(
    dets: np.ndarray,
) -> np.ndarray:
    return np.sum(
        dets,
        axis=1,
    )


def make_feature_frame(
    dets: np.ndarray,
    distance: int,
    p: float,
    bias_ratio: float,
    rounds: int,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rho": syndrome_density(
                dets
            ),
            "event_count": (
                syndrome_event_count(
                    dets
                )
            ),
            "distance": distance,
            "p": p,
            "bias_ratio": (
                bias_ratio
            ),
            "rounds": rounds,
        }
    )


@dataclass
class DensityBinPolicy:
    table: pd.DataFrame
    budget_us: float

    def select(
        self,
        rho: float,
        distance: int,
    ) -> str:
        subset = self.table[
            self.table[
                "distance"
            ].eq(distance)
            & self.table[
                "p99_us"
            ].le(
                self.budget_us
            )
        ].copy()

        if subset.empty:
            raise RuntimeError(
                "No decoder satisfies "
                "the latency budget."
            )

        subset[
            "rho_distance"
        ] = (
            subset["rho_mid"]
            - rho
        ).abs()

        best = subset.sort_values(
            [
                "rho_distance",
                "logical_failure_rate",
                "p99_us",
            ]
        ).iloc[0]

        return str(
            best["decoder"]
        )