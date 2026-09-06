from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from qcnn_lab.physics.datasets import default_specs, load_transition_dataset


def main():
    Path("results/figures").mkdir(parents=True, exist_ok=True)
    rows = []
    for family in default_specs().keys():
        _, meta = load_transition_dataset("data/processed", family)
        rows.append(meta)
        plt.plot(meta["parameter"], meta["physical_diagnostic"], label=family)
    pd.concat(rows, ignore_index=True).to_csv("results/datasets/transition_diagnostics.csv", index=False)
    plt.xlabel("Hamiltonian control parameter")
    plt.ylabel("Family-specific physical diagnostic")
    plt.legend()
    plt.tight_layout()
    plt.savefig("results/figures/transition_diagnostics.png", dpi=180)
    plt.close()
    print("Observable diagnostics written")


if __name__ == "__main__":
    main()