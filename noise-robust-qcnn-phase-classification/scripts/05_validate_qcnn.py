import json
from pathlib import Path

from qcnn_lab.qcnn.architecture import get_architecture, parameter_count, raw_circuit_metrics


def main():
    Path("results/architectures").mkdir(parents=True, exist_ok=True)
    rows = []
    for n in (4, 8, 16, 32):
        for name in ("light_shared_line", "light_shared_ring", "expressive_shared_line", "light_unshared_line"):
            arch = get_architecture(name)
            metrics = raw_circuit_metrics(n, arch)
            metrics["name"] = name
            rows.append(metrics)
            print(metrics)
    for n in (4, 8, 16, 32):
        shared = parameter_count(n, get_architecture("light_shared_line"))
        assert shared == 6 * (n.bit_length() - 1)
    assert parameter_count(8, get_architecture("light_shared_line")) < parameter_count(8, get_architecture("light_unshared_line"))
    Path("results/architectures/raw_metrics.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print("QCNN structure validation completed")


if __name__ == "__main__":
    main()