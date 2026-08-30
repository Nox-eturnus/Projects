from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter_ns

import numpy as np
import psutil


@dataclass(frozen=True)
class LatencyStats:
    decoder: str
    samples: int
    mean_us: float
    p50_us: float
    p95_us: float
    p99_us: float
    max_us: float
    throughput_per_s: float
    rss_mb_before: float
    rss_mb_after: float


def benchmark_single_shot_latency(
    decoder,
    dets: np.ndarray,
    warmup: int = 100,
) -> LatencyStats:
    if len(dets) <= warmup:
        raise ValueError(
            "Need more samples than warmup."
        )

    process = psutil.Process()

    rss_before = (
        process.memory_info().rss
        / (1024**2)
    )

    for row in dets[:warmup]:
        decoder.decode(row)

    latencies_ns = []

    for row in dets[warmup:]:
        start = perf_counter_ns()
        decoder.decode(row)
        end = perf_counter_ns()

        latencies_ns.append(
            end - start
        )

    rss_after = (
        process.memory_info().rss
        / (1024**2)
    )

    x_us = (
        np.asarray(
            latencies_ns,
            dtype=float,
        )
        / 1000.0
    )

    total_seconds = (
        np.sum(x_us) / 1e6
    )

    return LatencyStats(
        decoder=decoder.name,
        samples=len(x_us),
        mean_us=float(
            np.mean(x_us)
        ),
        p50_us=float(
            np.percentile(x_us, 50)
        ),
        p95_us=float(
            np.percentile(x_us, 95)
        ),
        p99_us=float(
            np.percentile(x_us, 99)
        ),
        max_us=float(
            np.max(x_us)
        ),
        throughput_per_s=float(
            len(x_us) / total_seconds
        ),
        rss_mb_before=rss_before,
        rss_mb_after=rss_after,
    )


def benchmark_batch_throughput(
    decoder,
    dets: np.ndarray,
    repeats: int = 10,
) -> float:
    decoder.decode_batch(
        dets[
            : min(
                100,
                len(dets),
            )
        ]
    )

    start = perf_counter_ns()

    total_shots = 0

    for _ in range(repeats):
        decoder.decode_batch(dets)
        total_shots += len(dets)

    end = perf_counter_ns()

    seconds = (
        end - start
    ) / 1e9

    return total_shots / seconds