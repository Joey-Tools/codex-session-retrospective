"""Fail-closed Git reads for the migration-only retrospective helper."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import time
from typing import Any

from . import (
    authority,
    executable_authority,
    git_safety,
    legacy_history_worktree,
    reporting,
    safe_io,
)
from .authority_errors import HistoryValidationError


HISTORY_GIT_TIMEOUT_SECONDS = 30
HISTORY_GIT_OUTPUT_LIMIT_BYTES = authority.MAX_GIT_OUTPUT_BYTES
HISTORY_ARTIFACT_LIMIT_BYTES = reporting.MAX_RETAINED_ARTIFACT_BYTES


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
    primary: BaseException | None = None
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
    except BaseException as error:
        primary = error
        raise
    finally:
        git_safety.close_repository_descriptors(
            (descriptor,),
            "history repository",
            primary=primary,
        )


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


def _safe_arguments(arguments: Sequence[str]) -> tuple[str, ...]:
    return (
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
        *arguments,
    )


def _bootstrap_command(
    executable: str,
    repository: Path,
    arguments: Sequence[str],
) -> tuple[str, ...]:
    return (
        executable,
        *_safe_arguments(()),
        "-C",
        str(repository),
        *arguments,
    )


def _run_process(
    command: tuple[str, ...],
    *,
    environment: dict[str, str],
    pass_fds: tuple[int, ...] = (),
    max_output_bytes: int | None = None,
    timeout_seconds: float | None = None,
    deadline: float | None = None,
    text: bool,
) -> subprocess.CompletedProcess[Any]:
    effective_timeout = (
        HISTORY_GIT_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    )
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HistoryValidationError(
                "history worktree inspection exceeded its deadline"
            )
        effective_timeout = min(effective_timeout, remaining)
    result = authority.run_bounded_history_command(
        command,
        env=environment,
        pass_fds=pass_fds,
        timeout_seconds=effective_timeout,
        max_output_bytes=(
            HISTORY_GIT_OUTPUT_LIMIT_BYTES
            if max_output_bytes is None
            else max_output_bytes
        ),
    )
    if not text:
        return result
    return subprocess.CompletedProcess(
        args=result.args,
        returncode=result.returncode,
        stdout=result.stdout.decode("utf-8", errors="surrogateescape"),
        stderr=result.stderr.decode("utf-8", errors="surrogateescape"),
    )


def _binding(repository: Path) -> _HistoryGitBinding:
    canonical = canonical_history_repository(repository)
    cache_key = os.fspath(canonical)
    cached = _BINDINGS.get(cache_key)
    if cached is not None:
        return cached
    try:
        git_authority = executable_authority.resolve_executable(
            executable_authority.DEFAULT_GIT_EXECUTABLE,
            label="history Git",
        )

        def bootstrap(
            arguments: tuple[str, ...],
        ) -> subprocess.CompletedProcess[bytes]:
            with executable_authority.executable_invocation(git_authority):
                return _run_process(
                    _bootstrap_command(
                        git_authority.path,
                        canonical,
                        arguments,
                    ),
                    environment=_environment(),
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
    except HistoryValidationError:
        raise
    except (
        OSError,
        ValueError,
        subprocess.TimeoutExpired,
        executable_authority.ExecutableAuthorityError,
    ) as error:
        raise HistoryValidationError(
            "history repository failed local safety admission"
        ) from error
    binding = _HistoryGitBinding(canonical, git_authority, admission)
    _BINDINGS[cache_key] = binding
    return binding


def _run_with_binding(
    binding: _HistoryGitBinding,
    arguments: Sequence[str],
    *,
    text: bool = False,
    max_output_bytes: int | None = None,
    timeout_seconds: float | None = None,
    deadline: float | None = None,
) -> subprocess.CompletedProcess[Any]:
    """Run one isolated read while holding and revalidating repository objects."""

    try:
        with executable_authority.executable_invocation(binding.executable):
            with git_safety.history_repository_git_invocation(
                binding.admission,
                binding.repository,
                binding.executable.path,
                _safe_arguments(arguments),
                _environment(),
                _directory_identity,
            ) as (command, environment, descriptors):
                return _run_process(
                    command,
                    environment=environment,
                    pass_fds=descriptors,
                    max_output_bytes=max_output_bytes,
                    timeout_seconds=timeout_seconds,
                    deadline=deadline,
                    text=text,
                )
    except HistoryValidationError:
        raise
    except (
        OSError,
        ValueError,
        subprocess.TimeoutExpired,
        executable_authority.ExecutableAuthorityError,
    ) as error:
        raise HistoryValidationError(
            "history repository safety binding changed"
        ) from error


def run_history_git(
    repository: Path,
    arguments: Sequence[str],
    *,
    text: bool = False,
    max_output_bytes: int | None = None,
) -> subprocess.CompletedProcess[Any]:
    return _run_with_binding(
        _binding(repository),
        arguments,
        text=text,
        max_output_bytes=max_output_bytes,
    )


def require_clean_worktree(repository: Path) -> None:
    """Prove the held worktree, index, and HEAD expose one exact file tree."""

    binding = _binding(repository)
    legacy_history_worktree.require_clean_worktree(
        binding.repository,
        admission=binding.admission,
        run_git=lambda arguments, deadline: _run_with_binding(
            binding,
            arguments,
            text=False,
            deadline=deadline,
        ),
        directory_identity=_directory_identity,
    )
