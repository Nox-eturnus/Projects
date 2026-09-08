from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, accuracy_score, f1_score, roc_auc_score

from qcnn_lab.analysis.calibration import brier_score, expected_calibration_error, negative_log_likelihood


def find_optimal_threshold(
    y_val: np.ndarray,
    p_val: np.ndarray,
    *,
    search_step: float = 0.01,
) -> float:
    """Find the decision threshold t* in (0, 1) maximizing Balanced Accuracy on validation set.

    Ties are broken in favor of the threshold closest to 0.5.
    Never uses or accesses test set data.
    """
    y_arr = np.asarray(y_val, dtype=int)
    p_arr = np.asarray(p_val, dtype=float)

    if len(y_arr) == 0 or len(np.unique(y_arr)) < 2:
        return 0.5

    thresholds = np.arange(search_step, 1.0, search_step)
    best_t = 0.5
    best_ba = -1.0
    min_dist_to_half = 1.0

    for t in thresholds:
        preds = (p_arr >= t).astype(int)
        ba = float(balanced_accuracy_score(y_arr, preds))
        dist_to_half = abs(t - 0.5)

        if ba > best_ba + 1e-7:
            best_ba = ba
            best_t = float(t)
            min_dist_to_half = dist_to_half
        elif abs(ba - best_ba) <= 1e-7:
            # Break tie by choosing threshold closest to 0.5
            if dist_to_half < min_dist_to_half - 1e-5:
                best_ba = ba
                best_t = float(t)
                min_dist_to_half = dist_to_half

    return float(best_t)


def evaluate_at_threshold(
    y_true: np.ndarray,
    p1: np.ndarray,
    threshold: float = 0.5,
) -> dict[str, float]:
    """Evaluate classification metrics at a specific decision threshold."""
    y_arr = np.asarray(y_true, dtype=int)
    p_arr = np.asarray(p1, dtype=float)
    preds = (p_arr >= threshold).astype(int)

    ba = float(balanced_accuracy_score(y_arr, preds))
    acc = float(accuracy_score(y_arr, preds))
    f1 = float(f1_score(y_arr, preds, zero_division=0))

    return {
        "threshold": float(threshold),
        "balanced_accuracy": ba,
        "accuracy": acc,
        "f1": f1,
    }


def score_distribution_summary(y_true: np.ndarray, p1: np.ndarray) -> dict[str, float]:
    """Compute class-conditional probability score distributions and separation."""
    y_arr = np.asarray(y_true, dtype=int)
    p_arr = np.asarray(p1, dtype=float)

    c0_scores = p_arr[y_arr == 0]
    c1_scores = p_arr[y_arr == 1]

    mean_c0 = float(np.mean(c0_scores)) if len(c0_scores) > 0 else float("nan")
    std_c0 = float(np.std(c0_scores, ddof=1)) if len(c0_scores) > 1 else 0.0
    mean_c1 = float(np.mean(c1_scores)) if len(c1_scores) > 0 else float("nan")
    std_c1 = float(np.std(c1_scores, ddof=1)) if len(c1_scores) > 1 else 0.0

    score_sep = mean_c1 - mean_c0 if not (np.isnan(mean_c0) or np.isnan(mean_c1)) else 0.0

    return {
        "mean_score_class_0": mean_c0,
        "std_score_class_0": std_c0,
        "mean_score_class_1": mean_c1,
        "std_score_class_1": std_c1,
        "score_separation": float(score_sep),
    }


class ValidationCalibrator:
    """Fit Platt / logistic recalibration strictly using validation set scores."""

    def __init__(self):
        self.clf = LogisticRegression(C=1.0, solver="lbfgs")
        self.is_fitted = False

    def fit(self, y_val: np.ndarray, p_val: np.ndarray) -> ValidationCalibrator:
        y_arr = np.asarray(y_val, dtype=int)
        p_arr = np.asarray(p_val, dtype=float).reshape(-1, 1)
        if len(np.unique(y_arr)) >= 2:
            self.clf.fit(p_arr, y_arr)
            self.is_fitted = True
        return self

    def predict_proba(self, p: np.ndarray) -> np.ndarray:
        p_arr = np.asarray(p, dtype=float).reshape(-1, 1)
        if not self.is_fitted:
            return np.asarray(p, dtype=float)
        return self.clf.predict_proba(p_arr)[:, 1]


def classify_generalization_regime(
    roc_auc: float,
    fixed_ba: float,
    adjusted_ba: float,
    score_sep: float,
) -> str:
    """Categorize model generalization behavior into descriptive diagnostic regimes.

    These labels are descriptive diagnostics of the (ranking, classification)
    operating point — not statistical hypothesis-test outcomes.

    1. 'discrimination and classification preserved':
       Strong ranking and strong fixed-threshold classification
       (fixed_ba >= 0.80 and roc_auc >= 0.85).
    2. 'discrimination preserved + threshold shifted':
       Model retains high ranking discrimination (ROC-AUC >= 0.85) but the
       fixed 0.5 threshold fails (fixed_ba < 0.65) while validation-tuned
       thresholding recovers performance (adjusted_ba >= 0.75).
    3. 'ranking preserved but classification degraded':
       Moderate ranking retained (ROC-AUC >= 0.70) without meeting the
       preserved/shifted criteria above.
    4. 'discrimination collapsed':
       Chance-level ranking (ROC-AUC < 0.70) and no meaningful separation.
    """
    if fixed_ba >= 0.80 and roc_auc >= 0.85:
        return "discrimination and classification preserved"
    elif roc_auc >= 0.85 and fixed_ba < 0.65 and adjusted_ba >= 0.75:
        return "discrimination preserved + threshold shifted"
    elif roc_auc >= 0.70:
        return "ranking preserved but classification degraded"
    else:
        return "discrimination collapsed"
