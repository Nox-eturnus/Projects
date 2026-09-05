from qkd_lab.config import load_yaml, mdi_objects
from qkd_lab.estimation.finite_key_mdi import estimate_mdi_finite_key
from qkd_lab.protocols.mdi_qkd import MDIPhysicalParameters, expected_mdi_block, mdi_coherent_gain


def test_mdi_swap_symmetry():
    a = MDIPhysicalParameters(10, 30, 0.2, 0.6, 1e-7, 0.015)
    b = MDIPhysicalParameters(30, 10, 0.2, 0.6, 1e-7, 0.015)
    assert abs(mdi_coherent_gain(0.4, 0.1, a) - mdi_coherent_gain(0.1, 0.4, b)) < 1e-15


def test_mdi_large_block_finite_key_runs():
    cfg = load_yaml('configs/mdi.yaml')
    alice, bob, basis, physical, budget = mdi_objects(cfg)
    block = expected_mdi_block(100_000_000_000, alice_intensities=alice, bob_intensities=bob, basis=basis, physical=physical)
    r = estimate_mdi_finite_key(block, budget)
    assert r.secure_bits > 0
    assert not r.abort


def test_aggregate_stochastic_mdi_simulation():
    from qkd_lab.protocols.mdi_qkd import simulate_aggregate_mdi_block
    cfg = load_yaml('configs/mdi.yaml')
    alice, bob, basis, physical, budget = mdi_objects(cfg)
    block = simulate_aggregate_mdi_block(
        100_000_000_000,
        alice_intensities=alice,
        bob_intensities=bob,
        basis=basis,
        physical=physical,
        seed=42,
    )
    r = estimate_mdi_finite_key(block, budget)
    assert r.secure_bits > 0
    assert not r.abort