from qcnn_lab.config import load_yaml
from qcnn_lab.physics.datasets import default_specs, save_task_dataset


def main():
    cfg = load_yaml("configs/project.yaml")
    spec = default_specs(int(cfg["n_qubits"]))["tfim"]
    save_task_dataset(
        "data/processed",
        spec,
        samples_per_class=int(cfg["samples_per_class"]),
        transition_points=int(cfg["transition_points"]),
        seed=int(cfg["seed"]),
    )
    print("TFIM dataset written")


if __name__ == "__main__":
    main()