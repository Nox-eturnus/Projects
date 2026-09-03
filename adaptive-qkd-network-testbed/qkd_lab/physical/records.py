from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from qkd_lab.models import CountRecord


def records_to_frame(records: dict[tuple[str, str], CountRecord]) -> pd.DataFrame:
    rows = []
    for (basis, intensity), rec in sorted(records.items()):
        row = {"basis": basis, "intensity": intensity, **asdict(rec)}
        row["gain"] = rec.gain
        row["error_gain"] = rec.error_gain
        row["qber"] = rec.qber
        rows.append(row)
    return pd.DataFrame(rows)