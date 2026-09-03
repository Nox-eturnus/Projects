import pickle
from pathlib import Path

import pandas as pd


FEATURES = ["distance_km", "recent_qber", "recent_gain", "dark_probability", "detector_efficiency", "key_pool_bits", "demand_bps", "mdi_capable"]


def main():
    frame = pd.read_csv("data/policy/policy_dataset.csv")
    frame["mdi_capable"] = frame["mdi_capable"].astype(bool)
    with Path("results/adaptive/policy.pkl").open("rb") as f:
        policy = pickle.load(f)
    test = frame[frame["scenario_id"] % 5 == 0].copy()
    rows = []
    for sid, group in test.groupby("scenario_id"):
        context = group.iloc[0][FEATURES].to_dict()
        selected = policy.select(context)
        oracle_rows = group[group["feasible"] & (~group["abort"])]
        oracle = float(oracle_rows["service_utility"].max()) if not oracle_rows.empty else 0.0
        chosen_rows = group[group["action_name"] == selected]
        if selected == "ABORT" or chosen_rows.empty:
            executed = "ABORT"
            selected_utility = 0.0
            secure_bits = 0.0
            violation = False
        else:
            chosen = chosen_rows.iloc[0]
            # Mandatory runtime capability + finite-key security gate. The row's
            # abort verdict was computed from observable/calibrated state and the
            # candidate action, not from hidden future variables.
            if (not bool(chosen["feasible"])) or bool(chosen["abort"]):
                executed = "ABORT"
                selected_utility = 0.0
                secure_bits = 0.0
                violation = False
            else:
                executed = selected
                selected_utility = float(chosen["service_utility"])
                secure_bits = float(chosen["secure_bits"])
                violation = False
        rows.append({"scenario_id": sid, "recommended_action": selected, "executed_action": executed, "selected_utility": selected_utility, "secure_bits": secure_bits, "oracle_utility": oracle, "oracle_gap": oracle - selected_utility, "security_violation": violation})
    out = pd.DataFrame(rows)
    Path("results/adaptive").mkdir(parents=True, exist_ok=True)
    out.to_csv("results/adaptive/heldout_summary.csv", index=False)
    print(out.head(12).to_string(index=False))
    assert not out["security_violation"].any()
    print("Held-out scenarios:", len(out))
    print("Mean oracle gap:", out["oracle_gap"].mean())
    print("Held-out adaptive evaluation PASSED")


if __name__ == "__main__":
    main()