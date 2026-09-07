import numpy as np

from qcnn_lab.noise.evaluate import noisy_predict
from qcnn_lab.noise.models import NoiseSpec, build_noise_model
from qcnn_lab.qcnn.architecture import get_architecture, parameter_count
from qcnn_lab.qcnn.evaluate import batch_predict


def test_zero_noise_aer_matches_statevector():
    """Verify that Aer simulation with zero noise converges to exact statevector simulation."""
    n_qubits = 4
    arch = get_architecture("light_shared_line")
    n_params = parameter_count(n_qubits, arch)

    rng = np.random.default_rng(999)
    # Generate 3 random normalized states
    states = []
    for _ in range(3):
        psi = rng.normal(size=2**n_qubits) + 1j * rng.normal(size=2**n_qubits)
        psi /= np.linalg.norm(psi)
        states.append(psi)
    states = np.asarray(states)

    params = rng.normal(0.0, 0.5, size=n_params)

    # Exact statevector predictions
    exact_p = batch_predict(states, params, arch, n_qubits)

    # Aer simulation with zero noise and high shot count
    zero_spec = NoiseSpec(name="zero_noise", depolarizing_1q=0.0, depolarizing_2q=0.0, readout=0.0)
    noise_model = build_noise_model(zero_spec)
    shots = 4096
    aer_p = noisy_predict(states, params, arch, n_qubits, noise_model, shots=shots, seed=42)

    # With 4096 shots, 3 * standard error = 3 * sqrt(p(1-p)/4096) <= 3 * 0.5 / 64 ~ 0.024
    max_diff = float(np.max(np.abs(exact_p - aer_p)))
    assert max_diff < 0.04, f"Zero-noise Aer prediction differed from exact statevector by {max_diff:.4f}"
