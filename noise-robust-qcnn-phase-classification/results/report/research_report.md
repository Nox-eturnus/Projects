# Noise-Robust QCNN for Quantum Phase and State Classification — Research Report

### Architecture & Provenance Summary
- **Primary N=8 QCNN Architecture:** `expressive_shared_line` (27 variational parameters across 3 scale-reduction rounds).
- **Baseline / Negative Result Architecture:** `light_shared_line` (18 variational parameters; demonstrated limited block expressivity / architecture-task mismatch across the evaluated phase-classification tasks).
- **Physical Hardware Demonstration Architecture:** `light_shared_line` executed at $N=4$ qubits on `ibm_fez` (retaining valid real-device calibration and proof-of-hardware execution).

## Claim boundary

This repository studies whether a QCNN provides a useful **inductive bias, parameter-efficiency profile, and noise-robustness envelope** for quantum-native state classification. It does **not** claim generic quantum advantage over classical machine learning.

Classical baselines are labelled by information access. In particular, the MPS prototype receives the full simulated statevector, whereas SVM/MLP/CNN baselines receive local observable maps. Those results must not be collapsed into an information-access-blind leaderboard.

## Multi-family phase classification and transition generalization

| family   | architecture           |   accuracy |   balanced_accuracy |   raw_p05_crossing | raw_crossing_bracketed   | transition_detected   |   validated_p05_crossing |   probability_span |   qcnn_steepest_change |   physical_diagnostic_steepest_change |   thermodynamic_reference_critical |
|:---------|:-----------------------|-----------:|--------------------:|-------------------:|:-------------------------|:----------------------|-------------------------:|-------------------:|-----------------------:|--------------------------------------:|-----------------------------------:|
| tfim     | expressive_shared_line |   1        |            1        |           0.847456 | True                     | True                  |                 0.847456 |          0.237475  |                  0.64  |                                  0.7  |                                  1 |
| xxz      | expressive_shared_line |   0.923077 |            0.916667 |         nan        | False                    | False                 |               nan        |          0.0949738 |                  0.685 |                                  1.45 |                                  1 |
| cluster  | expressive_shared_line |   0.923077 |            0.916667 |           0.589024 | True                     | True                  |                 0.589024 |          0.262235  |                  0.58  |                                  0.61 |                                  1 |

For finite systems, the learned or diagnostic crossover need not equal the thermodynamic-limit critical point. The transition sweep is therefore a **generalization/crossover diagnostic**, not a finite-size proof of an exact critical point.

## Architecture trade-offs

| family   | architecture           |   parameters |   depth |   two_qubit_operations |   accuracy |   balanced_accuracy |   training_seconds |
|:---------|:-----------------------|-------------:|--------:|-----------------------:|-----------:|--------------------:|-------------------:|
| tfim     | light_shared_line      |           18 |      47 |                     47 |   0.538462 |            0.535714 |            44.1384 |
| tfim     | light_shared_ring      |           18 |      49 |                     53 |   0.769231 |            0.77381  |            41.8309 |
| tfim     | expressive_shared_line |           27 |      35 |                     36 |   1        |            1        |            41.9894 |
| tfim     | light_unshared_line    |           54 |      47 |                     47 |   0.538462 |            0.559524 |            20.2056 |
| xxz      | light_shared_line      |           18 |      47 |                     47 |   0.461538 |            0.464286 |            41.1956 |
| xxz      | light_shared_ring      |           18 |      49 |                     53 |   0.692308 |            0.678571 |            49.243  |
| xxz      | expressive_shared_line |           27 |      35 |                     36 |   1        |            1        |            37.7875 |
| xxz      | light_unshared_line    |           54 |      47 |                     47 |   0.384615 |            0.380952 |            30.122  |
| cluster  | light_shared_line      |           18 |      47 |                     47 |   0.461538 |            0.440476 |            43.9622 |
| cluster  | light_shared_ring      |           18 |      49 |                     53 |   0.461538 |            0.452381 |            50.4175 |
| cluster  | expressive_shared_line |           27 |      35 |                     36 |   1        |            1        |            44.3318 |
| cluster  | light_unshared_line    |           54 |      47 |                     47 |   0.615385 |            0.595238 |            42.1958 |

