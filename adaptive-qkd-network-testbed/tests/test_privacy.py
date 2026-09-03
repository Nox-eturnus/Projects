import numpy as np

from qkd_lab.postprocessing.privacy import random_toeplitz_seed, toeplitz_hash, toeplitz_hash_fast, toeplitz_matrix
from qkd_lab.postprocessing.verification import verify_equal


def test_toeplitz_dimensions_and_repeatability():
    bits = np.array([1,0,1,1,0,1,0,0], dtype=np.uint8)
    seed = random_toeplitz_seed(4, len(bits), seed=42)
    t = toeplitz_matrix(4, len(bits), seed)
    assert t.shape == (4, 8)
    assert np.array_equal(toeplitz_hash(bits, 4, seed), toeplitz_hash(bits, 4, seed))
    assert np.array_equal(toeplitz_hash(bits, 4, seed), toeplitz_hash_fast(bits, 4, seed))


def test_verification_detects_mismatch():
    a = np.zeros(256, dtype=np.uint8)
    b = a.copy(); b[0] = 1
    assert verify_equal(a, a)
    assert not verify_equal(a, b)