import numpy as np

from qkd_lab.postprocessing.cascade import cascade_reconcile
from qkd_lab.postprocessing.ldpc_reconciliation import ldpc_reconcile
from qkd_lab.protocols.decoy_bb84 import make_correlated_raw_keys


def test_cascade_corrects_small_block():
    alice, bob = make_correlated_raw_keys(5000, 0.02, seed=100)
    r = cascade_reconcile(alice, bob, 0.02, passes=10, seed=200)
    assert r.success
    assert np.array_equal(r.alice_key, r.bob_key)
    assert r.disclosed_bits > 0


def test_ldpc_no_error_case():
    alice, bob = make_correlated_raw_keys(256, 0.0, seed=123)
    r = ldpc_reconcile(alice, bob, 0.005, max_iter=30)
    assert r.success
    assert np.array_equal(r.alice_key, r.bob_key)