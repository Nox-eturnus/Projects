import numpy as np
import pytest
from scipy import sparse

from qcnn_lab.analysis.calibration import (
    brier_score,
    expected_calibration_error,
    negative_log_likelihood,
)
from qcnn_lab.analysis.statistics import bootstrap_ci_from_samples, bootstrap_metric_ci
from qcnn_lab.noise.state_preparation import noisy_state_preparation_predict
from qcnn_lab.physics.hamiltonians import cluster_ising_hamiltonian, tfim_hamiltonian
from qcnn_lab.physics.operators import local_pauli, pauli_product
from qcnn_lab.physics.perturbations import (
    perturbed_cluster_hamiltonian,
    perturbed_tfim_hamiltonian,
)
from qcnn_lab.physics.thermal_states import compute_thermal_density_matrix
from qcnn_lab.qcnn.ablations import (
    UntrainedQCNNBaseline,
    evaluate_shuffled_label_permutation_distribution,
    make_random_quantum_states,
    make_shuffled_labels_data,
)
from qcnn_lab.qcnn.architecture import (
    build_qcnn,
    conv_param_count,
    get_architecture,
    parameter_count,
    raw_circuit_metrics,
)
from qcnn_lab.qcnn.finite_shots import (
    simulate_finite_shot_observable,
    simulate_finite_shot_probability,
)


def test_optimizer_seed_reproducibility():
    rng1 = np.random.default_rng(123)
    v1 = rng1.normal(0, 1, 10)
    rng2 = np.random.default_rng(123)
    v2 = rng2.normal(0, 1, 10)
    np.testing.assert_array_equal(v1, v2)


def test_shuffled_labels_destroy_test_signal():
    y = np.array([0] * 50 + [1] * 50)
    shuffled = make_shuffled_labels_data(y, seed=999)
    # Shuffling changes positions
    assert not np.array_equal(y, shuffled)
    assert sum(shuffled) == sum(y)


def test_random_states_have_no_label_signal():
    states, labels = make_random_quantum_states(20, n_qubits=4, seed=42)
    assert len(states) == 20
    assert states.shape[1] == 16
    for st in states:
        norm = np.linalg.norm(st)
        assert abs(norm - 1.0) < 1e-6
    assert sum(labels) == 10


def test_untrained_qcnn_baseline():
    arch = get_architecture("expressive_shared_line")
    clf = UntrainedQCNNBaseline(arch, n_qubits=4, seed=42)
    states, _ = make_random_quantum_states(4, n_qubits=4, seed=42)
    probs = clf.predict_proba(states)
    preds = clf.predict(states)
    assert len(probs) == 4
    assert np.all((probs >= 0.0) & (probs <= 1.0))
    assert np.all((preds == 0) | (preds == 1))


def test_granular_entanglement_architectures():
    arch_full = get_architecture("expressive_shared_line")
    arch_no_conv = get_architecture("expressive_no_conv_entanglement")
    arch_no_pool = get_architecture("expressive_no_pool_entanglement")
    arch_no_ent = get_architecture("expressive_no_entanglement")

    # Expressive shared line has 27 parameters for N=8
    assert parameter_count(8, arch_full) == 27
    # No conv entanglement: 4 conv + 3 pool = 7 per round * 3 rounds = 21
    assert parameter_count(8, arch_no_conv) == 21
    # No pool entanglement: 6 conv + 3 pool = 9 per round * 3 rounds = 27
    assert parameter_count(8, arch_no_pool) == 27
    # No entanglement anywhere: 4 conv + 3 pool = 7 per round * 3 rounds = 21
    assert parameter_count(8, arch_no_ent) == 21

    m_full = raw_circuit_metrics(8, arch_full)
    m_no_conv = raw_circuit_metrics(8, arch_no_conv)
    m_no_pool = raw_circuit_metrics(8, arch_no_pool)
    m_no_ent = raw_circuit_metrics(8, arch_no_ent)

    assert m_no_ent["two_qubit_operations"] == 0
    assert m_no_conv["two_qubit_operations"] < m_full["two_qubit_operations"]
    assert m_no_pool["two_qubit_operations"] < m_full["two_qubit_operations"]
    assert m_no_conv["two_qubit_operations"] + m_no_pool["two_qubit_operations"] == m_full["two_qubit_operations"]


