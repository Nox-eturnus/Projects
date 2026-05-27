from __future__ import annotations

from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister


def _prepare_bit(qc: QuantumCircuit, qubit, value: int) -> None:
    if value not in (0, 1):
        raise ValueError("Only classical bit values 0 or 1 are supported.")
    if value:
        qc.x(qubit)


def build_half_adder(a: int | None = None, b: int | None = None, measure: bool = True) -> QuantumCircuit:
    """Return a reversible 1-bit half-adder.

    Registers:
      a[0]      input A
      b[0]      input B, overwritten with SUM = A xor B
      carry[0]  output carry = A and B
    """
    a_reg = QuantumRegister(1, "a")
    b_reg = QuantumRegister(1, "b")
    carry = QuantumRegister(1, "carry")
    qc = QuantumCircuit(a_reg, b_reg, carry, name="half_adder")

    if a is not None:
        _prepare_bit(qc, a_reg[0], a)
    if b is not None:
        _prepare_bit(qc, b_reg[0], b)

    qc.ccx(a_reg[0], b_reg[0], carry[0])
    qc.cx(a_reg[0], b_reg[0])

    if measure:
        out = ClassicalRegister(2, "out")
        qc.add_register(out)
        qc.measure(b_reg[0], out[0])
        qc.measure(carry[0], out[1])
    return qc


def build_full_adder(
    a: int | None = None,
    b: int | None = None,
    carry_in: int | None = None,
    measure: bool = True,
) -> QuantumCircuit:
    """Return a 1-bit full-adder using reversible gates.

    Registers:
      a[0], b[0], cin[0] are inputs
      sum[0], carry[0] are outputs
      work[0] is an ancilla that is uncomputed back to |0>
    """
    a_reg = QuantumRegister(1, "a")
    b_reg = QuantumRegister(1, "b")
    cin = QuantumRegister(1, "cin")
    sum_reg = QuantumRegister(1, "sum")
    carry = QuantumRegister(1, "carry")
    work = QuantumRegister(1, "work")
    qc = QuantumCircuit(a_reg, b_reg, cin, sum_reg, carry, work, name="full_adder")

    if a is not None:
        _prepare_bit(qc, a_reg[0], a)
    if b is not None:
        _prepare_bit(qc, b_reg[0], b)
    if carry_in is not None:
        _prepare_bit(qc, cin[0], carry_in)

    # work = a xor b
    qc.cx(a_reg[0], work[0])
    qc.cx(b_reg[0], work[0])

    # sum = a xor b xor cin
    qc.cx(work[0], sum_reg[0])
    qc.cx(cin[0], sum_reg[0])

    # carry = majority(a, b, cin)
    qc.ccx(a_reg[0], b_reg[0], carry[0])
    qc.ccx(work[0], cin[0], carry[0])

    # uncompute work
    qc.cx(b_reg[0], work[0])
    qc.cx(a_reg[0], work[0])

    if measure:
        out = ClassicalRegister(2, "out")
        qc.add_register(out)
        qc.measure(sum_reg[0], out[0])
        qc.measure(carry[0], out[1])
    return qc


def build_subtractor_1bit(a: int, b: int, measure: bool = True) -> QuantumCircuit:
    """Compute A - B using 2's complement on one bit.

    For one bit, subtraction is implemented as A + (~B) + 1.
    The measured outputs are:
      difference = sum bit
      carry_out  = no-borrow indicator for unsigned subtraction
    """
    if a not in (0, 1) or b not in (0, 1):
        raise ValueError("Only 1-bit subtraction is supported.")

    a_reg = QuantumRegister(1, "a")
    b_reg = QuantumRegister(1, "b")
    cin = QuantumRegister(1, "cin")
    sum_reg = QuantumRegister(1, "sum")
    carry = QuantumRegister(1, "carry")
    work = QuantumRegister(1, "work")
    qc = QuantumCircuit(a_reg, b_reg, cin, sum_reg, carry, work, name="subtractor_1bit")

    _prepare_bit(qc, a_reg[0], a)
    _prepare_bit(qc, b_reg[0], b)
    qc.x(b_reg[0])   # bitwise NOT of B
    qc.x(cin[0])     # +1 for two's complement

    qc.cx(a_reg[0], work[0])
    qc.cx(b_reg[0], work[0])
    qc.cx(work[0], sum_reg[0])
    qc.cx(cin[0], sum_reg[0])
    qc.ccx(a_reg[0], b_reg[0], carry[0])
    qc.ccx(work[0], cin[0], carry[0])
    qc.cx(b_reg[0], work[0])
    qc.cx(a_reg[0], work[0])

    if measure:
        out = ClassicalRegister(2, "out")
        qc.add_register(out)
        qc.measure(qc.qregs[3][0], out[0])  # sum
        qc.measure(qc.qregs[4][0], out[1])  # carry
    return qc


