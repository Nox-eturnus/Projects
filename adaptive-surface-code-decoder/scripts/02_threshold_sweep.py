import os

import sinter
import stim


DISTANCES = [
    3,
    5,
    7,
    9,
    11,
]

P_VALUES = [
    0.002,
    0.003,
    0.004,
    0.005,
    0.006,
    0.007,
    0.008,
    0.009,
    0.010,
]


def make_tasks():
    for p in P_VALUES:
        for d in DISTANCES:
            circuit = stim.Circuit.generated(
                "surface_code:rotated_memory_x",
                distance=d,
                rounds=d,
                after_clifford_depolarization=p,
                after_reset_flip_probability=p,
                before_measure_flip_probability=p,
                before_round_data_depolarization=p,
            )

            yield sinter.Task(
                circuit=circuit,
                json_metadata={
                    "p": p,
                    "d": d,
                    "rounds": d,
                    "basis": "x",
                    "noise_model": (
                        "uniform_circuit_level"
                    ),
                },
            )


def main():
    workers = max(
        1,
        (os.cpu_count() or 2) - 1,
    )

    stats = sinter.collect(
        num_workers=workers,
        tasks=make_tasks(),
        decoders=["pymatching"],
        max_shots=2_000_000,
        max_errors=1_000,
        print_progress=True,
        save_resume_filepath=(
            "results/threshold/"
            "pymatching.csv"
        ),
    )

    print(sinter.CSV_HEADER)

    for stat in stats:
        print(stat.to_csv_line())


if __name__ == "__main__":
    main()