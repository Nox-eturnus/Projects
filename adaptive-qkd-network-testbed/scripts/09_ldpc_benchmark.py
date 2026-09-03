from pathlib import Path

import pandas as pd

from qkd_lab.math_utils import h2
from qkd_lab.postprocessing.ldpc_reconciliation import ldpc_reconcile
from qkd_lab.protocols.decoy_bb84 import make_correlated_raw_keys


def main():
    rows = []
    for n in (128, 256, 512):
        for qber in (0.005, 0.01):
            for seed in range(2):
                alice, bob = make_correlated_raw_keys(n, qber, seed=10_000 + n + seed)
                result = ldpc_reconcile(alice, bob, qber, matrix_seed=2026 + seed, max_iter=60)
                denom = n * h2(qber)
                rows.append({
                    "n": n,
                    "qber": qber,
                    "seed": seed,
                    "success": result.success,
                    "disclosed_bits": result.disclosed_bits,
                    "messages": result.messages,
                    "iterations": result.rounds,
                    "elapsed_ms": result.elapsed_ms,
                    "f_ec": result.disclosed_bits / denom if denom > 0 else 0.0,
                })
    frame = pd.DataFrame(rows)
    Path("results/reconciliation").mkdir(parents=True, exist_ok=True)
    frame.to_csv("results/reconciliation/ldpc.csv", index=False)
    print(frame.groupby(["n", "qber"], as_index=False)["success"].mean().to_string(index=False))
    print("LDPC benchmark written")


if __name__ == "__main__":
    main()