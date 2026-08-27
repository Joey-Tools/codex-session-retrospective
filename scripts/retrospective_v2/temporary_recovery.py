"""Serialized bounded recovery for crash-retained temporary directories."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import errno
import fcntl
import os
from pathlib import Path
import re
import stat
import time

from . import safe_io, temporary_paths


_RECOVERY_LOCK_NAME = ".recovery.lock"
_RECOVERY_LOCK_SECONDS = 30.0
_RECOVERY_POLL_SECONDS = 0.01
_RECOVERY_MAX_ENTRIES = 65
_RECOVERY_MAX_NAME_BYTES = 8 * 1024


class TemporaryRecoveryError(RuntimeError):
    """Raised when a stale sensitive directory cannot be recovered safely."""


def _directory_identity(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_uid,
        stat.S_IMODE(metadata.st_mode),
    )


def _revalidate_root(root_path: Path, root_fd: int) -> None:
    anchored = safe_io.validate_owner_only_directory_descriptor(root_fd, root_path)
    named = os.stat(root_path, follow_symlinks=False)
    if not stat.S_ISDIR(named.st_mode) or _directory_identity(
        named
    ) != _directory_identity(anchored):
        raise TemporaryRecoveryError("temporary recovery root changed")


def _revalidate_lock(root_path: Path, root_fd: int, lock_fd: int) -> None:
    safe_io.validate_owner_only_file_descriptor(
        lock_fd,
        root_path / _RECOVERY_LOCK_NAME,
        directory_fd=root_fd,
        name=_RECOVERY_LOCK_NAME,
    )


def _acquire_lock(lock_fd: int) -> None:
    deadline = time.monotonic() + _RECOVERY_LOCK_SECONDS
    while True:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as error:
            if error.errno not in {errno.EACCES, errno.EAGAIN}:
                raise TemporaryRecoveryError(
                    "temporary recovery lock could not be acquired"
                ) from error
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TemporaryRecoveryError("temporary recovery lock timed out")
        time.sleep(min(_RECOVERY_POLL_SECONDS, remaining))


@dataclass(slots=True)
class RecoveryCoordinator:
    """Hold the fixed-root lock only around inventory and tree mutations."""

    root_path: Path
    root_fd: int
    lock_fd: int
    locked: bool = True

    def revalidate(self) -> None:
        _revalidate_root(self.root_path, self.root_fd)
        _revalidate_lock(self.root_path, self.root_fd, self.lock_fd)

    def release(self) -> None:
        if not self.locked:
            return
        self.revalidate()
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
        except OSError as error:
            raise TemporaryRecoveryError(
                "temporary recovery lock could not be released"
            ) from error
        self.locked = False

    def acquire(self) -> None:
        if self.locked:
            self.revalidate()
            return
        self.revalidate()
        _acquire_lock(self.lock_fd)
        self.locked = True
        self.revalidate()


def _stale_names(root_fd: int, *, prefix: str) -> tuple[str, ...]:
    pattern = re.compile(re.escape(prefix) + r"[0-9a-f]{64}\Z", re.ASCII)
    names: list[str] = []
    name_bytes = 0
    with os.scandir(root_fd) as entries:
        for entry in entries:
            if len(names) >= _RECOVERY_MAX_ENTRIES:
                raise TemporaryRecoveryError(
                    "temporary recovery inventory is too large"
                )
            encoded_name = os.fsencode(entry.name)
            name_bytes += len(encoded_name)
            if name_bytes > _RECOVERY_MAX_NAME_BYTES:
                raise TemporaryRecoveryError(
                    "temporary recovery names exceed their limit"
                )
            names.append(entry.name)
    unexpected = tuple(
        name
        for name in names
        if name != _RECOVERY_LOCK_NAME and pattern.fullmatch(name) is None
    )
    if unexpected:
        raise TemporaryRecoveryError(
            "temporary recovery root contains an unrecognized entry"
        )
    return tuple(
        sorted(
            (name for name in names if name != _RECOVERY_LOCK_NAME),
            key=os.fsencode,
        )
    )


def _bind_stale_directory(
    *,
    root_path: Path,
    root_fd: int,
    source_root: Path,
    name: str,
) -> temporary_paths.BoundTemporaryDirectory:
    display_path = root_path / name
    named = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
    if not stat.S_ISDIR(named.st_mode):
        raise TemporaryRecoveryError("temporary recovery entry is not a directory")
    try:
        child_fd = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=root_fd,
        )
    except OSError as error:
        raise TemporaryRecoveryError(
            "temporary recovery entry could not be bound"
        ) from error
    active_error: BaseException | None = None
    try:
        anchored = safe_io.validate_owner_only_directory_descriptor(
            child_fd,
            display_path,
        )
        if _directory_identity(named) != _directory_identity(anchored):
            raise TemporaryRecoveryError(
                "temporary recovery entry changed while opened"
            )
        binding = temporary_paths.BoundTemporaryDirectory(
            path=display_path,
            _root_path=root_path,
            _source_root=source_root,
            _root_fd=root_fd,
            _child_fd=child_fd,
        )
        binding.revalidate()
        return binding
    except BaseException as error:
        active_error = error
        raise
    finally:
        if active_error is not None:
            try:
                os.close(child_fd)
            except OSError as close_error:
                temporary_paths.mark_incomplete_cleanup(
                    active_error,
                    stage="stale-binding-close",
                )
                active_error.add_note(
                    "stale temporary binding descriptor close failed: "
                    + type(close_error).__name__
                )


def _recover_one(
    binding: temporary_paths.BoundTemporaryDirectory,
    recover: Callable[[temporary_paths.BoundTemporaryDirectory], bool],
) -> bool:
    primary: BaseException | None = None
    try:
        recovered = recover(binding)
        if type(recovered) is not bool:
            raise TemporaryRecoveryError(
                "temporary recovery callback returned an invalid disposition"
            )
        binding.revalidate()
        if recovered:
            temporary_paths._cleanup_bound_directory(binding)
        return recovered
    except BaseException as error:
        primary = error
        temporary_paths.mark_incomplete_cleanup(
            error,
            stage="stale-tree-recovery",
        )
        raise
    finally:
        try:
            os.close(binding._child_fd)
        except OSError as close_error:
            target = primary or close_error
            temporary_paths.mark_incomplete_cleanup(
                target,
                stage="stale-tree-descriptor-close",
            )
            if primary is None:
                raise TemporaryRecoveryError(
                    "stale temporary binding could not be closed"
                ) from close_error
            primary.add_note(
                "stale temporary binding descriptor close failed: "
                + type(close_error).__name__
            )


@contextmanager
def serialized_stale_recovery(
    *,
    root: Path,
    prefix: str,
    recover: Callable[[temporary_paths.BoundTemporaryDirectory], bool],
) -> Iterator[RecoveryCoordinator]:
    """Recover stale entries and coordinate active sensitive temp lifecycles."""

    source_root = temporary_paths.local_codex_root()
    temporary_paths._require_root_outside_source(root, source_root)
    root_path, root_fd = safe_io.open_owner_only_directory(root, create=True)
    lock_fd = -1
    coordinator: RecoveryCoordinator | None = None
    primary: BaseException | None = None
    try:
        _revalidate_root(root_path, root_fd)
        lock_fd = safe_io.open_lock_file_at(
            root_fd,
            _RECOVERY_LOCK_NAME,
            display_path=root_path / _RECOVERY_LOCK_NAME,
        )
        _acquire_lock(lock_fd)
        coordinator = RecoveryCoordinator(root_path, root_fd, lock_fd)
        coordinator.revalidate()
        try:
            stale_names = _stale_names(root_fd, prefix=prefix)
        except TemporaryRecoveryError as error:
            temporary_paths.mark_incomplete_cleanup(
                error,
                stage="stale-root-inventory",
            )
            raise
        active_names: set[str] = set()
        for name in stale_names:
            try:
                binding = _bind_stale_directory(
                    root_path=root_path,
                    root_fd=root_fd,
                    source_root=source_root,
                    name=name,
                )
            except BaseException as error:
                temporary_paths.mark_incomplete_cleanup(
                    error,
                    stage="stale-binding",
                )
                raise
            if not _recover_one(binding, recover):
                active_names.add(name)
        coordinator.revalidate()
        try:
            remaining = _stale_names(root_fd, prefix=prefix)
        except TemporaryRecoveryError as error:
            temporary_paths.mark_incomplete_cleanup(
                error,
                stage="stale-root-revalidation",
            )
            raise
        if remaining != tuple(sorted(active_names, key=os.fsencode)):
            error = TemporaryRecoveryError(
                "temporary recovery inventory changed after active classification"
            )
            temporary_paths.mark_incomplete_cleanup(
                error,
                stage="stale-root-revalidation",
            )
            raise error
        yield coordinator
    except BaseException as error:
        primary = error
        raise
    finally:
        terminal_error: TemporaryRecoveryError | None = None
        if coordinator is not None and coordinator.locked:
            try:
                coordinator.release()
            except OSError as error:
                if primary is None:
                    terminal_error = TemporaryRecoveryError(
                        "temporary recovery lock could not be released"
                    )
                    terminal_error.__cause__ = error
                else:
                    primary.add_note("temporary recovery lock release failed")
            except TemporaryRecoveryError as error:
                if primary is None:
                    terminal_error = error
                else:
                    primary.add_note("temporary recovery lock release failed")
        for descriptor in (lock_fd, root_fd):
            if descriptor < 0:
                continue
            try:
                os.close(descriptor)
            except OSError as error:
                if primary is None and terminal_error is None:
                    terminal_error = TemporaryRecoveryError(
                        "temporary recovery descriptor could not be closed"
                    )
                    terminal_error.__cause__ = error
                elif primary is None:
                    terminal_error.add_note(
                        "additional temporary recovery descriptor close failed"
                    )
                else:
                    primary.add_note("temporary recovery descriptor close failed")
        if terminal_error is not None:
            raise terminal_error
