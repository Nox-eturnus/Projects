from pathlib import Path

import numpy as np

from qkd_lab.adaptive.actions import candidate_actions
from qkd_lab.adaptive.dataset import build_policy_frame


def main():
    rng = np.random.default_rng(2026)
    scenarios = []
    for scenario_id in range(30):
        distance = float(rng.uniform(10, 130))
        recent_qber = float(rng.uniform(0.01, 0.10))
        scenarios.append({
            "scenario_id": scenario_id,
            "distance_km": distance,
            "recent_qber": recent_qber,
            "recent_gain": float(max(1e-7, 0.12 * 10 ** (-0.02 * distance))),
            "dark_probability": float(10 ** rng.uniform(-8, -5)),
            "detector_efficiency": float(rng.uniform(0.2, 0.7)),
            "key_pool_bits": float(rng.uniform(0, 2_000_000)),
            "demand_bps": float(rng.uniform(1_000, 100_000)),
            "mdi_capable": bool(rng.random() < 0.45),
        })
    frame = build_policy_frame(scenarios, candidate_actions())
    Path("data/policy").mkdir(parents=True, exist_ok=True)
    frame.to_csv("data/policy/policy_dataset.csv", index=False)
    print(frame.head().to_string(index=False))
    print("Rows:", len(frame))
    print("Policy dataset written")


if __name__ == "__main__":
    main()