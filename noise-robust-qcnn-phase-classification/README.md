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

Quantum Convolutional Neural Networks ([Cong et al., 2019](https://doi.org/10.1038/s41567-019-0648-8)) interleave parameterized two-qubit unitary convolutions with projective or tracing pooling reductions to process quantum states with $O(\log N)$ circuit depth. While theoretically immune to barren plateaus under appropriate ansatz conditions, QCNNs deployed on Noisy Intermediate-Scale Quantum (NISQ) devices face severe practical constraints:
- **Expressivity vs. Hardware Depth Trade-Off:** Overly constrained parameter-sharing (e.g. 3-parameter convolutions) can under-fit non-entangled product states, while expressive unitaries accumulate gate infidelity.
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
   - 2-layer hardware-efficient ansatz using alternating $R_Y(\theta)$ and linear CNOT ladders ($2 \times 8 = 16$ single-qubit params + CNOTs) measuring $\langle Z_0 \rangle$.
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
- **Optimizer:** `scipy.optimize.minimize` with method `COBYLA` (`rhobeg=0.25`, `tol=1e-4`, maxiter up to 120).
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
- **Repeated Seed Statistics:** Training is repeated across 5 independent PRNG seeds ($12345, 12346, 12347, 12348, 12349$), reporting mean, standard deviation, and bounded 95% confidence intervals (clipped to $[0, 1]$ for probability/accuracy metrics).

---

## 12. Device Noise Transfer & Physical Hardware Validation ($N=4$)

### Simulation-to-Hardware Transfer
To validate execution on real quantum processors without requiring intractable error mitigation on large depths, we implement an $N=4$ qubit scale-down:
- **Target Backend:** `ibm_fez` (156-qubit Heron r2 processor).
- **Architecture Provenance:** The physical hardware demonstration explicitly executes the `light_shared_line` ansatz ($N=4$, depth $\approx 119$, 38 CNOTs) under IBM Runtime `EstimatorV2`.
- **Error Mitigation:** Dynamical Decoupling (DD with `XpXm` sequence) and Twirled Readout Error Extrapolation (TREX, resilience level 1).
- **Provenance Isolation:** Real-device hardware runs on `ibm_fez` are preserved with full calibration provenance, while simulation scripts provide side-by-side $N=4$ comparisons between `light_shared_line` and `expressive_shared_line`.

---

## 13. Reproducibility & Execution Pipeline (Phases 01–21)

The entire project is structured into deterministic, self-contained sequential phases:

```powershell
# 1. Environment & Pre-requisites
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pytest -v

# 2. Physics & Data Generation (Phases 01-05)
.\.venv\Scripts\python.exe scripts/01_verify_environment.py
.\.venv\Scripts\python.exe scripts/02_generate_ground_states.py
.\.venv\Scripts\python.exe scripts/03_build_qcnn_circuits.py
.\.venv\Scripts\python.exe scripts/04_classical_baselines.py
.\.venv\Scripts\python.exe scripts/05_vqc_baseline.py

# 3. Primary Training & Architecture Sweeps (Phases 06-09)
.\.venv\Scripts\python.exe scripts/06_train_ideal_tfim.py
.\.venv\Scripts\python.exe scripts/07_architecture_sweep.py
.\.venv\Scripts\python.exe scripts/08_mps_tensor_network.py
.\.venv\Scripts\python.exe scripts/09_sample_efficiency_sweep.py

# 4. Noise Robustness & Noise-Aware Training (Phases 10-13)
.\.venv\Scripts\python.exe scripts/10_validate_noise_models.py
.\.venv\Scripts\python.exe scripts/11_noise_robustness_sweep.py
.\.venv\Scripts\python.exe scripts/12_train_noise_aware.py
.\.venv\Scripts\python.exe scripts/13_unseen_noise_transfer.py

# 5. Hardware Scale & Provenance Benchmarking (Phases 14, 16, 18)
.\.venv\Scripts\python.exe scripts/14_prepare_hardware_scale.py
.\.venv\Scripts\python.exe scripts/16_device_noise_transfer.py
.\.venv\Scripts\python.exe scripts/18_sim_to_hardware_gap.py

# 6. Generalization, Statistics & Reporting (Phases 19-21)
.\.venv\Scripts\python.exe scripts/19_transition_generalization.py
.\.venv\Scripts\python.exe scripts/20_repeated_seed_statistics.py
.\.venv\Scripts\python.exe scripts/21_generate_research_report.py
```

---

## 14. Codebase Architecture & File Sitemap

```
Projects/
├── .github/workflows/
│   └── qcnn-test.yml               # Monorepo root CI workflow for QCNN test suite
└── noise-robust-qcnn-phase-classification/
├── configs/
│   ├── project.yaml                # Primary project configuration (expressive QCNN)
│   └── noise.yaml                  # Synthetic & realistic noise channel definitions
├── data/
│   ├── raw/                        # Ground state raw vectors
│   └── processed/                  # Normalized datasets & Hamiltonian metadata
├── qcnn_lab/
│   ├── analysis/
│   │   └── transition.py           # Robust crossing detection & slope analysis
│   ├── baselines/
│   │   ├── classical.py            # SVM, MLP, and 1D CNN observable models
│   │   ├── mps.py                  # Matrix Product State tensor network model
│   │   └── vqc.py                  # Standard Hardware-Efficient VQC baseline
│   ├── hardware/
│   │   └── ibm.py                  # IBM Runtime EstimatorV2 interface & error mitigation
│   ├── metrics/
│   │   └── classification.py       # Accuracy, balanced accuracy, F1, AUC, ECE
│   ├── noise/
│   │   ├── evaluate.py             # Aer noisy circuit simulation
│   │   ├── models.py               # Depolarizing & thermal relaxation noise models
│   │   ├── robustness.py           # Strict floor & threshold evaluation helper
│   │   └── train.py                # Warm-started SPSA noise-aware trainer
│   ├── physics/
│   │   ├── hamiltonians.py         # TFIM, XXZ, and Cluster-Ising sparse matrices
│   │   ├── states.py               # Canonical phase alignment & Qiskit endian conversion
│   │   └── datasets.py             # Labeled phase generation & state serialization
│   └── qcnn/
│       ├── architecture.py         # Param counts, convolution/pooling unitaries
│       ├── evaluate.py             # Exact statevector prediction & BCE loss
│       └── train.py                # COBYLA optimizer & stratified split engine
├── results/
│   ├── architectures/              # Architecture sweep CSVs
│   ├── baselines/                  # Classical & VQC benchmark outputs
│   ├── figures/                    # Transition curves & loss dynamics plots
│   ├── generalization/             # Multi-family crossing diagnostic results
│   ├── hardware/                   # N=4 hardware executions, jobs, and comparisons
│   ├── ideal/                      # Primary expressive QCNN trained weights & history
│   ├── noise/                      # Robustness sweeps & noise-aware checkpoints
│   ├── report/                     # Automated Markdown research report
│   └── statistics/                 # Seed statistics & sample efficiency data
├── scripts/                        # Phased reproducible runner scripts (01-21)
├── tests/                          # Pytest verification suite (26 unit tests)
├── pyproject.toml                  # Package configuration & dependencies
└── README.md                       # Master research documentation
```

---

## 15. Scientific Claims Boundary & Non-Advantage Statement

To maintain rigorous scientific standards, this project explicitly affirms:

1. **No Generic Quantum Advantage:** We do **not** claim quantum advantage over classical computation. Classical algorithms running on classical observable data or tensor networks can efficiently classify 1D ground states for moderate system sizes.
2. **Inductive Bias Characterization:** The goal of this research is to evaluate whether logarithmic-depth QCNNs represent a compact, learnable inductive bias for quantum states when presented directly on quantum hardware.
3. **Hardware Scale Scope:** The $N=4$ IBM Quantum demonstration validates transpilation feasibility, dynamical decoupling efficacy, and mitigation benefits; it does not claim NISQ utility for unconstrained macroscopic systems.
4. **Transparent Negative Results:** Structural limitations of lightweight architectures (such as `light_shared_line`) are published openly to prevent silent failure modes in quantum machine learning workflows.