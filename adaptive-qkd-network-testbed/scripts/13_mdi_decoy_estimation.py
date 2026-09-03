from qkd_lab.estimation.confidence import ProbabilityInterval
from qkd_lab.estimation.mdi_decoy_lp import estimate_mdi_bounds
from qkd_lab.protocols.mdi_qkd import MDIPhysicalParameters, mdi_coherent_gain, mdi_coherent_qber, mdi_n_m_error_yield, mdi_n_m_yield


def main():
    physical = MDIPhysicalParameters(20.0, 20.0, 0.2, 0.6, 1e-7, 0.015)
    pairs = [(0.4, 0.4), (0.4, 0.1), (0.1, 0.4), (0.1, 0.1), (0.4, 0.0002), (0.0002, 0.4), (0.1, 0.0002), (0.0002, 0.1), (0.0002, 0.0002)]
    gains = []
    errors = []
    for a, b in pairs:
        q = mdi_coherent_gain(a, b, physical)
        t = q * mdi_coherent_qber(a, b, physical)
        gains.append(ProbabilityInterval(q, q))
        errors.append(ProbabilityInterval(t, t))
    bounds = estimate_mdi_bounds(pairs, gains, errors, n_max=7)
    true_y11 = mdi_n_m_yield(1, 1, physical)
    true_e11 = mdi_n_m_error_yield(1, 1, physical) / true_y11
    print("true Y11:", true_y11, "lower:", bounds.y11_lower)
    print("true e11:", true_e11, "upper:", bounds.e11_upper)
    assert bounds.y11_lower <= true_y11 + 1e-12
    assert bounds.e11_upper + 1e-12 >= true_e11
    print("MDI decoy LP validation PASSED")


if __name__ == "__main__":
    main()