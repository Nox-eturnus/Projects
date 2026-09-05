import json
from pathlib import Path

from qkd_lab.config import bb84_objects, load_yaml
from qkd_lab.estimation.finite_key_bb84 import estimate_lim2014
from qkd_lab.models import BasisProbabilities, ChannelParameters
from qkd_lab.postprocessing.cascade import cascade_reconcile_blockwise
from qkd_lab.postprocessing.privacy import random_toeplitz_seed, toeplitz_hash_fast
from qkd_lab.postprocessing.verification import verify_equal
from qkd_lab.protocols.decoy_bb84 import expected_decoy_bb84_block, make_correlated_raw_keys


def main():
    cfg = load_yaml("configs/baseline.yaml")
    sec = load_yaml("configs/finite_key.yaml")
    intensities, _, _, detector = bb84_objects(cfg)

    # A short, high-transmission development case is used so the entire raw key
    # can actually be reconciled on a laptop while still producing a positive
    # finite key under the registered epsilon values.
    pulses = 30_000_000
    basis = BasisProbabilities(0.5, 0.5)
    channel = ChannelParameters(0.0, 0.20)
    block = expected_decoy_bb84_block(
        pulses,
        intensities=intensities,
        basis=basis,
        channel=channel,
        detector=detector,
    )
    x_total = block.basis_total("X")
    alice, bob = make_correlated_raw_keys(x_total.detected, x_total.qber, seed=2026)
    rec = cascade_reconcile_blockwise(
        alice,
        bob,
        x_total.qber,
        chunk_bits=10_000,
        passes=10,
        seed=2026,
    )
    if not rec.success:
        raise RuntimeError("blockwise reconciliation failed")
    tag_bits = int(sec.get("verification_bits", 50))
    if not verify_equal(rec.alice_key, rec.bob_key, tag_bits):
        raise RuntimeError("correctness verification failed")

    fk = estimate_lim2014(
        block.records,
        intensities,
        eps_sec=float(sec["eps_sec"]),
        eps_cor=float(sec["eps_cor"]),
        leak_ec=rec.disclosed_bits,
        verification_tag_bits=tag_bits,
    )
    if fk.abort or fk.secure_bits <= 0:
        raise RuntimeError("development case did not produce a positive finite key")

    seed = random_toeplitz_seed(fk.secure_bits, len(rec.alice_key), seed=99)
    final_key = toeplitz_hash_fast(rec.alice_key, fk.secure_bits, seed)
    assert len(final_key) == fk.secure_bits

    summary = {
        "pulses": pulses,
        "distance_km": channel.length_km,
        "x_detected": x_total.detected,
        "x_qber": x_total.qber,
        "reconciliation_algorithm": rec.algorithm,
        "reconciliation_disclosed_bits": rec.disclosed_bits,
        "reconciliation_messages": rec.messages,
        "finite_key_secure_bits": fk.secure_bits,
        "phase_error_upper": fk.phase_error_upper,
        "abort": fk.abort,
        "privacy_amplified_key_bits": len(final_key),
        "key_material_logged": False,
    }
    Path("results/bb84").mkdir(parents=True, exist_ok=True)
    Path("results/bb84/distillation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print("Complete end-to-end BB84 distillation PASSED")


if __name__ == "__main__":
    main()