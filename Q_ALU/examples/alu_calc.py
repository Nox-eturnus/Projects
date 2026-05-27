"""Quantum ALU — Interactive Calculator.

Choose an operation, enter operands, and decide whether to run
on a local simulator or real IBM quantum hardware.

Usage:
    python examples/alu_calc.py
"""
from __future__ import annotations

import warnings
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

warnings.filterwarnings("ignore", category=DeprecationWarning)

from qalu.circuits import (
    build_alu_2bit,
    build_ripple_carry_adder_2bit,
    build_subtractor_2bit,
    build_xor_2bit,
    build_and_2bit,
)
from qalu.execution import run_on_ideal_simulator

OP_MAP = {"ADD": 0, "SUB": 1, "XOR": 2, "AND": 3}


def _classical_expected(op_name: str, a: int, b: int) -> tuple[str, str]:
    """Return (expected_bitstring, human_readable) for display."""
    if op_name == "ADD":
        s = a + b
        bits = format(s, "03b")
        return bits, f"{s} (carry={'yes' if s > 3 else 'no'})"
    elif op_name == "SUB":
        diff = (a - b) % 4
        borrow = a < b
        cout = 0 if borrow else 1
        bits = format((cout << 2) | diff, "03b")
        return bits, f"{diff} (borrow={'yes' if borrow else 'no'})"
    elif op_name == "XOR":
        r = a ^ b
        bits = format(r, "02b")
        return bits, str(r)
    elif op_name == "AND":
        r = a & b
        bits = format(r, "02b")
        return bits, str(r)
    return "???", "?"


def _build_standalone(op_name: str, a: int, b: int):
    """Build the standalone (no-opcode) circuit for hardware runs."""
    if op_name == "ADD":
        return build_ripple_carry_adder_2bit(a, b)
    elif op_name == "SUB":
        return build_subtractor_2bit(a, b)
    elif op_name == "XOR":
        return build_xor_2bit(a, b)
    elif op_name == "AND":
        return build_and_2bit(a, b)


def run_simulated(op_name: str, a: int, b: int) -> None:
    """Run on the local ideal simulator using the full ALU circuit."""
    opcode = OP_MAP[op_name]
    qc = build_alu_2bit(opcode, a, b)
    expected_bits, expected_str = _classical_expected(op_name, a, b)

    print(f"\n  Operation : {op_name}")
    print(f"  A = {a} ({a:02b}),  B = {b} ({b:02b})")
    print(f"  Circuit   : Full 12-qubit ALU (opcode={opcode:02b})")
    print(f"  Backend   : Local AerSimulator (ideal, no noise)")
    print(f"  Simulating (1024 shots) ...")

    data = run_on_ideal_simulator(qc, shots=1024)
    counts = next(iter(data.values())).get_counts()
    dominant = max(counts, key=counts.get)

    print(f"\n  Result         : {dominant}")
    print(f"  Classical check: {expected_str}")
    print(f"  Raw counts     : {dict(sorted(counts.items()))}")
    print()


