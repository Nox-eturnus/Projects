import platform
import sys

import numpy
import pymatching
import sinter
import stim


def main():
    print("Python:", sys.version)
    print("Platform:", platform.platform())
    print("NumPy:", numpy.__version__)
    print("Stim:", stim.__version__)
    print("Sinter:", sinter.__version__)
    print("PyMatching:", pymatching.__version__)

    major_minor = tuple(
        map(int, stim.__version__.split(".")[:2])
    )

    assert major_minor >= (1, 16)

    print("Environment check PASSED")


if __name__ == "__main__":
    main()