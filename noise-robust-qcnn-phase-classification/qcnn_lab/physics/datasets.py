from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from qcnn_lab.physics.hamiltonians import cluster_ising_hamiltonian, tfim_hamiltonian, xxz_hamiltonian
from qcnn_lab.physics.observables import cluster_stabilizer_order, tfim_long_range_zz, xxz_staggered_structure
from qcnn_lab.physics.states import ground_state


@dataclass(frozen=True)
class TaskSpec:
    family: str
    n_qubits: int
    low_range: tuple[float, float]
    high_range: tuple[float, float]
    transition_range: tuple[float, float]
    critical_value: float


def default_specs(n_qubits: int = 8) -> dict[str, TaskSpec]:
    return {
        "tfim": TaskSpec("tfim", n_qubits, (0.20, 0.75), (1.25, 1.80), (0.55, 1.45), 1.0),
        "xxz": TaskSpec("xxz", n_qubits, (-0.75, 0.70), (1.30, 2.00), (0.55, 1.45), 1.0),
        "cluster": TaskSpec("cluster", n_qubits, (0.15, 0.70), (1.30, 1.85), (0.55, 1.45), 1.0),
    }


def _state_for(family: str, n: int, parameter: float) -> tuple[float, np.ndarray, float]:
    if family == "tfim":
        energy, state = ground_state(tfim_hamiltonian(n, h=parameter))
        diag = tfim_long_range_zz(state, n)
    elif family == "xxz":
        energy, state = ground_state(xxz_hamiltonian(n, delta=parameter))
        diag = xxz_staggered_structure(state, n)
    elif family == "cluster":
        energy, state = ground_state(cluster_ising_hamiltonian(n, h=parameter))
        diag = cluster_stabilizer_order(state, n)
    else:
        raise ValueError(f"unknown family {family}")
    return energy, state, diag


def generate_task_dataset(
    spec: TaskSpec,
    *,
    samples_per_class: int = 40,
    transition_points: int = 61,
    seed: int = 12345,
) -> tuple[np.ndarray, pd.DataFrame, np.ndarray, pd.DataFrame]:
    """Return labelled states/meta and an unlabeled transition sweep/meta."""
    rng = np.random.default_rng(seed)
    params0 = rng.uniform(*spec.low_range, size=samples_per_class)
    params1 = rng.uniform(*spec.high_range, size=samples_per_class)
    labelled_params = np.concatenate([params0, params1])
    labels = np.concatenate([np.zeros(samples_per_class, dtype=int), np.ones(samples_per_class, dtype=int)])
    order = rng.permutation(len(labels))
    labelled_params, labels = labelled_params[order], labels[order]

    states = []
    rows = []
    for idx, (parameter, label) in enumerate(zip(labelled_params, labels)):
        energy, state, diagnostic = _state_for(spec.family, spec.n_qubits, float(parameter))
        states.append(state)
        rows.append({
            "sample_id": idx,
            "family": spec.family,
            "n_qubits": spec.n_qubits,
            "parameter": float(parameter),
            "label": int(label),
            "ground_energy": energy,
            "physical_diagnostic": diagnostic,
            "split": "labelled",
        })

    sweep_params = np.linspace(spec.transition_range[0], spec.transition_range[1], transition_points)
    sweep_states = []
    sweep_rows = []
    for idx, parameter in enumerate(sweep_params):
        energy, state, diagnostic = _state_for(spec.family, spec.n_qubits, float(parameter))
        sweep_states.append(state)
        sweep_rows.append({
            "sample_id": idx,
            "family": spec.family,
            "n_qubits": spec.n_qubits,
            "parameter": float(parameter),
            "label": -1,
            "ground_energy": energy,
            "physical_diagnostic": diagnostic,
            "split": "transition_sweep",
        })
    return np.asarray(states), pd.DataFrame(rows), np.asarray(sweep_states), pd.DataFrame(sweep_rows)


def save_task_dataset(
    output_dir: str | Path,
    spec: TaskSpec,
    *,
    samples_per_class: int = 40,
    transition_points: int = 61,
    seed: int = 12345,
) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    states, meta, sweep_states, sweep_meta = generate_task_dataset(
        spec,
        samples_per_class=samples_per_class,
        transition_points=transition_points,
        seed=seed,
    )
    np.savez_compressed(output_dir / f"{spec.family}_states.npz", states=states)
    meta.to_csv(output_dir / f"{spec.family}_metadata.csv", index=False)
    np.savez_compressed(output_dir / f"{spec.family}_transition_states.npz", states=sweep_states)
    sweep_meta.to_csv(output_dir / f"{spec.family}_transition_metadata.csv", index=False)


def load_labelled_dataset(data_dir: str | Path, family: str) -> tuple[np.ndarray, pd.DataFrame]:
    data_dir = Path(data_dir)
    states = np.load(data_dir / f"{family}_states.npz")["states"]
    meta = pd.read_csv(data_dir / f"{family}_metadata.csv")
    if len(states) != len(meta):
        raise ValueError("state/metadata length mismatch")
    return states, meta


def load_transition_dataset(data_dir: str | Path, family: str) -> tuple[np.ndarray, pd.DataFrame]:
    data_dir = Path(data_dir)
    states = np.load(data_dir / f"{family}_transition_states.npz")["states"]
    meta = pd.read_csv(data_dir / f"{family}_transition_metadata.csv")
    if len(states) != len(meta):
        raise ValueError("state/metadata length mismatch")
    return states, meta