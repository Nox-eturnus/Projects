# mRNA Quantum Folding — Serial Implementation Plan

**How to use this document:** 15 parts, strictly serial. Do not start Part *N+1* until Part *N*'s "Definition of Done" passes. Each part states where it runs, what it needs from earlier parts, and exact logic for anything involving code.

## Venue Legend

| Tag | Venue | What goes here |
|---|---|---|
| 🖥 **LOCAL** | Your laptop (i9-14900HX / RTX 4070 8GB / 32GB RAM) | Classical solvers, data wrangling, SBM/SA, circuit simulation *within* your local qubit ceiling |
| ☁ **IBM-SIM** | IBM's cloud-hosted simulators via Qiskit Runtime (statevector, QASM, MPS) | Anything exceeding your local qubit ceiling, or anything you want off your laptop. **Free, unlimited, no queue, does not touch your QPU-minute budget.** |
| 🔬 **IBM-QPU** | Real superconducting hardware via Qiskit Runtime, Open Plan | Scarce (10 min/month base as of March 2026, some accounts have a temporary +180 min offer). Reserved exclusively for Part 12's final validation runs. |
| 📖 **THEORY** | Literature synthesis, derivation, written prose | No code, no compute |

**Your local qubit ceiling** (derived from hardware, not a guess — see reasoning below): Qiskit Aer statevector simulation needs `2^n × 16 bytes` for the state alone, plus ~1.5–2× overhead for gate buffers.
- RTX 4070 Laptop, 8GB VRAM → usable ~6–7GB → **~26–27 qubits** via Aer-GPU/cuStateVec.
- 32GB system RAM → usable ~24–26GB → **~29–30 qubits** via Aer-CPU (yes, your CPU path out-scales your GPU path here — 8GB VRAM is a harder ceiling than 32GB RAM).
- Anything above ~27–30 qubits (this includes your quartet-encoding and FSE-stretch-target runs, which your own plan estimates at 100–150+ qubits) is **not simulatable exactly on any single machine, laptop or otherwise** — it routes to ☁ IBM-SIM's MPS simulator (works if circuit entanglement stays bounded — verify against a small case before trusting it) or eventually 🔬 IBM-QPU.

**Note on the IBM figures above:** plan quotas and backend lists change. Re-verify via your dashboard / `service.usage()` before Part 12, not from this document.

---

## Part 1 — Literature Review & Terminology Foundation
**Venue:** 📖 THEORY
**Maps to:** Phase 0
**Prereqs:** none (this is first)

Write the actual report section, not notes-to-self:

1.1 **RNA structure fundamentals** — define WC pairing, wobble, stacking, loop taxonomy (hairpin/bulge/internal/multi), dot-bracket notation. Include one fully worked example structure with its dot-bracket string annotated loop-by-loop.

1.2 **MFE folding & DP limits** — write out the Zuker/Nussinov recursion and show, explicitly, *where* it breaks for pseudoknots: the recursion solves interval `[i,j]` by splitting at some `k` and combining independent solutions to `[i,k]` and `[k+1,j]`. For a crossing pair `(i,j)` crossing `(k,l)` with `i<k<j<l`, `k` and `l` land in different, non-nested subintervals — the split-and-combine step is structurally invalid, not just numerically suboptimal. State this as the actual mechanism, not "DP struggles with pseudoknots."

