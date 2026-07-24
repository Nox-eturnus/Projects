"""
pipeline -- Scalability Analysis & Reporting: Validation Tests.

Definition of Done:
  - Both plots render from logged data with no manual number entry
  - Written section ties back to feasibility-study framing
  - Consolidated validation checklist maps every checkpoint
"""

import json
import pandas as pd
from pathlib import Path

from plots import (
    generate_scaling_data,
    plot_scaling,
    plot_wallclock,
    plot_tier2b_headline,
    plot_energy_gap_heatmap,
    generate_scalability_report,
    run_full_part15,
    PLOTS_DIR,
)
from ideal_sweep import DATA_DIR


# =========================================================================
# Test 1: Scaling data generation
# =========================================================================

def test_scaling_data():
    """Verify scaling data covers all sequences and both encodings."""
    print("Test 1: Scaling data generation")

    df = generate_scaling_data()
    assert len(df) > 0, "No scaling data generated"

    # Both encodings
    encodings = set(df['encoding'].unique())
    assert 'pair' in encodings, "Missing pair encoding"
    assert 'stem' in encodings, "Missing stem encoding"

    # Stem always fewer variables than pair
    for seq_len in df['sequence_length'].unique():
        pair_vars = df[(df['sequence_length'] == seq_len) &
                       (df['encoding'] == 'pair')]['n_variables'].values
        stem_vars = df[(df['sequence_length'] == seq_len) &
                       (df['encoding'] == 'stem')]['n_variables'].values
        if len(pair_vars) > 0 and len(stem_vars) > 0:
            assert pair_vars.mean() >= stem_vars.mean(), (
                f"At length {seq_len}, pair ({pair_vars.mean():.1f}) "
                f"should >= stem ({stem_vars.mean():.1f})"
            )

    print(f"  {len(df)} data points, encodings: {sorted(encodings)}")
    print("  PASS")
    print()


# =========================================================================
# Test 2: Plot 1 renders
# =========================================================================

def test_plot1_renders():
    """Verify Plot 1 (scaling) renders to a file."""
    print("Test 2: Plot 1 (scaling) renders")

    df = generate_scaling_data()
    out_path = PLOTS_DIR / "test_plot1.png"
    result = plot_scaling(df, save_path=out_path)

    assert out_path.exists(), f"Plot not saved: {out_path}"
    assert out_path.stat().st_size > 1000, "Plot file too small"

    print(f"  Saved: {result} ({out_path.stat().st_size} bytes)")
    # Cleanup
    out_path.unlink()
    print("  PASS")
    print()


# =========================================================================
# Test 3: Plot 2 renders
# =========================================================================

def test_plot2_renders():
    """Verify Plot 2 (wall-clock) renders to a file."""
    print("Test 3: Plot 2 (wall-clock) renders")

    scaling_df = generate_scaling_data()
    part14 = json.load(open(DATA_DIR / "evaluation_results.json"))
    tier1_df = pd.DataFrame(part14['tier1'])
    part13_df = pd.read_json(DATA_DIR / "classical_benchmarks_results.json")

    out_path = PLOTS_DIR / "test_plot2.png"
    result = plot_wallclock(tier1_df, part13_df, scaling_df,
                            save_path=out_path)

    assert out_path.exists(), f"Plot not saved: {out_path}"
    assert out_path.stat().st_size > 1000, "Plot file too small"

    print(f"  Saved: {result} ({out_path.stat().st_size} bytes)")
    out_path.unlink()
    print("  PASS")
    print()


# =========================================================================
# Test 4: Plot 3 (Tier 2b headline) renders
# =========================================================================

def test_plot3_renders():
    """Verify Plot 3 (Tier 2b bar chart) renders."""
    print("Test 4: Plot 3 (Tier 2b headline) renders")

    part14 = json.load(open(DATA_DIR / "evaluation_results.json"))
    tier2b_df = pd.DataFrame(part14['tier2b'])

    out_path = PLOTS_DIR / "test_plot3.png"
    result = plot_tier2b_headline(tier2b_df, save_path=out_path)

    assert out_path.exists(), f"Plot not saved: {out_path}"
    assert out_path.stat().st_size > 1000, "Plot file too small"

    print(f"  Saved: {result} ({out_path.stat().st_size} bytes)")
    out_path.unlink()
    print("  PASS")
    print()


