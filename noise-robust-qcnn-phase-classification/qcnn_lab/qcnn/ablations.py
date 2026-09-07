from __future__ import annotations

from typing import Any, Tuple

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score

from qcnn_lab.analysis.calibration import brier_score
from qcnn_lab.physics.observables import (
    cluster_stabilizer_order,
    tfim_long_range_zz,
    xxz_staggered_structure,
)
from qcnn_lab.qcnn.architecture import QCNNArchitecture, parameter_count
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.train import train_ideal_qcnn


def make_shuffled_labels_data(
    labels: np.ndarray,
    *,
    seed: int = 12345,
) -> np.ndarray:
    """Randomly permute training labels while keeping quantum states fixed."""
    rng = np.random.default_rng(seed)
    shuffled = labels.copy()
    rng.shuffle(shuffled)
    return shuffled


def make_random_quantum_states(
    n_samples: int,
    n_qubits: int,
    *,
    seed: int = 12345,
) -> Tuple[np.ndarray, np.ndarray]:
    """Generate random Haar / normalized complex statevectors with arbitrary balanced labels."""
    dim = 2**n_qubits
    rng = np.random.default_rng(seed)
    real_parts = rng.normal(size=(n_samples, dim))
    imag_parts = rng.normal(size=(n_samples, dim))
    complex_states = real_parts + 1j * imag_parts

    norms = np.linalg.norm(complex_states, axis=1, keepdims=True)
    normalized_states = complex_states / norms

    labels = np.concatenate([
        np.zeros(n_samples // 2, dtype=int),
        np.ones(n_samples - (n_samples // 2), dtype=int),
    ])
    rng.shuffle(labels)
    return normalized_states, labels


def compute_physical_order_parameters(
    states: np.ndarray,
    family: str,
    n_qubits: int,
) -> np.ndarray:
    """Compute physical diagnostic / order parameter for each state."""
    features = []
    for st in states:
        if family == "tfim":
            val = tfim_long_range_zz(st, n_qubits)
        elif family == "cluster":
            val = cluster_stabilizer_order(st, n_qubits)
        elif family == "xxz":
            val = xxz_staggered_structure(st, n_qubits)
        else:
            raise ValueError(f"unknown family {family}")
        features.append(val)
    return np.asarray(features, dtype=float).reshape(-1, 1)


class PhysicsOrderParameterBaseline:
    """Simple baseline classifier using the known physical order parameter."""

    def __init__(self, family: str, n_qubits: int):
        self.family = family
        self.n_qubits = n_qubits
        self.clf = LogisticRegression()

    def fit(self, states: np.ndarray, labels: np.ndarray) -> PhysicsOrderParameterBaseline:
        feats = compute_physical_order_parameters(states, self.family, self.n_qubits)
        self.clf.fit(feats, labels)
        return self

    def predict_proba(self, states: np.ndarray) -> np.ndarray:
        feats = compute_physical_order_parameters(states, self.family, self.n_qubits)
        probs = self.clf.predict_proba(feats)
        if probs.shape[1] == 1:
            return np.ones(len(states)) if self.clf.classes_[0] == 1 else np.zeros(len(states))
        return probs[:, 1]

    def predict(self, states: np.ndarray) -> np.ndarray:
        p1 = self.predict_proba(states)
        return (p1 >= 0.5).astype(int)


class UntrainedQCNNBaseline:
    """Evaluate random untrained parameter initializations to measure inductive bias floor."""

    def __init__(self, architecture: QCNNArchitecture, n_qubits: int, seed: int = 12345):
        self.architecture = architecture
        self.n_qubits = n_qubits
        rng = np.random.default_rng(seed)
        self.params = rng.normal(0.0, 0.15, size=parameter_count(n_qubits, architecture))

    def predict_proba(self, states: np.ndarray) -> np.ndarray:
        return batch_predict(states, self.params, self.architecture, self.n_qubits)

    def predict(self, states: np.ndarray) -> np.ndarray:
        probs = self.predict_proba(states)
        return (probs >= 0.5).astype(int)


def evaluate_shuffled_label_permutation_distribution(
    states: np.ndarray,
    labels: np.ndarray,
    n_qubits: int,
    architecture: QCNNArchitecture,
    train_idx: np.ndarray,
    val_idx: np.ndarray,
    test_idx: np.ndarray,
    *,
    true_test_ba: float | None = None,
    n_permutations: int = 25,
    maxiter: int = 25,
    seed: int = 12345,
) -> dict[str, Any]:
    """Evaluate classifier performance over an ensemble of random label permutations.

    Measures:
    1. memorization (train BA on shuffled labels)
    2. out-of-sample generalization (test BA on true labels)
    3. test Brier score
    4. empirical permutation p-value: p = (1 + #{BA_perm >= BA_real}) / (1 + N_perm)
    """
    records = []
    for k in range(n_permutations):
        opt_seed = seed + 1000 + k * 31
        shuffled_train_y = make_shuffled_labels_data(labels[train_idx], seed=seed + k * 17)
        y_copy = labels.copy()
        y_copy[train_idx] = shuffled_train_y

        params, _, _ = train_ideal_qcnn(
            states,
            y_copy,
            n_qubits,
            architecture,
            train_idx,
            val_idx,
            maxiter=maxiter,
            seed=opt_seed,
        )

        train_p = batch_predict(states[train_idx], params, architecture, n_qubits)
        test_p = batch_predict(states[test_idx], params, architecture, n_qubits)

        train_ba_shuf = float(balanced_accuracy_score(shuffled_train_y, (train_p >= 0.5).astype(int)))
        train_ba_real = float(balanced_accuracy_score(labels[train_idx], (train_p >= 0.5).astype(int)))
        test_ba_real = float(balanced_accuracy_score(labels[test_idx], (test_p >= 0.5).astype(int)))
        test_bs = float(brier_score(labels[test_idx], test_p))

        records.append({
            "permutation_id": k + 1,
            "optimizer_seed": opt_seed,
            "train_ba_shuffled": train_ba_shuf,
            "train_ba_real": train_ba_real,
            "test_ba_real": test_ba_real,
            "test_brier": test_bs,
        })

    test_bas = [r["test_ba_real"] for r in records]
    train_shuf_bas = [r["train_ba_shuffled"] for r in records]

    p_value = None
    if true_test_ba is not None:
        count_ge = sum(1 for ba in test_bas if ba >= true_test_ba)
        p_value = float((count_ge + 1) / (len(test_bas) + 1))

    return {
        "n_permutations": n_permutations,
        "train_ba_shuffled_mean": float(np.mean(train_shuf_bas)),
        "train_ba_shuffled_std": float(np.std(train_shuf_bas, ddof=1)) if len(train_shuf_bas) > 1 else 0.0,
        "test_ba_real_mean": float(np.mean(test_bas)),
        "test_ba_real_std": float(np.std(test_bas, ddof=1)) if len(test_bas) > 1 else 0.0,
        "empirical_p_value": p_value,
        "true_test_ba": true_test_ba,
        "permutation_runs": records,
    }

