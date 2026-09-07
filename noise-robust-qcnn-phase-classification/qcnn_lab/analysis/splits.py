from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split


@dataclass(frozen=True)
class SplitIndices:
    train: np.ndarray
    validation: np.ndarray
    test: np.ndarray


def make_iid_split(
    df: pd.DataFrame,
    *,
    seed: int,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
) -> pd.DataFrame:
    """Create a stratified IID train/validation/test split manifest."""
    df = df.copy()
    if "sample_id" not in df.columns:
        df["sample_id"] = np.arange(len(df))
    if "hamiltonian_parameter" not in df.columns and "parameter" in df.columns:
        df["hamiltonian_parameter"] = df["parameter"]

    y = df["label"].to_numpy(dtype=int)
    idx = np.arange(len(df))

    train_idx, temp_idx = train_test_split(
        idx,
        train_size=train_fraction,
        stratify=y,
        random_state=seed,
    )
    remaining_fraction = 1.0 - train_fraction
    val_share = validation_fraction / remaining_fraction
    val_idx, test_idx = train_test_split(
        temp_idx,
        train_size=val_share,
        stratify=y[temp_idx],
        random_state=seed + 1,
    )

    df["split"] = ""
    df.loc[train_idx, "split"] = "train"
    df.loc[val_idx, "split"] = "validation"
    df.loc[test_idx, "split"] = "test"
    df["seed"] = seed
    df["split_type"] = "iid"

    cols = ["sample_id", "family", "hamiltonian_parameter", "label", "split", "seed"]
    available_cols = [c for c in cols if c in df.columns]
    return df[available_cols + [c for c in df.columns if c not in available_cols]]


def make_parameter_block_split(
    df: pd.DataFrame,
    block_cfg: dict,
    *,
    seed: int,
) -> pd.DataFrame:
    """Assign samples based on disjoint parameter blocks.

    Train: far-left + far-right parameter regions
    Validation: intermediate unseen bands
    Test: separate unseen bands

    Note: Parameter-block boundaries define a canonical deterministic spatial partitioning.
    Variance across repeated seed evaluations under parameter blocks isolates optimizer initialization
    and training trajectory sensitivity, rather than independent spatial resampling.
    """
    df = df.copy()
    if "sample_id" not in df.columns:
        df["sample_id"] = np.arange(len(df))
    if "hamiltonian_parameter" not in df.columns and "parameter" in df.columns:
        df["hamiltonian_parameter"] = df["parameter"]

    param = df["hamiltonian_parameter"].to_numpy(dtype=float)
    label = df["label"].to_numpy(dtype=int)

    train_low_max = float(block_cfg["train_low_max"])
    val_low_min = float(block_cfg["val_low_min"])
    val_low_max = float(block_cfg["val_low_max"])
    test_low_min = float(block_cfg["test_low_min"])

    test_high_max = float(block_cfg["test_high_max"])
    val_high_min = float(block_cfg["val_high_min"])
    val_high_max = float(block_cfg["val_high_max"])
    train_high_min = float(block_cfg["train_high_min"])

    splits = np.full(len(df), "", dtype=object)

    for i in range(len(df)):
        p = param[i]
        lbl = label[i]
        if lbl == 0:
            if p <= train_low_max:
                splits[i] = "train"
            elif val_low_min < p <= val_low_max:
                splits[i] = "validation"
            elif p > test_low_min:
                splits[i] = "test"
            else:
                splits[i] = "validation"
        else:
            if p >= train_high_min:
                splits[i] = "train"
            elif val_high_min <= p < val_high_max:
                splits[i] = "validation"
            elif p <= test_high_max:
                splits[i] = "test"
            else:
                splits[i] = "validation"

    df["split"] = splits
    df["seed"] = seed
    df["split_type"] = "parameter_block"

    cols = ["sample_id", "family", "hamiltonian_parameter", "label", "split", "seed"]
    available_cols = [c for c in cols if c in df.columns]
    return df[available_cols + [c for c in df.columns if c not in available_cols]]


def make_critical_holdout_split(
    df: pd.DataFrame,
    test_min: float,
    test_max: float,
    *,
    seed: int,
    validation_fraction: float = 0.15,
) -> pd.DataFrame:
    """Hold out the critical interval [test_min, test_max] entirely for testing."""
    df = df.copy()
    if "sample_id" not in df.columns:
        df["sample_id"] = np.arange(len(df))
    if "hamiltonian_parameter" not in df.columns and "parameter" in df.columns:
        df["hamiltonian_parameter"] = df["parameter"]

    param = df["hamiltonian_parameter"].to_numpy(dtype=float)
    label = df["label"].to_numpy(dtype=int)

    is_critical = (param >= test_min) & (param <= test_max)
    test_idx = np.where(is_critical)[0]
    non_critical_idx = np.where(~is_critical)[0]

    # Split non-critical indices into train and validation
    train_sub, val_sub = train_test_split(
        non_critical_idx,
        test_size=validation_fraction,
        stratify=label[non_critical_idx],
        random_state=seed,
    )

    df["split"] = ""
    df.loc[train_sub, "split"] = "train"
    df.loc[val_sub, "split"] = "validation"
    df.loc[test_idx, "split"] = "test"
    df["seed"] = seed
    df["split_type"] = "critical_holdout"

    cols = ["sample_id", "family", "hamiltonian_parameter", "label", "split", "seed"]
    available_cols = [c for c in cols if c in df.columns]
    return df[available_cols + [c for c in df.columns if c not in available_cols]]


def validate_split_manifest(
    manifest: pd.DataFrame,
    *,
    split_type: str | None = None,
    test_min: float | None = None,
    test_max: float | None = None,
) -> None:
    """Validate that train, validation, and test splits are strictly disjoint."""
    train_ids = set(manifest[manifest["split"] == "train"]["sample_id"])
    val_ids = set(manifest[manifest["split"] == "validation"]["sample_id"])
    test_ids = set(manifest[manifest["split"] == "test"]["sample_id"])

    assert len(train_ids.intersection(val_ids)) == 0, "train and validation overlap!"
    assert len(train_ids.intersection(test_ids)) == 0, "train and test overlap!"
    assert len(val_ids.intersection(test_ids)) == 0, "validation and test overlap!"

    total_samples = len(manifest)
    total_assigned = len(train_ids) + len(val_ids) + len(test_ids)
    assert total_samples == total_assigned, f"unassigned samples detected: {total_samples} != {total_assigned}"

    if split_type == "critical_holdout" and test_min is not None and test_max is not None:
        train_params = manifest[manifest["split"] == "train"]["hamiltonian_parameter"].to_numpy(dtype=float)
        val_params = manifest[manifest["split"] == "validation"]["hamiltonian_parameter"].to_numpy(dtype=float)

        train_leaks = np.any((train_params >= test_min) & (train_params <= test_max))
        val_leaks = np.any((val_params >= test_min) & (val_params <= test_max))

        assert not train_leaks, f"Critical region [{test_min}, {test_max}] leaked into training!"
        assert not val_leaks, f"Critical region [{test_min}, {test_max}] leaked into validation!"


def split_indices_from_manifest(manifest: pd.DataFrame) -> SplitIndices:
    """Return numpy arrays of integer row indices for train, validation, and test splits."""
    train_idx = np.where(manifest["split"] == "train")[0]
    val_idx = np.where(manifest["split"] == "validation")[0]
    test_idx = np.where(manifest["split"] == "test")[0]
    return SplitIndices(train=train_idx, validation=val_idx, test=test_idx)


def save_split_manifest(manifest: pd.DataFrame, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(output_path, index=False)


def load_split_manifest(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path)
