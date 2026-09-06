from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import numpy as np

from qcnn_lab.noise.evaluate import noisy_predict
from qcnn_lab.noise.models import NoiseSpec, build_noise_model
from qcnn_lab.qcnn.architecture import QCNNArchitecture, parameter_count
from qcnn_lab.qcnn.evaluate import binary_cross_entropy


@dataclass(frozen=True)
class NoiseAwareResult:
    params: np.ndarray
    history: list[dict]
    seconds: float


def train_noise_aware_spsa(
    states: np.ndarray,
    labels: np.ndarray,
    n_qubits: int,
    architecture: QCNNArchitecture,
    train_idx: np.ndarray,
    validation_idx: np.ndarray,
    training_specs: list[NoiseSpec],
    *,
    iterations: int = 60,
    batch_size: int = 12,
    shots: int = 256,
    a: float = 0.18,
    c: float = 0.10,
    seed: int = 12345,
) -> NoiseAwareResult:
    if not training_specs:
        raise ValueError("at least one training noise specification is required")
    rng = np.random.default_rng(seed)
    params = rng.normal(0.0, 0.15, size=parameter_count(n_qubits, architecture))
    history = []
    started = perf_counter()
    labels = np.asarray(labels, dtype=int)

    for k in range(iterations):
        ak = a / ((k + 1 + 10) ** 0.602)
        ck = c / ((k + 1) ** 0.101)
        delta = rng.choice([-1.0, 1.0], size=len(params))
        replace = batch_size > len(train_idx)
        batch = rng.choice(train_idx, size=min(batch_size, len(train_idx)) if not replace else batch_size, replace=replace)
        spec = training_specs[int(rng.integers(0, len(training_specs)))]
        noise_model = build_noise_model(spec)
        eval_seed = seed + 1000 + k
        p_plus = noisy_predict(states[batch], params + ck * delta, architecture, n_qubits, noise_model, shots=shots, seed=eval_seed)
        p_minus = noisy_predict(states[batch], params - ck * delta, architecture, n_qubits, noise_model, shots=shots, seed=eval_seed)
        loss_plus = binary_cross_entropy(labels[batch], p_plus)
        loss_minus = binary_cross_entropy(labels[batch], p_minus)
        ghat = (loss_plus - loss_minus) / (2.0 * ck) * delta
        params = params - ak * ghat
        row = {"iteration": k, "noise_profile": spec.name, "loss_plus": loss_plus, "loss_minus": loss_minus, "step_size": ak, "perturbation": ck}
        if k % 5 == 0 or k == iterations - 1:
            val_spec = training_specs[k % len(training_specs)]
            val_p = noisy_predict(states[validation_idx], params, architecture, n_qubits, build_noise_model(val_spec), shots=shots, seed=seed + 5000 + k)
            row["validation_loss"] = binary_cross_entropy(labels[validation_idx], val_p)
        history.append(row)
    return NoiseAwareResult(params=params, history=history, seconds=perf_counter() - started)