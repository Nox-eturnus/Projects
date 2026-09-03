from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from qkd_lab.adaptive.features import validate_feature_columns


@dataclass
class EmpiricalPolicy:
    table: pd.DataFrame
    feature_columns: tuple[str, ...]

    def select(self, context: dict) -> str:
        validate_feature_columns(list(self.feature_columns))
        candidates = self.table[self.table["feasible"] & (~self.table["abort"])].copy()
        if candidates.empty:
            return "ABORT"

        # Nearest-neighbour lookup in normalized observable feature space.
        distance = pd.Series(0.0, index=candidates.index)
        for col in self.feature_columns:
            if col == "mdi_capable":
                candidates = candidates[candidates[col] == context[col]]
                if candidates.empty:
                    return "ABORT"
                distance = distance.loc[candidates.index]
                continue
            scale = max(float(self.table[col].std()), 1e-9)
            distance = distance.loc[candidates.index] + ((candidates[col] - float(context[col])) / scale) ** 2
        nearest = candidates.assign(_distance=distance).nsmallest(min(40, len(candidates)), "_distance")
        score = nearest.groupby("action_name", as_index=False)["service_utility"].mean()
        if score.empty:
            return "ABORT"
        return str(score.sort_values("service_utility", ascending=False).iloc[0]["action_name"])


def fit_empirical_policy(frame: pd.DataFrame, feature_columns: list[str]) -> EmpiricalPolicy:
    validate_feature_columns(feature_columns)
    required = set(feature_columns) | {"action_name", "feasible", "abort", "service_utility"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"policy frame missing columns: {sorted(missing)}")
    return EmpiricalPolicy(frame.copy(), tuple(feature_columns))