from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

from qkd_lab.postprocessing.privacy import random_toeplitz_seed, toeplitz_hash


def main():
    rng = np.random.default_rng(2026)
    rows = []
    for input_bits, output_bits in ((256, 128), (1024, 256), (4096, 512)):
        bits = rng.integers(0, 2, input_bits, dtype=np.uint8)
        seed = random_toeplitz_seed(output_bits, input_bits, seed=input_bits)
        start = perf_counter()
        out1 = toeplitz_hash(bits, output_bits, seed)
        elapsed = (perf_counter() - start) * 1000.0
        out2 = toeplitz_hash(bits, output_bits, seed)
        assert np.array_equal(out1, out2)
        rows.append({"input_bits": input_bits, "output_bits": output_bits, "elapsed_ms": elapsed})
    frame = pd.DataFrame(rows)
    Path("results/reconciliation").mkdir(parents=True, exist_ok=True)
    frame.to_csv("results/reconciliation/privacy_amplification.csv", index=False)
    print(frame.to_string(index=False))
    print("Toeplitz privacy-amplification validation PASSED")


if __name__ == "__main__":
    main()