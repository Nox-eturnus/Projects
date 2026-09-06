# Noise-Robust QCNN for Quantum Phase and State Classification — Research Report

## Claim boundary

This repository studies whether a QCNN provides a useful **inductive bias, parameter-efficiency profile, and noise-robustness envelope** for quantum-native state classification. It does **not** claim generic quantum advantage over classical machine learning.

Classical baselines are labelled by information access. In particular, the MPS prototype receives the full simulated statevector, whereas SVM/MLP/CNN baselines receive local observable maps. Those results must not be collapsed into an information-access-blind leaderboard.

## Multi-family phase classification and transition generalization

| family   | architecture      |   accuracy |   balanced_accuracy |   qcnn_p05_crossing | qcnn_crossing_bracketed   |   qcnn_steepest_change |   physical_diagnostic_steepest_change |   thermodynamic_reference_critical |
|:---------|:------------------|-----------:|--------------------:|--------------------:|:--------------------------|-----------------------:|--------------------------------------:|-----------------------------------:|
| tfim     | light_shared_line |   0.538462 |            0.535714 |                0.55 | True                      |                  0.655 |                                  0.7  |                                  1 |
| xxz      | light_shared_line |   0.461538 |            0.452381 |                0.55 | True                      |                  0.985 |                                  1.45 |                                  1 |
| cluster  | light_shared_line |   0.538462 |            0.511905 |                0.55 | True                      |                  0.835 |                                  0.61 |                                  1 |

For finite systems, the learned or diagnostic crossover need not equal the thermodynamic-limit critical point. The transition sweep is therefore a **generalization/crossover diagnostic**, not a finite-size proof of an exact critical point.

## Architecture trade-offs

| family   | architecture           |   parameters |   depth |   two_qubit_operations |   accuracy |   balanced_accuracy |   training_seconds |
|:---------|:-----------------------|-------------:|--------:|-----------------------:|-----------:|--------------------:|-------------------:|
| tfim     | light_shared_line      |           18 |      47 |                     47 |   0.538462 |            0.535714 |            30.0401 |
| tfim     | light_shared_ring      |           18 |      49 |                     53 |   0.769231 |            0.77381  |            34.2451 |
| tfim     | expressive_shared_line |           27 |      35 |                     36 |   1        |            1        |            27.4739 |
| tfim     | light_unshared_line    |           54 |      47 |                     47 |   0.538462 |            0.559524 |            33.1007 |
| xxz      | light_shared_line      |           18 |      47 |                     47 |   0.461538 |            0.464286 |            30.4679 |
| xxz      | light_shared_ring      |           18 |      49 |                     53 |   0.692308 |            0.678571 |            35.0784 |
| xxz      | expressive_shared_line |           27 |      35 |                     36 |   1        |            1        |            17.5149 |
| xxz      | light_unshared_line    |           54 |      47 |                     47 |   0.384615 |            0.380952 |            12.2966 |
| cluster  | light_shared_line      |           18 |      47 |                     47 |   0.461538 |            0.440476 |            11.4913 |
| cluster  | light_shared_ring      |           18 |      49 |                     53 |   0.461538 |            0.452381 |            13.2223 |
| cluster  | expressive_shared_line |           27 |      35 |                     36 |   1        |            1        |            26.384  |
| cluster  | light_unshared_line    |           54 |      47 |                     47 |   0.615385 |            0.595238 |            29.8877 |

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
| qcnn    |                   4 |        0.435897 |      0.0444116 |                 0.43254  |              2.99055    |
| qcnn    |                   8 |        0.410256 |      0.0888231 |                 0.396825 |              3.93673    |
| qcnn    |                  16 |        0.717949 |      0.0444116 |                 0.710317 |              7.58828    |
| qcnn    |                  24 |        0.410256 |      0.0444116 |                 0.400794 |             11.1601     |
| svm_rbf |                   4 |        0.948718 |      0.0888231 |                 0.944444 |              0.0027149  |
| svm_rbf |                   8 |        1        |      0         |                 1        |              0.00142453 |
| svm_rbf |                  16 |        1        |      0         |                 1        |              0.00140767 |
| svm_rbf |                  24 |        1        |      0         |                 1        |              0.0016718  |

## Noise robustness of ideal-trained QCNN

