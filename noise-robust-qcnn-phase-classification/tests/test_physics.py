import numpy as np

from qcnn_lab.physics.hamiltonians import cluster_ising_hamiltonian, tfim_hamiltonian, xxz_hamiltonian
from qcnn_lab.physics.states import ground_state


def test_hamiltonians_are_hermitian():
    for H in (tfim_hamiltonian(4, h=0.5), xxz_hamiltonian(4, delta=1.2), cluster_ising_hamiltonian(4, h=0.8)):
        assert np.allclose(H.toarray(), H.toarray().conj().T)


def test_ground_state_normalizes():
    _, state = ground_state(tfim_hamiltonian(4, h=0.8))
    assert np.isclose(np.linalg.norm(state), 1.0)