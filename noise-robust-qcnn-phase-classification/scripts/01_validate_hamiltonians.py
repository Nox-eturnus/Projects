import numpy as np

from qcnn_lab.physics.hamiltonians import cluster_ising_hamiltonian, tfim_hamiltonian, xxz_hamiltonian
from qcnn_lab.physics.states import ground_state


def main():
    for name, H in {
        "tfim": tfim_hamiltonian(4, h=0.5),
        "xxz": xxz_hamiltonian(4, delta=1.5),
        "cluster": cluster_ising_hamiltonian(4, h=0.5),
    }.items():
        dense = H.toarray()
        assert np.allclose(dense, dense.conj().T)
        energy, state = ground_state(H)
        assert np.isclose(np.linalg.norm(state), 1.0)
        residual = np.linalg.norm(dense @ state - energy * state)
        assert residual < 1e-7
        print(name, "E0=", energy, "residual=", residual)
    print("Hamiltonian validation PASSED")


if __name__ == "__main__":
    main()