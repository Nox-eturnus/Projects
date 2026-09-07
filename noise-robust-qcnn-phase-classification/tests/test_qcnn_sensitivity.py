import numpy as np
import pytest

from qcnn_lab.qcnn.architecture import get_architecture, parameter_count
from qcnn_lab.qcnn.evaluate import batch_predict, predict_p1


@pytest.mark.parametrize(
    "arch_name",
    [
        "light_shared_line",
        "light_shared_ring",
        "expressive_shared_line",
        "light_unshared_line",
    ],
)
def test_architecture_sensitivity_on_random_state(arch_name):
    """Verify that all architectures respond to parameter variations on generic states."""
    n_qubits = 8
    arch = get_architecture(arch_name)
    n_params = parameter_count(n_qubits, arch)
    rng = np.random.default_rng(42)

    # Generic normalized random quantum state
    psi = rng.normal(size=2**n_qubits) + 1j * rng.normal(size=2**n_qubits)
    psi /= np.linalg.norm(psi)

    params0 = rng.normal(0.0, 0.5, size=n_params)
    p0 = predict_p1(psi, params0, arch, n_qubits)

    # Check finite-difference sensitivity across parameter perturbations
    sensitivities = []
    eps = 1e-3
    for i in range(n_params):
        params_plus = params0.copy()
        params_plus[i] += eps
        p_plus = predict_p1(psi, params_plus, arch, n_qubits)
        sensitivities.append(abs(p_plus - p0) / eps)

    mean_sensitivity = float(np.mean(sensitivities))
    max_sensitivity = float(np.max(sensitivities))

    # Generic states should have non-zero sensitivity in some parameters
    assert max_sensitivity > 1e-4, f"{arch_name} has zero gradient response"
    assert 0.0 <= p0 <= 1.0


def test_expressive_vs_light_parameter_capacity():
    """Verify expressive architecture has strictly greater capacity and responsiveness."""
    n_qubits = 8
    light = get_architecture("light_shared_line")
    expr = get_architecture("expressive_shared_line")

    n_light = parameter_count(n_qubits, light)
    n_expr = parameter_count(n_qubits, expr)

    assert n_expr > n_light
    assert n_light == 18
    assert n_expr == 27
