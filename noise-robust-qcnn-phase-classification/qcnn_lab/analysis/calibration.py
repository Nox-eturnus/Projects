from __future__ import annotations

import numpy as np
from sklearn.metrics import log_loss


def brier_score(y_true: np.ndarray, p1: np.ndarray) -> float:
    """Compute Brier score: mean squared error between probabilities and binary labels."""
    y_true = np.asarray(y_true, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    return float(np.mean((p1 - y_true) ** 2))


def negative_log_likelihood(y_true: np.ndarray, p1: np.ndarray, eps: float = 1e-7) -> float:
    """Compute negative log likelihood / binary cross entropy."""
    y_true = np.asarray(y_true, dtype=float)
    p1 = np.clip(np.asarray(p1, dtype=float), eps, 1.0 - eps)
    return float(-np.mean(y_true * np.log(p1) + (1.0 - y_true) * np.log(1.0 - p1)))


def expected_calibration_error(
    y_true: np.ndarray,
    p1: np.ndarray,
    *,
    n_bins: int = 10,
) -> float:
    """Compute Expected Calibration Error (ECE) with equal-width bins."""
    y_true = np.asarray(y_true, dtype=int)
    p1 = np.asarray(p1, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    n = len(y_true)
    if n == 0:
        return 0.0

    ece = 0.0
    for i in range(n_bins):
        low, high = edges[i], edges[i + 1]
        mask = (p1 >= low) & (p1 <= high if i == n_bins - 1 else p1 < high)
        count = int(mask.sum())
        if count > 0:
            bin_acc = float(np.mean(y_true[mask]))
            bin_conf = float(np.mean(p1[mask]))
            ece += (count / n) * abs(bin_acc - bin_conf)
    return float(ece)


def calibration_curve(
    y_true: np.ndarray,
    p1: np.ndarray,
    *,
    n_bins: int = 10,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return observed accuracy, mean confidence, and counts per bin for reliability diagram."""
    y_true = np.asarray(y_true, dtype=int)
    p1 = np.asarray(p1, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)

    accuracies = []
    confidences = []
    counts = []

    for i in range(n_bins):
        low, high = edges[i], edges[i + 1]
        mask = (p1 >= low) & (p1 <= high if i == n_bins - 1 else p1 < high)
        count = int(mask.sum())
        if count > 0:
            accuracies.append(float(np.mean(y_true[mask])))
            confidences.append(float(np.mean(p1[mask])))
            counts.append(count)
        else:
            accuracies.append(float("nan"))
            confidences.append(0.5 * (low + high))
            counts.append(0)

    return np.asarray(accuracies), np.asarray(confidences), np.asarray(counts)
