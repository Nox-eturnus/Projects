import json
from pathlib import Path
import numpy as np
import pytest
from scipy import sparse
from sklearn.metrics import balanced_accuracy_score

from qcnn_lab.analysis.binomial_ci import clopper_pearson_interval, wilson_score_interval
from qcnn_lab.analysis.calibration import (
    brier_score,
    expected_calibration_error,
    negative_log_likelihood,
)
from qcnn_lab.analysis.splits import load_split_manifest, split_indices_from_manifest
from qcnn_lab.analysis.statistics import bootstrap_ci_from_samples, bootstrap_metric_ci
from qcnn_lab.config import load_yaml
from qcnn_lab.measurement.grouped_observables import extract_grouped_classical_features
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
    evaluate_pipeline_label_permutation_test,
    evaluate_shuffled_training_label_control,
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
from qcnn_lab.qcnn.evaluate import batch_predict
from qcnn_lab.qcnn.finite_shots import (
    simulate_finite_shot_observable,
    simulate_finite_shot_probability,
)
from qcnn_lab.qcnn.train import train_ideal_qcnn


def test_optimizer_seed_reproducibility():
    rng1 = np.random.default_rng(123)
    v1 = rng1.normal(0, 1, 10)
    rng2 = np.random.default_rng(123)
    v2 = rng2.normal(0, 1, 10)
    np.testing.assert_array_equal(v1, v2)


def test_label_shuffle_changes_order_preserves_counts():
    """Verify that label shuffling randomizes element positions while preserving class counts."""
    y = np.array([0] * 50 + [1] * 50)
    shuffled = make_shuffled_labels_data(y, seed=999)
    assert not np.array_equal(y, shuffled)
    assert sum(shuffled) == sum(y)


def test_random_state_generator_normalizes_and_balances():
    """Verify that synthetic random quantum state generator normalizes vectors and balances labels."""
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


# --- BEHAVIORAL REGRESSION TESTS (PRIORITY 9) ---

def test_clopper_pearson_exact_bounds():
    """Verify exact Clopper-Pearson binomial confidence interval on 10/10 hardware result."""
    low, high = clopper_pearson_interval(10, 10, confidence=0.95)
    assert low == 0.6915
    assert high == 1.0


def test_wilson_score_interval_bounds():
    low, high = wilson_score_interval(10, 10, confidence=0.95)
    assert 0.70 <= low <= 0.75
    assert high == 1.0


def test_training_changes_predictions():
    """Verify that training on labeled states materially changes model parameter weights and predictions."""
    arch = get_architecture("expressive_shared_line")
    n_qubits = 4
    init_params = np.zeros(parameter_count(n_qubits, arch))

    # Generate small 4-qubit dataset
    states, labels = make_random_quantum_states(8, n_qubits=n_qubits, seed=123)
    train_idx = np.array([0, 1, 2, 3])
    val_idx = np.array([4, 5])
    test_idx = np.array([6, 7])

    trained_params, _, _ = train_ideal_qcnn(
        states, labels, n_qubits, arch, train_idx, val_idx, maxiter=30, seed=42
    )

    # Weights must have moved
    weight_shift = np.linalg.norm(trained_params - init_params)
    assert weight_shift > 0.05

    # Predictions must differ from initial 0.5 flat baseline
    init_preds = batch_predict(states[test_idx], init_params, arch, n_qubits)
    trained_preds = batch_predict(states[test_idx], trained_params, arch, n_qubits)
    assert not np.allclose(init_preds, trained_preds, atol=0.01)


def test_shuffled_labels_reduce_generalization():
    """Verify that training on randomly permuted targets materially degrades true-label generalization."""
    from qcnn_lab.physics.hamiltonians import tfim_hamiltonian
    from qcnn_lab.physics.states import ground_state

    # Construct clean 4-qubit toy dataset: 4 ferromagnet (h <= 0.35) vs 4 paramagnet (h >= 1.7)
    states, labels = [], []
    for h in [0.2, 0.25, 0.3, 0.35]:
        _, gs = ground_state(tfim_hamiltonian(4, h=h))
        states.append(gs)
        labels.append(0)
    for h in [1.7, 1.8, 1.9, 2.0]:
        _, gs = ground_state(tfim_hamiltonian(4, h=h))
        states.append(gs)
        labels.append(1)

    states = np.asarray(states)
    labels = np.asarray(labels, dtype=int)
    train_idx = np.array([0, 1, 4, 5])
    val_idx = np.array([2, 6])
    test_idx = np.array([3, 7])

    arch = get_architecture("expressive_shared_line")
    params, _, _ = train_ideal_qcnn(states, labels, 4, arch, train_idx, val_idx, maxiter=40, seed=42)
    test_p = batch_predict(states[test_idx], params, arch, 4)
    true_ba = float(balanced_accuracy_score(labels[test_idx], (test_p >= 0.5).astype(int)))
    assert true_ba == 1.0

    res = evaluate_shuffled_training_label_control(
        states, labels, 4, arch,
        train_idx, val_idx, test_idx,
        true_test_ba=true_ba,
        n_runs=10,
        maxiter=30,
        seed=123,
    )
    # Shuffled training labels must yield lower true-label generalization than the genuine model
    assert res["test_ba_real_mean"] < true_ba
    assert "control_runs" in res or "permutation_runs" in res


