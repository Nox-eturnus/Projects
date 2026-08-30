from dataclasses import dataclass
from math import sqrt

import sinter


@dataclass(frozen=True)
class BinomialEstimate:
    failures: int
    shots: int
    p_hat: float
    low: float
    high: float


def wilson_interval(
    failures: int,
    shots: int,
    z: float = 1.959963984540054,
) -> BinomialEstimate:
    if shots <= 0:
        raise ValueError(
            "shots must be positive"
        )

    if not 0 <= failures <= shots:
        raise ValueError(
            "failures must be between 0 and shots"
        )

    p = failures / shots

    denom = 1 + z**2 / shots

    centre = (
        p + z**2 / (2 * shots)
    ) / denom

    half = (
        z
        * sqrt(
            p * (1 - p) / shots
            + z**2 / (4 * shots**2)
        )
        / denom
    )

    return BinomialEstimate(
        failures=failures,
        shots=shots,
        p_hat=p,
        low=max(
            0.0,
            centre - half,
        ),
        high=min(
            1.0,
            centre + half,
        ),
    )


def per_round_logical_error(
    shot_error_rate: float,
    rounds: int,
) -> float:
    return float(
        sinter.shot_error_rate_to_piece_error_rate(
            shot_error_rate,
            pieces=rounds,
        )
    )
