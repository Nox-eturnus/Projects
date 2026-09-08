# Noise-Robust Quantum Convolutional Neural Network for Quantum Phase and State Classification

[![QCNN Test Suite](https://github.com/Nox-eturnus/Projects/actions/workflows/qcnn-test.yml/badge.svg)](https://github.com/Nox-eturnus/Projects/actions/workflows/qcnn-test.yml)
[![Python 3.11 | 3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](../LICENSE)

An end-to-end research testbed and benchmark studying whether **Quantum Convolutional Neural Networks (QCNNs)** provide an effective inductive bias, parameter-efficiency profile, and noise-robustness envelope for quantum-native many-body phase classification.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Formulation & Many-Body Physics](#2-problem-formulation--many-body-physics)
3. [QCNN Architecture Suite & Primary Model](#3-qcnn-architecture-suite--primary-model)
4. [Inductive Bias & Information-Access Taxonomy](#4-inductive-bias--information-access-taxonomy)
5. [Baselines (Classical, Tensor Network, Quantum)](#5-baselines-classical-tensor-network-quantum)
6. [Simulation & Optimization Framework](#6-simulation--optimization-framework)
7. [Architecture Sweep & Negative Results](#7-architecture-sweep--negative-results)
8. [Noise Robustness & Safe Threshold Evaluation](#8-noise-robustness--safe-threshold-evaluation)
9. [Noise-Aware Training via SPSA Warm-Start](#9-noise-aware-training-via-spsa-warm-start)
10. [Multi-Family Phase Generalization & Crossover Diagnostics](#10-multi-family-phase-generalization--crossover-diagnostics)
11. [Sample Efficiency & Statistical Reliability](#11-sample-efficiency--statistical-reliability)
12. [Device Noise Transfer & Physical Hardware Validation ($N=4$)](#12-device-noise-transfer--physical-hardware-validation-n4)
13. [Reproducibility & Execution Pipeline (Phases 01–21)](#13-reproducibility--execution-pipeline-phases-0121)
14. [Codebase Architecture & File Sitemap](#14-codebase-architecture--file-sitemap)
15. [Scientific Claims Boundary & Non-Advantage Statement](#15-scientific-claims-boundary--non-advantage-statement)

---

## 1. Executive Summary

Quantum Convolutional Neural Networks ([Cong et al., 2019](https://doi.org/10.1038/s41567-019-0648-8)) interleave parameterized two-qubit unitary convolutions with projective or tracing pooling reductions to process quantum states with $O(\log N)$ circuit depth. While QCNN architectures can avoid barren plateaus under specific theoretical assumptions and ansatz conditions, QCNNs deployed on Noisy Intermediate-Scale Quantum (NISQ) devices face severe practical constraints:
- **Expressivity vs. Hardware Depth Trade-Off:** Overly constrained convolution blocks can exhibit insufficient expressivity for particular phase-classification tasks, while expressive unitaries accumulate gate infidelity.
- **Deceptive Zero-Noise Failure Modes:** Standard evaluations measuring degradation thresholds often fail silently when baseline accuracy is already near random guessing ($p \approx 0.5$).
- **Fair Classical Comparisons:** Classical models provided full simulated statevectors (e.g., Matrix Product States) solve an entirely different computational task than quantum models processing direct state preparations.

This repository resolves these methodological pitfalls through:
1. **Primary Architecture:** `expressive_shared_line` with 27 variational parameters across 3 scale-reduction rounds, achieving 100% test accuracy for all three families in the architecture-sweep experiment.
2. **Negative Result Documentation:** Preserving `light_shared_line` (18 parameters) as an explicit negative result illustrating limited block expressivity and architecture-task mismatch.
3. **Sound Robustness Thresholding:** Introducing `evaluate_robustness_threshold` to formally disqualify sweeps where zero-noise performance is below threshold floors or missing entirely.
4. **End-to-End NISQ Pipeline:** Synthetic Pauli/depolarizing channel sweeps, SPSA noise-aware warm-start fine-tuning, device-derived IBM backend noise simulation, and physical execution on IBM Quantum superconducting hardware (`ibm_fez`).

---

## 2. Problem Formulation & Many-Body Physics

The testbed operates on exact ground states $|\psi_0(\lambda)\rangle$ of 1D spin chains across three distinct symmetry and entanglement regimes:

### A. Transverse-Field Ising Model (TFIM)
$$H_{\text{TFIM}} = -J \sum_{i=0}^{N-2} Z_i Z_{i+1} - h \sum_{i=0}^{N-1} X_i$$
- **Parameters:** Open boundary conditions, $J=1.0$, $h \in [0.2, 1.8]$.
- **Thermodynamic Transition:** $h_c = 1.0$.
- **Phases:**
  - $h < 1.0$: Ferromagnetic phase characterized by long-range correlation $\langle Z_0 Z_{N-1} \rangle \to 1$ for finite-size symmetric eigenstates (with spontaneous non-zero magnetization $M_z = \frac{1}{N}\sum_i \langle Z_i \rangle$ emerging only in the thermodynamic symmetry-broken limit).
  - $h > 1.0$: Paramagnetic phase (disordered, symmetric under $X$).

### B. Anisotropic Heisenberg Model (XXZ)
$$H_{\text{XXZ}} = \sum_{i=0}^{N-2} \left( X_i X_{i+1} + Y_i Y_{i+1} + \Delta Z_i Z_{i+1} \right)$$
- **Parameters:** Open boundary conditions, anisotropy $\Delta \in [-0.5, 2.5]$.
- **Thermodynamic Reference:** $\Delta_c = 1.0$.
- **Phases:**
  - $\Delta < 1.0$: Critical / gapless XY phase.
  - $\Delta > 1.0$: Gapped Néel antiferromagnetic order ($\mathbb{Z}_2$ staggered magnetization).

### C. Cluster-Ising Symmetry-Protected Topological (SPT) Chain
$$H_{\text{Cluster}} = -\sum_{i=1}^{N-2} Z_{i-1} X_i Z_{i+1} - h_1 \sum_{i=0}^{N-1} X_i$$
- **Parameters:** Open boundary conditions, 3-body stabilizer interaction, $h_1 \in [0.1, 1.9]$.
- **Thermodynamic Reference:** $h_{1,c} = 1.0$.
- **Phases:**
  - $h_1 < 1.0$: Cluster SPT phase protected by $\mathbb{Z}_2 \times \mathbb{Z}_2$ symmetry (non-local string order parameter).
  - $h_1 > 1.0$: Trivial paramagnetic phase.

Ground states are computed via exact diagonalization (`scipy.sparse.linalg.eigsh`) and mapped into canonical global phase:
$$\langle \psi_0 | \psi_0 \rangle = 1, \quad \text{phase}(\psi_0[\min \{k : |\psi_0[k]| > 10^{-12}\}]) = 0$$

---

## 3. QCNN Architecture Suite & Primary Model

A QCNN for $N = 2^k$ qubits consists of alternating Convolution ($C_m$) and Pooling ($P_m$) layers:

```
Qubit 0 ──[ Conv ]──●──────
          │         │ 
Qubit 1 ──[ Conv ]──X (Sink) ───[ Conv ]──●──────
                                │         │
Qubit 2 ──[ Conv ]──●──────     │         │
          │         │           │         │
Qubit 3 ──[ Conv ]──X (Sink) ───[ Conv ]──X (Sink) ───[ Conv ]──●──────
                                                      │         │
Qubit 4 ──[ Conv ]──●──────                           │         │
          │         │                                 │         │
Qubit 5 ──[ Conv ]──X (Sink) ───[ Conv ]──●──────     │         │
                                │         │           │         │
Qubit 6 ──[ Conv ]──●──────     │         │           │         │
          │         │           │         │           │         │
Qubit 7 ──[ Conv ]──X (Sink) ───[ Conv ]──X (Sink) ───[ Conv ]──X (Sink) ==> Qubit 7 (Readout)
```

In each scale-reduction round, source qubits act as control on sink qubits; source qubits are unmeasured and decoupled, while sink qubits remain active:
- **Round 1 ($8 \to 4$ qubits):** Active $[0, 1, 2, 3, 4, 5, 6, 7] \to$ Sinks $[1, 3, 5, 7]$
- **Round 2 ($4 \to 2$ qubits):** Active $[1, 3, 5, 7] \to$ Sinks $[3, 7]$
- **Round 3 ($2 \to 1$ qubit):** Active $[3, 7] \to$ Sink $[7]$ (Final Readout)

### Convolution Blocks
- **Light Convolution (`conv_kind="light"`, 3 params):**
  $$U_{\text{light}}(\theta_1, \theta_2, \theta_3) = R_Z(\pi/2) \cdot \text{CNOT} \cdot R_Y(\theta_3) \cdot \text{CNOT} \cdot (R_Z(\theta_1) \otimes R_Y(\theta_2)) \cdot \text{CNOT} \cdot R_Z(-\pi/2)$$
- **Expressive Convolution (`conv_kind="expressive"`, 6 params):**
  Uses independent local single-qubit rotations followed by two-qubit entangling interactions:
  $$U_{\text{expressive}}(\vec{\theta}) = R_{ZZ}(\theta_5) \cdot R_{XX}(\theta_4) \cdot \left[ (R_Z(\theta_2) R_Y(\theta_0)) \otimes (R_Z(\theta_3) R_Y(\theta_1)) \right]$$

### Pooling Blocks
- **Controlled Pooling (`_apply_pool`, 3 params):**
  Transfers information from source to sink qubit via:
  $$U_{\text{pool}}(\phi_0, \phi_1, \phi_2) = R_Y(\phi_2)_{\text{sink}} \cdot \text{CNOT}(\text{src} \to \text{sink}) \cdot \left( R_Z(\phi_0)_{\text{src}} \otimes R_Y(\phi_1)_{\text{sink}} \right) \cdot \text{CNOT}(\text{sink} \to \text{src}) \cdot R_Z(-\pi/2)_{\text{sink}}$$
  The source qubit is subsequently unmeasured and discarded, retaining only the sink qubit for downstream stages.

### Architecture Comparison ($N=8$ Qubits)

| Architecture | Conv Kind | Weight Sharing | Topology | Total Parameters | Primary Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`expressive_shared_line`** | **Expressive (6)** | **Shared** | **1D Line** | **27** | **Primary System QCNN** |
| `light_shared_line` | Light (3) | Shared | 1D Line | 18 | Baseline & Negative Result |
| `light_shared_ring` | Light (3) | Shared | 1D Periodic Ring | 18 | Periodic Boundary Baseline |
| `light_unshared_line` | Light (3) | Unshared per pair | 1D Line | 54 | Unshared Light Baseline |

---

## 4. Inductive Bias & Information-Access Taxonomy

A major scientific integrity issue in quantum machine learning literature is comparing quantum circuits directly to classical ML models without declaring **information access**. This repository enforces strict regime labeling:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      INFORMATION ACCESS REGIMES                            │
├────────────────────────┬─────────────────────────┬──────────────────────────┤
│ 1. Quantum State       │ 2. Classical Local      │ 3. Classical Full        │
│    Native Access       │    Observables Map      │    Statevector           │
├────────────────────────┼─────────────────────────┼──────────────────────────┤
│ - QCNN (O(log N) depth)│ - SVM (RBF Kernel)      │ - Matrix Product State   │
│ - VQC (Hardware-eff.)  │ - Multi-Layer Perceptron│   (MPS Tensor Network)   │
│                        │ - 1D Convolutional Net  │                          │
│ Input: Direct physical │ Input: L-point local    │ Input: Full 2^N complex  │
│ state preparation      │ expectations <Z_i>, <X_i│ statevector coefficients │
└────────────────────────┴─────────────────────────┴──────────────────────────┘
```

> **Crucial Rule:** Superior test accuracy of MPS over QCNN is expected because MPS receives the exact $2^N$ state coefficients directly in RAM. Such results must **never** be cited as a "classical victory over quantum advantage."

---

## 5. Baselines (Classical, Tensor Network, Quantum)

1. **Variational Quantum Classifier (VQC):**
   - 2-layer hardware-efficient ansatz using parameterized $R_Y$ and $R_Z$ rotations on every qubit followed by linear CNOT ladders. For $N=8$ and two layers, the ansatz contains 32 variational parameters ($2 \times 8 \times 2$) and reads out the final qubit $q_7$.
2. **Support Vector Machine (SVM):**
   - Radial Basis Function (RBF) kernel trained on five local and bond operator expectation channels (shape $5 \times N$): $X_i$, $Z_i$, $X_i X_{i+1}$, $Z_i Z_{i+1}$, and $Z_{i-1} X_i Z_{i+1}$.
3. **Multi-Layer Perceptron (MLP):**
   - 2 hidden layers (64, 32 units) with ReLU activation, Adam optimizer, and cross-entropy loss trained on the flattened 5-channel observable tensor ($5N$ inputs).
4. **1D Convolutional Neural Network (CNN):**
   - 1D spatial convolutions across the 5 local and bond observable channels with kernel size 3 and max pooling.
5. **Matrix Product State (MPS):**
   - Variational SVD truncation with maximum bond dimension $\chi \in \{4, 8, 16\}$, contracting directly against simulated ground statevectors.

---

## 6. Simulation & Optimization Framework

- **Ideal Objective:** Binary cross-entropy under exact statevector evolution:
  $$\mathcal{L}(\theta) = -\frac{1}{M} \sum_{m=1}^M \left[ y_m \log p_1(\theta; |\psi_m\rangle) + (1 - y_m) \log (1 - p_1(\theta; |\psi_m\rangle)) \right]$$
- **Optimizer:** `scipy.optimize.minimize` with method `COBYLA` (`rhobeg=0.25`, `tol=1e-4`) under the shared adaptive convergence policy: starting budget `max(300, 5 × parameter_count)` with looped continuation toward a ceiling of 1000 evaluations while best-loss window improvement stays active. Plateau detection uses absolute best-loss improvement over consecutive windows; `scipy_optimizer_success`, plateau detection, evaluation-limit, and `convergence_status` (`scipy_converged` / `plateau_converged` / `budget_exhausted_active` / `budget_exhausted_uncertain`) are tracked as separate signals.
- **Stratified Data Splits:** 70% Train, 15% Validation, 15% Test, stratified across Hamiltonian phase labels.

---

## 7. Architecture Sweep & Negative Results

The repository highlights the critical architectural divergence between minimal and expressive QCNNs:

- **`light_shared_line` Failure Mode:** On these datasets, the 3-parameter light convolution exhibits limited block expressivity and an architecture-task mismatch, frequently converging to flat output predictions where $p \approx 0.5$ across all phase states.
- **Structural and Inductive Bias Significance:** The architecture sweep shows that simply increasing parameter count is insufficient: `light_unshared_line` uses 54 parameters but remains substantially weaker than `expressive_shared_line` with 27. This indicates that gate/block structure and inductive bias (e.g., local rotations coupled with $R_{XX}$ and $R_{ZZ}$ entangling generators), rather than total parameter count alone, are essential for these tasks.
- **Optimization Scope:** While the expressive block achieves robust convergence, the exact optimization mechanisms (e.g., whether flat outputs arise from saddle points, landscape traps, or gradient vanishing) are not definitively established by these sweeps.

Documenting `light_shared_line` as an explicit negative result prevents readers from reproducing ineffective ansatz choices while highlighting the role of block-level expressivity over raw parameter count.

---

## 8. Noise Robustness & Safe Threshold Evaluation

Under open-system NISQ dynamics, quantum circuits undergo decoherence and gate errors. We parameterize noise via:
- 1-qubit depolarizing error rate: $p_1 = p_2 / 10$
- 2-qubit depolarizing error rate: $p_2 \in [0.0, 0.08]$
- Measurement readout bit-flip error: $p_{\text{ro}} \in [0.0, 0.03]$

### Robustness Floor & Threshold Formalism
We define operational failure as the lowest tested noise rate where balanced accuracy falls below a strict floor:
$$\text{Balanced Accuracy} < \tau_{\text{floor}} = 0.75$$

```python
# Formal evaluation via qcnn_lab.noise.robustness.evaluate_robustness_threshold
if zero_noise_row_missing:
    status = "zero_noise_baseline_missing"
    robustness_threshold_applicable = False
elif baseline_balanced_accuracy < floor:
    status = "baseline_below_floor"
    robustness_threshold_applicable = False
    first_tested_failure_probability = None
```

> **Why this matters:** When a model fails at zero noise ($p=0.5$), or when zero-noise data is absent, claiming that its "failure threshold is $p_2=0.005$" is mathematically erroneous. The evaluation module explicitly enforces that zero-noise baseline performance must be present and exceed the floor.

---

## 9. Noise-Aware Training via SPSA Warm-Start

To protect circuit parameters against environmental decoherence, we employ Simultaneous Perturbation Stochastic Approximation (SPSA):
$$\hat{g}_k(\theta_k) = \frac{\mathcal{L}(\theta_k + c_k \Delta_k) - \mathcal{L}(\theta_k - c_k \Delta_k)}{2 c_k} \Delta_k^{-1}$$
$$\theta_{k+1} = \theta_k - a_k \hat{g}_k(\theta_k)$$
where $\Delta_k \in \{-1, +1\}^{\dim \theta}$, $a_k = a / (k + 1 + A)^\alpha$, $c_k = c / (k + 1)^\gamma$.

### Warm-Starting from Ideal Optimization
Training SPSA from random initialization in the presence of noise frequently traps the optimizer in noise-induced local minima. By **warm-starting** SPSA with the optimal parameters $\theta^*_{\text{ideal}}$ obtained from ideal COBYLA simulation:
1. Convergence is achieved efficiently within 60 iterations.
2. The model exhibits improved transfer to specific unseen noise regimes (e.g., reaching 1.000 balanced accuracy on `unseen_phase_heavy` compared to 0.917 for the ideal model).
3. Under the controlled 2-qubit depolarizing sweep, noise-aware training does **not** significantly widen the operational failure threshold (both ideal and noise-aware models breach the $\tau=0.75$ floor near $p_2 \approx 0.05$). Characterizing this limitation provides an honest assessment of SPSA noise adaptation.

---

## 10. Multi-Family Phase Generalization & Crossover Diagnostics

We evaluate whether the learned QCNN represents an authentic physical classifier by applying it to continuous transition parameter sweeps across all three models:

```
P(class 1)
   1.0 ┼───────────────────────────────╭────── QCNN Prediction
       │                              ╭╯
   0.5 ┼┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄─●─┄┄┄┄┄┄ Crossover Point (p = 0.5)
       │                           ╭╯
   0.0 ┼───────╮───────────────────╯
       └───┬───┴───┬───┴───┬───┴───┬───┴───┬───
          0.4     0.8     1.0     1.2     1.6   Control Parameter (h or Δ)
                           ▲
                     Critical Point
```

### Transition Crossing Detection
1. **Strict Level Bracketing:** The curve must sample points strictly below $(0.5 - \text{atol})$ and strictly above $(0.5 + \text{atol})$, recorded in `raw_p05_crossing` and `raw_crossing_bracketed`.
2. **Probability Span Condition:** A valid physical transition requires $\Delta p = \max(p) - \min(p) \ge \Delta_{\text{min}}$ (configured via `transition.minimum_probability_span: 0.20` in `configs/project.yaml`). If span validation fails, `validated_p05_crossing` returns `None`.
3. **Finite-Size Warning:** In $N=8$ finite chains, the crossover point typically shifts from the thermodynamic $N \to \infty$ critical value due to finite-size scaling corrections ($h_c(L) - h_c(\infty) \propto L^{-1/\nu}$).

---

## 11. Sample Efficiency & Statistical Reliability

- **Sample Efficiency:** Models are evaluated across training set fractions $\eta \in [0.2, 0.4, 0.6, 0.8, 1.0]$. QCNNs demonstrate high data efficiency, saturating classification performance with as few as 24 labeled quantum states per phase.
- **Repeated Seed Statistics:** The statistical benchmark runs 330 experiments (10 spatial partitions × 5 optimizer seeds for IID and critical holdouts per family, plus 1 canonical spatial block × 10 optimizer seeds for parameter blocks), reporting means with partition-aware hierarchical bootstrap 95% confidence intervals (flat intervals retained as supplementary information). Parameter-block uncertainty is explicitly optimizer-seed variability on one canonical spatial block.

---

## 12. Device Noise Transfer & Physical Hardware Validation ($N=4$)

### Simulation-to-Hardware Transfer
To validate execution on real quantum processors without requiring intractable error mitigation on large depths, we implement an $N=4$ qubit scale-down:
- **Target Backend:** `ibm_fez` (156-qubit Heron r2 processor).
- **Architecture Provenance:** The physical IBM Quantum demonstration used the N=4 `expressive_shared_line` QCNN with 18 trainable parameters. Exact transpiled depth, two-qubit gate count, and logical-to-physical layout were not retained in the original execution artifact and are therefore not reported.
- **Error Mitigation:** Dynamical Decoupling (DD with `XpXm` sequence) and Twirled Readout Error Extrapolation (TREX, resilience level 1).
- **Provenance Isolation:** Real-device hardware runs on `ibm_fez` are preserved with full calibration provenance, while simulation scripts provide side-by-side $N=4$ comparisons between `light_shared_line` and `expressive_shared_line` architectures.

---

## 13. Phased Execution Pipeline

```powershell
# 5. Hardware Scale & Provenance Benchmarking (Phases 14, 16, 18)
.\.venv\Scripts\python.exe scripts/14_prepare_hardware_scale.py
.\.venv\Scripts\python.exe scripts/16_device_noise_transfer.py
.\.venv\Scripts\python.exe scripts/18_sim_to_hardware_gap.py

# 6. Generalization, Statistics & Reporting (Phases 19-21)
.\.venv\Scripts\python.exe scripts/19_transition_generalization.py
.\.venv\Scripts\python.exe scripts/20_repeated_seed_statistics.py
.\.venv\Scripts\python.exe scripts/21_generate_research_report.py

# 7. Advanced Generalization, OOD, Controls & Resource Scaling (Phases 22-30)
.\.venv\Scripts\python.exe scripts/22_build_evaluation_splits.py
.\.venv\Scripts\python.exe scripts/23_multiseed_generalization_benchmark.py --fast
.\.venv\Scripts\python.exe scripts/24_near_critical_ood_benchmark.py
.\.venv\Scripts\python.exe scripts/25_hamiltonian_ood_transfer.py
.\.venv\Scripts\python.exe scripts/26_sanity_and_ablation_suite.py
.\.venv\Scripts\python.exe scripts/27_finite_shot_resource_benchmark.py
.\.venv\Scripts\python.exe scripts/28_input_state_robustness.py
.\.venv\Scripts\python.exe scripts/29_run_expressive_hardware_benchmark.py --mode hardware --backend ibm_fez
.\.venv\Scripts\python.exe scripts/30_generate_generalization_report.py
```

---

## 14. Advanced Generalization & Robustness Suite (Phases 22–30)

Rather than treating a 100% IID test accuracy score as a terminal goal, Phases 22–30 evaluate whether QCNN phase classification survives progressively harder physical distribution shifts, separating architectural inductive bias from memorization and raw parameter count. The evaluation strictly enforces a **fail-closed reporting policy** (`N/A` for unexecuted conditions).

### Primary Evaluation Matrix

<!-- BEGIN AUTO RESULTS: PRIMARY_MATRIX -->
| Evaluation                 | TFIM BA                                           | XXZ BA                        | Cluster BA                    | Runs                      |
|:---------------------------|:--------------------------------------------------|:------------------------------|:------------------------------|:--------------------------|
| IID (Ideal)                | 0.915 ± 0.046 [0.890, 0.942]                      | 0.900 ± 0.054 [0.872, 0.928]  | 0.835 ± 0.069 [0.797, 0.870]  | 50                        |
| Critical-region OOD        | 0.577 ± 0.092 [0.546, 0.613]                      | 0.571 ± 0.088 [0.541, 0.606]  | 0.522 ± 0.079 [0.502, 0.555]  | 50                        |
| Hamiltonian OOD (δ=0.10)   | 0.955 (δ=0.10)                                    | 0.864 (δ=0.10)                | 0.818 (δ=0.10)                | 20                        |
| 1024-shot Readout          | 0.955 ± 0.000                                     | 0.898 ± 0.039                 | 0.891 ± 0.034                 | 20 seeds                  |
| Thermal (T=0.10)           | 0.500                                             | 0.944                         | 1.000                         | 16 points                 |
| Simulated Circuit Noise    | 0.909 (Aer noise model)                           | N/A — experiment not executed | N/A — experiment not executed | 1                         |
| Hardware Progression (N=4) | 10/10 correct [95% CI: 0.692, 1.000] on `ibm_fez` | N/A                           | N/A                           | n = 10 states (1 session) |
<!-- END AUTO RESULTS: PRIMARY_MATRIX -->

### Architectural Ablations & Controls

<!-- BEGIN AUTO RESULTS: ABLATIONS -->
> **Single-Split Reference Evaluations & Controls**
>
| model                            |   parameters |   two_qubit_gates |   iid_ba | critical_ood_ba      | hamiltonian_ood_ba   |
|:---------------------------------|-------------:|------------------:|---------:|:---------------------|:---------------------|
| Full Expressive QCNN             |           27 |                36 |    0.955 | 0.615                | 0.955                |
| No Conv Entanglement             |           21 |                14 |    0.955 | 0.538                | 0.955                |
| No Pool Entanglement             |           27 |                22 |    0.955 | 0.654                | 0.955                |
| No Entanglement Anywhere         |           21 |                 0 |    0.5   | 0.500                | 0.500                |
| No Pooling Ablation              |           18 |                42 |    0.955 | 0.500                | 0.955                |
| Unshared Weights Ablation        |           87 |                36 |    0.955 | 0.500                | 0.955                |
| Untrained QCNN Baseline          |           27 |                36 |    0.5   | 0.500                | 0.500                |
| Shuffled Training Labels Control |           27 |                36 |    0.509 | 0.463                | N/A — not executed   |
| Random Quantum States Control    |           27 |                36 |    0.583 | N/A — not applicable | N/A — not applicable |
| Physics Order Parameter          |            2 |                 0 |    0.955 | 0.538                | 0.955                |

> **Shuffled-Training-Label Control (N=25 runs)**:
> Training on randomly shuffled targets yielded mean true-label test BA 0.509 (empirical comparison p = 0.3462). Measures whether learning scrambled training labels generalizes to genuine ground truth.

> **Fixed-Split Full-Dataset Label Permutation Test (N=199 permutations)**:
> 0/199 permuted statistics equaled or exceeded the observed statistic; +1-corrected Monte-Carlo p = 0.0050 (the resolution floor 0.0050 of this permutation run). Null test BA 0.511 ± 0.102 (95th percentile: 0.676, max: 0.818). Tests the sharp null hypothesis that quantum statevectors and physical phase labels are independent (X indep Y). Global label permutation with original train/validation/test indices reused; split construction is not regenerated under permutation.

> **Multi-Seed Architectural Ablation Aggregate (Repeated Runs)**
>
> Architectural conclusions below are based on the repeated multi-seed aggregate; the preceding table is the canonical single-split reference/control evaluation.
>
| architecture                    |   parameter_count |   two_qubit_gates |   n_runs |   iid_ba_mean |   critical_ood_ba_mean |   hamiltonian_ood_ba_mean |
|:--------------------------------|------------------:|------------------:|---------:|--------------:|-----------------------:|--------------------------:|
| expressive_no_conv_entanglement |                21 |                14 |       10 |         0.927 |                  0.604 |                     0.955 |
| expressive_no_entanglement      |                21 |                 0 |       10 |         0.5   |                  0.5   |                     0.5   |
| expressive_no_pool_entanglement |                27 |                22 |       10 |         0.959 |                  0.704 |                     0.955 |
| expressive_no_pooling           |                18 |                42 |       10 |         0.932 |                  0.515 |                     0.955 |
| expressive_shared_line          |                27 |                36 |       10 |         0.936 |                  0.619 |                     0.955 |
| expressive_unshared_line        |                87 |                36 |       10 |         0.927 |                  0.604 |                     0.955 |

> **Ablation Insight**: Under the repeated adaptive-budget runs with optimizer telemetry, removing pooling entanglers improves mean IID and critical-region performance relative to the full architecture (critical Delta=+0.0846, 95% hierarchical CI [+0.0500, +0.1192], statistically resolved), while the effect of removing convolutional entanglement remains unresolved (critical Delta=-0.0154, 95% hierarchical CI [-0.0615, +0.0308]). Removing all entanglement collapses performance to chance, and removing the pooling hierarchy strongly reduces critical-region generalization. These results should be interpreted alongside the recorded optimizer-termination diagnostics.
<!-- END AUTO RESULTS: ABLATIONS -->

### Classical Measurement-Budget Comparator

<!-- BEGIN AUTO RESULTS: BUDGET -->
| Budget ($B$) | Family | QCNN Mean BA | Classical Pauli Mean BA | Settings |
| :---: | :---: | :---: | :---: | :---: |
| 128 | TFIM | 0.957 ± 0.027 | 0.952 ± 0.018 | 2 bases |
| 512 | TFIM | 0.955 ± 0.000 | 0.955 ± 0.000 | 2 bases |
| 2048 | TFIM | 0.955 ± 0.000 | 0.955 ± 0.000 | 2 bases |
| 4096 | TFIM | 0.955 ± 0.000 | 0.955 ± 0.000 | 2 bases |
| 128 | XXZ | 0.893 ± 0.050 | 0.916 ± 0.054 | 2 bases |
| 512 | XXZ | 0.893 ± 0.034 | 0.955 ± 0.026 | 2 bases |
| 2048 | XXZ | 0.884 ± 0.023 | 0.961 ± 0.027 | 2 bases |
| 4096 | XXZ | 0.884 ± 0.027 | 0.961 ± 0.027 | 2 bases |
| 128 | CLUSTER | 0.870 ± 0.054 | 0.952 ± 0.010 | 2 bases |
| 512 | CLUSTER | 0.882 ± 0.045 | 0.955 ± 0.000 | 2 bases |
| 2048 | CLUSTER | 0.902 ± 0.037 | 0.955 ± 0.000 | 2 bases |
| 4096 | CLUSTER | 0.907 ± 0.027 | 0.955 ± 0.000 | 2 bases |
<!-- END AUTO RESULTS: BUDGET -->

### Physical IBM Hardware Execution & Uncertainty

<!-- BEGIN AUTO RESULTS: HARDWARE -->
- **Observed Result**: **10/10** held-out N=4 TFIM test states correctly classified on `ibm_fez`.
- **Exact Binomial Uncertainty**: 95% Clopper-Pearson CI = **[0.692, 1.000]**.
- **QPU Job Provenance**: Raw Job ID `dafdv05nj4cs73ag8e5g`, Mitigated Job ID `dafdv2t1ierc738n8c6g`.
- **Execution Protocol**: Twirled Readout Error Extrapolation (TREX, resilience level 1) + Dynamical Decoupling (`XpXm`).
- **Demonstration Architecture**: N=4 `expressive_shared_line` QCNN with 18 trainable parameters. Exact transpiled depth, two-qubit gate count, and logical-to-physical layout were not retained in the original execution artifact and are therefore not reported (stored as null).
- **Multi-Session Status**: Single physical session complete (`multi_session_hardware_complete = false`); multi-session stability tracking across distinct calibration windows is pending.
<!-- END AUTO RESULTS: HARDWARE -->

### Key Experimental Discoveries

<!-- BEGIN AUTO RESULTS: KEY_DISCOVERIES -->
1. **Near-Critical Crossover & Family Boundaries:** TFIM displays clear distance-dependent generalization (critical-region BA = 0.577) and a bracketed finite-size crossover, while critical-region distribution shift severely disrupts the fixed decision boundary and probability calibration for XXZ (BA = 0.571) and Cluster (BA = 0.522), even though rank discrimination remains unexpectedly strong (ROC-AUC ≈ 1.0). Validation-only thresholding does not consistently recover the lost fixed-threshold performance.
2. **Hamiltonian Perturbation Generalization:** Models trained purely at zero disorder maintain high balanced accuracy under disordered TFIM and symmetry-preserving Cluster/XXZ deformations up to δ = 0.20 under nominal phase boundaries, accompanied by tracked spectral gaps and state fidelities.
3. **Ablation & Control Proving Ground:**
   - **Haar Random States**: Negative sanity control consistent with chance-level generalization (BA ≈ 0.583); no evidence of meaningful phase-label structure and no obvious label leakage.
   - **Untrained QCNN Baseline**: Random parameter initializations evaluate the inductive bias floor without optimization.
   - **Shuffled-Training-Label Control**: Training on randomly shuffled targets yielded mean true-label test BA 0.509 (empirical comparison p ≈ 0.3462).
   - **Fixed-Split Label-Permutation Test (N=199)**: 0/199 permuted statistics equaled or exceeded the observed statistic; +1-corrected Monte-Carlo p = 0.0050, the resolution floor of this permutation run.
   - **Entanglement Inductive Bias**: Full critical BA ≈ 0.619; no-conv-entanglement Δ = -0.0154 95% CI [-0.0615, +0.0308] (unresolved); no-pool-entanglement Δ = +0.0846 95% CI [+0.0500, +0.1192] (resolved improvement); no-pool-entanglement critical BA ≈ 0.704 exceeds full. Removing all entanglement collapses to chance; removing the pooling hierarchy strongly reduces critical-region generalization. Interpret alongside the recorded optimizer-termination diagnostics.
4. **Finite-Shot Budgets with Commuting Pauli Observables:** Under matched inference state-copy budgets, the QCNN shows a slightly higher mean BA than the two-observable classical comparator only for low-budget TFIM, while the physics-informed classical comparator outperforms it across the tested XXZ and Cluster budgets. This matches inference measurement resources, not total training resources (the classical model is trained using exact expectation values).
5. **Physical IBM Hardware Session:** Observed 10/10 correct classifications on a held-out N=4 TFIM test subset during one `ibm_fez` hardware session (95% Clopper-Pearson CI: [0.692, 1.000]). Multi-session calibration tracking across distinct cooling windows is pending. Exact transpiled depth, two-qubit counts, and layout were not retained and are not reported.
<!-- END AUTO RESULTS: KEY_DISCOVERIES -->


---

## 15. Codebase Architecture & File Sitemap

```
noise-robust-qcnn-phase-classification/
├── configs/
│   ├── project.yaml                # Primary project configuration (expressive QCNN)
│   ├── noise.yaml                  # Synthetic & realistic noise channel definitions
│   └── evaluation.yaml             # Split seeds, OOD intervals, and bootstrap settings (Phase 22)
├── data/
│   ├── raw/                        # Ground state raw vectors
│   └── processed/                  # Normalized datasets, evaluation pools & metadata
├── qcnn_lab/
│   ├── analysis/
│   │   ├── calibration.py          # Brier score, ECE, NLL & reliability curves (Phase 23)
│   │   ├── critical_generalization.py # Distance binning & crossover analysis (Phase 24)
│   │   ├── splits.py               # Disjoint IID, block & critical split manifests (Phase 22)
│   │   ├── statistics.py           # Bootstrap confidence intervals & aggregations (Phase 23)
│   │   └── transition.py           # Robust crossing detection & slope analysis
│   ├── baselines/                  # Classical, features, and MPS models
│   ├── hardware/                   # IBM Runtime EstimatorV2 & circuit transpilation
│   ├── noise/
│   │   ├── state_preparation.py    # Decoupled state-prep noise channels (Phase 28)
│   │   ├── evaluate.py             # Aer noisy circuit simulation
│   │   ├── models.py               # Depolarizing & thermal relaxation noise models
│   │   └── robustness.py           # Strict floor & threshold evaluation helper
│   ├── physics/
│   │   ├── perturbations.py        # TFIM disorder & symmetry-preserving Hamiltonians (Phase 25)
│   │   ├── thermal_states.py       # Gibbs density matrices & spectral evaluation (Phase 28)
│   │   ├── hamiltonians.py         # TFIM, XXZ, and Cluster-Ising sparse matrices
│   │   ├── states.py               # Canonical phase alignment & endian conversion
│   │   └── datasets.py             # Labeled phase generation & state serialization
│   └── qcnn/
│       ├── ablations.py            # Sanity controls & physics-informed order baselines (Phase 26)
│       ├── finite_shots.py         # Binomial sampling & budget-matched allocation (Phase 27)
│       ├── architecture.py         # Param counts, ablation variants & unitaries
│       ├── evaluate.py             # Exact statevector prediction & BCE loss
│       └── train.py                # COBYLA trainer & explicit manifest training
├── results/
│   ├── ablations/                  # Ablation summary & physics baseline comparisons
│   ├── evaluation_splits/          # Explicit CSV split manifests across seeds (Phase 22)
│   ├── figures/                    # 12 publication-ready PNG figures
│   ├── finite_shots/               # Shot scaling & budget-matched metrics
│   ├── hamiltonian_ood/            # Microscopic deformation transfer data
│   ├── near_critical/              # Dense grid predictions & crossover estimates
│   ├── report/                     # Master generalization report & evaluation matrix
│   ├── statistical_generalization/ # 330-run logs, hierarchical CIs, threshold diagnostics, and calibration curves
│   └── thermal_and_prep/           # Temperature sweeps & 2x2 noise factorization
├── scripts/                        # Phased reproducible runner scripts (00-32)
├── tests/                          # Pytest suite (unit + behavioral + research-freeze regression tests)
├── pyproject.toml                  # Package configuration & dependencies
└── README.md                       # Master research documentation
```

---

## 16. Scientific Claims Boundary & Non-Advantage Statement

To maintain rigorous scientific standards, this project explicitly affirms:

1. **No Generic Quantum Advantage:** We do **not** claim quantum advantage over classical computation. Classical algorithms running on classical observable data or tensor networks can efficiently classify 1D ground states for moderate system sizes.
2. **Inductive Bias Characterization:** The goal of this research is to evaluate whether logarithmic-depth QCNNs represent a compact, learnable inductive bias for quantum states when presented directly on quantum hardware.
3. **Hardware Scale Scope:** The $N=4$ IBM Quantum demonstration validates transpilation feasibility, dynamical decoupling efficacy, and mitigation benefits; it does not claim NISQ utility for unconstrained macroscopic systems.
4. **Transparent Negative Results:** Structural limitations of lightweight architectures (such as `light_shared_line` and ablation variants lacking entanglers or pooling) are published openly to prevent silent failure modes in quantum machine learning workflows.