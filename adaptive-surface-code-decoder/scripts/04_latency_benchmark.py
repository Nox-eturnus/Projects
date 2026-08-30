import json
import platform
import sys
from pathlib import Path

from qec_lab.benchmarking import (
    benchmark_batch_throughput,
    benchmark_single_shot_latency,
)
from qec_lab.circuits import (
    make_rotated_memory_circuit,
    make_uniform_noise,
)
from qec_lab.decoders import (
    BPOSDDecoder,
    CorrelatedMWPMDecoder,
    MWPMDecoder,
    UnionFindSurfaceDecoder,
)


def main():
    output = Path(
        "results/decoder_comparison"
    )
    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    records = []

    for d in [
        3,
        5,
        7,
        9,
        11,
    ]:
        p = 0.005

        circuit = (
            make_rotated_memory_circuit(
                distance=d,
                rounds=d,
                noise=make_uniform_noise(
                    p
                ),
                basis="x",
            )
        )

        dem = (
            circuit.detector_error_model(
                decompose_errors=True,
            )
        )

        dets, _ = (
            circuit
            .compile_detector_sampler()
            .sample(
                shots=5000,
                separate_observables=True,
            )
        )

        decoders = [
            MWPMDecoder(dem),
            CorrelatedMWPMDecoder(
                dem
            ),
            UnionFindSurfaceDecoder(
                dem
            ),
            BPOSDDecoder(dem),
        ]

        for decoder in decoders:
            latency = (
                benchmark_single_shot_latency(
                    decoder=decoder,
                    dets=dets,
                    warmup=100,
                )
            )

            batch_throughput = (
                benchmark_batch_throughput(
                    decoder=decoder,
                    dets=dets,
                    repeats=5,
                )
            )

            record = {
                "distance": d,
                "p": p,
                "decoder": decoder.name,
                "samples": (
                    latency.samples
                ),
                "mean_us": (
                    latency.mean_us
                ),
                "p50_us": (
                    latency.p50_us
                ),
                "p95_us": (
                    latency.p95_us
                ),
                "p99_us": (
                    latency.p99_us
                ),
                "max_us": (
                    latency.max_us
                ),
                "single_shot_throughput_per_s": (
                    latency
                    .throughput_per_s
                ),
                "batch_throughput_per_s": (
                    batch_throughput
                ),
                "rss_mb_before": (
                    latency.rss_mb_before
                ),
                "rss_mb_after": (
                    latency.rss_mb_after
                ),
                "python": sys.version,
                "platform": (
                    platform.platform()
                ),
            }

            records.append(record)
            print(record)

    with open(
        output / "latency.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            records,
            f,
            indent=2,
        )


if __name__ == "__main__":
    main()