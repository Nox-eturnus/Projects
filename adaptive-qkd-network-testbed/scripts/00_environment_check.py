import platform
import sys

import cryptography
import fastapi
import networkx
import numpy
import pandas
import scipy
import yaml


def main():
    print("Python:", sys.version)
    print("Platform:", platform.platform())
    print("NumPy:", numpy.__version__)
    print("SciPy:", scipy.__version__)
    print("Pandas:", pandas.__version__)
    print("NetworkX:", networkx.__version__)
    print("FastAPI:", fastapi.__version__)
    print("cryptography:", cryptography.__version__)
    print("PyYAML:", yaml.__version__)
    print("Environment check PASSED")


if __name__ == "__main__":
    main()