def run_hardware(op_name: str, a: int, b: int) -> None:
    """Run on real IBM quantum hardware using standalone circuits."""
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
    from qiskit.visualization import plot_histogram
    import matplotlib.pyplot as plt

    qc = _build_standalone(op_name, a, b)
    expected_bits, expected_str = _classical_expected(op_name, a, b)

    print(f"\n  Operation : {op_name}")
    print(f"  A = {a} ({a:02b}),  B = {b} ({b:02b})")
    print(f"  Circuit   : Standalone {op_name} ({qc.num_qubits} qubits)")

    # Connect to IBM
    print(f"  Connecting to IBM Quantum ...")
    try:
        service = QiskitRuntimeService(name="qgss-2025")
    except Exception:
        print("\n  ERROR: IBM credentials not found.")
        print("  Run 'python examples/setup_ibm.py' first to save your credentials.")
        return

    backend = service.least_busy(operational=True, simulator=False)
    print(f"  Backend   : {backend.name} ({backend.num_qubits} qubits)")

    # Transpile with max optimization
    pm = generate_preset_pass_manager(backend=backend, optimization_level=3)
    isa_circuit = pm.run(qc)
    ops = dict(isa_circuit.count_ops())
    twoq = sum(v for k, v in ops.items() if k in ("cx", "cz", "ecr"))
    fidelity = 0.995 ** twoq
    print(f"  Transpiled: depth={isa_circuit.depth()}, 2Q gates={twoq}, est. fidelity={fidelity:.0%}")

    # Submit with error mitigation
    sampler = Sampler(mode=backend)
    sampler.options.dynamical_decoupling.enable = True
    sampler.options.dynamical_decoupling.sequence_type = "XX"
    sampler.options.twirling.enable_gates = True

    print(f"\n  Submitting to {backend.name} ...")
    job = sampler.run([isa_circuit], shots=4096)
    print(f"  Job ID: {job.job_id()}")
    print(f"  Waiting for results (this may take a few minutes) ...")
    print(f"  (Press Ctrl+C to cancel — job will still run on IBM)\n")

    try:
        result = job.result()
    except KeyboardInterrupt:
        print(f"\n  Cancelled waiting. Check results on IBM dashboard with Job ID: {job.job_id()}")
        return

    counts = next(iter(result[0].data.values())).get_counts()
    dominant = max(counts, key=counts.get)
    correct_pct = counts.get(expected_bits, 0) / 4096 * 100
    match = "CORRECT" if dominant == expected_bits else "NOISY"

    print(f"  --- Results ---")
    print(f"  Expected       : {expected_bits} ({expected_str})")
    print(f"  Top result     : {dominant} ({correct_pct:.0f}% correct shots) [{match}]")
    print(f"  All counts     : {dict(sorted(counts.items()))}")

    # Plot
    title = f"{op_name} A={a} B={b} on {backend.name}"
    fig = plot_histogram(counts, title=title)
    save_path = ROOT / "diagrams" / "hardware_results.png"
    fig.savefig(save_path, dpi=150)
    print(f"  Plot saved to  : {save_path}")
    plt.show()
    print()


def interactive() -> None:
    """Interactive REPL for running ALU calculations."""
    print("\n+----------------------------------------------+")
    print("|        Quantum ALU - Interactive Mode         |")
    print("+----------------------------------------------+")
    print("|  Operations : ADD, SUB, XOR, AND              |")
    print("|  Operands   : 0-3 (2-bit integers)            |")
    print("|  Backends   : sim (local) / hw (IBM hardware)  |")
    print("|  Type 'q' to quit                             |")
    print("+----------------------------------------------+")

    while True:
        try:
            raw = input("\n> Enter OP A B [sim/hw] (e.g. ADD 2 3 sim): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not raw or raw.lower() in ("q", "quit", "exit"):
            print("Bye!")
            break

        parts = raw.split()

        # Default to sim if backend not specified
        if len(parts) == 3:
            parts.append("sim")

        if len(parts) != 4:
            print("  Format: OP A B [sim/hw]  (example: ADD 2 3 sim)")
            continue

        op_name, a_str, b_str, mode = parts
        op_name = op_name.upper()
        mode = mode.lower()

        if op_name not in OP_MAP:
            print(f"  Unknown operation '{op_name}'. Choose from: ADD, SUB, XOR, AND")
            continue

        try:
            a, b = int(a_str), int(b_str)
        except ValueError:
            print("  A and B must be integers (0-3).")
            continue

        if not (0 <= a <= 3 and 0 <= b <= 3):
            print("  Operands must be 0-3 (2-bit values).")
            continue

        if mode not in ("sim", "hw"):
            print("  Backend must be 'sim' (simulator) or 'hw' (real hardware).")
            continue

        if mode == "sim":
            run_simulated(op_name, a, b)
        else:
            run_hardware(op_name, a, b)


if __name__ == "__main__":
    interactive()