| profile              | sweep_kind             |   depolarizing_2q |   accuracy |   balanced_accuracy |       f1 |   roc_auc |   log_loss |
|:---------------------|:-----------------------|------------------:|-----------:|--------------------:|---------:|----------:|-----------:|
| mild_depolarizing    | named_profile          |             0.008 |   0.230769 |            0.22619  | 0.285714 |  0.142857 |   0.7194   |
| mixed_training_a     | named_profile          |             0.012 |   0.307692 |            0.309524 | 0.307692 |  0.22619  |   0.713664 |
| mixed_training_b     | named_profile          |             0.02  |   0.230769 |            0.25     | 0        |  0.142857 |   0.719736 |
| unseen_phase_heavy   | named_profile          |             0.01  |   0.384615 |            0.380952 | 0.428571 |  0.333333 |   0.709772 |
| unseen_readout_heavy | named_profile          |             0.01  |   0.461538 |            0.47619  | 0.363636 |  0.321429 |   0.712257 |
| depol2_0.0           | two_qubit_depolarizing |             0     |   0.384615 |            0.369048 | 0.5      |  0.47619  |   0.699116 |
| depol2_0.005         | two_qubit_depolarizing |             0.005 |   0.230769 |            0.22619  | 0.285714 |  0.142857 |   0.720001 |
| depol2_0.01          | two_qubit_depolarizing |             0.01  |   0.230769 |            0.22619  | 0.285714 |  0.142857 |   0.720001 |
| depol2_0.02          | two_qubit_depolarizing |             0.02  |   0.230769 |            0.22619  | 0.285714 |  0.142857 |   0.720001 |
| depol2_0.04          | two_qubit_depolarizing |             0.04  |   0.230769 |            0.22619  | 0.285714 |  0.142857 |   0.720001 |
| depol2_0.08          | two_qubit_depolarizing |             0.08  |   0.230769 |            0.22619  | 0.285714 |  0.142857 |   0.720001 |

Robustness threshold definition and result:

```json
{
  "failure_definition": "first tested 2q depolarizing probability with balanced_accuracy < 0.75",
  "balanced_accuracy_floor": 0.75,
  "first_tested_failure_probability": 0.0,
  "grid_is_coarse": true
}
```

## Noise-aware training and unseen-noise transfer

| experiment         | profile              |   depolarizing_2q | training    |       ece |   accuracy |   balanced_accuracy |       f1 |   roc_auc |   log_loss |
|:-------------------|:---------------------|------------------:|:------------|----------:|-----------:|--------------------:|---------:|----------:|-----------:|
| unseen_profile     | unseen_phase_heavy   |             0.01  | ideal       | 0.0439453 |   0.538462 |            0.547619 | 0.5      |  0.440476 |   0.699543 |
| unseen_profile     | unseen_phase_heavy   |             0.01  | noise_aware | 0.0531851 |   0.461538 |            0.5      | 0        |  0.357143 |   0.701655 |
| unseen_profile     | unseen_readout_heavy |             0.01  | ideal       | 0.0485276 |   0.461538 |            0.47619  | 0.363636 |  0.357143 |   0.700342 |
| unseen_profile     | unseen_readout_heavy |             0.01  | noise_aware | 0.0486779 |   0.538462 |            0.559524 | 0.4      |  0.404762 |   0.697457 |
| depolarizing_sweep | depol2_0.0           |             0     | ideal       | 0.0377103 |   0.538462 |            0.535714 | 0.571429 |  0.547619 |   0.688391 |
| depolarizing_sweep | depol2_0.0           |             0     | noise_aware | 0.0377103 |   0.538462 |            0.535714 | 0.571429 |  0.547619 |   0.688391 |
| depolarizing_sweep | depol2_0.005         |             0.005 | ideal       | 0.127103  |   0.384615 |            0.392857 | 0.333333 |  0.285714 |   0.705906 |
| depolarizing_sweep | depol2_0.005         |             0.005 | noise_aware | 0.127103  |   0.384615 |            0.392857 | 0.333333 |  0.285714 |   0.705906 |
| depolarizing_sweep | depol2_0.01          |             0.01  | ideal       | 0.127103  |   0.384615 |            0.392857 | 0.333333 |  0.285714 |   0.705906 |
| depolarizing_sweep | depol2_0.01          |             0.01  | noise_aware | 0.127103  |   0.384615 |            0.392857 | 0.333333 |  0.285714 |   0.705906 |
| depolarizing_sweep | depol2_0.02          |             0.02  | ideal       | 0.127103  |   0.384615 |            0.392857 | 0.333333 |  0.285714 |   0.705906 |
| depolarizing_sweep | depol2_0.02          |             0.02  | noise_aware | 0.127103  |   0.384615 |            0.392857 | 0.333333 |  0.285714 |   0.705906 |
| depolarizing_sweep | depol2_0.04          |             0.04  | ideal       | 0.127103  |   0.384615 |            0.392857 | 0.333333 |  0.285714 |   0.705906 |
| depolarizing_sweep | depol2_0.04          |             0.04  | noise_aware | 0.127103  |   0.384615 |            0.392857 | 0.333333 |  0.285714 |   0.705906 |
| depolarizing_sweep | depol2_0.08          |             0.08  | ideal       | 0.127103  |   0.384615 |            0.392857 | 0.333333 |  0.285714 |   0.705906 |
| depolarizing_sweep | depol2_0.08          |             0.08  | noise_aware | 0.127103  |   0.384615 |            0.392857 | 0.333333 |  0.285714 |   0.705906 |

