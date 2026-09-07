from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from qcnn_lab.config import load_yaml


def _table(path: str, columns: list[str] | None = None) -> str:
    p = Path(path)

    if not p.exists():
        return "_Not generated in this run._"

    frame = pd.read_csv(p)

    if columns is not None:
        columns = [c for c in columns if c in frame.columns]
        frame = frame[columns]

    return frame.to_markdown(index=False)


def _json(path: str):
    p = Path(path)

    if not p.exists():
        return None

    return json.loads(p.read_text(encoding="utf-8"))


def _json_block(value) -> str:
    return "```json\n" + json.dumps(value, indent=2) + "\n```"


def main():
    hardware_gap = _json(
        "results/hardware/sim_to_hardware_gap.json"
    )
    hw_jobs = _json(
        "results/hardware/hardware_jobs.json"
    )

    if hardware_gap is not None and hw_jobs is not None:
        hardware_status = (
            "Real-QPU hardware-transfer outputs are present."
        )
    else:
        hardware_status = (
            "Real-QPU hardware-transfer outputs are not present; "
            "run Phases 15-18 before making a "
            "hardware-transfer-complete claim."
        )

    sections = []

    cfg = load_yaml("configs/project.yaml")
    primary_arch = cfg.get("qcnn", {}).get("architecture", "expressive_shared_line")
    n_qubits = int(cfg.get("n_qubits", 8))

    tfim_ideal = _json("results/ideal/tfim_ideal_summary.json")
    primary_params = (
        tfim_ideal.get("parameters") if isinstance(tfim_ideal, dict) else None
    )
    primary_params_str = (
        f"{primary_params} variational parameters"
        if primary_params is not None
        else "parameters: Not available"
    )

    # Dynamic lookup for light_shared_line baseline params (fail-closed if missing)
    arch_sweep_p = Path("results/architectures/architecture_sweep.csv")
    light_params = None
    if arch_sweep_p.exists():
        sweep_df = pd.read_csv(arch_sweep_p)
        match = sweep_df[sweep_df["architecture"] == "light_shared_line"]
        if not match.empty and "parameters" in match.columns:
            light_params = int(match.iloc[0]["parameters"])
    light_params_str = (
        f"{light_params} variational parameters"
        if light_params is not None
        else "parameters: Not available"
    )

    # Dynamic lookup for hardware demonstration (fail-closed if missing)
    hw_summary = _json("results/hardware/hardware4_summary.json")
    hw_backend = (
        hw_jobs.get("backend") if isinstance(hw_jobs, dict) else None
    )
    hw_arch = (
        hw_jobs.get("architecture")
        if isinstance(hw_jobs, dict) and hw_jobs.get("architecture")
        else (hw_summary.get("architecture") if isinstance(hw_summary, dict) else None)
    )
    hw_n_qubits = (
        hw_summary.get("n_qubits")
        if isinstance(hw_summary, dict) and hw_summary.get("n_qubits")
        else (hw_jobs.get("n_qubits") if isinstance(hw_jobs, dict) else None)
    )

    hw_backend_str = f"`{hw_backend}`" if hw_backend else "Not available"
    hw_arch_str = f"`{hw_arch}`" if hw_arch else "Not available"
    hw_qubits_str = f"$N={hw_n_qubits}$" if hw_n_qubits else "qubits: Not available"

    sections.append(
        "# Noise-Robust QCNN for Quantum Phase and State Classification "
        "— Research Report\n"
    )

    sections.append(
        f"""
### Architecture & Provenance Summary
- **Primary N={n_qubits} QCNN Architecture:** `{primary_arch}` ({primary_params_str} across 3 scale-reduction rounds).
- **Baseline / Negative Result Architecture:** `light_shared_line` ({light_params_str}; demonstrated limited block expressivity / architecture-task mismatch across the evaluated phase-classification tasks).
- **Physical Hardware Demonstration Architecture:** {hw_arch_str} executed at {hw_qubits_str} qubits on {hw_backend_str} (retaining valid real-device calibration and proof-of-hardware execution).
"""
    )

    sections.append(
        """
## Claim boundary

This repository studies whether a QCNN provides a useful **inductive bias, parameter-efficiency profile, and noise-robustness envelope** for quantum-native state classification. It does **not** claim generic quantum advantage over classical machine learning.

Classical baselines are labelled by information access. In particular, the MPS prototype receives the full simulated statevector, whereas SVM/MLP/CNN baselines receive local observable maps. Those results must not be collapsed into an information-access-blind leaderboard.
"""
    )

    sections.append(
        "\n## Multi-family phase classification and transition generalization\n\n"
    )

    sections.append(
        _table(
            "results/generalization/transition_summary.csv",
            [
                "family",
                "architecture",
                "accuracy",
                "balanced_accuracy",
                "raw_p05_crossing",
                "raw_crossing_bracketed",
                "transition_detected",
                "validated_p05_crossing",
                "probability_span",
                "qcnn_steepest_change",
                "physical_diagnostic_steepest_change",
                "thermodynamic_reference_critical",
            ],
        )
    )

    sections.append(
        """

For finite systems, the learned or diagnostic crossover need not equal the thermodynamic-limit critical point. The transition sweep is therefore a **generalization/crossover diagnostic**, not a finite-size proof of an exact critical point.

## Architecture trade-offs

"""
    )

    sections.append(
        _table(
            "results/architectures/architecture_sweep.csv",
            [
                "family",
                "architecture",
                "parameters",
                "depth",
                "two_qubit_operations",
                "accuracy",
                "balanced_accuracy",
                "training_seconds",
            ],
        )
    )

    sections.append(
        "\n\n## Quantum baseline\n\n"
    )

    sections.append(
        _table(
            "results/baselines/vqc_baseline.csv"
        )
    )

    sections.append(
        "\n\n## Classical baselines\n\n"
    )

    sections.append(
        _table(
            "results/baselines/classical_baselines.csv"
        )
    )

    sections.append(
        "\n\n## Sample-efficiency / training-data regime\n\n"
    )

    sections.append(
        _table(
            "results/statistics/sample_efficiency_summary.csv"
        )
    )

    sections.append(
        "\n\n## Noise robustness of ideal-trained QCNN\n\n"
    )

    sections.append(
        _table(
            "results/noise/ideal_trained_robustness.csv"
        )
    )

    sections.append(
        "\n\nRobustness threshold definition and result:\n\n"
    )

    threshold = _json(
        "results/noise/ideal_robustness_threshold.json"
    )

    sections.append(
        _json_block(threshold)
    )

    sections.append(
        "\n\n## Noise-aware training and unseen-noise transfer\n\n"
    )

    sections.append(
        _table(
            "results/noise/unseen_noise_transfer.csv"
        )
    )

    sections.append("\n\n")

    threshold_comparison = _json(
        "results/noise/noise_aware_threshold_comparison.json"
    )

    sections.append(
        _json_block(threshold_comparison)
    )

    sections.append(
        "\n\n## Repeated-seed statistics\n\n"
    )

    sections.append(
        _table(
            "results/statistics/repeated_seed_summary.csv"
        )
    )

    sections.append(
        "\n\n## Device-derived simulation transfer\n\n"
    )

    sections.append(
        _table(
            "results/hardware/device_noise_transfer.csv"
        )
    )

    hw_comp = _json("results/hardware/hardware4_comparison.json")
    if hw_comp is not None:
        sections.append("\n\n### N=4 Simulation Architecture Comparison\n\n")
        sections.append(_json_block(hw_comp))

    sections.append(
        "\n\n## Real-QPU simulation-to-hardware gap\n\n"
    )

    sections.append(
        "**Status:** " + hardware_status + "\n\n"
    )

    if hardware_gap is None:
        sections.append(
            _json_block({})
        )
    else:
        sections.append(
            _json_block(hardware_gap)
        )

    sections.append(
        """

## Required interpretation

1. Report accuracy together with parameter count, circuit depth, two-qubit-operation count, training time, and circuit-evaluation burden.
2. Do not infer quantum advantage from a QCNN win against a baseline with a different information-access regime.
3. Separate synthetic classifier-noise experiments from device-derived/full state-preparation experiments.
4. Treat the N=4 hardware branch as proof of hardware transfer, not as evidence that arbitrary exact many-body state preparation is scalable.
5. Report negative results. If a larger/deeper QCNN degrades faster under noise, that is a central engineering result rather than a failed experiment.
"""
    )

    report = "".join(sections)

    out = Path("results/report")
    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_path = out / "research_report.md"

    report_path.write_text(
        report,
        encoding="utf-8",
    )

    print(report)
    print()
    print("Research report generation completed")
    print(f"Report written to: {report_path}")


if __name__ == "__main__":
    main()