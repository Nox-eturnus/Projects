# mRNA Quantum Folding

Quantum optimization for RNA secondary structure prediction, including the
**NP-hard pseudoknot MFE problem**. This pipeline maps RNA folding onto
QUBO/Ising Hamiltonians and solves them with VQE, QAOA, and classical
baselines (Simulated Annealing, Simulated Bifurcation Machine).

Both **Target A** (nested, pseudoknot-free) and **Target B** (pseudoknotted)
RNA structures are tested. While nested structures can be solved in polynomial
time by classical dynamic programming (Nussinov/Zuker), the general
pseudoknot-inclusive MFE prediction is NP-hard — this is the scientific
motivation for the quantum optimization approach.

## Setup

### Requirements

- Python 3.10+
- [ViennaRNA](https://www.tbi.univie.ac.at/RNA/) (provides the `RNA` Python module)
- NVIDIA GPU (optional, for SBM acceleration via PyTorch CUDA)

### Installation

```bash
python -m venv .venv
# Activate virtual environment:
#   Windows: .venv\Scripts\activate
#   Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
```

> **Note:** ViennaRNA must be installed separately. On conda:
> `conda install -c bioconda viennarna`. On pip (if a wheel is available):
> `pip install ViennaRNA`.

## Pipeline Stages

The pipeline follows this sequence:

```
Data → Encoding → QUBO → Genus Penalty → Classical Baseline →
Quantum Optimization → Noise Study → Classical Benchmarks → Evaluation → Plots
```

| Stage | Module | Description |
|-------|--------|-------------|
| **Data** | `data_loader.py` | Build Target A (nested), Target B (pseudoknotted), and FSE datasets |
| **Encoding** | `candidates.py`, `stems.py`, `quartets.py` | Generate pair/stem/quartet candidate sets |
| **QUBO** | `qubo.py` | Construct QUBO matrix with ViennaRNA Turner-model energies |
| **Genus Penalty** | `genus.py`, `genus_penalty.py` | Topological crossing penalty (μ* = −0.25) |
| **Classical Baseline** | `classical_solvers.py` | OR-Tools CP-SAT exact solver + ViennaRNA MFE |
| **Quantum Optimization** | `quantum_circuits.py`, `ideal_sweep.py` | VQE & QAOA statevector sweep (20 seeds × 6 configs) |
| **Noise Study** | `noisy_sweep.py` | Depolarizing noise sweep + crossover analysis |
| **Classical Benchmarks** | `classical_benchmarks.py` | Simulated Annealing & Simulated Bifurcation Machine |
| **Evaluation** | `evaluate.py` | Multi-tier metrics: Tier 1 (energy), Tier 2a (QUBO quality), Tier 2b (structural accuracy) |
| **Plots** | `plots.py` | Scaling, wall-clock, and headline accuracy charts |

## Quick Start

```bash
# Run the full pipeline (skips instances with existing results)
python run_pipeline.py

# Force re-run everything
python run_pipeline.py --force

# Run with validation (test suite + Target B coverage check)
python run_pipeline.py --validate

# Override qubit ceiling
python run_pipeline.py --max-qubits 12

# Minimal output
python run_pipeline.py --quiet
```

## Results

Results are stored in:

| File | Content |
|------|---------|
| `data/evaluation_results.json` | Tier 1/2a/2b performance metrics |
| `data/ideal_sweep_results.json` | VQE/QAOA ideal statevector results |
| `data/noisy_sweep_results.json` | Noisy simulator results |
| `data/crossover_analysis.json` | VQE/QAOA noise crossover points |
| `data/classical_benchmarks_results.json` | SA/SBM benchmark results |
| `data/mu_star.json` | Calibrated genus penalty (μ* = −0.25) |
| `plots/plot1_scaling.png` | Sequence length vs. qubit count |
| `plots/plot2_wallclock.png` | Wall-clock scaling per method |
| `plots/plot3_tier2b_headline.png` | Sensitivity/PPV/MCC bar chart |
| `plots/plot4_energy_gap_heatmap.png` | Energy gap heatmap |
| `plots/scalability_report.md` | Written scalability analysis |

## Validation

```bash
# Run the full test suite
pytest tests/ -v

# Or use the pipeline's built-in validation
python run_pipeline.py --validate
```

The validation checks:
- All module imports resolve correctly
- Genus = 0 for Target A, genus ≥ 1 for Target B
- QUBO→Ising energy identity holds
- VQE/QAOA converge to exact ground energy
- All 5 Target B instances appear in evaluation results

## Key Findings

1. **Genus Penalty Calibration:** μ* = −0.25 achieves 100% classification
   accuracy on the calibration set, correctly penalizing unwanted crossings
   without suppressing biologically correct pseudoknots.

2. **Headline Accuracy (Tier 2b):**
   - **VQE** (reps=1): Sensitivity 0.71, PPV 0.70, MCC 0.69
   - **SA**: Matches exact solver (Sensitivity 0.79, MCC 0.76)
   - **QAOA** (X mixer, p=1): Sensitivity 0.47, MCC 0.43

3. **Stem Encoding:** 3–5× qubit reduction vs. pair-level encoding,
   enabling 15–19 qubit pseudoknotted instances within NISQ constraints.

4. **Target A vs Target B:** Both nested and pseudoknotted structures
   are processed through the same unified pipeline, demonstrating that the
   QUBO formulation with genus penalty handles the NP-hard case.

## Project Structure

```
├── run_pipeline.py           # Unified entry point
├── data_loader.py            # Dataset compilation (Target A/B/FSE)
├── candidates.py             # Pair-level candidate generation
├── stems.py                  # Stem-level candidate generation
├── quartets.py               # Quartet-level candidate generation
├── genus.py                  # Topological genus computation
├── genus_penalty.py          # μ-sweep calibration
├── qubo.py                   # QUBO matrix construction
├── ising.py                  # QUBO → Ising mapping
├── classical_solvers.py      # CP-SAT exact solver + ViennaRNA
├── quantum_circuits.py       # VQE/QAOA circuit construction
├── ideal_sweep.py            # Ideal statevector sweep
├── noisy_sweep.py            # Noisy simulator experiments
├── classical_benchmarks.py   # SA/SBM baselines
├── evaluate.py               # Multi-tier performance evaluation
├── plots.py                  # Scalability analysis & plotting
├── data/                     # Datasets + result JSONs
├── plots/                    # Generated plots + scalability report
├── tests/                    # Validation test suite
├── Literature_Review.md      # Background & literature review
├── presentation.md           # Presentation deck (Marp-compatible)
└── requirements.txt          # Python dependencies
```

## License

This project was developed as part of an academic study on quantum
optimization for RNA structure prediction.