1.3 **Quantum optimization background** — QUBO/Ising formalism, VQE/QAOA mechanics at the depth needed to understand the RNA-specific mapping (forward-reference Part 7's cost function).

1.4 **CVaR aggregation** — write the formula explicitly:
```
CVaR_α(E) = (1/α) · E[ E · 1{E ≤ F⁻¹(α)} ]
```
Explain why this discards the noisy long tail of high-energy samples rather than averaging them in.

1.5 **Mixer taxonomy** — unconstrained (Pauli-X, hardware-efficient two-local) vs. Hamming-weight-preserving (XY), and the gate-count/constraint-density tradeoff (full treatment deferred to Part 10–12).

1.6 **Foundational citations** — for each of the 7 items in your master plan's §0.3 (stem-based quantum RNA folding, utility-scale quartet encoding, TT2NE, Dirks–Pierce/NUPACK/HotKnots, NP-hardness of pseudoknot MFE, RNA-As-Graphs, ViennaRNA), write 2–3 sentences in your own words on what specifically this project draws from each.

1.7 **Terminology disambiguation footnote** — the "quartet" (stacked base-pair unit) vs. "G-quartet"/G-tetrad distinction, one paragraph.

1.8 **Executive summary** — 3 short paragraphs, written last, after 1.1–1.7 exist: (1) the biological problem in plain terms, (2) why it's a computational challenge (the DP-breaks-on-pseudoknots mechanism from §1.2, condensed to 2–3 sentences), (3) the proposed quantum approach in one paragraph. This is the piece that goes into your presentation deck and README, not the full review.

**Definition of Done:** a complete, gap-free written document that a third party with zero context could read and understand (a) RNA secondary structure representation, (b) precisely why DP fails on pseudoknots, (c) the quantum formulation approach — without needing anything else.

---

## Part 2 — Local Environment Setup
**Venue:** 🖥 LOCAL
**Prereqs:** none (can run parallel to Part 1)

1. Python 3.11 venv.
2. Install: `qiskit`, `qiskit-aer` (+ `qiskit-aer-gpu` if pursuing the CUDA/cuQuantum path — check driver/CUDA compatibility with your mobile GPU first), `qiskit-ibm-runtime`, `ViennaRNA` (pip package wrapping the C library), `ortools`, `torch` (CUDA build matching your installed CUDA version), `networkx`, `numpy`, `pandas`, `matplotlib`.
3. Verify GPU is actually used, not silently falling back to CPU:
   - `torch.cuda.is_available()` → `True`.
   - Run a trivial 2-qubit circuit on `AerSimulator(method='statevector', device='GPU')`; check `result.metadata['device'] == 'GPU'` explicitly — Aer will fall back silently to CPU on a bad build without erroring.
4. IBM Runtime account: `QiskitRuntimeService(channel="ibm_quantum")`, save token, list backends, print current quota.

**Definition of Done:** one smoke-test script that (a) folds a trivial hairpin with ViennaRNA, (b) solves a 3-variable QUBO with OR-Tools CP-SAT, (c) runs a Bell circuit on Aer confirming `device='GPU'`, (d) lists IBM backends and prints remaining QPU-minute quota — all four succeed with no errors.

---

## Part 3 — Dataset Compilation & Genus Ground-Truth Computation
**Venue:** 🖥 LOCAL (data + code) + 📖 THEORY (validation reasoning)
**Maps to:** Phase 1
**Prereqs:** Part 2

### 3a. Target A (nested, pipeline-correctness set) — LOCAL
Data structure per instance: `{id, sequence, known_structure_dotbracket, source, length, topology_class}`.
- Generate synthetic hairpins programmatically (loop over stem length 3–6bp × loop size 4–6nt).
- Add a curated static-CSV subset of confirmed pseudoknot-free RNA STRAND entries (static file, not a live scrape — keeps results reproducible).

### 3b. Target B (pseudoknotted primary set) — LOCAL
Same structure, `source='PseudoBase'` / `'RNA STRAND (pk)'`. Curate as a static seed CSV with literature dot-bracket structures using nested bracket types (`()[]{}`) for crossing levels.

### 3c. FSE stretch target — LOCAL
Three sequences only: 77nt (→3_6), 87nt/144nt (→3_3), plus a short-length construct for 3_5, each with published reference base-pair lists.

### 3d. Genus computation — LOCAL, code (this is the important algorithm)

```
function compute_genus(base_pairs: list[(i,j)]) -> int:
    # base_pairs can be individual pairs OR grouped stems/quartets —
    # genus only depends on the crossing relation, so pick one granularity and be consistent.

    # 1. Build the interlacement (crossing) graph
    nodes = index 0..k-1, one per helix/pair
    for every unordered pair of helices (a1,b1), (a2,b2) with a1<b1, a2<b2:
        add edge iff exactly one of {a2,b2} lies strictly inside the open interval (a1,b1)
        i.e. (a1 < a2 < b1 < b2) OR (a2 < a1 < b2 < b1)

    # 2. Adjacency matrix A (k×k, symmetric, 0/1, zero diagonal), over GF(2)

    # 3. rank = rank_GF2(A) via standard bit-matrix Gaussian elimination:
    #    for each column, find a pivot row with a 1 in that column among
    #    remaining rows, swap it up, XOR into every other row with a 1 there,
    #    advance; count pivots used = rank

    return rank // 2   # theorem guarantees this is always an even/2-divisible integer
```

**Mandatory validation before trusting this on real data** — hard-assert all three:
1. Nested-only structure (no crossings) → 0 edges → rank 0 → **genus 0**.
2. Single H-type pseudoknot (2 helices, 1 crossing pair) → rank 2 → **genus 1**.
3. Kissing hairpin (3 helices: A,B don't cross each other, C crosses both) → rank 2 → **genus 1, NOT 2**. This is the check that specifically catches the naive-double-counting mistake your master plan's Phase 3 explicitly warns about — if you get 2 here, the crossing test in step 1 (not the rank/GF(2) math) is almost certainly wrong.

If any of these three fails, do not proceed — the bug is in the crossing-interval test, most likely an off-by-one on interval boundaries.

Apply `compute_genus` to the actual 3_6 / 3_3 / 3_5 base-pair lists — do NOT assume genus 1 by analogy to PseudoBase, and confirm 3_5 returns exactly 0.

**Definition of Done:** `compute_genus` passes all three validation assertions, and you have three actually-computed (not assumed) genus values for 3_6, 3_3, 3_5, with 3_5 == 0 confirmed.

---

## Part 4 — Candidate Generation: Pair-Level Encoding
**Venue:** 🖥 LOCAL
**Maps to:** Phase 2 (pair-level)
**Prereqs:** Part 3

```
function generate_pair_candidates(sequence) -> list[(i,j)]:
    valid_bp(a,b) = (a,b) in {AU, UA, GC, CG, GU, UG}   # wobble included, do not omit
    candidates = []
    for i in range(len(sequence)):
        for j in range(i+4, len(sequence)):   # j-i >= 4 enforces min loop-closure directly
            if valid_bp(sequence[i], sequence[j]):
                candidates.append((i,j))
    return candidates
```

**Crossing-audit test (mandatory):** on a known Target B instance, confirm both members of at least one known crossing pair-of-pairs appear simultaneously in the output. This should trivially pass since pair-level has no non-crossing filter by construction — verify anyway, since a dedup/sort bug could silently drop one and break every downstream pseudoknot experiment.

**Definition of Done:** candidate count matches a hand/brute-force count on a small (~12nt) test sequence, and the crossing-audit test passes.

---

## Part 5 — Candidate Generation: Stem-Level Encoding
**Venue:** 🖥 LOCAL
**Maps to:** Phase 2 (stem-level — flagged "highest risk" in the master plan)
**Prereqs:** Part 4

```
function generate_stem_candidates(sequence, pair_candidates) -> list[Stem]:
    # Stem = {pairs: [(i,j), ...], outer: (i0,j0), inner: (ik,jk)}
    stems = []
    for (i,j) in pair_candidates:
        stem = [(i,j)]
        while (i+1, j-1) is a valid candidate pair AND satisfies loop-closure:
            stem.append((i+1, j-1)); i += 1; j -= 1
        if len(stem) >= MIN_STEM_LEN:   # configurable, e.g. 2
            stems.append(stem)
    dedup by exact pair-set equality (same stem reached from two starting positions)
    return stems
```

**Critical:** do NOT add a step that discards a stem for crossing a previously-accepted stem. That greedy discard is exactly the silent non-crossing assumption the master plan flags. Every maximal stem from every starting pair is generated independently; crossing exclusion is a QUBO-time penalty decision (Part 8), never a candidate-generation-time filter.

**Crossing-audit test (mandatory), two parts:**
1. Two-stem case: confirm both stems of a known interleaving pair (per Part 3's crossing test) appear simultaneously.
2. Three-stem case: build a synthetic sequence with 3 non-nested overlapping helix regions and confirm all 3 appear as independent candidates — this is the FSE-relevant check, not just the simple pseudoknot case.

**Definition of Done:** both sub-tests pass. If either fails, do not proceed to Part 6 or Part 7 — every downstream phase inherits this candidate list.

---

## Part 6 — Candidate Generation: Quartet-Level Encoding
**Venue:** 🖥 LOCAL
**Maps to:** Phase 2 (quartet-level)
**Prereqs:** Part 4

```
function generate_quartet_candidates(sequence, pair_candidates) -> list[Quartet]:
    # Quartet = stacked pair-of-base-pairs: {pair1: (i,j), pair2: (i+1,j-1)}
    quartets = []
    for (i,j) in pair_candidates:
        if (i+1, j-1) in pair_candidates:
            quartets.append({(i,j), (i+1,j-1)})
    return quartets
```

This yields a larger, overlapping candidate set (long helices decompose into multiple quartets) — expected, and needed for Part 15's scaling comparison.

**Crossing-exclusion note:** the published utility-scale quartet formulation you're citing bakes a crossing-exclusion penalty directly into its cost function. That term belongs in Part 7/8's QUBO, **not** here — confirm `generate_quartet_candidates` stays pseudoknot-agnostic.

**Crossing-audit test:** same two-stem/three-stem checks as Part 5, applied to quartets.

**Definition of Done:** crossing-audit passes; quartet count > stem count for the same test sequence (expected scaling relationship — investigate if this inverts).

---

## Part 7 — QUBO Construction (energies + exclusivity; no genus penalty yet)
**Venue:** 🖥 LOCAL
**Maps to:** Phase 3 (one-/two-body terms)
**Prereqs:** Parts 4, 5, 6, 2 (ViennaRNA for energies)

For each encoding independently, build `Q = one_body + two_body + exclusivity` (genus term is Part 8):

1. **One-body:** for each candidate `c`, compute `E(c)` via `fold_compound.eval_structure()` on a structure containing only `c`'s pair(s) closed as an isolated hairpin/stack. Store as `Q[c][c] = E(c)`.
2. **Two-body stacking:** for structurally-adjacent/compatible candidate pairs `(c1,c2)`, compute the incremental stacking bonus as `eval_structure(combined) − E(c1) − E(c2)`. Store as `Q[c1][c2] += bonus`.
3. **Mutual exclusivity:** for any `(c1,c2)` sharing a nucleotide position, `Q[c1][c2] += P_excl`, where `P_excl` is set per-instance (e.g. 10× the largest one-body magnitude in *that* instance — don't hardcode a global constant, energy scale varies with sequence length).
4. **Document, don't fix:** multiloop penalties scaling with closing-helix count don't map onto fixed pairwise `Q` terms — state this once in the report as an accepted approximation.

**Definition of Done:** on a Target A instance, brute-force-solving the exclusivity-only QUBO yields a non-overlapping structure whose energy is in the right ballpark of ViennaRNA's own MFE energy (not necessarily identical — it's a simplification — but not off by an order of magnitude or sign-flipped). A large mismatch means step 1's energy extraction has a bug.

---

## Part 8 — Genus Penalty Calibration
**Venue:** 🖥 LOCAL
**Maps to:** Phase 3 (topological penalty)
**Prereqs:** Part 7, Part 3 (genus ground truth); needs Part 9's exact solver as a sub-routine — build that first if not done

1. **Path A** (stem-level, single-crossing topologies only): first check, via Part 3's `compute_genus` plus a raw crossing-pair count, that the crossing-pairs-to-genus ratio is exactly 1:1 for this instance. If so: `Q[stem_a][stem_b] += μ` once, `μ = 1.5` (TT2NE-anchored). If the ratio isn't 1:1 (e.g. kissing hairpins), route to Path B instead — do not apply Path A there.
2. **Path B** (quartet/pair-level, or any multi-crossing topology): for every crossing candidate pair, `Q[c1][c2] += μ_sweep` — NOT fixed at 1.5, this is the calibrated free parameter.
3. **Calibration sweep:**
```
for mu_candidate in linspace(0.1, 5.0, 50):
    build Q with mu_sweep = mu_candidate
    solve exactly (Part 9, on the small calibration subset only)
    check: exact solution has a crossing pair for known pseudoknots,
           and does NOT for known-nested negative controls
    record classification accuracy at this mu_candidate
mu_star = argmax(accuracy)
```
4. Lock `mu_star` as a stored constant for all subsequent Path B runs — sweep once, reuse everywhere.

**Definition of Done:** the sweep produces a real (non-flat, non-degenerate) accuracy curve, and `mu_star` lands strictly inside the swept range — if it sits at the boundary, widen the range and re-sweep before locking the value.

---

## Part 9 — Classical Ground Truth Establishment
**Venue:** 🖥 LOCAL
**Maps to:** Phase 4
**Prereqs:** Part 7 (needs this solver for Part 8's step 3 — implement this part first if sequencing tightly)

1. **Brute-force (N ≤ 25):**
```
best = None
for bitstring in all 2^N combinations:
    energy = bitstring^T · Q · bitstring
    if best is None or energy < best.energy: best = (bitstring, energy)
```
Use only as an independent cross-check against OR-Tools on the same small instance — a disagreement means a bug in the QUBO→MIP translation, not in the physics.

2. **OR-Tools CP-SAT exact solve:** fold `Q[i][j]+Q[j][i]` into one symmetric coefficient; CP-SAT needs a linear objective, so introduce an auxiliary `y_ij = x_i AND x_j` per off-diagonal term via standard linearization:
```
y_ij <= x_i
y_ij <= x_j
y_ij >= x_i + x_j - 1
objective += Q[i][j] * y_ij
```
Set a time limit; if CP-SAT times out without proving optimality, that result is **not** a valid ground truth — flag it explicitly rather than silently treating the best-found bound as exact.

3. **ViennaRNA baselines:** `RNA.fold_compound(seq).mfe()` for Target A; RNAPKplex (via bindings, or shell out to the standalone binary and parse dot-bracket output if bindings don't expose it) for Target B.

4. **`eval_structure()` scoring pass:** run every structure produced anywhere in the project (exact-solver, VQE/QAOA, SBM/SA outputs) through `fold_compound.eval_structure()` to get one comparable full-Turner-model energy, independent of which QUBO simplification produced it.

5. **Validation checkpoint (mandatory gate):** for every Target B instance, confirm the OR-Tools exact solution contains at least one crossing pair. If not: **stop, do not proceed to Part 10.** Check in order: (a) is Part 8's `mu_star` too large? (b) did Part 5/6's crossing-audit actually get re-run on *this specific instance*, not just the toy case?

**Definition of Done:** brute-force and OR-Tools agree exactly on all N≤25 instances; step 5 passes for every Target B instance, not just one.

---

## Part 10 — Ising Mapping & Ansatz/Mixer Circuit Construction (small-N validation only)
**Venue:** 🖥 LOCAL
**Maps to:** Phase 5 (circuit design, pre-noise-sweep)
**Prereqs:** Part 9

1. **QUBO→Ising:** substitute `x_i = (1-z_i)/2`, `z_i ∈ {-1,+1}`, expand algebraically into `Σ h_i Z_i + Σ J_ij Z_i Z_j + constant`. This is closed-form algebra — derive once, unit-test by converting a handful of bitstrings to spins and confirming `H_ising(spin) == QUBO(bitstring) − constant` exactly.
2. **Two-local ansatz:** one `RY(θ)` per qubit, then linear-nearest-neighbor `CZ` layer, repeated `reps` times (start `reps=1`).
3. **QAOA circuit:** alternating cost layer `exp(-iγH_C)` (built directly from `h_i`,`J_ij` as `RZ`/`RZZ` gates) and mixer layer:
   - Pauli-X mixer: `RX(β)` per qubit, zero two-qubit gates.
   - XY mixer: pairwise `RXX(β)+RYY(β)` on Hamming-weight-constrained pairs.
4. **Validate both** on a Target A instance within your local qubit ceiling: run VQE/QAOA with Aer statevector, confirm convergence to Part 9's exact ground energy within a stated tolerance. Pure software-correctness check — don't draw any mixer-performance conclusions here, that's Part 11/12.

**Definition of Done:** both ansätze (and both mixers) converge to within tolerance of Part 9's exact energy on a small Target A instance. If any fails, re-check step 1's unit test before suspecting the optimizer.

---

## Part 11 — Noise Progression, Tier 1: Ideal & Shot-Noise Only
**Venue:** 🖥 LOCAL (≤ qubit ceiling) or ☁ IBM-SIM (above ceiling — free, no queue, no budget cost)
**Maps to:** Phase 5, sampling-noise-only experiment
**Prereqs:** Part 10

1. **Ideal statevector sweep:** both ansätze/mixers, zero shot noise, across a fixed seed count decided now (e.g. 20 — keep this number fixed through Part 13). Record mean/variance of final energy per configuration.
2. **Shot-noise-only sweep:** same ideal unitary, zero gate error, sweep shot count (e.g. 128/512/2048/8192), compute CVaR-aggregated cost per Part 1.4's formula.
3. **Routing rule:** if `n_qubits` ≤ your local ceiling, run locally. If it exceeds it (quartet-encoding, FSE), submit the identical circuit to IBM's free cloud simulator — exact statevector if it fits their own memory ceiling, otherwise the MPS simulator for larger/low-entanglement circuits. Validate MPS against a small known case before trusting it on anything you can't independently cross-check.
4. **Log per run** (not per configuration-type): qubit count, circuit depth, two-qubit gate count (mixer layer and total), variable count — feeds Part 15's plots directly with no recomputation.

**Definition of Done:** populated results table (encoding × ansatz/mixer × instance × shot-count × seed) with energy mean/variance, ready for Part 12/15.

---

## Part 12 — Noise Progression, Tier 2: Noisy Simulator & Real Hardware
**Venue:** ☁ IBM-SIM (noisy sim — free) → 🔬 IBM-QPU (real hardware — scarce, use last)
**Maps to:** Phase 5, hardware-noise experiment + mixer crossover point
**Prereqs:** Part 11

1. **Noisy simulator:** build a noise model from real calibration data (`NoiseModel.from_backend(...)` or IBM's pre-baked "Fake" backend classes) and re-run Part 11's exact circuits with it injected. Still free/unlimited.
2. **Locate the crossover point:** plot final energy/CVaR vs. noise level for both mixers across ideal→shot-noise→noisy-sim. Curve-fit both series against a noise-level proxy (e.g. total 2-qubit-gate-count × per-gate error rate) and solve for the numeric intersection — report the number, don't eyeball a plot.
3. **Real hardware (budget-critical):**
   - Check your *current* quota fresh (`service.usage()` or current dashboard equivalent) — don't trust any past-referenced figure, verify at the moment you run this.
   - Batch every hardware-tier run into one session to minimize queue overhead against your minute budget.
   - Submit only 2–3 points bracketing the noisy-sim's predicted crossover — not a full sweep (that already happened for free in step 1). Hardware here validates a prediction, it doesn't reproduce the whole experiment.
   - Apply whatever error-mitigation options Qiskit Runtime currently exposes for your backend (dynamical decoupling, measurement mitigation) — check current docs for exact option names at run time, these get restructured across releases.

**Definition of Done:** the empirically-measured crossover point falls within the noisy-simulator's predicted confidence interval. If it doesn't, that's a genuine, reportable finding — document it as a result, not a bug.

---

## Part 13 — SBM & SA Benchmarking
**Venue:** 🖥 LOCAL (SBM on GPU via PyTorch; SA on CPU)
**Maps to:** Phase 6
**Prereqs:** Part 9, Part 11 (fixed seed count)

1. **SBM:**
```
x, y = random_init(N)          # continuous, torch tensors on GPU
for t in range(T_steps):
    y += dt * (-(1 - a(t))*x + c0 * (Q @ x))   # a(t): pump schedule 0→1
    x += dt * y
    x = clip(x, -1, 1)
solution = sign(x)
```
Run for the same seed count as Part 11 (20). Log wall-clock and "evaluations" = one per full integration time-step (Phase 6's matched-granularity unit).

2. **SA:**
```
spins = random_init(N)
for sweep in range(n_sweeps):
    T = T_schedule(sweep)
    for i in random_order(N):        # one full sweep = N proposed flips
        dE = energy_delta_if_flipped(spins, i, Q)
        if dE < 0 or random() < exp(-dE/T): spins[i] *= -1
```
One evaluation = one full sweep. Same 20 seeds.

3. **Statistical parity check (mandatory):** confirm exactly 20 SBM and 20 SA runs per instance — the master plan explicitly flags an earlier draft applying this rigor only to quantum methods as a bug.

**Definition of Done:** SBM and SA tables exist, 20 seeds each, matched evaluation units logged, ready for Part 14.

---

## Part 14 — Multi-Tier Performance Evaluation
**Venue:** 🖥 LOCAL
**Note:** Tier 2b is required, not optional — the rubric's "report accuracy" line means structure-level accuracy, not just energy comparison. Don't stop at Tier 1 even under time pressure.
**Maps to:** Phase 7
**Prereqs:** Parts 9, 11, 12, 13

1. **Tier 1:** compare every method's (QAOA, VQE, SBM, SA) final objective to Part 9's exact value. Primary metric = evaluation count (Part 13's units); secondary = circuit-call count (quantum only) and wall-clock (explicitly caveated as confounded by queue/calibration time).
2. **Tier 2a:** convert Part 9's exact solution to dot-bracket (helper below), compare against (i) known biology, (ii) ViennaRNA/RNAPKplex baseline. A mismatch here isolates error to Part 7/8's QUBO approximation, not the optimizer.
3. **Tier 2b (headline result):**
```
function bitstring_to_dotbracket(bitstring, candidate_list):
    mark each "1" candidate's positions as paired
    assign bracket type by nesting depth: a pair gets bracket-type k
        if it crosses exactly k-1 already-assigned lower-type pairs
        (reuse Part 3's interlacement logic to determine this)
    return dot-bracket string
```
Then compute confusion counts directly against the true structure: `TP` = predicted pairs matching true, `FP` = predicted-not-true, `FN` = true-not-predicted, `TN` = everything else over all `C(N,2)` position-pairs. Compute Sensitivity `=TP/(TP+FN)`, PPV `=TP/(TP+FP)`, MCC (standard formula). Run this **directly** on every method's top output — do not infer Tier 2b from Tier 2a.
4. **Cross-encoding consistency:** convert pair/stem/quartet-level best structures to dot-bracket via the same helper; report as an agreement/disagreement table per topological feature, not a single aggregate percentage (which would hide exactly which features disagree).

**Definition of Done:** one consolidated table (Tier 1, 2a, 2b, cross-encoding) per instance × method — this feeds Part 15 and the paper's results section directly.

---

## Part 15 — Scalability Analysis & Reporting
**Venue:** 🖥 LOCAL (plots) + 📖 THEORY (writing)
**Maps to:** Phase 8
**Prereqs:** Part 14, Part 11's logs

1. **Plot 1 (required):** sequence length vs. variable/qubit count, one line per encoding — pulled directly from Part 11's logs, no recomputation.
2. **Plot 2 (required):** sequence length vs. wall-clock (log scale) for exact-solver / VQE / QAOA / SBM / SA — from Part 14's Tier 1 data.
3. **Written section (THEORY):** cost-function evaluations as primary complexity proxy; wall-clock secondary with the queue-time caveat restated.
   - **Status: pseudoknot extension completed.** All 5 Target B instances (`pk_htype_001–004`, `pk_kissing_001`) have been run through Parts 11, 13, and 14 with full 20-seed statistical parity. The μ* calibration (Part 8) converged to μ* = −0.25 with 100% classification accuracy on the calibration set.
   - **Use the NP-hardness justification** — restate, in this section's own words, the Phase 1 argument: Target A is classically polynomial-solvable and motivates nothing about quantum methods; Target B matters because general pseudoknot MFE prediction is NP-hard. This is the paper's actual scientific argument for exploring quantum methods at all — it needs to appear here explicitly, not just in the introduction.
   - **Update the scalability report's framing.** The current `plots/scalability_report.md` §5 still contains the stale "feasibility study" framing (stating Target B was "not tested at experimental scale"). This must be replaced with the NP-hardness framing now that Target B results exist.

**Definition of Done:** both plots render from logged data with no manual number entry; the written section uses the NP-hardness justification and explicitly cites Target B results. The scalability report's §5 no longer contains the stale feasibility-only framing. Finally, walk the master plan's full "Consolidated Validation Checkpoint Checklist" line by line — every checkbox should map to a specific completed Part above. Any checklist item without a corresponding completed step is a gap to close before calling the project done.

---

## Part 16 — Final Submission Package
**Venue:** 🖥 LOCAL + 📖 THEORY
**Prereqs:** Part 15

**Repo restructuring & cleanup (do this first — but only after Part 15's checklist has already passed on the working, still-partwise repo; don't delete anything until the "dirty" version is confirmed correct):**

1. **Classify every file** currently in the project folder into three buckets before touching anything:
   - *Production* — code actually on the path from raw sequence to the headline Tier 2b result: data loading (Target A + Target B + FSE), candidate generation (pair/stem/quartet), QUBO construction, genus penalty injection (with locked μ* = −0.25), the exact/VQE/QAOA/SBM/SA solvers, evaluation, plotting. **Include `run_target_b.py` / `run_target_b_fast.py` logic in the main pipeline** — these should not remain as standalone extension scripts but be folded into the single entry point.
   - *Validation scaffolding* — the crossing-audit tests (Parts 4–6), genus-assertion checks (Part 3), the QUBO→Ising unit test (Part 10), the brute-force-vs-OR-Tools cross-check and Target B crossing-pair gate (Part 9), the μ-sweep calibration script (Part 8). These earned their keep during development but aren't needed to *reproduce* the result on an already-validated pipeline.
   - *Disposable* — `__pycache__`, `.ipynb_checkpoints`, scratch/exploratory notebooks, superseded CSVs, old plot versions, IBM job logs from earlier aborted runs, anything duplicated across parts.
2. **Delete everything in the disposable bucket.**
3. **Consolidate validation scaffolding** into a single `tests/` folder (runnable via `pytest`, or a `--validate` flag on the main entry point). It should still be there for a skeptical grader to run, but the main pipeline run must not depend on it executing.
4. **Merge the 16 part-numbered scripts/notebooks into a small set of semantically-named modules** — e.g. `data.py`, `candidates.py`, `qubo.py`, `classical_solvers.py`, `quantum_circuits.py`, `noise_study.py`, `evaluate.py`, `plots.py` — instead of `part1_*.py` … `part16_*.py`. Nothing in the final repo's file names, folder names, or docstrings should read "Part N" / "Phase N"; that numbering was a build-order scaffold for you, not the project's actual structure, and its presence is the main visual tell that this was assembled incrementally rather than designed as a whole.
5. **Single entry point:** one script or notebook (`run_pipeline.py` / `main.ipynb`) that calls the consolidated modules in sequence — data → candidates → QUBO → classical ground truth → quantum experiments → noise study → evaluation → plots — so the project reads as one coherent pipeline, not 16 independent hand-offs.
6. **Trim `results/`** down to only the tables/plots actually referenced in the paper/deck, not every intermediate sweep output generated along the way.

**README:** setup steps, what the (now-consolidated) pipeline does stage-by-stage — framed to match the methods-section narrative ("Data → Encoding → QUBO → Genus penalty → Classical baseline → Quantum optimization → Noise study → Evaluation"), not "Part 1 … Part 16". **Explicitly state that both Target A (nested) and Target B (pseudoknotted) instances are tested**, and that the NP-hardness of pseudoknot MFE prediction is the scientific motivation. Include where the results tables/plots land.
**Presentation deck (5–10 slides):** pull directly from Part 1's §1.8 executive summary, Part 15's two plots, Part 14's headline Tier 2b numbers, and a closing "future directions" slide (explicitly named by the rubric — don't fold it silently into the scalability discussion). **The deck must include at least one slide showing Target B (pseudoknot) results** — specifically: the μ* calibration outcome (−0.25, 100% accuracy), and a comparison of Tier 2b accuracy between Target A (nested) and Target B (pseudoknotted) instances. This is the project's headline claim: that the pipeline handles the NP-hard case, not just the polynomial one.
**Reproducibility check:** *after* the restructuring above, run the whole pipeline once from a clean environment/fresh clone before submitting. This isn't redundant with step 1–6 — it's what catches a cleanup mistake where something the production path actually needed got classified as disposable or scaffolding. **Verify that all 5 Target B instances appear in the final Part 14 output** — a restructuring bug that silently drops them would undermine the NP-hardness claim.

**Definition of Done:** a third party can clone/open the submission and reproduce your headline result without asking you anything, and nothing in the repo's file names, folder structure, or README reveals that it was built as 16 sequential parts. The presentation deck includes a dedicated Target B results slide, and the README explicitly frames the project around the NP-hard pseudoknot case.