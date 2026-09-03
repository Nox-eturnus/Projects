from pathlib import Path

import pandas as pd

from qkd_lab.math_utils import h2
from qkd_lab.postprocessing.cascade import cascade_reconcile
from qkd_lab.protocols.decoy_bb84 import make_correlated_raw_keys


def main():
    rows = []
    for n in (2_000, 5_000, 10_000):
        for qber in (0.01, 0.02, 0.03):
            alice, bob = make_correlated_raw_keys(n, qber, seed=n + int(qber * 10000))
            result = cascade_reconcile(alice, bob, qber, passes=8, seed=2026)
            denom = n * h2(qber)
            rows.append({
                "n": n,
                "qber": qber,
                "success": result.success,
                "disclosed_bits": result.disclosed_bits,
                "messages": result.messages,
                "rounds": result.rounds,
                "elapsed_ms": result.elapsed_ms,
                "f_ec": result.disclosed_bits / denom if denom > 0 else 0.0,
            })
    frame = pd.DataFrame(rows)
    Path("results/reconciliation").mkdir(parents=True, exist_ok=True)
    frame.to_csv("results/reconciliation/cascade.csv", index=False)
    print(frame.to_string(index=False))
    print("Cascade benchmark written")


if __name__ == "__main__":
    main()