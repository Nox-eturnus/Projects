from qcnn_lab.config import load_yaml
from qcnn_lab.physics.datasets import default_specs, save_task_dataset


def main():
    cfg = load_yaml("configs/project.yaml")
    specs = default_specs(int(cfg["n_qubits"]))
    for offset, family in enumerate(("xxz", "cluster"), start=1):
        save_task_dataset(
            "data/processed",
            specs[family],
            samples_per_class=int(cfg["samples_per_class"]),
            transition_points=int(cfg["transition_points"]),
            seed=int(cfg["seed"]) + offset,
        )
        print(family, "dataset written")


if __name__ == "__main__":
    main()