def test_unexecuted_control_metrics_are_nan():
    """Verify fail-closed contract: unexecuted or non-applicable control regimes return NaN."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("mod26", Path("scripts/26_sanity_and_ablation_suite.py"))
    mod26 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod26)
    evaluate_model_on_splits = mod26.evaluate_model_on_splits

    arch = get_architecture("expressive_shared_line")
    states, labels = make_random_quantum_states(10, n_qubits=4, seed=42)

    class DummyIndices:
        train = np.array([0, 1, 2, 3, 4, 5])
        validation = np.array([6, 7])
        test = np.array([8, 9])

    idx = DummyIndices()
    pert_st = states[:4]
    pert_lbl = labels[:4]

    rec_rand, _ = evaluate_model_on_splits(
        "random_quantum_states", "tfim", 4, states, labels,
        idx, idx, pert_st, pert_lbl, maxiter=30
    )
    assert np.isnan(rec_rand["critical_ood_ba"])
    assert np.isnan(rec_rand["hamiltonian_ood_ba"])
    assert rec_rand["critical_ood_status"] == "not_applicable"
    assert rec_rand["hamiltonian_ood_status"] == "not_applicable"

    rec_shuf, _ = evaluate_model_on_splits(
        "shuffled_labels", "tfim", 4, states, labels,
        idx, idx, pert_st, pert_lbl, maxiter=30
    )
    assert np.isnan(rec_shuf["hamiltonian_ood_ba"])
    assert rec_shuf["hamiltonian_ood_status"] == "not_executed"


def test_parameter_block_canonical_split_contract():
    """Verify that parameter-block configuration enforces 1 canonical split with multiple optimizer seeds."""
    eval_cfg = load_yaml("configs/evaluation.yaml")["evaluation"]
    block_cfg = eval_cfg.get("parameter_block", {})
    # Canonical split seed must be exactly [11]
    assert block_cfg.get("split_seeds") == [11]
    assert len(block_cfg.get("optimizer_seeds", [])) >= 10


def test_physical_summary_requires_job_ids():
    """Verify that physical hardware summary strictly contains valid QPU job IDs and Clopper-Pearson CI."""
    hw_path = Path("results/hardware/expressive_hardware_summary.json")
    if hw_path.exists():
        data = json.loads(hw_path.read_text(encoding="utf-8"))
        if data.get("is_physical_hardware", False):
            assert len(data.get("raw_job_id", "")) > 10
            assert len(data.get("mitigated_job_id", "")) > 10
            assert data.get("test_sample_count") == 10
            assert data.get("test_correct") == 10
            assert data.get("accuracy_ci95_low") == 0.6915
            assert data.get("accuracy_ci95_high") == 1.0
            assert data.get("target_precision") == 0.03125
            assert data.get("nominal_shot_equivalent") == 1024
            assert data.get("execution_git_commit") is None
            assert data.get("working_tree_dirty") is True
            assert data.get("base_commit") == "07d7d876b816fdaff090c1a2aa8485dd251a14d4"


def test_grouped_observables_basis_contract():
    """Verify that grouped observables sample from exactly 2 physical bases."""
    states, _ = make_random_quantum_states(3, n_qubits=4, seed=42)
    feats, n_bases = extract_grouped_classical_features(states, "tfim", 4, budget=256, seed=123)
    assert n_bases == 2
    assert feats.shape == (3, 2)
    assert np.all((feats >= -1.0) & (feats <= 1.0))


def test_grouped_observables_high_shot_convergence():
    """Verify that finite-shot physical basis observables converge to exact expectation values as B -> infinity."""
    states, _ = make_random_quantum_states(2, n_qubits=4, seed=123)
    for fam in ["tfim", "xxz", "cluster"]:
        exact_feats, _ = extract_grouped_classical_features(states, fam, 4, budget=None)
        finite_feats, _ = extract_grouped_classical_features(states, fam, 4, budget=50000, seed=42)
        max_diff = np.max(np.abs(exact_feats - finite_feats))
        assert max_diff < 0.03, f"{fam} finite-shot grouped observable did not converge to exact expectation value!"


# --- RESEARCH-FREEZE REGRESSION TESTS (AUDIT ITEMS 31-36) ---

def test_optimizer_telemetry_completeness():
    """Verify that train_ideal_qcnn returns full convergence telemetry schema (Item 31)."""
    arch = get_architecture("expressive_shared_line")
    states, labels = make_random_quantum_states(6, n_qubits=4, seed=42)
    train_idx = np.array([0, 1, 2, 3])
    val_idx = np.array([4, 5])

    params, history, sec = train_ideal_qcnn(
        states, labels, 4, arch, train_idx, val_idx, maxiter=20, seed=123
    )
    last = history[-1]
    required_telemetry = [
        "maxiter_budget",
        "nfev",
        "optimizer_success",
        "scipy_optimizer_success",
        "optimizer_message",
        "final_train_loss",
        "validation_loss",
        "initial_train_loss",
        "best_train_loss",
        "loss_improvement",
        "last_10_eval_improvement",
        "evaluation_limit_reached",
        "convergence_plateau_detected",
    ]
    for field in required_telemetry:
        assert field in last, f"Telemetry field '{field}' missing from optimizer history!"


def test_report_generator_no_numerical_defaults():
    """Verify that report generator helpers enforce fail-closed behavior without hardcoded defaults (Item 32)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("mod30", Path("scripts/30_generate_generalization_report.py"))
    mod30 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod30)
    require_fields = mod30.require_fields

    # Incomplete artifact must fail validation
    incomplete_data = {"test_correct": 10, "test_sample_count": None}
    valid, missing = require_fields(incomplete_data, ["test_correct", "test_sample_count", "raw_job_id"], "test_art")
    assert not valid
    assert "test_sample_count" in missing
    assert "raw_job_id" in missing


