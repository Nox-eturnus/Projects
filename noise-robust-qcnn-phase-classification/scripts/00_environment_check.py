import platform
import sys

import numpy
import pandas
import scipy
import sklearn
import torch
import yaml

try:
    import qiskit
    import qiskit_aer
    import qiskit_ibm_runtime
except Exception as exc:
    raise SystemExit(f"Qiskit stack import failed: {exc}")


def main():
    print("Python:", sys.version)
    print("Platform:", platform.platform())
    print("NumPy:", numpy.__version__)
    print("SciPy:", scipy.__version__)
    print("Pandas:", pandas.__version__)
    print("scikit-learn:", sklearn.__version__)
    print("PyTorch:", torch.__version__)
    print("Qiskit:", qiskit.__version__)
    print("Qiskit Aer:", qiskit_aer.__version__)
    print("Qiskit IBM Runtime:", qiskit_ibm_runtime.__version__)
    print("PyYAML:", yaml.__version__)
    print("Environment check completed")


if __name__ == "__main__":
    main()