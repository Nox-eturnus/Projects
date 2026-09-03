from qkd_lab.math_utils import h2, poisson_tail, poisson_vector


def main():
    assert h2(0.0) == 0.0
    assert abs(h2(0.5) - 1.0) < 1e-12
    assert abs(poisson_vector(0.5, 30).sum() - 1.0) < 1e-12
    assert poisson_tail(0.5, 30) < 1e-12
    print("Math validation PASSED")


if __name__ == "__main__":
    main()