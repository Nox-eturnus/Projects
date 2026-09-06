import numpy as np

from qcnn_lab.baselines.mps import compress_state


def test_mps_exact_when_bond_large_enough():
    rng = np.random.default_rng(1)
    state = rng.normal(size=16) + 1j * rng.normal(size=16)
    state = state / np.linalg.norm(state)
    recon = compress_state(state, 4, max_bond=4)
    assert abs(np.vdot(state, recon)) ** 2 > 1 - 1e-10