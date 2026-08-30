import stim


def main():
    circuit = stim.Circuit(
        """
        R 0
        H 0

        HERALDED_ERASE(0.01) 0
        DETECTOR rec[-1]

        M 0
        """
    )

    print(circuit)

    sampler = circuit.compile_sampler()

    samples = sampler.sample(
        shots=20
    )

    print(samples)


if __name__ == "__main__":
    main()