## Quantum baseline

| family   | model                  | access_regime        |   training_seconds |   parameters |   depth |   two_qubit_operations |   output_qubit |   accuracy |   balanced_accuracy |   f1 |   roc_auc |   log_loss |
|:---------|:-----------------------|:---------------------|-------------------:|-------------:|--------:|-----------------------:|---------------:|-----------:|--------------------:|-----:|----------:|-----------:|
| tfim     | hardware_efficient_vqc | direct_quantum_state |            5.05819 |           32 |      13 |                     14 |              7 |   0.461538 |                 0.5 |    0 |         1 |   0.436469 |
| xxz      | hardware_efficient_vqc | direct_quantum_state |            4.93815 |           32 |      13 |                     14 |              7 |   1        |                 1   |    1 |         1 |   0.588469 |
| cluster  | hardware_efficient_vqc | direct_quantum_state |            4.9088  |           32 |      13 |                     14 |              7 |   1        |                 1   |    1 |         1 |   0.497942 |

## Classical baselines

| family   | model              | access_regime              | complexity_name      |   model_complexity |   training_seconds |   accuracy |   balanced_accuracy |       f1 |   roc_auc |    log_loss |
|:---------|:-------------------|:---------------------------|:---------------------|-------------------:|-------------------:|-----------:|--------------------:|---------:|----------:|------------:|
| tfim     | svm_rbf            | local_observable_map       | support_vectors      |                 11 |          0.0109771 |   1        |            1        | 1        |         1 | 0.0453224   |
| tfim     | mlp                | local_observable_map       | trainable_parameters |               4737 |          0.0108591 |   0.923077 |            0.916667 | 0.933333 |         1 | 0.503913    |
| tfim     | classical_cnn_1d   | local_observable_map       | trainable_parameters |               1057 |          1.67976   |   1        |            1        | 1        |         1 | 1.05394e-05 |
| tfim     | mps_prototype_chi8 | full_simulated_statevector | max_bond_dimension   |                  8 |          0.0070408 |   1        |            1        | 1        |         1 | 0.290304    |
| xxz      | svm_rbf            | local_observable_map       | support_vectors      |                 17 |          0.0021772 |   1        |            1        | 1        |         1 | 0.0306227   |
| xxz      | mlp                | local_observable_map       | trainable_parameters |               4737 |          0.021889  |   0.846154 |            0.857143 | 0.833333 |         1 | 0.6162      |
| xxz      | classical_cnn_1d   | local_observable_map       | trainable_parameters |               1057 |          0.582115  |   1        |            1        | 1        |         1 | 9.99152e-05 |
| xxz      | mps_prototype_chi8 | full_simulated_statevector | max_bond_dimension   |                  8 |          0.0017832 |   1        |            1        | 1        |         1 | 0.639289    |
| cluster  | svm_rbf            | local_observable_map       | support_vectors      |                 15 |          0.0026208 |   1        |            1        | 1        |         1 | 0.0723798   |
| cluster  | mlp                | local_observable_map       | trainable_parameters |               4737 |          0.0244744 |   1        |            1        | 1        |         1 | 0.280267    |
| cluster  | classical_cnn_1d   | local_observable_map       | trainable_parameters |               1057 |          0.207245  |   1        |            1        | 1        |         1 | 8.16734e-05 |
| cluster  | mps_prototype_chi8 | full_simulated_statevector | max_bond_dimension   |                  8 |          0.0015091 |   1        |            1        | 1        |         1 | 0.380895    |

## Sample-efficiency / training-data regime

| model   |   samples_per_class |   accuracy_mean |   accuracy_std |   balanced_accuracy_mean |   training_seconds_mean |
|:--------|--------------------:|----------------:|---------------:|-------------------------:|------------------------:|
| qcnn    |                   4 |        1        |      0         |                 1        |              6.6163     |
| qcnn    |                   8 |        1        |      0         |                 1        |             12.413      |
| qcnn    |                  16 |        1        |      0         |                 1        |             21.7226     |
| qcnn    |                  24 |        1        |      0         |                 1        |             35.7267     |
| svm_rbf |                   4 |        0.948718 |      0.0888231 |                 0.944444 |              0.0162022  |
| svm_rbf |                   8 |        1        |      0         |                 1        |              0.00301813 |
| svm_rbf |                  16 |        1        |      0         |                 1        |              0.00315333 |
| svm_rbf |                  24 |        1        |      0         |                 1        |              0.00379693 |

