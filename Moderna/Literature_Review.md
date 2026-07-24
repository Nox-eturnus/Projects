# Part 1: Literature Review & Terminology Foundation

## 1.1 RNA Structure Fundamentals
RNA sequences fold into complex secondary structures driven primarily by hydrogen bonding between nucleotides. The most stable and common interactions are Watson-Crick (WC) pairings, which include Adenine-Uracil (A-U) and Guanine-Cytosine (G-C). In addition to WC pairs, "wobble" base pairs (G-U) are frequently observed and contribute to structural stability.

When multiple base pairs form consecutively without interruption, they create a "stem" or "helix". This base-pair stacking provides the bulk of the thermodynamic stability in an RNA structure due to stabilizing pi-pi interactions between adjacent aromatic rings. 

Regions of the RNA sequence that do not form base pairs are categorized by their structural context into a specific loop taxonomy:
*   **Hairpin loop**: An unpaired sequence of nucleotides that loops back on itself to close a helix.
*   **Bulge**: Unpaired nucleotides present on only one side of a helix, introducing a kink or bend in the stem.
*   **Internal loop**: Unpaired nucleotides occurring on both sides of a helix, separating two paired regions.
*   **Multibranch loop**: A junction where three or more helices meet, connected by unpaired single-stranded regions.

Secondary structures are commonly represented using **dot-bracket notation**. In this text-based format, an unpaired nucleotide is denoted by a dot (`.`), while a base pair is represented by matching open and close parentheses `(` and `)`. 

**Fully Worked Example:**
Consider the following synthetic RNA sequence and its structure:

**Sequence:**
`1 2 3 4 5 6 7 8 9 10 11` (Indices)
`G G C A A A U G C  U  C` (Nucleotides)
`( ( ( . . . . ) .  )  )` (Dot-Bracket Notation)

**Annotated Loop-by-Loop Breakdown:**
*   **Base Pairs (WC and Wobble):** `G1-C11`, `G2-U10` (wobble pair), and `C3-G8`.
*   **Stem 1 (Outer):** Formed by the contiguous stack of `G1-C11` and `G2-U10`.
*   **Bulge (Size 1):** The single unpaired nucleotide `C9` interrupts the stem between `(G2-U10)` and `(C3-G8)`.
*   **Stem 2 (Inner):** The single base pair `C3-G8` isolated by the bulge.
*   **Hairpin Loop (Size 4):** The unpaired sequence `A4, A5, A6, U7` closes the inner stem at `C3-G8`.

## 1.2 MFE Folding & DP Limits
The classical approach to predicting RNA secondary structure relies on dynamic programming (DP) algorithms, notably the Zuker and Nussinov algorithms, to find the Minimum Free Energy (MFE) structure. 

The core of these DP algorithms relies on a recursion that solves the folding problem for a subsequence interval `[i, j]` by splitting it at some intermediate point `k` (`i ≤ k < j`). The algorithm then optimally and independently solves the sub-intervals `[i, k]` and `[k+1, j]`. In a simplified form (like Nussinov for maximizing base pairs), the recursion looks like:

```text
OPT(i, j) = max {
    OPT(i, j-1),                                        // j is unpaired
    max_{i ≤ k < j} [ OPT(i, k-1) + 1 + OPT(k+1, j-1) ] // j pairs with k
}
```
*Note: The Zuker algorithm is more complex as it scores loops rather than individual base pairs, but it relies on the exact same structural decomposition logic.*

**Where and why DP breaks for pseudoknots:**
This split-and-combine step intrinsically assumes that base pairs never cross. If we have a crossing pair `(i, j)` that crosses another pair `(k, l)` such that `i < k < j < l`, a pseudoknot is formed. When the DP recursion attempts to split the sequence at some boundary (for instance, at or around `k`), the nucleotides `k` and `l` inevitably land in different, non-nested sub-intervals. Because the DP assumes the sub-intervals `[i, k-1]` and `[k, j]` can be solved *independently*, it cannot evaluate the energetic contribution of the `(k, l)` pairing, as `k` and `l` are evaluated in separate, disconnected recursion branches. Thus, the split-and-combine step is structurally invalid for pseudoknots, preventing standard DP from exploring these topological configurations at all.

