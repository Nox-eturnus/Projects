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

    nfev = int(getattr(result, "nfev", len(history)))
    eval_limit_reached = bool(nfev >= initial_budget)
    scipy_success = bool(result.success)
    msg = str(result.message)

    # Compute trajectory diagnostics
    initial_loss = float(history[0]["train_loss"]) if history else float("nan")
    best_loss = float(min(h["train_loss"] for h in history)) if history else float("nan")
    final_loss = float(history[-1]["train_loss"]) if history else float(result.fun)
    loss_imp = initial_loss - final_loss
    last_10 = history[-10:] if len(history) >= 10 else history
    last_10_imp = float(last_10[0]["train_loss"] - last_10[-1]["train_loss"]) if len(last_10) > 1 else 0.0

    # Optional continuation if evaluation-limited and still actively improving
    if enable_continuation and eval_limit_reached and last_10_imp > 1e-3 and total_budget < max_budget_ceiling:
        cont_budget = min(max_budget_ceiling - total_budget, initial_budget)
        if cont_budget > 20:
            total_budget += cont_budget
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
            best_loss = float(min(h["train_loss"] for h in history))
            final_loss = float(history[-1]["train_loss"])
            loss_imp = initial_loss - final_loss
            last_10 = history[-10:] if len(history) >= 10 else history
            last_10_imp = float(last_10[0]["train_loss"] - last_10[-1]["train_loss"]) if len(last_10) > 1 else 0.0

    plateau_detected = bool(last_10_imp < 1e-4)

    params = np.asarray(result.x, dtype=float)
    val_p = batch_predict(states[validation_idx], params, architecture, n_qubits)
    val_loss = float(binary_cross_entropy(labels[validation_idx], val_p))

    # Comprehensive optimizer telemetry
    history.append({
        "evaluation": len(history),
        "validation_loss": val_loss,
        "final_train_loss": final_loss,
        "initial_train_loss": initial_loss,
        "best_train_loss": best_loss,
        "loss_improvement": loss_imp,
        "last_10_eval_improvement": last_10_imp,
        "nfev": nfev,
        "maxiter_budget": total_budget,
        "success": bool(scipy_success or plateau_detected),
        "scipy_optimizer_success": bool(scipy_success),
        "optimizer_success": bool(scipy_success or plateau_detected),
        "message": msg,
        "optimizer_message": msg,
        "termination_reason": msg,
        "evaluation_limit_reached": eval_limit_reached,
        "convergence_plateau_detected": plateau_detected,
    })
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