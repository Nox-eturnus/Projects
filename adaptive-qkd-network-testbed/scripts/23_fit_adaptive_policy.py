import json
import pickle
from pathlib import Path

import pandas as pd

from qkd_lab.adaptive.policy import fit_empirical_policy


FEATURES = ["distance_km", "recent_qber", "recent_gain", "dark_probability", "detector_efficiency", "key_pool_bits", "demand_bps", "mdi_capable"]


def main():
    frame = pd.read_csv("data/policy/policy_dataset.csv")
    frame["mdi_capable"] = frame["mdi_capable"].astype(bool)
    train = frame[frame["scenario_id"] % 5 != 0].copy()
    policy = fit_empirical_policy(train, FEATURES)
    Path("results/adaptive").mkdir(parents=True, exist_ok=True)
    with Path("results/adaptive/policy.pkl").open("wb") as f:
        pickle.dump(policy, f)
    metadata = {"features": FEATURES, "training_scenarios": int(train["scenario_id"].nunique()), "split_rule": "scenario_id % 5 != 0"}
    Path("results/adaptive/policy_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    print("Adaptive policy fit PASSED")


if __name__ == "__main__":
    main()