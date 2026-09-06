import json
from dataclasses import asdict
from pathlib import Path

from qcnn_lab.hardware.ibm import choose_backends, snapshot_backend


def main():
    backends = choose_backends(min_qubits=4, count=2)
    snapshots = [asdict(snapshot_backend(b)) for b in backends]
    out = Path("results/hardware"); out.mkdir(parents=True, exist_ok=True)
    (out / "backend_snapshot.json").write_text(json.dumps(snapshots, indent=2), encoding="utf-8")
    print(json.dumps(snapshots, indent=2))
    print("IBM backend snapshot PASSED")


if __name__ == "__main__":
    main()