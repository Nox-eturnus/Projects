from pathlib import Path

import numpy as np
import pandas as pd

from qkd_lab.adaptive.actions import candidate_actions
from qkd_lab.adaptive.dataset import build_policy_frame
from qkd_lab.config import load_yaml


def generate_dynamic_trajectories() -> list[dict]:
    cfg = load_yaml("configs/adaptive.yaml")["trajectories"]
    rng = np.random.default_rng(cfg["random_seed"])
    num_trajectories = cfg["num_trajectories"]
    steps_per_trajectory = cfg["steps_per_trajectory"]
    drift_sigma = cfg["drift_sigma_qber"]
    attack_prob = cfg["attack_probability"]
    burst_demand = cfg["burst_demand_bps"]
    normal_demand = cfg["normal_demand_bps"]

    scenarios = []
    global_id = 0

    for traj_id in range(num_trajectories):
        # Baseline conditions for this trajectory
        distance = float(rng.uniform(15, 110))
        dark_prob = float(10 ** rng.uniform(-8, -5))
        det_eff = float(rng.uniform(0.25, 0.70))
        mdi_capable = bool(rng.random() < 0.50)
        has_attack = bool(rng.random() < attack_prob)
        attack_start = rng.integers(2, max(3, steps_per_trajectory - 2)) if has_attack else -1
        attack_duration = rng.integers(2, 4)

        base_qber = float(rng.uniform(0.015, 0.045))
        qber = base_qber
        key_pool = float(rng.uniform(200_000, 1_500_000))

        for step in range(steps_per_trajectory):
            # 1. Channel drift
            qber_drift = float(rng.normal(0.0, drift_sigma))
            qber = max(0.005, min(0.14, qber + qber_drift))

            # 2. Attack episode
            in_attack = has_attack and (attack_start <= step < attack_start + attack_duration)
            if in_attack:
                # Sudden elevated QBER from intercept-resend or noise injection
                effective_qber = min(0.14, qber + float(rng.uniform(0.05, 0.09)))
                gain_penalty = float(rng.uniform(0.3, 0.6))
            else:
                effective_qber = qber
                gain_penalty = 1.0

            # Expected optical gain from distance & attenuation
            base_gain = float(max(1e-7, 0.12 * (10 ** (-0.02 * distance))))
            gain = max(1e-7, base_gain * gain_penalty)

            # 3. Demand burst
            is_burst = (step == 3 or step == 4) and (traj_id % 2 == 1)
            demand = burst_demand if is_burst else normal_demand

            # Key pool dynamic evolution: previous step consumption
            if step > 0:
                key_pool = max(0.0, key_pool - demand * 0.1 + float(rng.uniform(0, 100_000)))

            scenario = {
                "scenario_id": global_id,
                "trajectory_id": traj_id,
                "time_step": step,
                "phase": "attack" if in_attack else ("burst" if is_burst else "normal"),
                "distance_km": distance,
                "recent_qber": effective_qber,
                "recent_gain": gain,
                "dark_probability": dark_prob,
                "detector_efficiency": det_eff,
                "key_pool_bits": key_pool,
                "demand_bps": float(demand),
                "mdi_capable": mdi_capable,
            }
            scenarios.append(scenario)
            global_id += 1

    return scenarios


def main():
    scenarios = generate_dynamic_trajectories()
    actions = candidate_actions()
    frame = build_policy_frame(scenarios, actions)
    Path("data/policy").mkdir(parents=True, exist_ok=True)
    frame.to_csv("data/policy/policy_dataset.csv", index=False)
    print(f"Generated {len(scenarios)} dynamic trajectory steps across {scenarios[-1]['trajectory_id'] + 1} trajectories.")
    print(f"Total action-scenario rows: {len(frame)}")
    print("Policy dataset written to data/policy/policy_dataset.csv")


if __name__ == "__main__":
    main()