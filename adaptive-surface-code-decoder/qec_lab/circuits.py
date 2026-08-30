from dataclasses import dataclass

import stim


@dataclass(frozen=True)
class NoiseParameters:
    p_gate: float
    p_reset: float
    p_measure: float
    p_idle: float


def make_rotated_memory_circuit(
    distance: int,
    rounds: int,
    noise: NoiseParameters,
    basis: str = "x",
) -> stim.Circuit:
    if distance < 3 or distance % 2 == 0:
        raise ValueError(
            "Use odd surface-code distance >= 3."
        )

    if rounds < 1:
        raise ValueError("rounds must be >= 1")

    if basis not in {"x", "z"}:
        raise ValueError(
            "basis must be 'x' or 'z'"
        )

    task = f"surface_code:rotated_memory_{basis}"

    return stim.Circuit.generated(
        task,
        distance=distance,
        rounds=rounds,
        after_clifford_depolarization=noise.p_gate,
        after_reset_flip_probability=noise.p_reset,
        before_measure_flip_probability=noise.p_measure,
        before_round_data_depolarization=noise.p_idle,
    )


def make_uniform_noise(
    p: float,
) -> NoiseParameters:
    return NoiseParameters(
        p_gate=p,
        p_reset=p,
        p_measure=p,
        p_idle=p,
    )