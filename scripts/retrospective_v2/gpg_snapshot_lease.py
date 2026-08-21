"""Per-snapshot leases for concurrent crash-recoverable GPG snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import errno
import fcntl
import os

from . import safe_io, temporary_paths


ACTIVE_LEASE_NAME = ".active.lock"
_LOCK_FLAGS = (
    os.O_RDWR
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_CLOEXEC", 0)
)


class GpgSnapshotLeaseError(RuntimeError):
    """Raised when snapshot activity or lease cleanup cannot be proved."""


def _identity(descriptor: int) -> tuple[int, int]:
    metadata = os.fstat(descriptor)
    return metadata.st_dev, metadata.st_ino


def _close(
    descriptor: int,
    *,
    primary: BaseException | None,
    label: str,
) -> None:
    try:
        os.close(descriptor)
    except OSError as error:
        target = primary or error
        temporary_paths.mark_incomplete_cleanup(target, stage=label)
        if primary is None:
            raise GpgSnapshotLeaseError(
                "publisher snapshot lease descriptor could not be closed"
            ) from error
        primary.add_note("publisher snapshot lease descriptor close failed")


def _validate_named(
    temporary: temporary_paths.BoundTemporaryDirectory,
    descriptor: int,
    identity: tuple[int, int],
) -> None:
    temporary.revalidate()
    safe_io.validate_owner_only_file_descriptor(
        descriptor,
        temporary.path / ACTIVE_LEASE_NAME,
        directory_fd=temporary._child_fd,
        name=ACTIVE_LEASE_NAME,
    )
    if _identity(descriptor) != identity:
        raise GpgSnapshotLeaseError("publisher snapshot lease identity changed")


@dataclass(slots=True)
class ActiveSnapshotLease:
    """Hold one owner-only activity lock until coordinated tree cleanup."""

    temporary: temporary_paths.BoundTemporaryDirectory
    descriptor: int
    identity: tuple[int, int]
    closed: bool = False

    def revalidate(self) -> None:
        if self.closed:
            raise GpgSnapshotLeaseError("publisher snapshot lease is already closed")
        _validate_named(self.temporary, self.descriptor, self.identity)

    def release(self, *, primary: BaseException | None) -> None:
        if self.closed:
            return
        release_error: BaseException | None = None
        try:
            self.revalidate()
            fcntl.flock(self.descriptor, fcntl.LOCK_UN)
        except BaseException as error:
            release_error = error
            temporary_paths.mark_incomplete_cleanup(
                primary or error,
                stage="publisher-snapshot-lease-release",
            )
            if primary is not None:
                primary.add_note("publisher snapshot lease release failed")
        finally:
            self.closed = True
            _close(
                self.descriptor,
                primary=primary or release_error,
                label="publisher-snapshot-lease-close",
            )
        if release_error is not None and primary is None:
            raise GpgSnapshotLeaseError(
                "publisher snapshot lease could not be released"
            ) from release_error

    def close_after_tree_cleanup(self, *, primary: BaseException | None) -> None:
        """Close a still-held lease after bound cleanup ran without the root lock."""

        if self.closed:
            return
        close_primary = primary
        try:
            metadata = os.fstat(self.descriptor)
            safe_io.validate_owner_only_file_descriptor(
                self.descriptor,
                self.temporary.path / ACTIVE_LEASE_NAME,
                single_link=False,
            )
            if (metadata.st_dev, metadata.st_ino) != self.identity:
                raise GpgSnapshotLeaseError(
                    "publisher snapshot retained lease identity changed"
                )
            fcntl.flock(self.descriptor, fcntl.LOCK_UN)
        except BaseException as error:
            temporary_paths.mark_incomplete_cleanup(
                primary or error,
                stage="publisher-snapshot-retained-lease",
            )
            if primary is None:
                close_primary = error
            else:
                primary.add_note("publisher snapshot retained lease release failed")
        finally:
            self.closed = True
            _close(
                self.descriptor,
                primary=close_primary,
                label="publisher-snapshot-retained-lease-close",
            )
        if close_primary is not None and primary is None:
            raise GpgSnapshotLeaseError(
                "publisher snapshot retained lease could not be released"
            ) from close_primary


def acquire_active_lease(
    temporary: temporary_paths.BoundTemporaryDirectory,
) -> ActiveSnapshotLease:
    """Atomically create and lock the activity receipt for a new snapshot."""

    temporary.revalidate()
    try:
        descriptor = os.open(
            ACTIVE_LEASE_NAME,
            _LOCK_FLAGS | os.O_CREAT | os.O_EXCL,
            safe_io.OWNER_FILE_MODE,
            dir_fd=temporary._child_fd,
        )
    except OSError as error:
        raise GpgSnapshotLeaseError(
            "publisher snapshot activity lease could not be created"
        ) from error
    primary: BaseException | None = None
    try:
        safe_io.harden_created_owner_only_file_descriptor(
            descriptor,
            temporary.path / ACTIVE_LEASE_NAME,
        )
        os.fsync(temporary._child_fd)
        identity = _identity(descriptor)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _validate_named(temporary, descriptor, identity)
        return ActiveSnapshotLease(temporary, descriptor, identity)
    except BaseException as error:
        primary = error
        raise
    finally:
        if primary is not None:
            _close(
                descriptor,
                primary=primary,
                label="publisher-snapshot-lease-acquire-close",
            )


def stale_snapshot_is_recoverable(
    temporary: temporary_paths.BoundTemporaryDirectory,
) -> bool:
    """Return false only when a validated activity lease is currently busy."""

    temporary.revalidate()
    path = temporary.path / ACTIVE_LEASE_NAME
    try:
        descriptor = os.open(
            ACTIVE_LEASE_NAME,
            _LOCK_FLAGS,
            dir_fd=temporary._child_fd,
        )
    except FileNotFoundError:
        return True
    except OSError as error:
        raise GpgSnapshotLeaseError(
            "publisher snapshot activity lease could not be opened"
        ) from error
    primary: BaseException | None = None
    terminal_error: BaseException | None = None
    acquired = False
    try:
        safe_io.validate_owner_only_file_descriptor(
            descriptor,
            path,
            directory_fd=temporary._child_fd,
            name=ACTIVE_LEASE_NAME,
        )
        identity = _identity(descriptor)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as error:
            if error.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
        _validate_named(temporary, descriptor, identity)
        return acquired
    except BaseException as error:
        primary = error
        temporary_paths.mark_incomplete_cleanup(
            error,
            stage="publisher-snapshot-lease-classification",
        )
        raise
    finally:
        if acquired:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError as error:
                target = primary or error
                temporary_paths.mark_incomplete_cleanup(
                    target,
                    stage="publisher-snapshot-stale-lease-release",
                )
                if primary is None:
                    terminal_error = error
                else:
                    primary.add_note("stale publisher snapshot lease release failed")
        _close(
            descriptor,
            primary=primary or terminal_error,
            label="publisher-snapshot-stale-lease-close",
        )
        if terminal_error is not None and primary is None:
            raise GpgSnapshotLeaseError(
                "stale publisher snapshot lease could not be released"
            ) from terminal_error
