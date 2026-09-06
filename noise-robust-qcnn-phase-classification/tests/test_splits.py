import numpy as np

from qcnn_lab.qcnn.train import stratified_splits


def test_stratified_splits_are_disjoint_and_complete():
    y = np.array([0] * 20 + [1] * 20)
    s = stratified_splits(y, seed=7)
    all_idx = np.concatenate([s.train, s.validation, s.test])
    assert len(np.unique(all_idx)) == len(y)
    assert set(all_idx) == set(range(len(y)))
    for idx in (s.train, s.validation, s.test):
        assert set(y[idx]) == {0, 1}