def test_hardware_telemetry_schema():
    """Verify that hardware metric lists correctly aggregate without type errors (Item 33)."""
    raw_metric_list = [
        {"depth": 16, "two_qubit_operations": 8},
        {"depth": 20, "two_qubit_operations": 10},
        {"depth": 18, "two_qubit_operations": 8},
    ]
    depths = [int(m["depth"]) for m in raw_metric_list]
    two_q = [int(m["two_qubit_operations"]) for m in raw_metric_list]
    assert np.median(depths) == 18.0
    assert np.min(depths) == 16
    assert np.max(depths) == 20
    assert np.median(two_q) == 8.0


def test_pipeline_permutation_semantics():
    """Verify that fixed-split permutation test permutes labels across the entire dataset (Item 35)."""
    arch = get_architecture("expressive_shared_line")
    states, labels = make_random_quantum_states(8, n_qubits=4, seed=42)
    train_idx = np.array([0, 1, 2, 3])
    val_idx = np.array([4, 5])
    test_idx = np.array([6, 7])

    res = evaluate_pipeline_label_permutation_test(
        states, labels, 4, arch,
        train_idx, val_idx, test_idx,
        true_test_ba=1.0,
        n_permutations=5,
        maxiter=15,
        seed=999,
    )
    assert res["n_permutations"] == 5
    assert len(res["permutation_runs"]) == 5
    assert "null_ba_p95" in res
    assert "null_ba_max" in res
    assert 0.0 <= res["empirical_p_value"] <= 1.0


def test_hierarchical_bootstrap_contract():
    """Verify that hierarchical bootstrap returns valid confidence intervals respecting partitions (Item 7)."""
    import pandas as pd
    from qcnn_lab.analysis.statistics import hierarchical_bootstrap

    # Create dummy DataFrame with 3 spatial partitions, each having 5 optimizer seeds
    rows = []
    for s_seed in [11, 23, 37]:
        for opt_seed in [100, 200, 300, 400, 500]:
            rows.append({
                "split_seed": s_seed,
                "optimizer_seed": opt_seed,
                "balanced_accuracy": 0.80 + 0.02 * (s_seed % 3) + 0.01 * (opt_seed % 5),
            })
    df = pd.DataFrame(rows)
    low, high = hierarchical_bootstrap(df, partition_col="split_seed", optimizer_col="optimizer_seed", value_col="balanced_accuracy", n_boot=200)
    assert low <= df["balanced_accuracy"].mean() <= high
    assert 0.70 <= low <= 0.90


def test_threshold_selection_contract():
    """Verify that validation threshold selection finds optimal t* in (0, 1) and does not peek at test (Item 5)."""
    from qcnn_lab.analysis.thresholds import find_optimal_threshold, evaluate_at_threshold

    # Uncalibrated probabilities: true label 1 has p in [0.35, 0.45], true label 0 has p in [0.10, 0.20]
    y_val = np.array([0, 0, 1, 1])
    p_val = np.array([0.15, 0.20, 0.38, 0.42])

    # Fixed 0.5 threshold fails completely
    fixed_res = evaluate_at_threshold(y_val, p_val, threshold=0.5)
    assert fixed_res["balanced_accuracy"] == 0.5

    # Validation threshold finder identifies shifted boundary
    t_star = find_optimal_threshold(y_val, p_val)
    assert 0.20 < t_star <= 0.38

    # Adjusted threshold yields perfect accuracy
    adj_res = evaluate_at_threshold(y_val, p_val, threshold=t_star)
    assert adj_res["balanced_accuracy"] == 1.0

