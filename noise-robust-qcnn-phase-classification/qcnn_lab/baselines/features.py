from __future__ import annotations

import numpy as np

from qcnn_lab.physics.observables import site_feature_map


def observable_tensor(states: np.ndarray, n_qubits: int) -> np.ndarray:
    return np.asarray([site_feature_map(state, n_qubits) for state in states], dtype=np.float32)


def flatten_observables(features: np.ndarray) -> np.ndarray:
    features = np.asarray(features, dtype=np.float32)
    return features.reshape(len(features), -1)