```json
{
  "balanced_accuracy_floor": 0.75,
  "ideal_first_tested_failure_probability": 0.0,
  "noise_aware_first_tested_failure_probability": 0.0,
  "interpretation": "A higher first-tested failure probability indicates a wider operational robustness envelope on this predefined coarse sweep."
}
```

## Repeated-seed statistics

| family   | condition              |   n_repeats |   accuracy_mean |   accuracy_std |   accuracy_ci95_low |   accuracy_ci95_high |   balanced_accuracy_mean |   balanced_accuracy_std |   balanced_accuracy_ci95_low |   balanced_accuracy_ci95_high |   f1_mean |    f1_std |   f1_ci95_low |   f1_ci95_high |   roc_auc_mean |   roc_auc_std |   roc_auc_ci95_low |   roc_auc_ci95_high |   log_loss_mean |   log_loss_std |   log_loss_ci95_low |   log_loss_ci95_high |
|:---------|:-----------------------|------------:|----------------:|---------------:|--------------------:|---------------------:|-------------------------:|------------------------:|-----------------------------:|------------------------------:|----------:|----------:|--------------:|---------------:|---------------:|--------------:|-------------------:|--------------------:|----------------:|---------------:|--------------------:|---------------------:|
| cluster  | ideal                  |           5 |        0.569231 |      0.0421325 |            0.516916 |             0.621545 |                 0.540476 |               0.039123  |                     0.491899 |                      0.589054 |  0.694737 | 0.0384367 |     0.647011  |       0.742462 |       0.214286 |     0.0445435 |           0.158978 |            0.269594 |        0.693147 |    3.63895e-13 |            0.693147 |             0.693147 |
| cluster  | mixed_training_b_noise |           5 |        0.538462 |      0.0942111 |            0.421483 |             0.65544  |                 0.569048 |               0.0876436 |                     0.460224 |                      0.677872 |  0.25     | 0.259808  |    -0.0725938 |       0.572594 |       0.47381  |     0.184312  |           0.244955 |            0.702664 |        0.703083 |    0.0133987   |            0.686446 |             0.71972  |
| tfim     | ideal                  |           5 |        0.538462 |      0.0942111 |            0.421483 |             0.65544  |                 0.538095 |               0.0997446 |                     0.414246 |                      0.661944 |  0.560879 | 0.0742309 |     0.468709  |       0.653049 |       0.528571 |     0.141261  |           0.353173 |            0.70397  |        0.693147 |    2.45855e-11 |            0.693147 |             0.693147 |
| tfim     | mixed_training_b_noise |           5 |        0.384615 |      0.108786  |            0.24954  |             0.519691 |                 0.388095 |               0.110272  |                     0.251175 |                      0.525016 |  0.359048 | 0.163459  |     0.156087  |       0.562009 |       0.361905 |     0.134845  |           0.194473 |            0.529337 |        0.707996 |    0.00795277  |            0.698122 |             0.717871 |
| xxz      | ideal                  |           5 |        0.476923 |      0.0643585 |            0.397011 |             0.556835 |                 0.47381  |               0.0615143 |                     0.397429 |                      0.55019  |  0.509615 | 0.0841507 |     0.405128  |       0.614102 |       0.445238 |     0.0592852 |           0.371626 |            0.51885  |        0.693147 |    6.48499e-14 |            0.693147 |             0.693147 |
| xxz      | mixed_training_b_noise |           5 |        0.476923 |      0.100295  |            0.35239  |             0.601456 |                 0.497619 |               0.103236  |                     0.369435 |                      0.625803 |  0.321616 | 0.114649  |     0.179261  |       0.463972 |       0.445238 |     0.106679  |           0.312779 |            0.577697 |        0.702072 |    0.00891571  |            0.691002 |             0.713143 |

## Device-derived simulation transfer

| backend      |   accuracy |   balanced_accuracy |       f1 |   roc_auc |   log_loss |
|:-------------|-----------:|--------------------:|---------:|----------:|-----------:|
| ibm_fez      |        0.5 |                 0.5 | 0.444444 |      0.62 |   0.692809 |
| ibm_kingston |        0.4 |                 0.4 | 0.25     |      0.3  |   0.697941 |

## Real-QPU simulation-to-hardware gap

**Status:** Real-QPU hardware-transfer outputs are present.

```json
{
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