## Noise robustness of ideal-trained QCNN

| profile              | sweep_kind             |   depolarizing_2q |   accuracy |   balanced_accuracy |       f1 |   roc_auc |   log_loss |
|:---------------------|:-----------------------|------------------:|-----------:|--------------------:|---------:|----------:|-----------:|
| mild_depolarizing    | named_profile          |             0.008 |   1        |            1        | 1        |  1        |   0.524787 |
| mixed_training_a     | named_profile          |             0.012 |   1        |            1        | 1        |  1        |   0.563288 |
| mixed_training_b     | named_profile          |             0.02  |   1        |            1        | 1        |  1        |   0.609827 |
| unseen_phase_heavy   | named_profile          |             0.01  |   1        |            1        | 1        |  1        |   0.597862 |
| unseen_readout_heavy | named_profile          |             0.01  |   1        |            1        | 1        |  1        |   0.55244  |
| depol2_0.0           | two_qubit_depolarizing |             0     |   1        |            1        | 1        |  1        |   0.455041 |
| depol2_0.005         | two_qubit_depolarizing |             0.005 |   1        |            1        | 1        |  1        |   0.500167 |
| depol2_0.01          | two_qubit_depolarizing |             0.01  |   1        |            1        | 1        |  1        |   0.521352 |
| depol2_0.02          | two_qubit_depolarizing |             0.02  |   1        |            1        | 1        |  1        |   0.564855 |
| depol2_0.04          | two_qubit_depolarizing |             0.04  |   0.846154 |            0.833333 | 0.875    |  0.97619  |   0.623658 |
| depol2_0.08          | two_qubit_depolarizing |             0.08  |   0.461538 |            0.440476 | 0.588235 |  0.607143 |   0.686208 |

Robustness threshold definition and result:

```json
{
  "failure_definition": "first tested 2q depolarizing probability with balanced_accuracy < 0.75",
  "balanced_accuracy_floor": 0.75,
  "first_tested_failure_probability": 0.08,
  "failure_noise_threshold": 0.04848484848484848,
  "status": "threshold_found",
  "robustness_threshold_applicable": true,
  "baseline_metric": 1.0,
  "grid_is_coarse": true
}
```

## Noise-aware training and unseen-noise transfer

| experiment         | profile              |   depolarizing_2q | training    |       ece |   accuracy |   balanced_accuracy |       f1 |   roc_auc |   log_loss |
|:-------------------|:---------------------|------------------:|:------------|----------:|-----------:|--------------------:|---------:|----------:|-----------:|
| unseen_profile     | unseen_phase_heavy   |             0.01  | ideal       | 0.366962  |   0.923077 |            0.916667 | 0.933333 |  1        |   0.589937 |
| unseen_profile     | unseen_phase_heavy   |             0.01  | noise_aware | 0.436824  |   1        |            1        | 1        |  1        |   0.575623 |
| unseen_profile     | unseen_readout_heavy |             0.01  | ideal       | 0.419396  |   1        |            1        | 1        |  1        |   0.54718  |
| unseen_profile     | unseen_readout_heavy |             0.01  | noise_aware | 0.413086  |   1        |            1        | 1        |  1        |   0.536283 |
| depolarizing_sweep | depol2_0.0           |             0     | ideal       | 0.355168  |   1        |            1        | 1        |  1        |   0.445867 |
| depolarizing_sweep | depol2_0.0           |             0     | noise_aware | 0.346304  |   1        |            1        | 1        |  1        |   0.432307 |
| depolarizing_sweep | depol2_0.005         |             0.005 | ideal       | 0.385442  |   1        |            1        | 1        |  1        |   0.49241  |
| depolarizing_sweep | depol2_0.005         |             0.005 | noise_aware | 0.378456  |   1        |            1        | 1        |  1        |   0.481106 |
| depolarizing_sweep | depol2_0.01          |             0.01  | ideal       | 0.400466  |   1        |            1        | 1        |  1        |   0.515963 |
| depolarizing_sweep | depol2_0.01          |             0.01  | noise_aware | 0.394381  |   1        |            1        | 1        |  1        |   0.505747 |
| depolarizing_sweep | depol2_0.02          |             0.02  | ideal       | 0.426683  |   1        |            1        | 1        |  1        |   0.558391 |
| depolarizing_sweep | depol2_0.02          |             0.02  | noise_aware | 0.422476  |   1        |            1        | 1        |  1        |   0.550979 |
| depolarizing_sweep | depol2_0.04          |             0.04  | ideal       | 0.302809  |   0.846154 |            0.833333 | 0.875    |  1        |   0.6181   |
| depolarizing_sweep | depol2_0.04          |             0.04  | noise_aware | 0.299579  |   0.846154 |            0.833333 | 0.875    |  1        |   0.612147 |
| depolarizing_sweep | depol2_0.08          |             0.08  | ideal       | 0.0932242 |   0.615385 |            0.595238 | 0.705882 |  0.678571 |   0.674563 |
| depolarizing_sweep | depol2_0.08          |             0.08  | noise_aware | 0.0211839 |   0.538462 |            0.511905 | 0.666667 |  0.761905 |   0.67032  |

