from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import numpy as np
from scipy.optimize import minimize
from sklearn.model_selection import train_test_split

from qcnn_lab.qcnn.architecture import QCNNArchitecture, parameter_count
from qcnn_lab.qcnn.evaluate import batch_predict, binary_cross_entropy


@dataclass(frozen=True)
class SplitIndices:
    train: np.ndarray
    validation: np.ndarray
    test: np.ndarray


def stratified_splits(labels: np.ndarray, *, train_fraction: float = 0.70, validation_fraction: float = 0.15, seed: int = 12345) -> SplitIndices:
    labels = np.asarray(labels, dtype=int)
    idx = np.arange(len(labels))
    train_idx, temp_idx = train_test_split(idx, train_size=train_fraction, stratify=labels, random_state=seed)
    remaining = 1.0 - train_fraction
    val_share = validation_fraction / remaining
    val_idx, test_idx = train_test_split(temp_idx, train_size=val_share, stratify=labels[temp_idx], random_state=seed + 1)
    return SplitIndices(np.sort(train_idx), np.sort(val_idx), np.sort(test_idx))


def train_ideal_qcnn(
    states: np.ndarray,
    labels: np.ndarray,
    n_qubits: int,
    architecture: QCNNArchitecture,
    train_idx: np.ndarray,
    validation_idx: np.ndarray,
    *,
    maxiter: int = 120,
    seed: int = 12345,
) -> tuple[np.ndarray, list[dict], float]:
    rng = np.random.default_rng(seed)
    x0 = rng.normal(0.0, 0.15, size=parameter_count(n_qubits, architecture))
    history: list[dict] = []
    started = perf_counter()

    def objective(x: np.ndarray) -> float:
        p = batch_predict(states[train_idx], x, architecture, n_qubits)
        loss = binary_cross_entropy(labels[train_idx], p)
        history.append({"evaluation": len(history), "train_loss": loss})
        return loss

    result = minimize(objective, x0, method="COBYLA", options={"maxiter": int(maxiter), "rhobeg": 0.25, "tol": 1e-4})
    params = np.asarray(result.x, dtype=float)
    val_p = batch_predict(states[validation_idx], params, architecture, n_qubits)
    val_loss = binary_cross_entropy(labels[validation_idx], val_p)
    history.append({"evaluation": len(history), "validation_loss": val_loss, "success": bool(result.success), "message": str(result.message)})
    return params, history, perf_counter() - started


def train_qcnn_from_manifest(
    states: np.ndarray,
    labels: np.ndarray,
    n_qubits: int,
    architecture: QCNNArchitecture,
    manifest: any,
    *,
    maxiter: int = 120,
    seed: int = 12345,
) -> tuple[np.ndarray, list[dict], float]:
    """Train QCNN using explicit indices from a split manifest DataFrame or SplitIndices."""
    if hasattr(manifest, "train") and hasattr(manifest, "validation"):
        train_idx, val_idx = manifest.train, manifest.validation
    else:
        import pandas as pd
        if isinstance(manifest, pd.DataFrame):
            train_idx = np.where(manifest["split"] == "train")[0]
            val_idx = np.where(manifest["split"] == "validation")[0]
        else:
            raise TypeError(f"unsupported manifest type {type(manifest)}")
    return train_ideal_qcnn(
        states,
        labels,
        n_qubits,
        architecture,
        train_idx,
        val_idx,
        maxiter=maxiter,
        seed=seed,
    )