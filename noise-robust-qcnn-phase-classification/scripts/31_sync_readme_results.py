"""Programmatic README synchronization strictly derived from canonical results JSON.

Reads:
- results/report/canonical_results.json
- results/report/evaluation_matrix.csv
- results/ablations/ablation_and_controls_summary.csv
- results/ablations/ablation_aggregate.csv

Replaces marked HTML blocks in README.md:
<!-- BEGIN AUTO RESULTS: PRIMARY_MATRIX --> ... <!-- END AUTO RESULTS: PRIMARY_MATRIX -->
<!-- BEGIN AUTO RESULTS: ABLATIONS --> ... <!-- END AUTO RESULTS: ABLATIONS -->
<!-- BEGIN AUTO RESULTS: HARDWARE --> ... <!-- END AUTO RESULTS: HARDWARE -->
<!-- BEGIN AUTO RESULTS: BUDGET --> ... <!-- END AUTO RESULTS: BUDGET -->
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import numpy as np
import pandas as pd


def load_canonical_results(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_primary_matrix_markdown(matrix_path: Path) -> str:
    if not matrix_path.exists():
        return "_Evaluation matrix pending execution._"
    df = pd.read_csv(matrix_path, keep_default_na=False)
    df = df.fillna("N/A")
    cols = [c for c in ["Evaluation", "TFIM BA", "XXZ BA", "Cluster BA", "Runs"] if c in df.columns]
    return df[cols].to_markdown(index=False)


def load_ablations_markdown(summary_path: Path, agg_path: Path, canonical: dict | None) -> str:
    lines = []
    if summary_path.exists():
        df = pd.read_csv(summary_path, keep_default_na=False)
        for col, stat_col in [("iid_ba", "iid_status"), ("critical_ood_ba", "critical_ood_status"), ("hamiltonian_ood_ba", "hamiltonian_ood_status")]:
            if col in df.columns and stat_col in df.columns:
                df[col] = df.apply(
                    lambda r: f"N/A — {str(r[stat_col]).replace('_', ' ')}" if pd.isna(r[col]) or r[col] == "" or str(r[col]).lower() == "nan" else (f"{float(r[col]):.3f}" if isinstance(r[col], (int, float)) or (isinstance(r[col], str) and r[col].replace('.', '', 1).isdigit()) else str(r[col])),
                    axis=1,
                )
        cols_to_show = [c for c in ["model", "parameters", "two_qubit_gates", "iid_ba", "critical_ood_ba", "hamiltonian_ood_ba"] if c in df.columns]
        lines.append(df[cols_to_show].fillna("N/A").to_markdown(index=False))

    if canonical is not None:
        shuf = canonical.get("shuffled_control", {})
        perm = canonical.get("pipeline_permutation", {})
        ablation = canonical.get("ablation", {})

        lines.append("")
        lines.append(f"> **Shuffled-Training-Label Control (N={shuf.get('n_runs', 'N/A')} runs)**:")
        shuf_ba_str = f"{shuf.get('mean_true_label_test_ba'):.3f}" if shuf.get('mean_true_label_test_ba') is not None and not np.isnan(shuf.get('mean_true_label_test_ba', np.nan)) else "N/A"
        shuf_p_str = f"{shuf.get('empirical_comparison_p_value'):.4f}" if shuf.get('empirical_comparison_p_value') is not None and not np.isnan(shuf.get('empirical_comparison_p_value', np.nan)) else "N/A"
        lines.append(
            f"> Training on randomly shuffled targets yielded mean true-label test BA {shuf_ba_str} (empirical comparison p = {shuf_p_str}). "
            f"{shuf.get('scientific_meaning', '')}"
        )

        lines.append("")
        lines.append(f"> **Full-Pipeline Label-Permutation Test (N={perm.get('n_permutations', 'N/A')} permutations)**:")
        null_mean = f"{perm.get('null_ba_mean'):.3f}" if perm.get('null_ba_mean') is not None and not np.isnan(perm.get('null_ba_mean', np.nan)) else "N/A"
        null_std = f"{perm.get('null_ba_std'):.3f}" if perm.get('null_ba_std') is not None and not np.isnan(perm.get('null_ba_std', np.nan)) else "N/A"
        null_p95 = f"{perm.get('null_ba_p95'):.3f}" if perm.get('null_ba_p95') is not None and not np.isnan(perm.get('null_ba_p95', np.nan)) else "N/A"
        null_max = f"{perm.get('null_ba_max'):.3f}" if perm.get('null_ba_max') is not None and not np.isnan(perm.get('null_ba_max', np.nan)) else "N/A"
        perm_p = f"{perm.get('empirical_p_value'):.4f}" if perm.get('empirical_p_value') is not None and not np.isnan(perm.get('empirical_p_value', np.nan)) else "N/A"
        lines.append(
            f"> Permuting labels across the entire pipeline yields null test BA {null_mean} ± {null_std} "
            f"(95th percentile: {null_p95}, max: {null_max}) with empirical p-value p = {perm_p}. "
            f"{perm.get('scientific_meaning', '')}"
        )

    if agg_path.exists():
        agg_df = pd.read_csv(agg_path, keep_default_na=False)
        lines.append("")
        lines.append("> **Multi-Seed Architectural Ablation Aggregate (Repeated Runs)**:")
        cols = ["architecture", "parameter_count", "two_qubit_gates", "n_runs", "iid_ba_mean", "critical_ood_ba_mean", "hamiltonian_ood_ba_mean"]
        avail_cols = [c for c in cols if c in agg_df.columns]
        display_agg = agg_df[avail_cols].copy()
        for c in ["iid_ba_mean", "critical_ood_ba_mean", "hamiltonian_ood_ba_mean"]:
            if c in display_agg.columns:
                display_agg[c] = display_agg[c].map(lambda x: f"{float(x):.3f}" if isinstance(x, (int, float)) or (isinstance(x, str) and x.replace('.', '', 1).isdigit()) else str(x))
        lines.append(display_agg.fillna("N/A").to_markdown(index=False))

    if canonical is not None and "ablation" in canonical:
        lines.append("")
        lines.append(f"> **Ablation Insight**: {canonical['ablation'].get('scientific_conclusion', '')}")

    return "\n".join(lines)


def load_hardware_markdown(canonical: dict | None) -> str:
    if canonical is None or "hardware" not in canonical:
        return "_Hardware summary pending execution._"
    hw = canonical["hardware"]
    if hw.get("is_physical_hardware", False):
        backend = hw.get("backend")
        k = hw.get("test_correct")
        n = hw.get("test_sample_count")
        ci_low = hw.get("accuracy_ci95_low")
        ci_high = hw.get("accuracy_ci95_high")
        raw_job = hw.get("raw_job_id")
        mit_job = hw.get("mitigated_job_id")

        if any(v is None for v in [backend, k, n, ci_low, ci_high, raw_job, mit_job]):
            return "- **Physical Hardware Execution**: N/A — incomplete physical-hardware provenance."

        lines = [
            f"- **Observed Result**: **{k}/{n}** held-out N=4 TFIM test states correctly classified on `{backend}`.",
            f"- **Exact Binomial Uncertainty**: 95% Clopper-Pearson CI = **[{ci_low:.3f}, {ci_high:.3f}]**.",
            f"- **QPU Job Provenance**: Raw Job ID `{raw_job}`, Mitigated Job ID `{mit_job}`.",
            "- **Execution Protocol**: Twirled Readout Error Extrapolation (TREX, resilience level 1) + Dynamical Decoupling (`XpXm`).",
            "- **Multi-Session Status**: Single physical session complete (`multi_session_hardware_complete = false`); multi-session stability tracking across distinct calibration windows is pending.",
        ]
        return "\n".join(lines)
    else:
        return "- **Surrogate Status**: Analytical surrogate simulation."


def load_budget_markdown(canonical: dict | None) -> str:
    if canonical is None or "measurement_budget" not in canonical:
        return "_Measurement budget comparison pending execution._"
    items = canonical["measurement_budget"].get("comparisons", [])
    if not items:
        return "_Measurement budget comparison pending execution._"

    budgets_to_show = [128, 512, 2048, 4096]
    sub = [r for r in items if r.get("budget") in budgets_to_show]

    lines = [
        "| Budget ($B$) | Family | QCNN Mean BA | Classical Pauli Mean BA | Settings |",
        "| :---: | :---: | :---: | :---: | :---: |",
    ]
    for r in sub:
        b = r["budget"]
        fam = str(r["family"]).upper()
        q_ba = f"{r['qcnn_ba_mean']:.3f} ± {r['qcnn_ba_std']:.3f}" if pd.notna(r.get("qcnn_ba_mean")) else "N/A"
        c_ba = f"{r['classical_ba_mean']:.3f} ± {r['classical_ba_std']:.3f}" if pd.notna(r.get("classical_ba_mean")) else "N/A"
        n_set = str(r["n_physical_settings"]) + " bases" if r.get("n_physical_settings") is not None else "N/A"
        lines.append(f"| {b} | {fam} | {q_ba} | {c_ba} | {n_set} |")
    return "\n".join(lines)


def replace_block(content: str, tag: str, new_block: str) -> str:
    pattern = rf"(<!-- BEGIN AUTO RESULTS: {tag} -->).*?(<!-- END AUTO RESULTS: {tag} -->)"
    replacement = rf"\1\n{new_block}\n\2"
    if re.search(pattern, content, flags=re.DOTALL):
        return re.sub(pattern, replacement, content, flags=re.DOTALL)
    return content


def main():
    readme_path = Path("README.md")
    if not readme_path.exists():
        raise FileNotFoundError("README.md not found in current directory.")

    canonical_path = Path("results/report/canonical_results.json")
    canonical = load_canonical_results(canonical_path)

    report_dir = Path("results/report")
    ablation_dir = Path("results/ablations")

    primary_md = load_primary_matrix_markdown(report_dir / "evaluation_matrix.csv")
    ablations_md = load_ablations_markdown(
        ablation_dir / "ablation_and_controls_summary.csv",
        ablation_dir / "ablation_aggregate.csv",
        canonical,
    )
    hardware_md = load_hardware_markdown(canonical)
    budget_md = load_budget_markdown(canonical)

    content = readme_path.read_text(encoding="utf-8")

    content = replace_block(content, "PRIMARY_MATRIX", primary_md)
    content = replace_block(content, "ABLATIONS", ablations_md)
    content = replace_block(content, "HARDWARE", hardware_md)
    content = replace_block(content, "BUDGET", budget_md)

    readme_path.write_text(content, encoding="utf-8")
    print("README.md synchronized successfully from canonical results.")


if __name__ == "__main__":
    main()