def build_xor_gate(a: int | None = None, b: int | None = None, measure: bool = True) -> QuantumCircuit:
    a_reg = QuantumRegister(1, "a")
    b_reg = QuantumRegister(1, "b")
    out = QuantumRegister(1, "out")
    qc = QuantumCircuit(a_reg, b_reg, out, name="xor")
    if a is not None:
        _prepare_bit(qc, a_reg[0], a)
    if b is not None:
        _prepare_bit(qc, b_reg[0], b)
    qc.cx(a_reg[0], out[0])
    qc.cx(b_reg[0], out[0])
    if measure:
        classical = ClassicalRegister(1, "c")
        qc.add_register(classical)
        qc.measure(out[0], classical[0])
    return qc


def build_and_gate(a: int | None = None, b: int | None = None, measure: bool = True) -> QuantumCircuit:
    a_reg = QuantumRegister(1, "a")
    b_reg = QuantumRegister(1, "b")
    out = QuantumRegister(1, "out")
    qc = QuantumCircuit(a_reg, b_reg, out, name="and")
    if a is not None:
        _prepare_bit(qc, a_reg[0], a)
    if b is not None:
        _prepare_bit(qc, b_reg[0], b)
    qc.ccx(a_reg[0], b_reg[0], out[0])
    if measure:
        classical = ClassicalRegister(1, "c")
        qc.add_register(classical)
        qc.measure(out[0], classical[0])
    return qc


def build_or_gate(a: int | None = None, b: int | None = None, measure: bool = True) -> QuantumCircuit:
    a_reg = QuantumRegister(1, "a")
    b_reg = QuantumRegister(1, "b")
    out = QuantumRegister(1, "out")
    qc = QuantumCircuit(a_reg, b_reg, out, name="or")
    if a is not None:
        _prepare_bit(qc, a_reg[0], a)
    if b is not None:
        _prepare_bit(qc, b_reg[0], b)

    # OR = NOT((NOT A) AND (NOT B))
    qc.x(a_reg[0])
    qc.x(b_reg[0])
    qc.ccx(a_reg[0], b_reg[0], out[0])
    qc.x(out[0])
    qc.x(a_reg[0])
    qc.x(b_reg[0])

    if measure:
        classical = ClassicalRegister(1, "c")
        qc.add_register(classical)
        qc.measure(out[0], classical[0])
    return qc


def build_parallel_half_adder_demo(measure: bool = True) -> QuantumCircuit:
    """Prepare A and B in superposition, then run a half-adder on all basis states."""
    a_reg = QuantumRegister(1, "a")
    b_reg = QuantumRegister(1, "b")
    carry = QuantumRegister(1, "carry")
    qc = QuantumCircuit(a_reg, b_reg, carry, name="parallel_half_adder")

    qc.h(a_reg[0])
    qc.h(b_reg[0])
    qc.ccx(a_reg[0], b_reg[0], carry[0])
    qc.cx(a_reg[0], b_reg[0])

    if measure:
        out = ClassicalRegister(3, "out")
        qc.add_register(out)
        qc.measure(a_reg[0], out[0])      # original A
        qc.measure(b_reg[0], out[1])      # sum
        qc.measure(carry[0], out[2])      # carry
    return qc


# ---------------------------------------------------------------------------
# 2-bit helpers
# ---------------------------------------------------------------------------

def _prepare_2bit(qc: QuantumCircuit, reg: QuantumRegister, value: int | None) -> None:
    """Encode a 2-bit integer into a register, or leave it at |00⟩ if *value* is None."""
    if value is None:
        return
    if not 0 <= value <= 3:
        raise ValueError("2-bit value must be 0–3.")
    if value & 1:
        qc.x(reg[0])
    if value & 2:
        qc.x(reg[1])


