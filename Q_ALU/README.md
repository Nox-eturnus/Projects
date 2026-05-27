# Quantum ALU with Qiskit

A reversible-computing Quantum ALU built on Qiskit, progressing from 1-bit gate primitives to a 2-bit ripple-carry ALU with an opcode register. Supports both local simulation and execution on real IBM quantum hardware.

## Scope

```text
1-bit logic ops       : AND, OR, XOR
1-bit arithmetic      : half adder, full adder, subtractor
2-bit logic ops       : AND, OR, XOR (bitwise)
2-bit arithmetic      : ripple-carry adder, subtractor (two's complement)
2-bit ALU             : opcode-controlled (ADD / SUB / XOR / AND), 12 qubits
execution targets     : ideal simulation, real IBM QPU via IBM Cloud
```

## Architecture

The ALU uses a conditional-compute design (12 qubits):

```text
opcode register   ─┐
                   ├─→  conditional compute  ─→  shared result register
operand registers ─┘
```

Each operation is computed conditionally, gated on its opcode pattern, directly into a shared result register:

- **Arithmetic path** (op[1]=0): ADD and SUB share a single conditional ripple-carry adder. SUB preprocesses B (conditional NOT + carry-in = 1) for two's complement.
- **Logic path** (op[1]=1): XOR and AND use multi-controlled gates conditioned on their opcode pattern.

Ancillae are uncomputed after each stage, keeping the circuit fully reversible.

### Opcode mapping

| Opcode (2-qubit) | Operation |
|:-:|:-:|
| `00` | ADD |
| `01` | SUB |
| `10` | XOR |
| `11` | AND |

OR is available as a standalone gate builder but excluded from the opcode set to keep the encoding at 2 qubits.

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
python examples/alu_calc.py
```

The interactive calculator lets you choose any operation and run it on either a local simulator or real IBM quantum hardware:

```
> Enter OP A B [sim/hw] (e.g. ADD 2 3 sim): ADD 2 3 sim

  Operation : ADD
  A = 2 (10),  B = 3 (11)
  Circuit   : Full 12-qubit ALU (opcode=00)
  Backend   : Local AerSimulator (ideal, no noise)
  Simulating (1024 shots) ...

  Result         : 101
  Classical check: 5 (carry=yes)
  Raw counts     : {'101': 1024}
```

To run on real hardware, append `hw` instead of `sim`. The calculator will connect to IBM Cloud, pick the least busy backend, and submit the job.

### Hardware setup (one-time)

1. Get an API key and CRN from your IBM Cloud / IBM Quantum account.
2. Paste them into `examples/setup_ibm.py`.
3. Run `python examples/setup_ibm.py` once to save credentials locally.

## Circuit diagrams

```bash
python examples/draw_circuits.py
```

Generates PNG diagrams for every circuit in the `diagrams/` folder.

## Project layout

```text
qalu/
  circuits.py        # reversible circuit builders (1-bit + 2-bit + ALU)
  execution.py       # simulator + hardware execution helpers
examples/
  alu_calc.py        # interactive ALU calculator (sim + hardware)
  draw_circuits.py   # circuit diagram generator
  setup_ibm.py       # one-time IBM credential setup
diagrams/            # rendered circuit diagrams
```

## Subtraction

Both the 1-bit and 2-bit subtractors use two's complement: `A - B = A + ~B + 1`. The carry-out serves as a no-borrow indicator (1 when A >= B unsigned).
