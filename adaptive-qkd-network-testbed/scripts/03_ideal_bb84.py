from qkd_lab.protocols.ideal_bb84 import simulate_ideal_bb84


def main():
    noiseless = simulate_ideal_bb84(200_000, seed=1)
    attacked = simulate_ideal_bb84(500_000, intercept_resend_fraction=1.0, seed=2)
    biased = simulate_ideal_bb84(200_000, p_x_alice=0.9, p_x_bob=0.9, seed=3)
    print("Noiseless:", noiseless)
    print("Full intercept-resend:", attacked)
    print("Biased basis:", biased)
    assert noiseless.qber == 0.0
    assert abs(attacked.qber - 0.25) < 0.01
    expected_biased = 0.9 * 0.9 + 0.1 * 0.1
    assert abs(biased.sifting_fraction - expected_biased) < 0.01
    print("Ideal BB84 sanity PASSED")


if __name__ == "__main__":
    main()