def _full_adder_block(
    qc: QuantumCircuit, a_bit, b_bit, cin, s_bit, cout, work,
) -> None:
    """Append a single reversible full-adder to *qc* (no measurement).

    After this block:
      s_bit  = a_bit XOR b_bit XOR cin
      cout   = majority(a_bit, b_bit, cin)
      work   is returned to |0⟩
    """
    qc.cx(a_bit, work)
    qc.cx(b_bit, work)
    qc.cx(work, s_bit)
    qc.cx(cin, s_bit)
    qc.ccx(a_bit, b_bit, cout)
    qc.ccx(work, cin, cout)
    qc.cx(b_bit, work)
    qc.cx(a_bit, work)


# ---------------------------------------------------------------------------
# 2-bit arithmetic
# ---------------------------------------------------------------------------

def build_ripple_carry_adder_2bit(
    a: int | None = None,
    b: int | None = None,
    measure: bool = True,
) -> QuantumCircuit:
    """Return a 2-bit ripple-carry adder.

    Registers
    ---------
    a[1:0], b[1:0]   operands
    sum[1:0]          result bits
    cout              carry-out
    c0                internal carry between bit-0 and bit-1
    w0, w1            ancillae (uncomputed)
    """
    a_reg = QuantumRegister(2, "a")
    b_reg = QuantumRegister(2, "b")
    sum_reg = QuantumRegister(2, "sum")
    cout = QuantumRegister(1, "cout")
    c0 = QuantumRegister(1, "c0")
    w0 = QuantumRegister(1, "w0")
    w1 = QuantumRegister(1, "w1")
    qc = QuantumCircuit(a_reg, b_reg, sum_reg, cout, c0, w0, w1,
                         name="ripple_carry_add_2bit")

    _prepare_2bit(qc, a_reg, a)
    _prepare_2bit(qc, b_reg, b)

    # bit-0 full adder (carry-in is 0 implicitly)
    # with cin=|0⟩ a full adder still works correctly
    cin0 = QuantumRegister(1, "cin0")
    qc.add_register(cin0)
    _full_adder_block(qc, a_reg[0], b_reg[0], cin0[0], sum_reg[0], c0[0], w0[0])

    # bit-1 full adder, carry-in = c0
    _full_adder_block(qc, a_reg[1], b_reg[1], c0[0], sum_reg[1], cout[0], w1[0])

    if measure:
        out = ClassicalRegister(3, "out")
        qc.add_register(out)
        qc.measure(sum_reg[0], out[0])
        qc.measure(sum_reg[1], out[1])
        qc.measure(cout[0], out[2])
    return qc


def build_subtractor_2bit(
    a: int | None = None,
    b: int | None = None,
    measure: bool = True,
) -> QuantumCircuit:
    """Compute A − B (mod 4) using two's complement through the ripple-carry adder.

    Flips B and sets carry-in = 1 so the adder computes A + ~B + 1.
    carry-out acts as a no-borrow indicator (1 means A >= B unsigned).
    """
    a_reg = QuantumRegister(2, "a")
    b_reg = QuantumRegister(2, "b")
    sum_reg = QuantumRegister(2, "sum")
    cout = QuantumRegister(1, "cout")
    c0 = QuantumRegister(1, "c0")
    w0 = QuantumRegister(1, "w0")
    w1 = QuantumRegister(1, "w1")
    cin0 = QuantumRegister(1, "cin0")
    qc = QuantumCircuit(a_reg, b_reg, sum_reg, cout, c0, w0, w1, cin0,
                         name="ripple_carry_sub_2bit")

    _prepare_2bit(qc, a_reg, a)
    _prepare_2bit(qc, b_reg, b)

    # two's complement: NOT b, carry-in = 1
    qc.x(b_reg[0])
    qc.x(b_reg[1])
    qc.x(cin0[0])

    _full_adder_block(qc, a_reg[0], b_reg[0], cin0[0], sum_reg[0], c0[0], w0[0])
    _full_adder_block(qc, a_reg[1], b_reg[1], c0[0], sum_reg[1], cout[0], w1[0])

    if measure:
        out = ClassicalRegister(3, "out")
        qc.add_register(out)
        qc.measure(sum_reg[0], out[0])
        qc.measure(sum_reg[1], out[1])
        qc.measure(cout[0], out[2])
    return qc


# ---------------------------------------------------------------------------
# 2-bit bitwise logic
# ---------------------------------------------------------------------------

