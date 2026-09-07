from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, log_loss, roc_auc_score


@dataclass(frozen=True)
class BinaryMetrics:
    accuracy: float
    balanced_accuracy: float
    f1: float
    roc_auc: float
    log_loss: float
    brier_score: float
    ece: float


def binary_metrics(y_true: np.ndarray, p1: np.ndarray) -> BinaryMetrics:
    y_true = np.asarray(y_true, dtype=int)
    p1 = np.clip(np.asarray(p1, dtype=float), 1e-7, 1 - 1e-7)
    y_pred = (p1 >= 0.5).astype(int)
    auc = float("nan") if len(np.unique(y_true)) < 2 else float(roc_auc_score(y_true, p1))
    bs = float(np.mean((p1 - y_true) ** 2))
    ece = expected_calibration_error(y_true, p1)
    return BinaryMetrics(
        accuracy=float(accuracy_score(y_true, y_pred)),
        balanced_accuracy=float(balanced_accuracy_score(y_true, y_pred)),
        f1=float(f1_score(y_true, y_pred, zero_division=0)),
        roc_auc=auc,
        log_loss=float(log_loss(y_true, np.column_stack([1 - p1, p1]), labels=[0, 1])),
        brier_score=bs,
        ece=float(ece),
    )



def bootstrap_accuracy_ci(y_true: np.ndarray, p1: np.ndarray, *, n_boot: int = 2000, seed: int = 12345) -> tuple[float, float]:
    y_true = np.asarray(y_true, dtype=int)
    p1 = np.asarray(p1, dtype=float)
    if len(y_true) == 0:
        raise ValueError("empty sample")
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y_true), size=len(y_true))
        vals.append(accuracy_score(y_true[idx], p1[idx] >= 0.5))
    low, high = np.quantile(vals, [0.025, 0.975])
    return float(low), float(high)


def expected_calibration_error(y_true: np.ndarray, p1: np.ndarray, bins: int = 10) -> float:
    y_true = np.asarray(y_true, dtype=int)
    p1 = np.asarray(p1, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(y_true)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p1 >= lo) & (p1 < hi if hi < 1 else p1 <= hi)
        if not np.any(mask):
            continue
        conf = float(np.mean(p1[mask]))
        acc = float(np.mean(y_true[mask]))
        ece += mask.sum() / total * abs(acc - conf)
    return float(ece)