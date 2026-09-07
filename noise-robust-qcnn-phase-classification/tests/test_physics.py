import numpy as np

from qcnn_lab.physics.hamiltonians import cluster_ising_hamiltonian, tfim_hamiltonian, xxz_hamiltonian
from qcnn_lab.physics.states import ground_state


def test_hamiltonians_are_hermitian():
    for H in (tfim_hamiltonian(4, h=0.5), xxz_hamiltonian(4, delta=1.2), cluster_ising_hamiltonian(4, h=0.8)):
        assert np.allclose(H.toarray(), H.toarray().conj().T)


def test_ground_state_normalizes():
    _, state = ground_state(tfim_hamiltonian(4, h=0.8))
    assert np.isclose(np.linalg.norm(state), 1.0)


def test_state_ordering_roundtrip():
    n = 4
    rng = np.random.default_rng(123)
    psi = rng.normal(size=2**n) + 1j * rng.normal(size=2**n)
    psi /= np.linalg.norm(psi)
    from qcnn_lab.physics.states import physics_to_qiskit_state, qiskit_to_physics_state
    qiskit_psi = physics_to_qiskit_state(psi, n)
    restored = qiskit_to_physics_state(qiskit_psi, n)
    assert np.allclose(psi, restored)


def test_state_ordering_basis_mapping():
    """Verify that |1000> in physics (site 0 is 1) maps to index 1 in Qiskit (qubit 0 is 1)."""
    from qcnn_lab.physics.states import physics_to_qiskit_state
    n = 4
    # Physics basis state |1000>: site 0 = 1, sites 1,2,3 = 0. Index is 1 * 2^3 = 8
    psi = np.zeros(2**n, dtype=complex)
    psi[8] = 1.0
    q_psi = physics_to_qiskit_state(psi, n)
    # In Qiskit, qubit 0 is rightmost in bitstring |q3 q2 q1 q0>. So site 0 -> qubit 0.
    # Bitstring is |0001>, which is index 1 in standard binary integer.
    assert np.isclose(q_psi[1], 1.0)
    assert np.isclose(np.sum(np.abs(q_psi)), 1.0)