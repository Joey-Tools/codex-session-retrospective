"""Canonical history-repository separation from retrospective sources."""

from __future__ import annotations

import os
from pathlib import Path
import re

from . import safe_io, temporary_paths


_SEPARATION_DETAIL = "outside canonical retrospective source roots"
_ACCOUNT_HOME_RE = re.compile(r"\A~(?=/|\Z)")


def require_repository(value: str | os.PathLike[str]) -> Path:
    """Return a canonical history path that cannot overlap local sources."""

    source_root = temporary_paths.local_codex_root()
    raw_value = os.fspath(value)
    if not raw_value:
        raise ValueError("history repository path must not be empty")
    expanded = Path(
        _ACCOUNT_HOME_RE.sub(os.fspath(source_root.parent), raw_value, count=1)
    ).expanduser()
    candidate = Path(os.path.abspath(os.fspath(expanded)))
    try:
        return temporary_paths.require_run_directory_outside_sources(candidate)
    except safe_io.UnsafePathError as error:
        raise safe_io.UnsafePathError(
            "history repository overlaps a retrospective source root"
        ) from error


def readiness(
    value: str | os.PathLike[str] | None,
) -> tuple[Path | None, str]:
    """Return a content-free doctor result for history/source separation."""

    try:
        return require_repository(value), _SEPARATION_DETAIL  # type: ignore[arg-type]
    except (OSError, TypeError, ValueError) as error:
        return None, type(error).__name__


def start_paths(
    run_dir: str | os.PathLike[str], history_repo: str | os.PathLike[str]
) -> tuple[Path, Path]:
    """Validate both CLI start paths before any run state can be created."""

    return (
        temporary_paths.require_run_directory_outside_sources(run_dir),
        require_repository(history_repo),
    )
