import os

import sinter
import stim

from ldpc.sinter_decoders import (
    SinterBeliefFindDecoder,
    SinterBpOsdDecoder,
)


DISTANCES = [
    3,
    5,
    7,
    9,
]

P_VALUES = [
    0.002,
    0.004,
    0.006,
    0.008,
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
                },
            )


def main():
    custom_decoders = {
        "bp_osd": SinterBpOsdDecoder(
            max_iter=10,
            bp_method="ms",
            ms_scaling_factor=0.625,
            schedule="parallel",
            osd_method="osd0",
        ),
        "belief_find": (
            SinterBeliefFindDecoder(
                max_iter=10,
                bp_method="ms",
                ms_scaling_factor=0.625,
                schedule="parallel",
            )
        ),
    }

    stats = sinter.collect(
        num_workers=max(
            1,
            (os.cpu_count() or 2) - 1,
        ),
        tasks=make_tasks(),
        decoders=[
            "pymatching",
            "pymatching-correlated",
            "bp_osd",
            "belief_find",
        ],
        custom_decoders=custom_decoders,
        max_shots=500_000,
        max_errors=500,
        save_resume_filepath=(
            "results/"
            "decoder_comparison/"
            "decoder_comparison.csv"
        ),
        print_progress=True,
    )

    print(sinter.CSV_HEADER)

    for stat in stats:
        print(stat.to_csv_line())


if __name__ == "__main__":
    main()