from __future__ import annotations

ALLOWED_FEATURES = (
    "distance_km",
    "recent_qber",
    "recent_gain",
    "dark_probability",
    "detector_efficiency",
    "key_pool_bits",
    "demand_bps",
    "mdi_capable",
)

FORBIDDEN_LEAKAGE_FEATURES = (
    "true_attack_strength",
    "future_qber",
    "current_block_secure_bits",
    "true_y1",
    "true_y11",
)


def validate_feature_columns(columns: list[str]) -> None:
    bad = sorted(set(columns) & set(FORBIDDEN_LEAKAGE_FEATURES))
    if bad:
        raise ValueError(f"feature leakage detected: {bad}")