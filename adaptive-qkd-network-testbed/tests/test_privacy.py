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


def test_verification_length_and_two_universal():
    from qkd_lab.postprocessing.verification import (
        verification_length,
        generate_verification_seed,
        two_universal_tag,
    )
    # eps_cor = 1e-10 -> ceil(-log2(1e-10)) = ceil(33.219) = 34
    t_len = verification_length(1e-10)
    assert t_len == 34

    bits = np.array([1, 0, 1, 1, 0, 0, 1, 0, 1, 1], dtype=np.uint8)
    seed = generate_verification_seed(len(bits), 8, seed=123)
    tag1 = two_universal_tag(bits, 8, seed)
    tag2 = two_universal_tag(bits, 8, seed)
    assert np.array_equal(tag1, tag2)
    assert len(tag1) == 8


def test_privacy_zero_and_negative_output():
    bits = np.array([1, 0, 1, 1], dtype=np.uint8)
    seed = np.zeros(10, dtype=np.uint8)
    assert len(toeplitz_hash(bits, 0, seed)) == 0
    assert len(toeplitz_hash(bits, -5, seed)) == 0
    assert len(toeplitz_hash_fast(bits, 0, seed)) == 0
    assert len(toeplitz_hash_fast(bits, -5, seed)) == 0
    assert len(random_toeplitz_seed(0, 10)) == 0
    assert len(random_toeplitz_seed(-2, 10)) == 0