def test_ablation_circuit_builds():
    for name in [
        "expressive_no_conv_entanglement",
        "expressive_no_pool_entanglement",
        "expressive_no_entanglement",
        "expressive_no_pooling",
        "expressive_unshared_line",
    ]:
        arch = get_architecture(name)
        params = np.zeros(parameter_count(8, arch))
        qc, out_q = build_qcnn(8, params, arch)
        assert qc.num_qubits == 8
        assert out_q >= 0


def test_finite_shot_probability_converges_to_exact():
    exact_p = 0.65
    shots_high = 50_000
    p_hat = simulate_finite_shot_probability(exact_p, shots=shots_high, seed=42)
    assert abs(p_hat - exact_p) < 0.01


def test_more_shots_reduce_sampling_variance():
    exact_p = 0.50
    samples_low = [simulate_finite_shot_probability(exact_p, shots=128, seed=s) for s in range(200)]
    samples_high = [simulate_finite_shot_probability(exact_p, shots=4096, seed=s) for s in range(200)]
    var_low = np.var(samples_low)
    var_high = np.var(samples_high)
    assert var_high < var_low * 0.2


def test_thermal_state_trace_is_one():
    H = tfim_hamiltonian(4, h=1.0)
    vecs, weights = compute_thermal_density_matrix(H, temperature=0.5)
    assert abs(np.sum(weights) - 1.0) < 1e-10


def test_thermal_state_is_positive_semidefinite():
    H = tfim_hamiltonian(4, h=1.0)
    vecs, weights = compute_thermal_density_matrix(H, temperature=1.0)
    assert np.all(weights >= 0.0)


def test_thermal_state_T_to_zero_matches_ground_state():
    H = tfim_hamiltonian(4, h=0.8)
    vecs, weights = compute_thermal_density_matrix(H, temperature=0.0)
    assert weights[0] == 1.0
    assert np.all(weights[1:] == 0.0)


def test_state_noise_zero_matches_ideal():
    ideal_p = np.array([0.1, 0.5, 0.9])
    noisy_p = noisy_state_preparation_predict(ideal_p, p_state=0.0)
    np.testing.assert_allclose(ideal_p, noisy_p)


def test_hamiltonian_perturbation_zero_matches_original():
    H_orig = tfim_hamiltonian(4, h=1.2)
    H_pert = perturbed_tfim_hamiltonian(4, h=1.2, delta=0.0)
    np.testing.assert_allclose(H_orig.toarray(), H_pert.toarray())


def test_symmetry_preserving_perturbation_contract():
    n = 4
    H_pert = perturbed_cluster_hamiltonian(n, h=0.5, delta=0.1, seed=123).toarray()
    p_even = pauli_product(n, {0: "X", 2: "X"}).toarray()
    p_odd = pauli_product(n, {1: "X", 3: "X"}).toarray()

    comm_even = H_pert @ p_even - p_even @ H_pert
    comm_odd = H_pert @ p_odd - p_odd @ H_pert
    np.testing.assert_allclose(comm_even, np.zeros_like(comm_even), atol=1e-10)
    np.testing.assert_allclose(comm_odd, np.zeros_like(comm_odd), atol=1e-10)


def test_confidence_interval_bounds():
    vals = np.array([0.80, 0.82, 0.85, 0.83, 0.81])
    low, high = bootstrap_ci_from_samples(vals, n_boot=500, confidence=0.95, seed=42)
    assert low <= np.mean(vals) <= high


def test_calibration_metrics_bounds():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.2, 0.8, 0.9])
    bs = brier_score(y, p)
    ece = expected_calibration_error(y, p)
    nll = negative_log_likelihood(y, p)

    assert 0.0 <= bs <= 1.0
    assert 0.0 <= ece <= 1.0
    assert nll >= 0.0