# =========================================================================
# Test 5: Plot 4 (heatmap) renders
# =========================================================================

def test_plot4_renders():
    """Verify Plot 4 (energy gap heatmap) renders."""
    print("Test 5: Plot 4 (energy gap heatmap) renders")

    part14 = json.load(open(DATA_DIR / "evaluation_results.json"))
    tier1_df = pd.DataFrame(part14['tier1'])

    out_path = PLOTS_DIR / "test_plot4.png"
    result = plot_energy_gap_heatmap(tier1_df, save_path=out_path)

    assert out_path.exists(), f"Plot not saved: {out_path}"
    assert out_path.stat().st_size > 1000, "Plot file too small"

    print(f"  Saved: {result} ({out_path.stat().st_size} bytes)")
    out_path.unlink()
    print("  PASS")
    print()


# =========================================================================
# Test 6: Scalability report generates
# =========================================================================

def test_report_generates():
    """Verify the written scalability report is generated."""
    print("Test 6: Scalability report generates")

    scaling_df = generate_scaling_data()
    part14 = json.load(open(DATA_DIR / "evaluation_results.json"))
    tier1_df = pd.DataFrame(part14['tier1'])
    tier2a_df = pd.DataFrame(part14['tier2a'])
    tier2b_df = pd.DataFrame(part14['tier2b'])

    out_path = PLOTS_DIR / "test_report.md"
    result = generate_scalability_report(
        scaling_df, tier1_df, tier2b_df, tier2a_df, save_path=out_path
    )

    assert out_path.exists(), f"Report not saved: {out_path}"
    content = out_path.read_text(encoding='utf-8')

    # Check required sections
    assert 'Resource Scaling' in content, "Missing Resource Scaling section"
    assert 'Cost-Function Evaluations' in content, "Missing complexity section"
    assert 'Structural Accuracy' in content, "Missing Tier 2b section"
    assert 'Scientific Framing' in content, "Missing framing section"
    assert 'Validation Checklist' in content, "Missing checklist"
    assert 'np-hard' in content.lower(), "Missing NP-hard framing"

    print(f"  Report: {len(content)} chars, {content.count(chr(10))} lines")
    out_path.unlink()
    print("  PASS")
    print()


# =========================================================================
# Test 7: Full pipeline run
# =========================================================================

def test_full_part15():
    """Run the complete pipeline pipeline."""
    print("Test 7: Full pipeline run")

    outputs = run_full_part15(verbose=True)

    # Verify all outputs exist
    for name, path in outputs.items():
        assert path.exists(), f"Missing output: {name} -> {path}"
        print(f"  {name}: {path} ({path.stat().st_size} bytes)")

    # Verify plots directory
    assert PLOTS_DIR.exists()
    plot_files = list(PLOTS_DIR.glob("*.png"))
    assert len(plot_files) >= 4, f"Expected >= 4 plots, got {len(plot_files)}"

    # Verify report
    report_path = PLOTS_DIR / "scalability_report.md"
    assert report_path.exists()
    content = report_path.read_text(encoding='utf-8')
    assert len(content) > 500, "Report too short"

    print()
    print("  PASS -- pipeline Definition of Done satisfied")
    print()


# =========================================================================
# Main
# =========================================================================

def main():
    print("=" * 60)
    print("pipeline -- Scalability Analysis & Reporting: Tests")
    print("=" * 60)
    print()

    test_scaling_data()
    test_plot1_renders()
    test_plot2_renders()
    test_plot3_renders()
    test_plot4_renders()
    test_report_generates()
    test_full_part15()

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("pipeline Definition of Done satisfied:")
    print("  [OK] Plot 1: qubit scaling renders from logged data")
    print("  [OK] Plot 2: wall-clock scaling renders from logged data")
    print("  [OK] Plot 3: Tier 2b headline bar chart renders")
    print("  [OK] Plot 4: Energy gap heatmap renders")
    print("  [OK] Written section with proper framing")
    print("  [OK] Consolidated validation checklist")
    print("=" * 60)


if __name__ == '__main__':
    main()
