from __future__ import annotations

import numpy as np

from qkd_lab.rng import make_rng


def toeplitz_matrix(output_bits: int, input_bits: int, seed: np.ndarray) -> np.ndarray:
    if output_bits < 0 or input_bits < 0:
        raise ValueError("dimensions must be non-negative")
    if output_bits == 0:
        return np.zeros((0, input_bits), dtype=np.uint8)
    expected = output_bits + input_bits - 1
    seed = np.asarray(seed, dtype=np.uint8).reshape(-1)
    if len(seed) != expected:
        raise ValueError(f"Toeplitz seed must have {expected} bits")
    first_col = seed[:output_bits]
    first_row = np.concatenate(([first_col[0]], seed[output_bits:]))
    out = np.empty((output_bits, input_bits), dtype=np.uint8)
    for i in range(output_bits):
        for j in range(input_bits):
            out[i, j] = first_row[j - i] if j >= i else first_col[i - j]
    return out


def toeplitz_hash(bits: np.ndarray, output_bits: int, seed: np.ndarray) -> np.ndarray:
    bits = np.asarray(bits, dtype=np.uint8).reshape(-1)
    if output_bits <= 0:
        return np.zeros(0, dtype=np.uint8)
    if output_bits > len(bits):
        raise ValueError("privacy amplification cannot increase key length")
    return (toeplitz_matrix(output_bits, len(bits), seed) @ bits) % 2


def random_toeplitz_seed(output_bits: int, input_bits: int, seed: int | None = None) -> np.ndarray:
    if output_bits <= 0 or input_bits <= 0:
        return np.zeros(0, dtype=np.uint8)
    rng = make_rng(seed)
    return rng.integers(0, 2, size=output_bits + input_bits - 1, dtype=np.uint8)


def toeplitz_hash_fast(bits: np.ndarray, output_bits: int, seed: np.ndarray) -> np.ndarray:
    """FFT-backed Toeplitz multiplication using SciPy's matmul_toeplitz."""
    from scipy.linalg import matmul_toeplitz

    bits = np.asarray(bits, dtype=np.uint8).reshape(-1)
    if output_bits <= 0:
        return np.zeros(0, dtype=np.uint8)
    if output_bits > len(bits):
        raise ValueError("privacy amplification cannot increase key length")
    expected = output_bits + len(bits) - 1
    seed = np.asarray(seed, dtype=np.uint8).reshape(-1)
    if len(seed) != expected:
        raise ValueError(f"Toeplitz seed must have {expected} bits")
    first_col = seed[:output_bits]
    first_row = np.concatenate(([first_col[0]], seed[output_bits:]))
    product = matmul_toeplitz(
        (first_col.astype(float), first_row.astype(float)),
        bits.astype(float),
        check_finite=False,
    )
    rounded = np.rint(product).astype(np.int64)
    return (rounded % 2).astype(np.uint8)