```json
{
  "balanced_accuracy_floor": 0.75,
  "ideal": {
    "status": "threshold_found",
    "baseline_metric": 1.0,
    "floor": 0.75,
    "robustness_threshold_applicable": true,
    "first_tested_failure_probability": 0.08,
    "failure_noise_threshold": 0.05399999999999999
  },
  "noise_aware": {
    "status": "threshold_found",
    "baseline_metric": 1.0,
    "floor": 0.75,
    "robustness_threshold_applicable": true,
    "first_tested_failure_probability": 0.08,
    "failure_noise_threshold": 0.050370370370370364
  },
  "ideal_first_tested_failure_probability": 0.08,
  "noise_aware_first_tested_failure_probability": 0.08,
  "ideal_failure_noise_threshold": 0.05399999999999999,
  "noise_aware_failure_noise_threshold": 0.050370370370370364,
  "interpretation": "A higher first-tested failure probability indicates a wider operational robustness envelope on this predefined coarse sweep."
}
```

## Repeated-seed statistics

| family   | condition              |   n_repeats |   accuracy_mean |   accuracy_std |   accuracy_ci95_low |   accuracy_ci95_high |   balanced_accuracy_mean |   balanced_accuracy_std |   balanced_accuracy_ci95_low |   balanced_accuracy_ci95_high |   f1_mean |    f1_std |   f1_ci95_low |   f1_ci95_high |   roc_auc_mean |   roc_auc_std |   roc_auc_ci95_low |   roc_auc_ci95_high |   log_loss_mean |   log_loss_std |   log_loss_ci95_low |   log_loss_ci95_high |
|:---------|:-----------------------|------------:|----------------:|---------------:|--------------------:|---------------------:|-------------------------:|------------------------:|-----------------------------:|------------------------------:|----------:|----------:|--------------:|---------------:|---------------:|--------------:|-------------------:|--------------------:|----------------:|---------------:|--------------------:|---------------------:|
| cluster  | ideal                  |           5 |        0.861538 |      0.0643585 |            0.781627 |             0.94145  |                 0.85     |               0.0697217 |                     0.763429 |                      0.936571 |  0.888039 | 0.0463807 |      0.83045  |       0.945628 |       1        |     0         |           1        |            1        |        0.434051 |     0.0329768  |            0.393105 |             0.474997 |
| cluster  | mixed_training_b_noise |           5 |        0.861538 |      0.0643585 |            0.781627 |             0.94145  |                 0.85     |               0.0697217 |                     0.763429 |                      0.936571 |  0.888039 | 0.0463807 |      0.83045  |       0.945628 |       1        |     0         |           1        |            1        |        0.554826 |     0.0091975  |            0.543406 |             0.566246 |
| tfim     | ideal                  |           5 |        1        |      0         |            1        |             1        |                 1        |               0         |                     1        |                      1        |  1        | 0         |      1        |       1        |       1        |     0         |           1        |            1        |        0.435368 |     0.0152618  |            0.416418 |             0.454318 |
| tfim     | mixed_training_b_noise |           5 |        0.861538 |      0.034401  |            0.818824 |             0.904253 |                 0.852381 |               0.0363046 |                     0.807303 |                      0.897459 |  0.883095 | 0.029129  |      0.846927 |       0.919264 |       0.995238 |     0.0106479 |           0.982017 |            1        |        0.593529 |     0.00943601 |            0.581813 |             0.605245 |
| xxz      | ideal                  |           5 |        1        |      0         |            1        |             1        |                 1        |               0         |                     1        |                      1        |  1        | 0         |      1        |       1        |       1        |     0         |           1        |            1        |        0.542729 |     0.0189058  |            0.519254 |             0.566204 |
| xxz      | mixed_training_b_noise |           5 |        0.830769 |      0.084265  |            0.72614  |             0.935398 |                 0.838095 |               0.0774267 |                     0.741957 |                      0.934233 |  0.816037 | 0.103881  |      0.687052 |       0.945023 |       0.916667 |     0.0607026 |           0.841294 |            0.992039 |        0.637152 |     0.00886455 |            0.626145 |             0.648158 |

