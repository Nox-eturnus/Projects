from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from qcnn_lab.analysis.splits import (
    make_critical_holdout_split,
    make_iid_split,
    make_parameter_block_split,
    save_split_manifest,
    validate_split_manifest,
)
from qcnn_lab.config import load_yaml
from qcnn_lab.physics.datasets import default_specs, load_labelled_dataset, load_transition_dataset


def build_evaluation_dataset(family: str, data_dir: Path) -> tuple[np.ndarray, pd.DataFrame]:
    """Combine labelled and transition sweep datasets to provide continuous critical parameter coverage."""
    states, meta = load_labelled_dataset(data_dir, family)
    trans_states, trans_meta = load_transition_dataset(data_dir, family)

    # Assign physical ground truth labels to transition states based on critical boundary
    specs = default_specs(int(meta["n_qubits"].iloc[0]))
    h_c = specs[family].critical_value

    trans_meta = trans_meta.copy()
    trans_meta["label"] = (trans_meta["parameter"] >= h_c).astype(int)

    all_states = np.concatenate([states, trans_states], axis=0)
    all_meta = pd.concat([meta, trans_meta], ignore_index=True)
    all_meta["sample_id"] = np.arange(len(all_meta))
    all_meta["hamiltonian_parameter"] = all_meta["parameter"]

    # Save combined evaluation dataset for 1:1 index alignment
    eval_states_path = data_dir / f"{family}_eval_states.npz"
    eval_meta_path = data_dir / f"{family}_eval_metadata.csv"
    np.savez_compressed(eval_states_path, states=all_states)
    all_meta.to_csv(eval_meta_path, index=False)
    return all_states, all_meta


def main():
    parser = argparse.ArgumentParser(description="Build hard train/validation/test evaluation splits.")
    parser.add_argument("--config", default="configs/evaluation.yaml", help="Path to evaluation config")
    parser.add_argument("--data-dir", default="data/processed", help="Path to processed data directory")
    parser.add_argument("--out-dir", default="results/evaluation_splits", help="Output directory for split manifests")
    args = parser.parse_args()

    cfg = load_yaml(args.config)["evaluation"]
    split_seeds = [int(s) for s in cfg["split_seeds"]]
    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    families = ["tfim", "xxz", "cluster"]
    manifest_records = []

    for family in families:
        states, meta = build_evaluation_dataset(family, data_dir)
        print(f"Building splits for {family.upper()} ({len(meta)} total samples)...")

        crit_cfg = cfg["critical_holdout"][family]
        test_min = float(crit_cfg["test_min"])
        test_max = float(crit_cfg["test_max"])

        block_cfg = cfg["parameter_block"][family]

        for seed in split_seeds:
            # 1. IID Split
            iid_manifest = make_iid_split(
                meta,
                seed=seed,
                train_fraction=float(cfg["iid"]["train_fraction"]),
                validation_fraction=float(cfg["iid"]["validation_fraction"]),
            )
            validate_split_manifest(iid_manifest, split_type="iid")
            iid_path = out_dir / f"{family}_iid_seed{seed}.csv"
            save_split_manifest(iid_manifest, iid_path)

            # 2. Parameter-block Split
            block_manifest = make_parameter_block_split(
                meta,
                block_cfg=block_cfg,
                seed=seed,
            )
            validate_split_manifest(block_manifest, split_type="parameter_block")
            block_path = out_dir / f"{family}_block_seed{seed}.csv"
            save_split_manifest(block_manifest, block_path)

            # 3. Critical-region Holdout Split
            crit_manifest = make_critical_holdout_split(
                meta,
                test_min=test_min,
                test_max=test_max,
                seed=seed,
                validation_fraction=float(cfg["iid"]["validation_fraction"]),
            )
            validate_split_manifest(
                crit_manifest,
                split_type="critical_holdout",
                test_min=test_min,
                test_max=test_max,
            )
            crit_path = out_dir / f"{family}_critical_seed{seed}.csv"
            save_split_manifest(crit_manifest, crit_path)

            manifest_records.append({
                "family": family,
                "seed": seed,
                "iid_train": int((iid_manifest["split"] == "train").sum()),
                "iid_val": int((iid_manifest["split"] == "validation").sum()),
                "iid_test": int((iid_manifest["split"] == "test").sum()),
                "block_train": int((block_manifest["split"] == "train").sum()),
                "block_val": int((block_manifest["split"] == "validation").sum()),
                "block_test": int((block_manifest["split"] == "test").sum()),
                "critical_train": int((crit_manifest["split"] == "train").sum()),
                "critical_val": int((crit_manifest["split"] == "validation").sum()),
                "critical_test": int((crit_manifest["split"] == "test").sum()),
            })

    summary_df = pd.DataFrame(manifest_records)
    summary_df.to_csv(out_dir / "splits_summary.csv", index=False)
    print(f"Successfully generated {len(manifest_records) * 3} split manifests in {out_dir}")
    print(f"Splits summary written to {out_dir / 'splits_summary.csv'}")


if __name__ == "__main__":
    main()
