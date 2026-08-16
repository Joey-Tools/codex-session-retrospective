"""Fail-closed Git reads for the migration-only retrospective helper."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
from typing import Any

from . import executable_authority, git_safety, safe_io
from .authority_errors import HistoryValidationError


HISTORY_GIT_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class _HistoryGitBinding:
    repository: Path
    executable: executable_authority.ExecutableAuthority
    admission: git_safety.LocalRepositoryAdmission


_BINDINGS: dict[str, _HistoryGitBinding] = {}


def canonical_history_repository(path: Path) -> Path:
    """Resolve one caller path before repository admission."""

    return Path(os.path.realpath(path.expanduser())).absolute()


def _directory_identity(path: Path) -> tuple[int, int, int, int]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = os.open(path, flags)
    try:
        metadata = safe_io.validate_owner_only_directory_descriptor(
            descriptor,
            path,
            exact_mode=False,
        )
        path_metadata = os.lstat(path)
        identity = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_uid,
        )
        path_identity = (
            path_metadata.st_dev,
            path_metadata.st_ino,
            path_metadata.st_mode,
            path_metadata.st_uid,
        )
        if identity != path_identity:
            raise git_safety.LocalRepositorySafetyError(
                "metadata-changed",
                "history repository directory changed during inspection",
            )
        return identity
    finally:
        os.close(descriptor)


def _environment() -> dict[str, str]:
    return {
        **git_safety.local_only_git_environment(),
        "GIT_ATTR_NOSYSTEM": "1",
        "HOME": os.devnull,
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.defpath,
        "TZ": "UTC",
        "XDG_CONFIG_HOME": os.devnull,
    }


def _command(
    executable: str,
    repository: Path,
    arguments: Sequence[str],
    *,
    admission: git_safety.LocalRepositoryAdmission | None,
) -> tuple[str, ...]:
    prefix = (
        executable,
        "--no-pager",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.askPass=/usr/bin/false",
        "-c",
        "credential.helper=",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.attributesFile=/dev/null",
        "-c",
        "core.commitGraph=false",
        "-c",
        "core.multiPackIndex=false",
        "-c",
        "maintenance.auto=false",
        "-c",
        "submodule.recurse=false",
        "-c",
        "diff.external=",
        "-c",
        "color.ui=false",
    )
    if admission is None:
        return (*prefix, "-C", str(repository), *arguments)
    return (
        *prefix,
        f"--git-dir={admission.git_dir}",
        f"--work-tree={repository}",
        *arguments,
    )


def _run_process(
    command: tuple[str, ...],
    *,
    text: bool,
) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        check=False,
        env=_environment(),
        timeout=HISTORY_GIT_TIMEOUT_SECONDS,
    )


def _binding(repository: Path) -> _HistoryGitBinding:
    canonical = canonical_history_repository(repository)
    cache_key = os.fspath(canonical)
    cached = _BINDINGS.get(cache_key)
    if cached is not None:
        return cached
    try:
        authority = executable_authority.resolve_executable(
            executable_authority.DEFAULT_GIT_EXECUTABLE,
            label="history Git",
        )

        def bootstrap(
            arguments: tuple[str, ...],
        ) -> subprocess.CompletedProcess[bytes]:
            with executable_authority.executable_invocation(authority):
                return _run_process(
                    _command(
                        authority.path,
                        canonical,
                        arguments,
                        admission=None,
                    ),
                    text=False,
                )

        local_config = bootstrap(
            ("config", "--local", "--no-includes", "--name-only", "--list")
        )
        if local_config.returncode != 0:
            raise HistoryValidationError(
                "history repository local configuration cannot be inspected"
            )
        git_safety.validate_complete_local_repository(b"false", local_config.stdout)
        admission = git_safety.admit_history_repository(
            canonical,
            bootstrap,
            _directory_identity,
        )
    except (
        HistoryValidationError,
        OSError,
        ValueError,
        subprocess.TimeoutExpired,
        executable_authority.ExecutableAuthorityError,
    ) as error:
        raise HistoryValidationError(
            "history repository failed local safety admission"
        ) from error
    binding = _HistoryGitBinding(canonical, authority, admission)
    _BINDINGS[cache_key] = binding
    return binding


def run_history_git(
    repository: Path,
    arguments: Sequence[str],
    *,
    text: bool = False,
) -> subprocess.CompletedProcess[Any]:
    """Run one isolated read while holding and revalidating repository objects."""

    binding = _binding(repository)
    try:
        with executable_authority.executable_invocation(binding.executable):
            with git_safety.bind_local_repository_command(
                binding.admission,
                _directory_identity,
            ):
                return _run_process(
                    _command(
                        binding.executable.path,
                        binding.repository,
                        arguments,
                        admission=binding.admission,
                    ),
                    text=text,
                )
    except (
        HistoryValidationError,
        OSError,
        ValueError,
        subprocess.TimeoutExpired,
        executable_authority.ExecutableAuthorityError,
    ) as error:
        raise HistoryValidationError(
            "history repository safety binding changed"
        ) from error
