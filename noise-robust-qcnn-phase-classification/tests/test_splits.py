import numpy as np
import pandas as pd

from qcnn_lab.analysis.splits import (
    load_split_manifest,
    make_critical_holdout_split,
    make_iid_split,
    make_parameter_block_split,
    split_indices_from_manifest,
    validate_split_manifest,
)
from qcnn_lab.qcnn.train import stratified_splits


def test_stratified_splits_are_disjoint_and_complete():
    y = np.array([0] * 20 + [1] * 20)
    s = stratified_splits(y, seed=7)
    all_idx = np.concatenate([s.train, s.validation, s.test])
    assert len(np.unique(all_idx)) == len(y)
    assert set(all_idx) == set(range(len(y)))
    for idx in (s.train, s.validation, s.test):
        assert set(y[idx]) == {0, 1}


def test_no_split_overlap():
    df = pd.DataFrame({
        "sample_id": range(40),
        "parameter": np.linspace(0.1, 1.9, 40),
        "label": [0] * 20 + [1] * 20,
    })
    manifest = make_iid_split(df, seed=42)
    validate_split_manifest(manifest, split_type="iid")
    train = manifest[manifest["split"] == "train"]["sample_id"].tolist()
    val = manifest[manifest["split"] == "validation"]["sample_id"].tolist()
    test = manifest[manifest["split"] == "test"]["sample_id"].tolist()

    assert len(set(train).intersection(set(val))) == 0
    assert len(set(train).intersection(set(test))) == 0
    assert len(set(val).intersection(set(test))) == 0
    assert len(train) + len(val) + len(test) == len(df)


def test_parameter_holdout_is_disjoint():
    df = pd.DataFrame({
        "sample_id": range(40),
        "parameter": np.linspace(0.1, 1.9, 40),
        "label": [0] * 20 + [1] * 20,
    })
    block_cfg = {
        "train_low_max": 0.5,
        "val_low_min": 0.5,
        "val_low_max": 0.7,
        "test_low_min": 0.7,
        "test_high_max": 1.3,
        "val_high_min": 1.3,
        "val_high_max": 1.5,
        "train_high_min": 1.5,
    }
    manifest = make_parameter_block_split(df, block_cfg, seed=11)
    validate_split_manifest(manifest, split_type="parameter_block")

    train_params = manifest[manifest["split"] == "train"]["hamiltonian_parameter"]
    test_params = manifest[manifest["split"] == "test"]["hamiltonian_parameter"]
    # Train is either far left (<= 0.5) or far right (>= 1.5)
    for p in train_params:
        assert p <= 0.5 or p >= 1.5


def test_critical_region_absent_from_training():
    df = pd.DataFrame({
        "sample_id": range(50),
        "parameter": np.linspace(0.2, 1.8, 50),
        "label": [0] * 25 + [1] * 25,
    })
    test_min, test_max = 0.80, 1.20
    manifest = make_critical_holdout_split(df, test_min=test_min, test_max=test_max, seed=37)
    validate_split_manifest(manifest, split_type="critical_holdout", test_min=test_min, test_max=test_max)

    train_params = manifest[manifest["split"] == "train"]["hamiltonian_parameter"]
    val_params = manifest[manifest["split"] == "validation"]["hamiltonian_parameter"]
    test_params = manifest[manifest["split"] == "test"]["hamiltonian_parameter"]

    assert len(test_params) > 0
    assert np.all((test_params >= test_min) & (test_params <= test_max))
    assert not np.any((train_params >= test_min) & (train_params <= test_max))
    assert not np.any((val_params >= test_min) & (val_params <= test_max))


def test_split_reproducibility():
    df = pd.DataFrame({
        "sample_id": range(30),
        "parameter": np.linspace(0.2, 1.8, 30),
        "label": [0] * 15 + [1] * 15,
    })
    m1 = make_iid_split(df, seed=99)
    m2 = make_iid_split(df, seed=99)
    pd.testing.assert_frame_equal(m1, m2)

    indices = split_indices_from_manifest(m1)
    assert len(indices.train) == (m1["split"] == "train").sum()