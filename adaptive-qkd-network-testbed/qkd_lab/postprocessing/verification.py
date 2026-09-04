from __future__ import annotations

import math
import numpy as np

from qkd_lab.postprocessing.privacy import random_toeplitz_seed, toeplitz_hash_fast


def bits_to_bytes(bits: np.ndarray) -> bytes:
    bits = np.asarray(bits, dtype=np.uint8).reshape(-1)
    if len(bits) == 0:
        return b""
    return np.packbits(bits).tobytes()


def verification_length(eps_cor: float) -> int:
    """Calculate minimum verification tag length (in bits) for eps_cor composable correctness.
    
    Under a 2-universal hash family mapping {0,1}^n to {0,1}^t, the collision probability
    for unequal keys is at most 2^(-t). Requiring 2^(-t) <= eps_cor yields:
        t >= ceil(log2(1 / eps_cor))
    """
    if not (0.0 < eps_cor < 1.0):
        raise ValueError(f"eps_cor must be in (0, 1), got {eps_cor}")
    return max(1, math.ceil(-math.log2(eps_cor)))


def generate_verification_seed(num_bits: int, tag_bits: int, seed: int | None = None) -> np.ndarray:
    """Generate a random seed for Toeplitz 2-universal verification hashing."""
    if num_bits <= 0 or tag_bits <= 0:
        return np.zeros(0, dtype=np.uint8)
    return random_toeplitz_seed(tag_bits, num_bits, seed=seed)


def two_universal_tag(bits: np.ndarray, tag_bits: int, seed: np.ndarray) -> np.ndarray:
    """Compute a 2-universal verification tag using Toeplitz hashing over GF(2).
    
    Security note:
        Publishing this tag over the public channel leaks tag_bits of key information
        to Eve. In finite-key composable security, this leakage must be subtracted from
        the secret key length during privacy amplification.
    """
    bits = np.asarray(bits, dtype=np.uint8).reshape(-1)
    if len(bits) == 0 or tag_bits <= 0:
        return np.zeros(0, dtype=np.uint8)
    if tag_bits > len(bits):
        raise ValueError(f"tag_bits ({tag_bits}) cannot exceed key length ({len(bits)})")
    return toeplitz_hash_fast(bits, tag_bits, seed)


def verification_tag(bits: np.ndarray, tag_bits: int = 64, seed: np.ndarray | None = None) -> np.ndarray:
    """Backward-compatible tag generator using 2-universal Toeplitz hashing."""
    bits = np.asarray(bits, dtype=np.uint8).reshape(-1)
    if seed is None:
        seed = generate_verification_seed(len(bits), tag_bits)
    return two_universal_tag(bits, tag_bits, seed)


def verify_equal(
    alice: np.ndarray,
    bob: np.ndarray,
    tag_bits: int = 64,
    seed: np.ndarray | None = None,
) -> bool:
    """Verify equality of Alice and Bob keys using a 2-universal Toeplitz hash tag.
    
    Parameters:
        alice: Alice's reconciled key bits.
        bob: Bob's reconciled key bits.
        tag_bits: Number of verification bits (t_ver >= ceil(log2(1 / eps_cor))).
        seed: Public random seed for the Toeplitz matrix. If None, randomly generated.
        
    Returns:
        True if tags match, False otherwise.
        
    Public Channel Leakage:
        Transmitting Alice's tag leaks t_ver bits of information. In addition, Bob's
        public 1-bit acknowledgment (pass/fail) leaks 1 bit. Total verification leakage = t_ver + 1 bits.
    """
    alice = np.asarray(alice, dtype=np.uint8).reshape(-1)
    bob = np.asarray(bob, dtype=np.uint8).reshape(-1)
    if len(alice) != len(bob):
        return False
    if len(alice) == 0:
        return True
    if tag_bits > len(alice):
        tag_bits = len(alice)
    if seed is None:
        seed = generate_verification_seed(len(alice), tag_bits)
    tag_a = two_universal_tag(alice, tag_bits, seed)
    tag_b = two_universal_tag(bob, tag_bits, seed)
    return bool(np.array_equal(tag_a, tag_b))