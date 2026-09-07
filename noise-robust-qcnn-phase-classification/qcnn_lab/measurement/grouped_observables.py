r"""Physically faithful measurement basis sampling for classical comparator baselines.

Implements genuine quantum state sampling from experimentally accessible,
qubit-wise commuting Pauli measurement bases rather than treating multi-site
or averaged expectation values as independent Bernoulli observables:

1. TFIM:
   - Setting 1 (Z-basis, B/2 shots): measures Z_0 Z_{N-1} from sampled bitstrings.
   - Setting 2 (X-basis, B/2 shots): applies H^{\otimes N}, measures transverse
     magnetization (1/N) \sum_i X_i preserving site-to-site sample covariance.

2. XXZ:
   - Setting 1 (Z-basis, B/2 shots): measures staggered structure factor from
     sampled Z bitstrings: (1 / binom(N, 2)) \sum_{i<j} (-1)^{j-i} z_i z_j.
   - Setting 2 (X-basis, B/2 shots): applies H^{\otimes N}, measures nearest-neighbor
     exchange (1/(N-1)) \sum_i X_i X_{i+1}.

3. Cluster:
   - Setting A (Z on even, X on odd, B/2 shots): measures odd-site stabilizers
     Z_{i-1} X_i Z_{i+1} and odd-site X_i.
   - Setting B (X on even, Z on odd, B/2 shots): measures even-site stabilizers
     Z_{i-1} X_i Z_{i+1} and even-site X_i.
   Combined across the 2 settings to yield the cluster stabilizer order parameter
   and average transverse field.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Tuple
import numpy as np

from qcnn_lab.physics.observables import (
    cluster_stabilizer_order,
    tfim_long_range_zz,
    xxz_staggered_structure,
)
from qcnn_lab.physics.operators import expectation, local_pauli, pauli_product

_H = np.array([[1.0, 1.0], [1.0, -1.0]], dtype=complex) / np.sqrt(2.0)
_I = np.eye(2, dtype=complex)


@lru_cache(maxsize=16)
def get_basis_rotation_matrix(setting: str, n_qubits: int) -> np.ndarray:
    """Precompute and cache tensor-product rotation unitaries."""
    if setting == "all_x":
        u = _H
        for _ in range(n_qubits - 1):
            u = np.kron(u, _H)
        return u
    elif setting == "cluster_a":
        # Even sites: Z (Identity); Odd sites: X (Hadamard)
        u = _I if 0 % 2 == 0 else _H
        for i in range(1, n_qubits):
            u = np.kron(u, _H if i % 2 == 1 else _I)
        return u
    elif setting == "cluster_b":
        # Even sites: X (Hadamard); Odd sites: Z (Identity)
        u = _H if 0 % 2 == 0 else _I
        for i in range(1, n_qubits):
            u = np.kron(u, _I if i % 2 == 1 else _H)
        return u
    elif setting == "all_z":
        return np.eye(2**n_qubits, dtype=complex)
    else:
        raise ValueError(f"Unknown setting: {setting}")


def sample_spins_from_state(
    state: np.ndarray,
    setting: str,
    n_qubits: int,
    shots: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample measurement outcomes (spins in {-1, +1}) for n_qubits from pure state.

    Returns array of shape (shots, n_qubits) with values in {-1, +1}.
    """
    if shots <= 0:
        raise ValueError(f"shots must be positive, got {shots}")

    u = get_basis_rotation_matrix(setting, n_qubits)
    rotated = u @ np.asarray(state, dtype=complex).reshape(-1)
    probs = np.abs(rotated) ** 2
    probs = probs / np.sum(probs)

    dim = 2**n_qubits
    indices = rng.choice(dim, size=shots, p=probs)
    # Unpack integer outcomes into bitstrings (site 0 is MSB)
    bits = ((indices[:, None] >> np.arange(n_qubits - 1, -1, -1)) & 1)
    # Map bit 0 -> +1 (eigenvalue +1), bit 1 -> -1 (eigenvalue -1)
    spins = 1 - 2 * bits
    return spins


