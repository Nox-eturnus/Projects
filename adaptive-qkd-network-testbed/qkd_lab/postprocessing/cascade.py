from __future__ import annotations

from time import perf_counter

import numpy as np

from qkd_lab.postprocessing.reconciliation import ReconciliationResult
from qkd_lab.rng import make_rng


def _parity(bits: np.ndarray, indices: np.ndarray) -> int:
    return int(bits[indices].sum() % 2)


def _locate_one_error(
    alice: np.ndarray,
    bob: np.ndarray,
    indices: np.ndarray,
) -> tuple[int, int, int]:
    """Binary-search one error in a block known to have odd parity mismatch.

    Returns (index, disclosed_parity_bits, messages).
    """
    disclosed = 0
    messages = 0
    work = indices.copy()
    while len(work) > 1:
        mid = len(work) // 2
        left = work[:mid]
        disclosed += 1
        messages += 1
        if _parity(alice, left) != _parity(bob, left):
            work = left
        else:
            work = work[mid:]
    return int(work[0]), disclosed, messages


def cascade_reconcile(
    alice: np.ndarray,
    bob: np.ndarray,
    qber_estimate: float,
    *,
    passes: int = 6,
    seed: int | None = 1234,
) -> ReconciliationResult:
    alice = np.asarray(alice, dtype=np.uint8).reshape(-1)
    bob_work = np.asarray(bob, dtype=np.uint8).reshape(-1).copy()
    if alice.shape != bob_work.shape:
        raise ValueError("Alice and Bob keys must have identical shape")
    if len(alice) == 0:
        return ReconciliationResult(alice, bob_work, True, 0, 0, 0, 0.0, "cascade_style")
    if not 0.0 <= qber_estimate <= 0.5:
        raise ValueError("qber_estimate must lie in [0,0.5]")

    rng = make_rng(seed)
    q = max(qber_estimate, 1.0 / max(1000, len(alice)))
    base_block = max(2, int(0.73 / q))
    disclosed = 0
    messages = 0
    start = perf_counter()

    for pass_index in range(passes):
        permutation = rng.permutation(len(alice))
        block_size = min(len(alice), base_block * (2 ** (pass_index % 4)))
        changed = False

        for start_idx in range(0, len(alice), block_size):
            block = permutation[start_idx : start_idx + block_size]
            if len(block) == 0:
                continue
            disclosed += 1
            messages += 1
            if _parity(alice, block) != _parity(bob_work, block):
                index, extra_disclosed, extra_messages = _locate_one_error(alice, bob_work, block)
                disclosed += extra_disclosed
                messages += extra_messages
                bob_work[index] ^= 1
                changed = True

        if np.array_equal(alice, bob_work):
            break

    elapsed_ms = (perf_counter() - start) * 1000.0
    return ReconciliationResult(
        alice_key=alice.copy(),
        bob_key=bob_work,
        success=bool(np.array_equal(alice, bob_work)),
        disclosed_bits=disclosed,
        messages=messages,
        rounds=pass_index + 1,
        elapsed_ms=elapsed_ms,
        algorithm="cascade_style",
    )


def cascade_reconcile_blockwise(
    alice: np.ndarray,
    bob: np.ndarray,
    qber_estimate: float,
    *,
    chunk_bits: int = 10_000,
    passes: int = 8,
    seed: int = 2026,
) -> ReconciliationResult:
    """Reconcile a large key as independent Cascade-style chunks.

    Leakage and message counts are summed across chunks. Independent chunking is
    less communication-efficient than a highly optimized large-block Cascade,
    but it makes the complete executable pipeline memory/runtime manageable and
    keeps all disclosed parity bits explicitly accounted.
    """
    alice = np.asarray(alice, dtype=np.uint8).reshape(-1)
    bob = np.asarray(bob, dtype=np.uint8).reshape(-1)
    if alice.shape != bob.shape:
        raise ValueError("Alice and Bob keys must have identical shape")
    if chunk_bits <= 0:
        raise ValueError("chunk_bits must be positive")
    if len(alice) == 0:
        return ReconciliationResult(alice.copy(), bob.copy(), True, 0, 0, 0, 0.0, "cascade_blockwise")

    corrected = bob.copy()
    disclosed = 0
    messages = 0
    total_rounds = 0
    elapsed_ms = 0.0
    all_success = True
    for chunk_index, start in enumerate(range(0, len(alice), chunk_bits)):
        stop = min(len(alice), start + chunk_bits)
        result = cascade_reconcile(
            alice[start:stop],
            corrected[start:stop],
            qber_estimate,
            passes=passes,
            seed=seed + chunk_index,
        )
        corrected[start:stop] = result.bob_key
        disclosed += result.disclosed_bits
        messages += result.messages
        total_rounds += result.rounds
        elapsed_ms += result.elapsed_ms
        all_success = all_success and result.success

    return ReconciliationResult(
        alice_key=alice.copy(),
        bob_key=corrected,
        success=bool(all_success and np.array_equal(alice, corrected)),
        disclosed_bits=disclosed,
        messages=messages,
        rounds=total_rounds,
        elapsed_ms=elapsed_ms,
        algorithm="cascade_blockwise",
    )