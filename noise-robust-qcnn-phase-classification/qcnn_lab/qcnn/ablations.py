from __future__ import annotations

from typing import Tuple

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score

from qcnn_lab.physics.observables import (
    cluster_stabilizer_order,
    tfim_long_range_zz,
    xxz_staggered_structure,
)


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
    # Sample real and imaginary parts from standard normal distribution
    real_parts = rng.normal(size=(n_samples, dim))
    imag_parts = rng.normal(size=(n_samples, dim))
    complex_states = real_parts + 1j * imag_parts

    # Normalize each statevector to unit norm
    norms = np.linalg.norm(complex_states, axis=1, keepdims=True)
    normalized_states = complex_states / norms

    # Balanced arbitrary labels (first half 0, second half 1, shuffled)
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
        # Return probability of class 1
        probs = self.clf.predict_proba(feats)
        if probs.shape[1] == 1:
            return np.ones(len(states)) if self.clf.classes_[0] == 1 else np.zeros(len(states))
        return probs[:, 1]

    def predict(self, states: np.ndarray) -> np.ndarray:
        p1 = self.predict_proba(states)
        return (p1 >= 0.5).astype(int)