## Device-derived simulation transfer

| backend      | architecture      |   accuracy |   balanced_accuracy |       f1 |   roc_auc |   log_loss |
|:-------------|:------------------|-----------:|--------------------:|---------:|----------:|-----------:|
| ibm_fez      | light_shared_line |        0.5 |                 0.5 | 0.444444 |      0.62 |   0.692809 |
| ibm_kingston | light_shared_line |        0.4 |                 0.4 | 0.25     |      0.3  |   0.697941 |

### N=4 Simulation Architecture Comparison

```json
{
  "n_qubits": 4,
  "architectures": {
    "light_shared_line": {
      "architecture": "light_shared_line",
      "training_seconds": 10.147594599999138,
      "accuracy": 0.8,
      "balanced_accuracy": 0.8,
      "f1": 0.8333333333333334,
      "roc_auc": 0.6,
      "log_loss": 0.6931471805599477
    },
    "expressive_shared_line": {
      "architecture": "expressive_shared_line",
      "training_seconds": 13.082379500003299,
      "accuracy": 1.0,
      "balanced_accuracy": 1.0,
      "f1": 1.0,
      "roc_auc": 1.0,
      "log_loss": 0.38326663343627715
    }
  }
}
```

## Real-QPU simulation-to-hardware gap

**Status:** Real-QPU hardware-transfer outputs are present.

```json
{
  "architecture": "light_shared_line",
  "ideal": {
    "accuracy": 0.75,
    "balanced_accuracy": 0.75,
    "f1": 0.8,
    "roc_auc": 0.5,
    "log_loss": 0.6931471805599521
  },
  "hardware_raw": {
    "accuracy": 0.75,
    "balanced_accuracy": 0.75,
    "f1": 0.6666666666666666,
    "roc_auc": 1.0,
    "log_loss": 0.6083329561361517
  },
  "hardware_mitigated": {
    "accuracy": 0.25,
    "balanced_accuracy": 0.25,
    "f1": 0.0,
    "roc_auc": 0.1875,
    "log_loss": 0.7185529919680231
  },
  "mean_abs_probability_gap_raw": 0.057500000000003805,
  "mean_abs_probability_gap_mitigated": 0.020584399562942814
}
```

## Required interpretation

1. Report accuracy together with parameter count, circuit depth, two-qubit-operation count, training time, and circuit-evaluation burden.
2. Do not infer quantum advantage from a QCNN win against a baseline with a different information-access regime.
3. Separate synthetic classifier-noise experiments from device-derived/full state-preparation experiments.
4. Treat the N=4 hardware branch as proof of hardware transfer, not as evidence that arbitrary exact many-body state preparation is scalable.
5. Report negative results. If a larger/deeper QCNN degrades faster under noise, that is a central engineering result rather than a failed experiment.
