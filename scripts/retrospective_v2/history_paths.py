"""Canonical history-repository separation from retrospective sources."""

from __future__ import annotations

import os
from pathlib import Path
import re

from . import safe_io, temporary_paths


_SEPARATION_DETAIL = "outside canonical retrospective source roots"
_ACCOUNT_HOME_RE = re.compile(r"\A~(?=/|\Z)")


def _roots_overlap(candidate: Path, source: Path) -> bool:
    lexical_candidate = Path(os.path.abspath(os.fspath(candidate)))
    lexical_source = Path(os.path.abspath(os.fspath(source)))
    resolved_candidate = lexical_candidate.resolve(strict=False)
    resolved_source = lexical_source.resolve(strict=False)
    return any(
        (
            lexical_candidate.is_relative_to(lexical_source),
            lexical_source.is_relative_to(lexical_candidate),
            resolved_candidate.is_relative_to(resolved_source),
            resolved_source.is_relative_to(resolved_candidate),
        )
    )


def require_repository(value: str | os.PathLike[str]) -> Path:
    """Return a canonical history path that cannot overlap local sources."""

    source_root = temporary_paths.local_codex_root()
    raw_value = os.fspath(value)
    expanded = Path(
        _ACCOUNT_HOME_RE.sub(os.fspath(source_root.parent), raw_value, count=1)
    ).expanduser()
    candidate = Path(os.path.abspath(os.fspath(expanded)))
    if True in (
        _roots_overlap(candidate, source_root / "sessions"),
        _roots_overlap(candidate, source_root / "archived_sessions"),
    ):
        raise safe_io.UnsafePathError(
            "history repository overlaps a retrospective source root"
        )
    return candidate


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
