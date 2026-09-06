from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

from qcnn_lab.config import load_yaml
from qcnn_lab.noise.models import build_noise_model, noise_specs_from_config


def p1(noise_model=None):
    qc = QuantumCircuit(1, 1); qc.x(0); qc.measure(0, 0)
    backend = AerSimulator(noise_model=noise_model)
    counts = backend.run(qc, shots=5000, seed_simulator=11).result().get_counts()
    return counts.get("1", 0) / 5000


def main():
    specs = noise_specs_from_config(load_yaml("configs/noise.yaml"))
    ideal = p1()
    noisy = p1(build_noise_model(specs["mixed_training_b"]))
    print("ideal |1> readout:", ideal)
    print("noisy |1> readout:", noisy)
    assert ideal > 0.99
    assert noisy < ideal
    print("Noise-model validation PASSED")


if __name__ == "__main__":
    main()