import json
import pickle
from pathlib import Path

import pandas as pd

from qkd_lab.adaptive.features import ALLOWED_FEATURES
from qkd_lab.adaptive.policy import fit_empirical_policy
from qkd_lab.config import load_yaml


def main():
    cfg = load_yaml("configs/adaptive.yaml")
    split_mod = cfg["evaluation"]["train_trajectory_split_modulo"]

    frame = pd.read_csv("data/policy/policy_dataset.csv")
    frame["mdi_capable"] = frame["mdi_capable"].astype(bool)

    # Split by trajectory_id to test generalization to unseen trajectories
    train = frame[frame["trajectory_id"] % split_mod != 0].copy()
    features = list(ALLOWED_FEATURES)

    policy = fit_empirical_policy(train, features)
    Path("results/adaptive").mkdir(parents=True, exist_ok=True)
    with Path("results/adaptive/policy.pkl").open("wb") as f:
        pickle.dump(policy, f)

    metadata = {
        "features": features,
        "training_trajectories": int(train["trajectory_id"].nunique()),
        "training_scenarios": int(train["scenario_id"].nunique()),
        "split_rule": f"trajectory_id % {split_mod} != 0",
    }
    Path("results/adaptive/policy_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    print("Adaptive policy fit PASSED")


if __name__ == "__main__":
    main()