## 1.3 Quantum Optimization Background
Quantum optimization maps combinatorial problems into a physical energy minimization problem. To solve the RNA folding problem on a quantum device, the problem must first be formulated as a **Quadratic Unconstrained Binary Optimization (QUBO)** model, which can be directly mapped to an Ising Hamiltonian.

In the QUBO formalism, we define binary decision variables (e.g., $x_i \in \{0, 1\}$ representing whether a specific base pair, stem, or quartet is present in the folded structure). The objective is to minimize a cost function containing linear (one-body) terms and quadratic (two-body) terms. The quadratic terms naturally capture pairwise interactions, such as the stabilizing thermodynamic stacking bonuses between adjacent structural elements or the energetic penalties for structurally incompatible (mutually exclusive) elements. (This mapping is detailed further in Part 7's cost function.)

Once mapped to an Ising Hamiltonian ($H_C$), parameterized quantum circuits such as the **Variational Quantum Eigensolver (VQE)** or the **Quantum Approximate Optimization Algorithm (QAOA)** can be used. These hybrid quantum-classical algorithms prepare a quantum state via a parameterized ansatz circuit. A classical optimizer then iteratively adjusts the circuit parameters to minimize the expectation value of the Hamiltonian, driving the quantum state toward the low-energy bitstrings that represent optimal or near-optimal RNA structures.

## 1.4 CVaR Aggregation
In near-term quantum optimization, output distributions are often heavily affected by hardware noise and poor algorithmic convergence, resulting in a long tail of high-energy (suboptimal) samples. Rather than evaluating the simple expected value (mean) of the energy, we use **Conditional Value-at-Risk (CVaR)** aggregation.

The formula for CVaR at a tail probability $\alpha \in (0, 1]$ is:
`CVaR_α(E) = (1/α) · E[ E · 1{E ≤ F⁻¹(α)} ]`
*(where $F^{-1}(\alpha)$ is the $\alpha$-quantile of the energy distribution)*

**Why this is used:**
Averaging the entire distribution includes the noisy long tail of high-energy, invalid states, which can artificially pull the cost landscape in the wrong direction and mislead the classical optimizer. By discarding samples with energies above the $\alpha$-quantile, CVaR aggregation focuses exclusively on the best (lowest energy) samples found in a given batch. This effectively smooths the optimization landscape and directs the optimizer to improve the ground-state probability, rather than wasting effort trying to slightly improve the worst-case samples.

## 1.5 Mixer Taxonomy
In QAOA, the mixer Hamiltonian is responsible for driving transitions between different basis states, allowing the algorithm to explore the solution space. 

*   **Unconstrained Mixers (e.g., Pauli-X, Hardware-Efficient Two-Local):**
    These apply independent operations (like $R_X(\beta)$ rotations) to each qubit. They are extremely hardware-efficient, require zero two-qubit gates in the mixer layer, and can explore the entire $2^N$ Hilbert space. However, they rely entirely on large energetic penalty terms in the cost Hamiltonian (the QUBO) to suppress invalid configurations (e.g., overlapping base pairs).
*   **Hamming-Weight-Preserving (XY) Mixers:**
    These mixers use correlated two-qubit operations (like $R_{XX}(\beta) + R_{YY}(\beta)$) to swap states only between valid configurations, preserving the total number of "1"s (Hamming weight) or explicitly enforcing problem constraints natively in the circuit. While this drastically reduces the searchable Hilbert space to only valid solutions, it comes at the cost of a significantly deeper circuit with high two-qubit gate counts, which can overwhelm near-term noisy hardware. The choice between these mixers represents a fundamental tradeoff between constraint-density in the cost function versus gate-count density in the circuit.

## 1.6 Foundational Citations
This project builds upon a synthesis of several foundational lines of research:

*   **Stem-based quantum RNA folding:** Previous work established that grouping individual base pairs into contiguous "stems" drastically reduces the number of binary variables needed to model an RNA structure. This reduction is critical for fitting practical RNA sequences into the limited qubit counts of near-term quantum devices.
*   **Utility-scale quartet encoding:** The concept of decomposing RNA helices into overlapping "quartets" (stacked pairs of base pairs) provides a scalable mechanism for capturing thermodynamic stacking energies locally without requiring complex multi-variable interactions. This project leverages this encoding to analyze scalability limits systematically.
*   **TT2NE:** The TT2NE framework introduced a systematic way to classify and penalize complex topological features like pseudoknots using topological genus. By mapping interlacement graphs to surface genus, this project adapts a rigorous mathematical penalty for crossing structures rather than relying on arbitrary heuristics.
*   **Dirks–Pierce / NUPACK / HotKnots:** These dynamic programming extensions and heuristic models attempted to bridge the gap in classical algorithms for pseudoknot prediction. Their thermodynamic models and limitations provide both the baseline parameters and the exact performance ceiling that our quantum optimization approach seeks to overcome.
*   **NP-hardness of pseudoknot MFE:** The rigorous theoretical proof that predicting the minimum free energy RNA structure with arbitrary pseudoknots is NP-hard justifies the shift away from polynomial-time classical algorithms. It establishes that heuristic or quantum optimization methods are fundamentally necessary for solving the general RNA folding problem.
*   **RNA-As-Graphs:** This representation abstracts RNA secondary structures into mathematical graphs, facilitating the analysis of topologies and loops. It heavily informs our algorithmic approach to crossing-graph generation, candidate validation, and genus computation.
*   **ViennaRNA:** As the gold-standard classical library for RNA bioinformatics, ViennaRNA provides the validated Turner energy parameters and baseline unpseudoknotted MFE predictions. This project relies on ViennaRNA to compute the localized one-body and two-body interaction energies injected into the QUBO model.

***

*Note on Terminology:* In this document and subsequent implementations, the term **"quartet"** explicitly refers to a structural unit consisting of two stacked, adjacent Watson-Crick or wobble base pairs within an RNA helix (e.g., `i` paired with `j`, and `i+1` paired with `j-1`). This must not be confused with a **"G-quartet"** (or G-tetrad), which is a specific planar, square arrangement of four Guanine bases bonded via Hoogsteen hydrogen bonding, commonly found in G-quadruplex structures.

## 1.8 Executive Summary

RNA sequences fold into complex secondary structures driven by base-pair bonding, and predicting these minimum free energy structures from an RNA sequence is a fundamental challenge in computational biology. While many RNA structures form simple nested, tree-like shapes, critical functional RNAs often form "pseudoknots"—interleaved, crossing base-pair patterns that are essential for function but mathematically difficult to predict.

This difficulty arises because classical dynamic programming (DP) algorithms rely on splitting the sequence into independent, non-overlapping sub-intervals. For pseudoknots, the crossing pairs inherently span across these split boundaries, rendering the split-and-combine step structurally invalid. Consequently, predicting the optimal RNA structure with arbitrary pseudoknots is known to be an NP-hard problem, establishing a hard computational limit for classical DP methods.

To overcome this classical bottleneck, this project reformulates RNA folding as a quantum optimization problem. By encoding RNA structural elements as binary variables and mapping their thermodynamic stacking energies and structural exclusivity into a Quadratic Unconstrained Binary Optimization (QUBO) model, the problem is translated into an Ising Hamiltonian. This formulation allows hybrid quantum-classical algorithms, such as VQE and QAOA, to natively explore the complex energy landscape, offering a novel paradigm for resolving NP-hard pseudoknot topologies.
