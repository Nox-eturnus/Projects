from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

import numpy as np


def get_git_provenance(base_dir: Path | str | None = None) -> dict[str, Any]:
    """Inspect working tree status and return git provenance.

    Returns:
        {
            "execution_git_commit": "<sha>" if clean else None,
            "base_commit": "<sha>" or "unknown",
            "working_tree_dirty": bool,
        }
    """
    cwd = str(base_dir) if base_dir is not None else None
    working_dirty = True
    base_commit = "unknown"
    execution_git_commit = None

    try:
        commit_res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        base_commit = commit_res.stdout.strip()

        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        working_dirty = bool(status_res.stdout.strip())
        if not working_dirty:
            execution_git_commit = base_commit
    except Exception:
        pass

    return {
        "execution_git_commit": execution_git_commit,
        "base_commit": base_commit,
        "working_tree_dirty": working_dirty,
    }


def compute_file_hashes(paths: Sequence[Path | str], full_sha256: bool = True) -> dict[str, str]:
    """Compute cryptographic hashes for specified file paths."""
    results: dict[str, str] = {}
    for p in paths:
        path_obj = Path(p)
        if path_obj.exists() and path_obj.is_file():
            content = path_obj.read_bytes()
            h = hashlib.sha256(content).hexdigest()
            results[str(path_obj).replace("\\", "/")] = h if full_sha256 else h[:16]
        else:
            results[str(path_obj).replace("\\", "/")] = "file_not_found"
    return results


def hash_parameter_vector(params: np.ndarray | Sequence[float], full_sha256: bool = True) -> str:
    """Compute cryptographic SHA-256 hash of parameter vector."""
    arr = np.asarray(params, dtype=np.float64)
    h = hashlib.sha256(arr.tobytes()).hexdigest()
    return h if full_sha256 else h[:16]


def record_experiment_provenance(
    script_name: str,
    *,
    dataset_files: Sequence[Path | str] | None = None,
    config_files: Sequence[Path | str] | None = None,
    source_files: Sequence[Path | str] | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate structured provenance dictionary for archival records."""
    git_info = get_git_provenance()
    all_files: list[Path | str] = []
    if dataset_files:
        all_files.extend(dataset_files)
    if config_files:
        all_files.extend(config_files)
    if source_files:
        all_files.extend(source_files)

    file_hashes = compute_file_hashes(all_files, full_sha256=True)

    prov = {
        "script": script_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
        "git_provenance": git_info,
        "execution_git_commit": git_info["execution_git_commit"],
        "base_commit": git_info["base_commit"],
        "working_tree_dirty": git_info["working_tree_dirty"],
        "input_file_hashes": file_hashes,
    }
    if extra_metadata:
        prov.update(extra_metadata)
    return prov
