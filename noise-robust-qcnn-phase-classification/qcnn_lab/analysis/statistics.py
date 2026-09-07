from __future__ import annotations

from typing import Callable

import numpy as np
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, roc_auc_score

from qcnn_lab.analysis.calibration import brier_score, expected_calibration_error


def bootstrap_ci_from_samples(
    values: np.ndarray,
    *,
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 12345,
) -> tuple[float, float]:
    """Compute empirical bootstrap confidence interval for a 1D array of sample values."""
    arr = np.asarray(values, dtype=float)
    if len(arr) == 0:
        raise ValueError("empty sample for bootstrap CI")
    if len(arr) == 1:
        return float(arr[0]), float(arr[0])

    rng = np.random.default_rng(seed)
    n = len(arr)
    boots = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[i] = np.mean(arr[idx])

    alpha = 1.0 - confidence
    low = float(np.quantile(boots, alpha / 2.0))
    high = float(np.quantile(boots, 1.0 - alpha / 2.0))
    return low, high


bootstrap_confidence_interval = bootstrap_ci_from_samples


def bootstrap_metric_ci(
    y_true: np.ndarray,
    p1: np.ndarray,
    metric_name: str,
    *,
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 12345,
) -> tuple[float, float]:
    """Compute non-parametric bootstrap confidence interval for a classification metric."""
    y_true = np.asarray(y_true, dtype=int)
    p1 = np.asarray(p1, dtype=float)
    n = len(y_true)
    if n == 0:
        raise ValueError("empty sample")

    rng = np.random.default_rng(seed)
    boot_vals = []

    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        y_b = y_true[idx]
        p_b = p1[idx]
        pred_b = (p_b >= 0.5).astype(int)

        if metric_name == "accuracy":
            val = accuracy_score(y_b, pred_b)
        elif metric_name == "balanced_accuracy":
            val = balanced_accuracy_score(y_b, pred_b)
        elif metric_name == "f1":
            val = f1_score(y_b, pred_b, zero_division=0)
        elif metric_name == "roc_auc":
            if len(np.unique(y_b)) < 2:
                continue
            val = roc_auc_score(y_b, p_b)
        elif metric_name == "brier_score":
            val = brier_score(y_b, p_b)
        elif metric_name == "ece":
            val = expected_calibration_error(y_b, p_b)
        else:
            raise ValueError(f"unknown metric {metric_name}")
        boot_vals.append(val)

    if len(boot_vals) == 0:
        return float("nan"), float("nan")

    alpha = 1.0 - confidence
    low = float(np.quantile(boot_vals, alpha / 2.0))
    high = float(np.quantile(boot_vals, 1.0 - alpha / 2.0))
    return low, high


def aggregate_statistics(
    values: np.ndarray,
    *,
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 12345,
) -> dict[str, float]:
    """Compute mean, std, median, and 95% bootstrap confidence interval."""
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return {"mean": float("nan"), "std": float("nan"), "median": float("nan"), "ci_low": float("nan"), "ci_high": float("nan")}
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    median = float(np.median(arr))
    ci_low, ci_high = bootstrap_ci_from_samples(arr, n_boot=n_boot, confidence=confidence, seed=seed)
    return {
        "mean": mean,
        "std": std,
        "median": median,
        "ci_low": ci_low,
        "ci_high": ci_high,
    }