def build_xor_2bit(
    a: int | None = None, b: int | None = None, measure: bool = True,
) -> QuantumCircuit:
    a_reg = QuantumRegister(2, "a")
    b_reg = QuantumRegister(2, "b")
    out_reg = QuantumRegister(2, "out")
    qc = QuantumCircuit(a_reg, b_reg, out_reg, name="xor_2bit")
    _prepare_2bit(qc, a_reg, a)
    _prepare_2bit(qc, b_reg, b)
    for i in range(2):
        qc.cx(a_reg[i], out_reg[i])
        qc.cx(b_reg[i], out_reg[i])
    if measure:
        c = ClassicalRegister(2, "c")
        qc.add_register(c)
        qc.measure(out_reg[0], c[0])
        qc.measure(out_reg[1], c[1])
    return qc


def build_and_2bit(
    a: int | None = None, b: int | None = None, measure: bool = True,
) -> QuantumCircuit:
    a_reg = QuantumRegister(2, "a")
    b_reg = QuantumRegister(2, "b")
    out_reg = QuantumRegister(2, "out")
    qc = QuantumCircuit(a_reg, b_reg, out_reg, name="and_2bit")
    _prepare_2bit(qc, a_reg, a)
    _prepare_2bit(qc, b_reg, b)
    for i in range(2):
        qc.ccx(a_reg[i], b_reg[i], out_reg[i])
    if measure:
        c = ClassicalRegister(2, "c")
        qc.add_register(c)
        qc.measure(out_reg[0], c[0])
        qc.measure(out_reg[1], c[1])
    return qc


def build_or_2bit(
    a: int | None = None, b: int | None = None, measure: bool = True,
) -> QuantumCircuit:
    a_reg = QuantumRegister(2, "a")
    b_reg = QuantumRegister(2, "b")
    out_reg = QuantumRegister(2, "out")
    qc = QuantumCircuit(a_reg, b_reg, out_reg, name="or_2bit")
    _prepare_2bit(qc, a_reg, a)
    _prepare_2bit(qc, b_reg, b)
    for i in range(2):
        qc.x(a_reg[i])
        qc.x(b_reg[i])
        qc.ccx(a_reg[i], b_reg[i], out_reg[i])
        qc.x(out_reg[i])
        qc.x(a_reg[i])
        qc.x(b_reg[i])
    if measure:
        c = ClassicalRegister(2, "c")
        qc.add_register(c)
        qc.measure(out_reg[0], c[0])
        qc.measure(out_reg[1], c[1])
    return qc


# ---------------------------------------------------------------------------
# 2-bit opcode-controlled ALU
# ---------------------------------------------------------------------------

# Opcode mapping (2-qubit register):
#   00 = ADD   01 = SUB   10 = XOR   11 = AND

