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

        # Step 1: Filter on hard constraints like mdi_capable
        pool = candidates
        if "mdi_capable" in self.feature_columns and "mdi_capable" in context:
            pool = pool[pool["mdi_capable"] == context["mdi_capable"]]
            if pool.empty:
                return "ABORT"

        # Step 2: Compute context distance at the unique scenario level to avoid action-row cutoff bias
        has_scenario_id = "scenario_id" in pool.columns
        if not has_scenario_id:
            pool = pool.assign(_scenario_id=pool.groupby(list(self.feature_columns), sort=False).ngroup())
        id_col = "scenario_id" if has_scenario_id else "_scenario_id"

        numeric_cols = [c for c in self.feature_columns if c != "mdi_capable"]
        scenario_features = (
            pool[[id_col] + numeric_cols]
            .drop_duplicates(subset=[id_col])
            .set_index(id_col)
        )
        if scenario_features.empty:
            return "ABORT"

        dist = pd.Series(0.0, index=scenario_features.index)
        for col in numeric_cols:
            scale = max(float(self.table[col].std()), 1e-9)
            dist += ((scenario_features[col] - float(context[col])) / scale) ** 2

        # Step 3: Pick K nearest unique scenario contexts
        k = min(12, len(scenario_features))
        nearest_ids = dist.nsmallest(k).index

        # Step 4: Score candidate actions across all matching rows for equal context support
        matched_rows = pool[pool[id_col].isin(nearest_ids)]
        score = matched_rows.groupby("action_name", as_index=False)["service_utility"].mean()
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