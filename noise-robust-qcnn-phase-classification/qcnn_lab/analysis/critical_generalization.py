from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score

from qcnn_lab.analysis.calibration import brier_score


@dataclass(frozen=True)
class DistanceBandMetrics:
    band_name: str
    d_min: float
    d_max: float
    n_samples: int
    accuracy: float
    balanced_accuracy: float
    brier_score: float
    mean_confidence: float


def assign_distance_bands(
    distances: np.ndarray,
    bands: Sequence[tuple[str, float, float]] = (
        ("0.00-0.10", 0.0, 0.10),
        ("0.10-0.20", 0.10, 0.20),
        ("0.20-0.40", 0.20, 0.40),
        (">0.40", 0.40, float("inf")),
    ),
) -> list[str]:
    """Assign distance |h - h_c| to discrete distance bins."""
    labels = []
    for d in distances:
        assigned = bands[-1][0]
        for name, lo, hi in bands:
            if lo <= d < hi:
                assigned = name
                break
        labels.append(assigned)
    return labels


def evaluate_distance_bands(
    y_true: np.ndarray,
    p1: np.ndarray,
    distances: np.ndarray,
    bands: Sequence[tuple[str, float, float]] = (
        ("0.00-0.10", 0.0, 0.10),
        ("0.10-0.20", 0.10, 0.20),
        ("0.20-0.40", 0.20, 0.40),
        (">0.40", 0.40, float("inf")),
    ),
) -> list[DistanceBandMetrics]:
    """Compute performance metrics grouped by distance from critical point."""
    y_true = np.asarray(y_true, dtype=int)
    p1 = np.asarray(p1, dtype=float)
    distances = np.asarray(distances, dtype=float)

    results = []
    for name, lo, hi in bands:
        mask = (distances >= lo) & (distances < hi)
        n = int(mask.sum())
        if n == 0:
            continue
        y_sub = y_true[mask]
        p_sub = p1[mask]
        pred_sub = (p_sub >= 0.5).astype(int)

        acc = float(accuracy_score(y_sub, pred_sub))
        if len(np.unique(y_sub)) > 1:
            ba = float(balanced_accuracy_score(y_sub, pred_sub))
        else:
            ba = acc

        bs = brier_score(y_sub, p_sub)
        mean_conf = float(np.mean(np.maximum(p_sub, 1.0 - p_sub)))

        results.append(DistanceBandMetrics(
            band_name=name,
            d_min=lo,
            d_max=hi,
            n_samples=n,
            accuracy=acc,
            balanced_accuracy=ba,
            brier_score=bs,
            mean_confidence=mean_conf,
        ))
    return results
