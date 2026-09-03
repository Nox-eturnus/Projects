from __future__ import annotations

from math import ceil, log
from time import perf_counter

import numpy as np

from qkd_lab.math_utils import h2
from qkd_lab.postprocessing.reconciliation import ReconciliationResult
from qkd_lab.rng import make_rng


def make_systematic_sparse_pcm(
    n: int,
    m: int,
    *,
    column_weight: int = 3,
    seed: int = 2026,
) -> np.ndarray:
    """Create a reproducible sparse parity-check matrix H=[A|I].

    This is an educational LDPC construction: sparse and full-row-rank by
    construction, but not an optimized standardized QKD LDPC code.
    """
    if not 1 <= m < n:
        raise ValueError("require 1 <= m < n")
    rng = make_rng(seed)
    k = n - m
    A = np.zeros((m, k), dtype=np.uint8)
    w = min(max(1, column_weight), m)
    for col in range(k):
        rows = rng.choice(m, size=w, replace=False)
        A[rows, col] = 1
    H = np.concatenate([A, np.eye(m, dtype=np.uint8)], axis=1)
    return H


def min_sum_syndrome_decode(
    H: np.ndarray,
    syndrome: np.ndarray,
    error_rate: float,
    *,
    max_iter: int = 100,
    scaling: float = 0.8,
) -> tuple[np.ndarray, bool, int]:
    H = np.asarray(H, dtype=np.uint8)
    syndrome = np.asarray(syndrome, dtype=np.uint8).reshape(-1)
    m, n = H.shape
    if syndrome.shape != (m,):
        raise ValueError("syndrome length must equal number of parity checks")
    p = min(0.499999, max(1e-6, error_rate))
    prior = log((1.0 - p) / p)

    edge_checks, edge_vars = np.nonzero(H)
    edge_checks = edge_checks.astype(int)
    edge_vars = edge_vars.astype(int)
    ecount = len(edge_checks)
    check_edges = [np.flatnonzero(edge_checks == i) for i in range(m)]
    var_edges = [np.flatnonzero(edge_vars == j) for j in range(n)]

    q_msg = np.full(ecount, prior, dtype=float)
    r_msg = np.zeros(ecount, dtype=float)

    hard = np.zeros(n, dtype=np.uint8)
    for iteration in range(1, max_iter + 1):
        # Check-node update. Syndrome=1 flips the required parity sign.
        for check in range(m):
            edges = check_edges[check]
            if len(edges) == 0:
                continue
            values = q_msg[edges]
            signs = np.where(values >= 0.0, 1.0, -1.0)
            abs_values = np.abs(values)
            target_sign = -1.0 if syndrome[check] else 1.0
            for local, edge in enumerate(edges):
                if len(edges) == 1:
                    product_sign = target_sign
                    magnitude = 50.0
                else:
                    other = np.arange(len(edges)) != local
                    product_sign = target_sign * float(np.prod(signs[other]))
                    magnitude = float(np.min(abs_values[other]))
                r_msg[edge] = scaling * product_sign * magnitude

        posterior = np.full(n, prior, dtype=float)
        for var in range(n):
            edges = var_edges[var]
            if len(edges):
                posterior[var] += float(r_msg[edges].sum())
        hard = (posterior < 0.0).astype(np.uint8)

        if np.array_equal((H @ hard) % 2, syndrome):
            return hard, True, iteration

        # Variable-node update.
        for var in range(n):
            edges = var_edges[var]
            if len(edges) == 0:
                continue
            total = prior + float(r_msg[edges].sum())
            for edge in edges:
                q_msg[edge] = total - r_msg[edge]

    return hard, False, max_iter


def suggested_parity_checks(n: int, qber_estimate: float, overhead: float = 1.35) -> int:
    if n < 4:
        raise ValueError("n must be >= 4")
    q = min(0.49, max(1e-6, qber_estimate))
    fraction = min(0.80, max(0.08, overhead * h2(q)))
    return min(n - 1, max(1, ceil(n * fraction)))


def ldpc_reconcile(
    alice: np.ndarray,
    bob: np.ndarray,
    qber_estimate: float,
    *,
    matrix_seed: int = 2026,
    max_iter: int = 150,
) -> ReconciliationResult:
    alice = np.asarray(alice, dtype=np.uint8).reshape(-1)
    bob = np.asarray(bob, dtype=np.uint8).reshape(-1)
    if alice.shape != bob.shape:
        raise ValueError("Alice and Bob keys must have identical shape")
    n = len(alice)
    if n < 4:
        raise ValueError("LDPC demonstration requires at least 4 bits")

    m = suggested_parity_checks(n, qber_estimate)
    H = make_systematic_sparse_pcm(n, m, seed=matrix_seed)
    syndrome_alice = (H @ alice) % 2
    syndrome_bob = (H @ bob) % 2
    syndrome_error = syndrome_alice ^ syndrome_bob

    start = perf_counter()
    estimated_error, converged, iterations = min_sum_syndrome_decode(
        H,
        syndrome_error,
        qber_estimate,
        max_iter=max_iter,
    )
    corrected = bob ^ estimated_error
    elapsed_ms = (perf_counter() - start) * 1000.0
    success = bool(converged and np.array_equal(corrected, alice))

    return ReconciliationResult(
        alice_key=alice.copy(),
        bob_key=corrected,
        success=success,
        disclosed_bits=m,
        messages=1,
        rounds=iterations,
        elapsed_ms=elapsed_ms,
        algorithm="ldpc_min_sum",
    )