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
    maxiter: int | None = None,
    seed: int = 12345,
    max_budget_ceiling: int = 1000,
    enable_continuation: bool = True,
) -> tuple[np.ndarray, list[dict], float]:
    """Train an ideal QCNN with the shared adaptive convergence policy.

    Starting budget is ``max(300, 5 * parameter_count)`` unless ``maxiter``
    is explicitly supplied. While the run is evaluation-limited and the
    best-loss window improvement stays active, optimization continues in a
    loop up to ``max_budget_ceiling``. Plateau detection uses the absolute
    best-loss improvement over consecutive windows so deterioration is never
    misclassified as convergence. Telemetry keeps ``scipy_optimizer_success``,
    ``convergence_plateau_detected`` / ``plateau_detected``,
    ``evaluation_limit_reached``, and ``convergence_status`` separate;
    ``optimizer_success`` is a legacy alias (scipy OR plateau).
    """
    rng = np.random.default_rng(seed)
    p_count = parameter_count(n_qubits, architecture)
    x0 = rng.normal(0.0, 0.15, size=p_count)
    history: list[dict] = []
    started = perf_counter()

    # Convergence policy: initial budget scales with parameter count
    if maxiter is not None:
        initial_budget = int(maxiter)
    else:
        initial_budget = max(300, 5 * p_count)

    def objective(x: np.ndarray) -> float:
        p = batch_predict(states[train_idx], x, architecture, n_qubits)
        loss = binary_cross_entropy(labels[train_idx], p)
        history.append({"evaluation": len(history), "train_loss": loss})
        return loss

    total_budget = initial_budget
    result = minimize(
        objective,
        x0,
        method="COBYLA",
        options={"maxiter": int(initial_budget), "rhobeg": 0.25, "tol": 1e-4},
    )

    def _trajectory_diagnostics(hist: list[dict]) -> dict:
        if not hist:
            return {
                "initial_loss": float("nan"),
                "best_loss": float("nan"),
                "final_loss": float(result.fun) if hasattr(result, "fun") else float("nan"),
                "loss_improvement": float("nan"),
                "best_loss_window_improvement": 0.0,
                "last_10_eval_improvement": 0.0,
            }
        losses = np.asarray([h["train_loss"] for h in hist], dtype=float)
        initial_loss = float(losses[0])
        final_loss = float(losses[-1])
        best_loss = float(np.min(losses))
        loss_imp = initial_loss - final_loss
        # Best-loss window improvement: compare best loss in previous
        # window vs current window (robust to end-point noise/deterioration).
        window = 10
        if len(losses) >= 2 * window:
            prev_best = float(np.min(losses[-2 * window:-window]))
            curr_best = float(np.min(losses[-window:]))
            best_window_imp = prev_best - curr_best
        elif len(losses) > 1:
            half = len(losses) // 2
            prev_best = float(np.min(losses[:half]))
            curr_best = float(np.min(losses[half:]))
            best_window_imp = prev_best - curr_best
        else:
            best_window_imp = 0.0
        last_10 = hist[-10:] if len(hist) >= 10 else hist
        last_10_imp = float(last_10[0]["train_loss"] - last_10[-1]["train_loss"]) if len(last_10) > 1 else 0.0
        return {
            "initial_loss": initial_loss,
            "best_loss": best_loss,
            "final_loss": final_loss,
            "loss_improvement": loss_imp,
            "best_loss_window_improvement": float(best_window_imp),
            "last_10_eval_improvement": float(last_10_imp),
        }

    def _plateau_converged(hist: list[dict], *, eps: float = 1e-4) -> bool:
        """Plateau iff best-loss improvement is negligible in magnitude.

        Uses |Delta L_best| over consecutive windows so that loss
        deterioration (negative signed change) is NOT misclassified
        as convergence.
        """
        losses = np.asarray([h["train_loss"] for h in hist], dtype=float)
        if len(losses) < 20:
            return False
        window = 10
        prev_best = float(np.min(losses[-2 * window:-window]))
        curr_best = float(np.min(losses[-window:]))
        return bool(abs(prev_best - curr_best) < eps)

    nfev = int(getattr(result, "nfev", len(history)))
    eval_limit_reached = bool(nfev >= total_budget)
    scipy_success = bool(result.success)
    msg = str(result.message)

    diag = _trajectory_diagnostics(history)
    initial_loss = diag["initial_loss"]
    best_loss = diag["best_loss"]
    final_loss = diag["final_loss"]
    loss_imp = diag["loss_improvement"]
    best_window_imp = diag["best_loss_window_improvement"]
    last_10_imp = diag["last_10_eval_improvement"]

    # Continuation loop: keep extending the budget while the run is
    # evaluation-limited AND still actively improving, up to the ceiling.
    # Active improvement requires a strictly positive best-loss gain
    # above tolerance (deterioration must not trigger continuation).
    n_continuations = 0
    while (
        enable_continuation
        and eval_limit_reached
        and not _plateau_converged(history)
        and best_window_imp > 1e-3
        and total_budget < max_budget_ceiling
    ):
        cont_budget = min(max_budget_ceiling - total_budget, initial_budget)
        if cont_budget <= 20:
            break
        total_budget += cont_budget
        n_continuations += 1
        result = minimize(
            objective,
            result.x,
            method="COBYLA",
            options={"maxiter": int(cont_budget), "rhobeg": 0.05, "tol": 1e-4},
        )
        nfev = len(history)
        eval_limit_reached = bool(nfev >= total_budget)
        scipy_success = bool(result.success)
        msg = str(result.message)
        diag = _trajectory_diagnostics(history)
        initial_loss = diag["initial_loss"]
        best_loss = diag["best_loss"]
        final_loss = diag["final_loss"]
        loss_imp = diag["loss_improvement"]
        best_window_imp = diag["best_loss_window_improvement"]
        last_10_imp = diag["last_10_eval_improvement"]

    plateau_detected = _plateau_converged(history)

    params = np.asarray(result.x, dtype=float)
    val_p = batch_predict(states[validation_idx], params, architecture, n_qubits)
    val_loss = float(binary_cross_entropy(labels[validation_idx], val_p))

    # Keep convergence concepts strictly separated: scipy success,
    # plateau detection, and budget exhaustion are independent signals.
    # `optimizer_success` is retained as a legacy alias (scipy OR plateau)
    # for backward-compatible telemetry consumers.
    if scipy_success:
        convergence_status = "scipy_converged"
    elif plateau_detected:
        convergence_status = "plateau_converged"
    elif eval_limit_reached and best_window_imp > 1e-3:
        convergence_status = "budget_exhausted_active"
    elif eval_limit_reached:
        convergence_status = "budget_exhausted_uncertain"
    else:
        convergence_status = "budget_exhausted_uncertain"

    # Comprehensive optimizer telemetry
    history.append({
        "evaluation": len(history),
        "validation_loss": val_loss,
        "final_train_loss": final_loss,
        "initial_train_loss": initial_loss,
        "best_train_loss": best_loss,
        "loss_improvement": loss_imp,
        "best_loss_window_improvement": best_window_imp,
        "last_10_eval_improvement": last_10_imp,
        "nfev": nfev,
        "maxiter_budget": total_budget,
        "initial_budget": initial_budget,
        "n_continuations": n_continuations,
        "max_budget_ceiling": max_budget_ceiling,
        "success": bool(scipy_success or plateau_detected),
        "scipy_optimizer_success": bool(scipy_success),
        "optimizer_success": bool(scipy_success or plateau_detected),
        "message": msg,
        "optimizer_message": msg,
        "termination_reason": msg,
        "evaluation_limit_reached": eval_limit_reached,
        "convergence_plateau_detected": plateau_detected,
        "plateau_detected": plateau_detected,
        "convergence_status": convergence_status,
    })
    return params, history, perf_counter() - started


def train_qcnn_from_manifest(
    states: np.ndarray,
    labels: np.ndarray,
    n_qubits: int,
    architecture: QCNNArchitecture,
    manifest: any,
    *,
    maxiter: int | None = None,
    seed: int = 12345,
) -> tuple[np.ndarray, list[dict], float]:
    """Train QCNN using explicit indices from a split manifest DataFrame or SplitIndices.

    ``maxiter=None`` selects the shared adaptive convergence budget.
    """
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