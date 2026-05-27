"""Draw every QALU circuit and save the diagrams as PNGs.

Usage:
    python examples/draw_circuits.py

Output goes to  diagrams/  in the project root.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")  # non-interactive backend so it works without a display

from qalu.circuits import (
    build_half_adder,
    build_full_adder,
    build_subtractor_1bit,
    build_xor_gate,
    build_and_gate,
    build_or_gate,
    build_ripple_carry_adder_2bit,
    build_subtractor_2bit,
    build_xor_2bit,
    build_and_2bit,
    build_or_2bit,
    build_alu_2bit,
)

OUTDIR = ROOT / "diagrams"
OUTDIR.mkdir(exist_ok=True)


def _save(qc, name: str) -> None:
    path = OUTDIR / f"{name}.png"
    fig = qc.draw("mpl")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  saved  {path.relative_to(ROOT)}")
    import matplotlib.pyplot as plt
    plt.close(fig)


def main() -> None:
    print("Drawing circuits …\n")

    # ── 1-bit gates ──
    _save(build_xor_gate(1, 0, measure=False),           "1bit_xor")
    _save(build_and_gate(1, 1, measure=False),            "1bit_and")
    _save(build_or_gate(1, 0, measure=False),             "1bit_or")

    # ── 1-bit arithmetic ──
    _save(build_half_adder(1, 1, measure=False),          "1bit_half_adder")
    _save(build_full_adder(1, 1, 1, measure=False),       "1bit_full_adder")
    _save(build_subtractor_1bit(1, 0, measure=False),     "1bit_subtractor")

    # ── 2-bit arithmetic ──
    _save(build_ripple_carry_adder_2bit(3, 2, measure=False),  "2bit_adder")
    _save(build_subtractor_2bit(3, 1, measure=False),          "2bit_subtractor")

    # ── 2-bit logic ──
    _save(build_xor_2bit(3, 1, measure=False),            "2bit_xor")
    _save(build_and_2bit(3, 2, measure=False),             "2bit_and")
    _save(build_or_2bit(2, 1, measure=False),              "2bit_or")

    # ── ALU (all 4 opcodes) ──
    _save(build_alu_2bit(0, 2, 3, measure=False),         "alu_add")
    _save(build_alu_2bit(1, 3, 1, measure=False),         "alu_sub")
    _save(build_alu_2bit(2, 3, 1, measure=False),         "alu_xor")
    _save(build_alu_2bit(3, 3, 2, measure=False),         "alu_and")

    # ── ALU with measurements (complete circuit) ──
    _save(build_alu_2bit(0, 2, 3, measure=True),          "alu_add_measured")

    print(f"\nDone — {len(list(OUTDIR.glob('*.png')))} diagrams in {OUTDIR.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
