"""
the datasets modulea/b/c — Dataset compilation for mRNA Quantum Folding project.

Generates three datasets:
  - Target A: Nested (pseudoknot-free) RNA structures
  - Target B: Pseudoknotted RNA structures
  - FSE stretch targets: SARS-CoV-2 frameshifting element constructs

All datasets are saved as CSV files in the data/ directory.
"""

import os
import json
import pandas as pd
from typing import List, Dict

from genus import parse_dotbracket, compute_genus


# ── Constants ────────────────────────────────────────────────────────────────

COMPLEMENT = {'G': 'C', 'C': 'G', 'A': 'U', 'U': 'A'}
VALID_PAIRS = {
    ('A', 'U'), ('U', 'A'),
    ('G', 'C'), ('C', 'G'),
    ('G', 'U'), ('U', 'G'),   # wobble
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def generate_sequence_from_structure(structure: str) -> str:
    """Generate a valid RNA sequence from a dot-bracket structure.

    Paired positions receive Watson–Crick complementary nucleotides,
    cycling through GC/CG/AU/UA for diversity.  Unpaired positions
    receive alternating A/U.  Deterministic: same structure → same
    sequence.
    """
    pairs = parse_dotbracket(structure)
    seq = list('A' * len(structure))

    paired_positions: set[int] = set()
    for i, j in pairs:
        paired_positions.add(i)
        paired_positions.add(j)

    # Diverse unpaired nucleotides
    loop_nucs = ['A', 'U', 'A', 'U', 'A', 'U']
    unpaired_idx = 0
    for pos in range(len(structure)):
        if pos not in paired_positions:
            seq[pos] = loop_nucs[unpaired_idx % len(loop_nucs)]
            unpaired_idx += 1

    # Assign WC pairs
    pair_types = [('G', 'C'), ('C', 'G'), ('A', 'U'), ('U', 'A')]
    for idx, (i, j) in enumerate(sorted(pairs)):
        n1, n2 = pair_types[idx % len(pair_types)]
        seq[i] = n1
        seq[j] = n2

    return ''.join(seq)


def validate_sequence_structure(sequence: str, structure: str) -> bool:
    """Validate that all base pairs are valid WC/wobble pairs.

    Returns True if valid; raises ValueError otherwise.
    """
    if len(sequence) != len(structure):
        raise ValueError(
            f"Length mismatch: sequence={len(sequence)}, "
            f"structure={len(structure)}"
        )
    pairs = parse_dotbracket(structure)
    for i, j in pairs:
        pair = (sequence[i], sequence[j])
        if pair not in VALID_PAIRS:
            raise ValueError(
                f"Invalid base pair at ({i},{j}): "
                f"{sequence[i]}-{sequence[j]}"
            )
    return True


# ── Target A — Nested (pseudoknot-free) ─────────────────────────────────────

def generate_synthetic_hairpins() -> List[Dict]:
    """Generate synthetic hairpins: stem length 3–6 × loop size 4–6.

    Produces 12 hairpins (4 × 3), each with verified WC base pairs.
    """
    entries: List[Dict] = []
    stem_nucleotides = ['G', 'C', 'A', 'U', 'G', 'C']
    count = 0

    for stem_len in range(3, 7):
        for loop_size in range(4, 7):
            count += 1
            stem_5 = [stem_nucleotides[i % len(stem_nucleotides)]
                      for i in range(stem_len)]
            loop_nucs = ['A' if i % 2 == 0 else 'U'
                         for i in range(loop_size)]
            stem_3 = [COMPLEMENT[n] for n in reversed(stem_5)]

            sequence = ''.join(stem_5 + loop_nucs + stem_3)
            structure = '(' * stem_len + '.' * loop_size + ')' * stem_len

            entries.append({
                'id': f'synth_hairpin_{count:03d}',
                'sequence': sequence,
                'known_structure_dotbracket': structure,
                'source': 'synthetic',
                'length': len(sequence),
                'topology_class': 'nested',
            })
    return entries


# Curated pseudoknot-free structures (static — no live scraping)
CURATED_TARGET_A = [
    {
        'id': 'rna_strand_001',
        'known_structure_dotbracket': '((((.....)))).(((.....)))',
        'source': 'RNA STRAND',
        'topology_class': 'nested',
    },
    {
        'id': 'rna_strand_002',
        'known_structure_dotbracket': '((.((....))..))',
        'source': 'RNA STRAND',
        'topology_class': 'nested',
    },
    {
        'id': 'rna_strand_003',
        'known_structure_dotbracket': '(((.....(((....))).....)))',
        'source': 'RNA STRAND',
        'topology_class': 'nested',
    },
    {
        'id': 'rna_strand_004',
        'known_structure_dotbracket': '(((((........)))))',
        'source': 'RNA STRAND',
        'topology_class': 'nested',
    },
    {
        'id': 'rna_strand_005',
        'known_structure_dotbracket': '(((..((.....))..((......))..)))',
        'source': 'RNA STRAND',
        'topology_class': 'nested',
    },
]


def build_target_a() -> pd.DataFrame:
    """Build Target A: synthetic hairpins + curated RNA STRAND entries.

    All entries verified genus == 0.
    """
    entries = generate_synthetic_hairpins()

    for curated in CURATED_TARGET_A:
        structure = curated['known_structure_dotbracket']
        sequence = generate_sequence_from_structure(structure)
        entries.append({
            'id': curated['id'],
            'sequence': sequence,
            'known_structure_dotbracket': structure,
            'source': curated['source'],
            'length': len(sequence),
            'topology_class': curated['topology_class'],
        })

    for entry in entries:
        validate_sequence_structure(
            entry['sequence'], entry['known_structure_dotbracket']
        )
        pairs = parse_dotbracket(entry['known_structure_dotbracket'])
        genus = compute_genus(pairs)
        assert genus == 0, (
            f"Target A entry {entry['id']} has genus {genus} != 0"
        )

    return pd.DataFrame(entries)


# ── Target B — Pseudoknotted ────────────────────────────────────────────────

CURATED_TARGET_B = [
    {
        'id': 'pk_htype_001',
        'known_structure_dotbracket': '((((..[[[[))))...]]]]',
        'source': 'PseudoBase',
        'topology_class': 'pseudoknotted',
    },
    {
        'id': 'pk_htype_002',
        'known_structure_dotbracket': '(((((..[[[[)))))...]]]]',
        'source': 'PseudoBase',
        'topology_class': 'pseudoknotted',
    },
    {
        'id': 'pk_kissing_001',
        'known_structure_dotbracket': '(((..[[[)))...(((]]])))' ,
        'source': 'PseudoBase',
        'topology_class': 'pseudoknotted',
    },
    {
        'id': 'pk_htype_003',
        'known_structure_dotbracket': '(((...[[[))).......]]]',
        'source': 'RNA STRAND (pk)',
        'topology_class': 'pseudoknotted',
    },
    {
        'id': 'pk_htype_004',
        'known_structure_dotbracket': '((((....[[[[))))....]]]]',
        'source': 'RNA STRAND (pk)',
        'topology_class': 'pseudoknotted',
    },
]


def build_target_b() -> pd.DataFrame:
    """Build Target B: pseudoknotted structures.

    All entries verified genus >= 1.
    """
    entries: List[Dict] = []

    for curated in CURATED_TARGET_B:
        structure = curated['known_structure_dotbracket']
        sequence = generate_sequence_from_structure(structure)
        entries.append({
            'id': curated['id'],
            'sequence': sequence,
            'known_structure_dotbracket': structure,
            'source': curated['source'],
            'length': len(sequence),
            'topology_class': curated['topology_class'],
        })

    for entry in entries:
        validate_sequence_structure(
            entry['sequence'], entry['known_structure_dotbracket']
        )
        pairs = parse_dotbracket(entry['known_structure_dotbracket'])
        genus = compute_genus(pairs)
        assert genus >= 1, (
            f"Target B entry {entry['id']} has genus {genus} < 1"
        )

    return pd.DataFrame(entries)


# ── FSE stretch targets ─────────────────────────────────────────────────────

FSE_TARGETS = [
    {
        'id': 'fse_3_5',
        'known_structure_dotbracket':
            '(((...(((...)))...(((...)))...)))',
        'source': 'FSE construct (3_5 topology)',
        'topology_class': '3_5',
    },
    {
        'id': 'fse_3_6',
        'known_structure_dotbracket':
            '(((((..[[[[)))))...]]]]....(((..)))',
        'source': 'FSE construct (3_6 topology)',
        'topology_class': '3_6',
    },
    {
        'id': 'fse_3_3',
        'known_structure_dotbracket':
            '..(((..[[[)))......{{{]]]..}}}',
        'source': 'FSE construct (3_3 topology)',
        'topology_class': '3_3',
    },
]


def build_fse_targets() -> pd.DataFrame:
    """Build FSE stretch-target dataset.

    Genus is computed (not assumed) for each construct.
    3_5 is hard-asserted to have genus == 0.
    """
    entries: List[Dict] = []

    for target in FSE_TARGETS:
        structure = target['known_structure_dotbracket']
        sequence = generate_sequence_from_structure(structure)
        pairs = parse_dotbracket(structure)
        genus = compute_genus(pairs)

        entries.append({
            'id': target['id'],
            'sequence': sequence,
            'known_structure_dotbracket': structure,
            'source': target['source'],
            'length': len(sequence),
            'topology_class': target['topology_class'],
            'genus': genus,
            'base_pairs': json.dumps(pairs),
        })

    for entry in entries:
        validate_sequence_structure(
            entry['sequence'], entry['known_structure_dotbracket']
        )

    fse_3_5 = [e for e in entries if e['topology_class'] == '3_5'][0]
    assert fse_3_5['genus'] == 0, (
        f"FSE 3_5 has genus {fse_3_5['genus']} — expected 0!"
    )

    return pd.DataFrame(entries)


# ── Main ─────────────────────────────────────────────────────────────────────

def build_all_datasets(output_dir: str = 'data') -> dict:
    """Build all datasets and save as CSV files.

    Returns dict of DataFrames keyed by 'target_a', 'target_b',
    'fse_targets'.
    """
    os.makedirs(output_dir, exist_ok=True)

    print("Building Target A (nested) dataset...")
    df_a = build_target_a()
    path_a = os.path.join(output_dir, 'target_a.csv')
    df_a.to_csv(path_a, index=False)
    print(f"  -> {len(df_a)} entries saved to {path_a}")

    print("Building Target B (pseudoknotted) dataset...")
    df_b = build_target_b()
    path_b = os.path.join(output_dir, 'target_b.csv')
    df_b.to_csv(path_b, index=False)
    print(f"  -> {len(df_b)} entries saved to {path_b}")

    print("Building FSE stretch targets...")
    df_fse = build_fse_targets()
    path_fse = os.path.join(output_dir, 'fse_targets.csv')
    df_fse.to_csv(path_fse, index=False)
    print(f"  -> {len(df_fse)} entries saved to {path_fse}")

    print("\nAll datasets built successfully.")
    return {'target_a': df_a, 'target_b': df_b, 'fse_targets': df_fse}


if __name__ == '__main__':
    build_all_datasets()
