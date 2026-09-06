from __future__ import annotations

import numpy as np


def crossing_point(x: np.ndarray, y: np.ndarray, level: float = 0.5) -> tuple[float, bool]:
    """Estimate where y crosses `level` by linear interpolation.

    Returns `(x_crossing, bracketed)`. If the sampled curve never brackets the
    requested level, the closest sampled point is returned with `bracketed=False`.
    The fallback is deliberately explicit so a non-crossing classifier is never
    silently reported as a successful transition estimate.
    """
    x = np.asarray(x, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("x and y must have the same length >= 2")
    order = np.argsort(x)
    x, y = x[order], y[order]
    shifted = y - float(level)
    exact = np.flatnonzero(np.isclose(shifted, 0.0, atol=1e-12))
    if len(exact):
        return float(x[exact[0]]), True
    changes = np.flatnonzero(shifted[:-1] * shifted[1:] < 0.0)
    if len(changes):
        # If a noisy curve crosses more than once, use the crossing with the
        # largest local probability change rather than silently picking first.
        i = int(changes[np.argmax(np.abs(np.diff(y)[changes]))])
        x0, x1 = x[i], x[i + 1]
        y0, y1 = y[i], y[i + 1]
        frac = (level - y0) / (y1 - y0)
        return float(x0 + frac * (x1 - x0)), True
    i = int(np.argmin(np.abs(shifted)))
    return float(x[i]), False


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