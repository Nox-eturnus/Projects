from qkd_lab.config import bb84_objects, load_yaml
from qkd_lab.estimation.finite_key_bb84 import estimate_lim2014, gamma_lim2014
from qkd_lab.protocols.decoy_bb84 import expected_decoy_bb84_block


def test_gamma_nonnegative():
    assert gamma_lim2014(1e-10, 0.02, 1e6, 1e7) >= 0


def test_large_block_can_produce_key():
    cfg = load_yaml('configs/baseline.yaml')
    sec = load_yaml('configs/finite_key.yaml')
    intensities, basis, channel, detector = bb84_objects(cfg)
    block = expected_decoy_bb84_block(10_000_000_000, intensities=intensities, basis=basis, channel=channel, detector=detector)
    r = estimate_lim2014(block.records, intensities, eps_sec=float(sec['eps_sec']), eps_cor=float(sec['eps_cor']))
    assert r.secure_bits > 0
    assert not r.abort
    assert 0 <= r.phase_error_upper < 0.5