"""Fail-closed admission for the Python executable used by CI producers."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import sys


class CiRuntimeError(RuntimeError):
    """The active CI Python executable is not owner controlled."""


def require_owner_controlled_python(executable: Path | None = None) -> None:
    """Require one canonical, private-to-modify Python executable leaf."""

    selected = Path(sys.executable) if executable is None else executable
    if not selected.is_absolute():
        raise CiRuntimeError("CI Python executable must be absolute")
    if selected != Path(os.path.normpath(os.fspath(selected))):
        raise CiRuntimeError("CI Python executable must be normalized")
    if selected != Path(os.path.realpath(selected)):
        raise CiRuntimeError("CI Python executable must not be a symlink")
    try:
        metadata = selected.lstat()
    except OSError as exc:
        raise CiRuntimeError("CI Python executable cannot be inspected") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise CiRuntimeError("CI Python executable must be a regular file")
    if metadata.st_uid != os.geteuid():
        raise CiRuntimeError("CI Python executable must be owned by the runner")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise CiRuntimeError("CI Python executable must not be group/world writable")
    if metadata.st_nlink != 1:
        raise CiRuntimeError("CI Python executable must have one link")