def extract_tfim_grouped_features(
    state: np.ndarray,
    n_qubits: int,
    budget: int | None = None,
    seed: int = 12345,
) -> Tuple[float, float]:
    """Extract TFIM features using 2 physical measurement settings (Z-basis and X-basis)."""
    if budget is None or budget <= 0:
        f_zz = tfim_long_range_zz(state, n_qubits)
        f_x = float(np.mean([expectation(state, local_pauli(n_qubits, i, "X")) for i in range(n_qubits)]))
        return f_zz, f_x

    rng = np.random.default_rng(seed)
    shots_z = max(1, budget // 2)
    shots_x = max(1, budget - shots_z)

    # Setting 1: Z-basis
    spins_z = sample_spins_from_state(state, "all_z", n_qubits, shots_z, rng)
    f_zz = float(np.mean(spins_z[:, 0] * spins_z[:, -1]))

    # Setting 2: X-basis
    spins_x = sample_spins_from_state(state, "all_x", n_qubits, shots_x, rng)
    f_x = float(np.mean(np.mean(spins_x, axis=1)))

    return f_zz, f_x


def extract_xxz_grouped_features(
    state: np.ndarray,
    n_qubits: int,
    budget: int | None = None,
    seed: int = 12345,
) -> Tuple[float, float]:
    """Extract XXZ features using 2 physical measurement settings (Z-basis and X-basis)."""
    if budget is None or budget <= 0:
        f_stag = xxz_staggered_structure(state, n_qubits)
        f_xx = float(np.mean([expectation(state, pauli_product(n_qubits, {i: "X", i + 1: "X"})) for i in range(n_qubits - 1)]))
        return f_stag, f_xx

    rng = np.random.default_rng(seed)
    shots_z = max(1, budget // 2)
    shots_x = max(1, budget - shots_z)

    # Setting 1: Z-basis for staggered structure factor
    spins_z = sample_spins_from_state(state, "all_z", n_qubits, shots_z, rng)
    pairs = [(i, j) for i in range(n_qubits) for j in range(i + 1, n_qubits)]
    pair_contributions = [((-1) ** (j - i)) * spins_z[:, i] * spins_z[:, j] for i, j in pairs]
    shot_stag = np.mean(pair_contributions, axis=0)
    f_stag = float(np.mean(shot_stag))

    # Setting 2: X-basis for nearest-neighbor XX exchange
    spins_x = sample_spins_from_state(state, "all_x", n_qubits, shots_x, rng)
    nn_contributions = [spins_x[:, i] * spins_x[:, i + 1] for i in range(n_qubits - 1)]
    shot_xx = np.mean(nn_contributions, axis=0)
    f_xx = float(np.mean(shot_xx))

    return f_stag, f_xx


def extract_cluster_grouped_features(
    state: np.ndarray,
    n_qubits: int,
    budget: int | None = None,
    seed: int = 12345,
) -> Tuple[float, float]:
    """Extract Cluster features using 2 physical measurement settings (Setting A and Setting B)."""
    if budget is None or budget <= 0:
        f_stab = cluster_stabilizer_order(state, n_qubits)
        f_x = float(np.mean([expectation(state, local_pauli(n_qubits, i, "X")) for i in range(n_qubits)]))
        return f_stab, f_x

    rng = np.random.default_rng(seed)
    shots_a = max(1, budget // 2)
    shots_b = max(1, budget - shots_a)

    # Setting A: odd H, even I
    spins_a = sample_spins_from_state(state, "cluster_a", n_qubits, shots_a, rng)
    # Setting B: even H, odd I
    spins_b = sample_spins_from_state(state, "cluster_b", n_qubits, shots_b, rng)

    # Stabilizers: odd i from Setting A, even i from Setting B
    odd_stabs = [float(np.mean(spins_a[:, i - 1] * spins_a[:, i] * spins_a[:, i + 1])) for i in range(1, n_qubits - 1, 2)]
    even_stabs = [float(np.mean(spins_b[:, i - 1] * spins_b[:, i] * spins_b[:, i + 1])) for i in range(2, n_qubits - 1, 2)]
    f_stab = float(np.mean(odd_stabs + even_stabs))

    # Transverse field X: odd i from Setting A, even i from Setting B
    odd_x = [float(np.mean(spins_a[:, i])) for i in range(1, n_qubits, 2)]
    even_x = [float(np.mean(spins_b[:, i])) for i in range(0, n_qubits, 2)]
    f_x = float(np.mean(odd_x + even_x))

    return f_stab, f_x


def extract_grouped_classical_features(
    states: np.ndarray,
    family: str,
    n_qubits: int,
    budget: int | None = None,
    seed: int = 12345,
) -> Tuple[np.ndarray, int]:
    """Batch extract physical Pauli features under finite-budget basis grouping.

    Returns:
        features: shape (n_samples, 2)
        n_settings: number of physical measurement settings (always 2)
    """
    extractor_map = {
        "tfim": extract_tfim_grouped_features,
        "xxz": extract_xxz_grouped_features,
        "cluster": extract_cluster_grouped_features,
    }
    if family not in extractor_map:
        raise ValueError(f"Unknown family {family}. Must be one of {list(extractor_map.keys())}")

    fn = extractor_map[family]
    features = []
    for idx, st in enumerate(states):
        # Derive a distinct deterministic seed per sample
        sample_seed = seed + idx * 997 if budget is not None else seed
        feat = fn(st, n_qubits, budget=budget, seed=sample_seed)
        features.append(feat)

    return np.asarray(features, dtype=float), 2
