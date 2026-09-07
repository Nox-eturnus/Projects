from __future__ import annotations

import numpy as np


def crossing_point(
    x: np.ndarray,
    y: np.ndarray,
    level: float = 0.5,
    atol: float = 1e-3,
) -> tuple[float | None, bool]:
    """Estimate where y crosses `level` by linear interpolation.

    Returns `(x_crossing, bracketed)`.
    A valid crossing requires values strictly below (level - atol) and strictly above (level + atol).
    If the curve is flat (e.g. within atol of level throughout) or entirely on one side,
    returns `(None, False)`.
    If there are multiple crossings, selects the crossing interval with the largest
    contrast |y1 - y0|.
    """
    x = np.asarray(x, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("x and y must have the same length >= 2")
    order = np.argsort(x)
    x, y = x[order], y[order]
    shifted = y - float(level)

    # Must have points strictly below and strictly above level
    if not (np.any(shifted < -atol) and np.any(shifted > atol)):
        return None, False

    s = np.zeros(len(shifted), dtype=int)
    s[shifted > atol] = 1
    s[shifted < -atol] = -1

    nonzero_idx = np.flatnonzero(s != 0)
    candidates: list[tuple[float, float]] = []

    for k in range(len(nonzero_idx) - 1):
        i = int(nonzero_idx[k])
        j = int(nonzero_idx[k + 1])
        if s[i] != s[j]:
            contrast = abs(y[j] - y[i])
            frac = (level - y[i]) / (y[j] - y[i])
            xc = float(x[i] + frac * (x[j] - x[i]))
            candidates.append((xc, contrast))

    if not candidates:
        return None, False

    # Pick candidate with largest contrast
    best_xc, _ = max(candidates, key=lambda c: c[1])
    return best_xc, True


def steepest_change_point(x: np.ndarray, y: np.ndarray) -> float:
    """Return x at the largest absolute finite-difference slope."""
    x = np.asarray(x, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)
    if len(x) != len(y) or len(x) < 3:
        raise ValueError("x and y must have the same length >= 3")
    order = np.argsort(x)
    x, y = x[order], y[order]
    grad = np.gradient(y, x)
    return float(x[int(np.argmax(np.abs(grad)))])


def moving_average(y: np.ndarray, window: int = 3) -> np.ndarray:
    y = np.asarray(y, dtype=float).reshape(-1)
    if window <= 1:
        return y.copy()
    if window % 2 == 0:
        raise ValueError("window must be odd")
    if window > len(y):
        raise ValueError("window cannot exceed data length")
    pad = window // 2
    padded = np.pad(y, (pad, pad), mode="edge")
    kernel = np.ones(window, dtype=float) / window
    return np.convolve(padded, kernel, mode="valid")