def build_alu_2bit(
    opcode: int | None = None,
    a: int | None = None,
    b: int | None = None,
    measure: bool = True,
) -> QuantumCircuit:
    """Build a 2-bit ALU that selects an operation via a 2-qubit opcode register.

    Opcode mapping:
      00 → ADD    01 → SUB    10 → XOR    11 → AND

    When *opcode* is ``None`` the register is left in |00⟩ (ADD by default);
    pass a value 0–3 to select a specific operation.

    Implementation strategy  (compact, 12-qubit design)
    ----------------------------------------------------
    Instead of computing all four operations into private registers and
    multiplexing, each operation is computed *conditionally* — gated on its
    opcode pattern — directly into a shared result register.

    * Arithmetic path (op[1]=0): ADD and SUB share a single conditional
      ripple-carry adder.  SUB preprocesses B (conditional NOT) and sets
      carry-in = 1 for two's complement.
    * Logic path: XOR and AND each use a small block of multi-controlled
      gates conditioned on their opcode pattern.

    Ancillae (c0, w) are uncomputed back to |0⟩ after each stage so the
    circuit stays fully reversible.
    """
    op = QuantumRegister(2, "op")
    a_reg = QuantumRegister(2, "a")
    b_reg = QuantumRegister(2, "b")
    result = QuantumRegister(3, "result")   # 2 data bits + carry/flag
    c0 = QuantumRegister(1, "c0")           # internal carry (bit-0 → bit-1)
    w = QuantumRegister(1, "w")             # work ancilla for majority
    cin = QuantumRegister(1, "cin")         # carry-in (set to 1 for SUB)

    qc = QuantumCircuit(op, a_reg, b_reg, result, c0, w, cin,
                         name="alu_2bit")

    # --- encode inputs ---
    _prepare_2bit(qc, a_reg, a)
    _prepare_2bit(qc, b_reg, b)
    if opcode is not None:
        _prepare_2bit(qc, op, opcode)

    # ==================================================================
    # ARITHMETIC PATH  (fires when original op[1] = 0, i.e. ADD or SUB)
    # ==================================================================
    qc.x(op[1])          # after flip: op[1]=1 for ADD/SUB, 0 for XOR/AND

    # -- SUB preprocessing (only when op[0]=1, i.e. SUB) ---------------
    # Conditionally flip B and set cin = 1 for two's complement.
    qc.ccx(op[0], op[1], b_reg[0])
    qc.ccx(op[0], op[1], b_reg[1])
    qc.ccx(op[0], op[1], cin[0])

    # -- Bit-0 full adder (conditioned on op[1]) -----------------------
    # result[0] = a[0] XOR b[0] XOR cin
    qc.ccx(op[1], a_reg[0], result[0])
    qc.ccx(op[1], b_reg[0], result[0])
    qc.ccx(op[1], cin[0],   result[0])

    # c0 = MAJ(a[0], b[0], cin)  via  w = a[0]⊕b[0]
    qc.ccx(op[1], a_reg[0], w[0])
    qc.ccx(op[1], b_reg[0], w[0])
    qc.mcx([op[1], a_reg[0], b_reg[0]], c0[0])
    qc.mcx([op[1], w[0], cin[0]],       c0[0])
    # uncompute w
    qc.ccx(op[1], b_reg[0], w[0])
    qc.ccx(op[1], a_reg[0], w[0])

    # -- Bit-1 full adder (conditioned on op[1]) -----------------------
    # result[1] = a[1] XOR b[1] XOR c0
    qc.ccx(op[1], a_reg[1], result[1])
    qc.ccx(op[1], b_reg[1], result[1])
    qc.ccx(op[1], c0[0],    result[1])

    # result[2] = MAJ(a[1], b[1], c0)  via  w = a[1]⊕b[1]
    qc.ccx(op[1], a_reg[1], w[0])
    qc.ccx(op[1], b_reg[1], w[0])
    qc.mcx([op[1], a_reg[1], b_reg[1]], result[2])
    qc.mcx([op[1], w[0], c0[0]],        result[2])
    # uncompute w
    qc.ccx(op[1], b_reg[1], w[0])
    qc.ccx(op[1], a_reg[1], w[0])

    # -- Uncompute c0 (reverse of bit-0 carry computation) -------------
    qc.ccx(op[1], a_reg[0], w[0])
    qc.ccx(op[1], b_reg[0], w[0])
    qc.mcx([op[1], w[0], cin[0]],       c0[0])
    qc.mcx([op[1], a_reg[0], b_reg[0]], c0[0])
    qc.ccx(op[1], b_reg[0], w[0])
    qc.ccx(op[1], a_reg[0], w[0])

    # -- SUB postprocessing: restore B and cin -------------------------
    qc.ccx(op[0], op[1], cin[0])
    qc.ccx(op[0], op[1], b_reg[1])
    qc.ccx(op[0], op[1], b_reg[0])

    qc.x(op[1])          # restore op[1]

    # ==================================================================
    # LOGIC PATH
    # ==================================================================

    # -- XOR (op=10 → op[0]=0, op[1]=1) --------------------------------
    qc.x(op[0])
    for i in range(2):
        qc.mcx([op[0], op[1], a_reg[i]], result[i])
        qc.mcx([op[0], op[1], b_reg[i]], result[i])
    qc.x(op[0])

    # -- AND (op=11 → op[0]=1, op[1]=1) --------------------------------
    for i in range(2):
        qc.mcx([op[0], op[1], a_reg[i], b_reg[i]], result[i])

    if measure:
        out = ClassicalRegister(3, "out")
        qc.add_register(out)
        qc.measure(result[0], out[0])
        qc.measure(result[1], out[1])
        qc.measure(result[2], out[2])
    return qc


def build_parallel_alu_2bit_demo(measure: bool = True) -> QuantumCircuit:
    """Put operands in superposition and run the ALU to show quantum parallelism."""
    return build_alu_2bit(opcode=0, a=None, b=None, measure=measure)
