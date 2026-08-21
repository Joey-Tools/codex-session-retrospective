"""Descriptor-bound, configuration-free publisher keyring snapshots."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat

from . import (
    gpg_snapshot_lease,
    gpg_snapshot_recovery,
    safe_io,
    temporary_paths,
    temporary_recovery,
)


_KEYGRIP_FILE_RE = re.compile(r"[0-9A-F]{40}\.key\Z", re.ASCII | re.IGNORECASE)
_MAX_PUBLIC_KEYRING_BYTES = 16 * 1024 * 1024
_MAX_TRUST_DATABASE_BYTES = 16 * 1024 * 1024
_MAX_PRIVATE_KEY_BYTES = 1024 * 1024
_MAX_PRIVATE_KEYS = 16
_MAX_GPG_LOCK_BYTES = 1024
_MAX_GPG_LOCK_FILES = 8
_MAX_SNAPSHOT_TOP_LEVEL_ENTRIES = gpg_snapshot_recovery.MAX_SNAPSHOT_TOP_LEVEL_ENTRIES
_GPG_LOCK_NAME_RE = re.compile(
    r"\.\#lk0x[0-9A-Fa-f]{8,32}\.[A-Za-z0-9._-]{1,255}\.[1-9][0-9]{0,19}\Z",
    re.ASCII,
)
_GPG_AGENT_SENTINEL = "gnupg_spawn_agent_sentinel.lock"
_KEYRING_COMMITMENT_DOMAIN = b"codex-session-retrospective-gpg-keyring-v2\0"


class ConfigFreeKeyringError(RuntimeError):
    """Raised when a config-free publisher keyring cannot be proved or cleaned."""


@dataclass(frozen=True, slots=True)
class _GpgLockBinding:
    name: str
    descriptor: int
    identity: tuple[int, int]
    initial_link_count: int


@dataclass(frozen=True, slots=True)
class ConfigFreeKeyringSnapshot:
    path: Path
    source_commitment: str


def _close_descriptor(
    descriptor: int,
    *,
    active_error: BaseException | None,
    label: str,
) -> None:
    try:
        os.close(descriptor)
    except OSError as close_error:
        message = f"{label} descriptor cleanup failed: {close_error}"
        if active_error is None:
            raise ConfigFreeKeyringError(message) from close_error
        active_error.add_note(message)


def _revalidate_keyring_directory(
    descriptor: int,
    path: Path,
    identity: tuple[int, int],
) -> None:
    safe_io.validate_owner_only_directory_descriptor(descriptor, path)
    named = os.stat(path, follow_symlinks=False)
    if not stat.S_ISDIR(named.st_mode) or (named.st_dev, named.st_ino) != identity:
        raise ConfigFreeKeyringError("publisher keyring directory identity changed")
    reopened_path, reopened = safe_io.open_owner_only_directory(
        path,
        reject_symlink_ancestors=True,
    )
    active_error: BaseException | None = None
    try:
        reopened_metadata = os.fstat(reopened)
        if (
            reopened_path != path
            or (reopened_metadata.st_dev, reopened_metadata.st_ino) != identity
        ):
            raise ConfigFreeKeyringError(
                "publisher keyring path no longer names the bound directory"
            )
    except BaseException as error:
        active_error = error
        raise
    finally:
        _close_descriptor(
            reopened,
            active_error=active_error,
            label="publisher keyring revalidation",
        )


def _source_file_policy(
    metadata: os.stat_result, path: Path, *, private: bool
) -> tuple[int, ...]:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or (private and stat.S_IMODE(metadata.st_mode) != safe_io.OWNER_FILE_MODE)
    ):
        raise ConfigFreeKeyringError(
            f"publisher keyring file access policy is invalid: {path.name}"
        )
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_uid,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
    )


def _read_keyring_file_at(
    directory_fd: int,
    name: str,
    *,
    display_path: Path,
    max_bytes: int,
    private: bool,
) -> bytes:
    before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    before_policy = _source_file_policy(before, display_path, private=private)
    descriptor = safe_io.open_checked_file_at(
        directory_fd,
        name,
        display_path=display_path,
        require_owner_only=private,
    )
    active_error: BaseException | None = None
    try:
        if safe_io.descriptor_acl_policy_bytes(descriptor):
            raise ConfigFreeKeyringError(
                f"publisher keyring file has an extended ACL: {display_path.name}"
            )
    except BaseException as error:
        active_error = error
        raise
    finally:
        _close_descriptor(
            descriptor,
            active_error=active_error,
            label="publisher keyring file",
        )
    try:
        payload = safe_io.read_bounded_bytes_at(
            directory_fd,
            name,
            display_path=display_path,
            max_bytes=max_bytes,
            require_owner_only=private,
        )
    except (OSError, ValueError, safe_io.UnsafePathError) as exc:
        raise ConfigFreeKeyringError(
            f"publisher keyring file cannot be read safely: {display_path.name}"
        ) from exc
    after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    if _source_file_policy(after, display_path, private=private) != before_policy:
        raise ConfigFreeKeyringError(
            f"publisher keyring file changed while copied: {display_path.name}"
        )
    return payload


def _copy_config_free_keyring(
    source: Path,
    source_fd: int,
    destination: Path,
) -> str:
    commitment = hashlib.sha256(_KEYRING_COMMITMENT_DOMAIN)

    def commit(name: str, payload: bytes | None) -> None:
        encoded_name = name.encode("ascii", errors="strict")
        commitment.update(len(encoded_name).to_bytes(4, "big"))
        commitment.update(encoded_name)
        if payload is None:
            commitment.update(b"\x00")
            return
        commitment.update(b"\x01")
        commitment.update(len(payload).to_bytes(8, "big"))
        commitment.update(payload)

    public_keyring = _read_keyring_file_at(
        source_fd,
        "pubring.kbx",
        display_path=source / "pubring.kbx",
        max_bytes=_MAX_PUBLIC_KEYRING_BYTES,
        private=False,
    )
    commit("pubring.kbx", public_keyring)
    safe_io.atomic_create_bytes(destination / "pubring.kbx", public_keyring)
    try:
        trust_database = _read_keyring_file_at(
            source_fd,
            "trustdb.gpg",
            display_path=source / "trustdb.gpg",
            max_bytes=_MAX_TRUST_DATABASE_BYTES,
            private=True,
        )
    except FileNotFoundError:
        commit("trustdb.gpg", None)
    else:
        commit("trustdb.gpg", trust_database)
        safe_io.atomic_create_bytes(destination / "trustdb.gpg", trust_database)

    source_private_path = source / "private-keys-v1.d"
    try:
        source_private_fd = os.open(
            "private-keys-v1.d",
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=source_fd,
        )
    except OSError as exc:
        raise ConfigFreeKeyringError(
            "publisher private-key directory is unavailable"
        ) from exc
    active_error: BaseException | None = None
    try:
        private_identity_metadata = safe_io.validate_owner_only_directory_descriptor(
            source_private_fd,
            source_private_path,
        )
        private_identity = (
            private_identity_metadata.st_dev,
            private_identity_metadata.st_ino,
        )
        named_private = os.stat(
            "private-keys-v1.d",
            dir_fd=source_fd,
            follow_symlinks=False,
        )
        if (named_private.st_dev, named_private.st_ino) != private_identity:
            raise ConfigFreeKeyringError(
                "publisher private-key directory changed while opened"
            )
        with os.scandir(source_private_fd) as entries:
            names = tuple(entry.name for entry in entries)
        if (
            not names
            or len(names) > _MAX_PRIVATE_KEYS
            or any(_KEYGRIP_FILE_RE.fullmatch(name) is None for name in names)
        ):
            raise ConfigFreeKeyringError(
                "publisher private-key inventory is not canonical"
            )
        destination_private = destination / "private-keys-v1.d"
        safe_io.ensure_owner_only_directory(destination_private)
        private_payloads: dict[str, bytes] = {}
        for name in sorted(names):
            payload = _read_keyring_file_at(
                source_private_fd,
                name,
                display_path=source_private_path / name,
                max_bytes=_MAX_PRIVATE_KEY_BYTES,
                private=True,
            )
            private_payloads[name] = payload
            commit(f"private-keys-v1.d/{name}", payload)
            safe_io.atomic_create_bytes(destination_private / name, payload)
        with os.scandir(source_private_fd) as entries:
            names_after = tuple(entry.name for entry in entries)
        if sorted(names_after) != sorted(names):
            raise ConfigFreeKeyringError(
                "publisher private-key inventory changed while copied"
            )
        for name in sorted(names):
            if (
                _read_keyring_file_at(
                    source_private_fd,
                    name,
                    display_path=source_private_path / name,
                    max_bytes=_MAX_PRIVATE_KEY_BYTES,
                    private=True,
                )
                != private_payloads[name]
            ):
                raise ConfigFreeKeyringError(
                    "publisher private-key content changed while copied"
                )
        private_after = safe_io.validate_owner_only_directory_descriptor(
            source_private_fd,
            source_private_path,
        )
        named_private_after = os.stat(
            "private-keys-v1.d",
            dir_fd=source_fd,
            follow_symlinks=False,
        )
        if (private_after.st_dev, private_after.st_ino) != private_identity or (
            named_private_after.st_dev,
            named_private_after.st_ino,
        ) != private_identity:
            raise ConfigFreeKeyringError(
                "publisher private-key directory changed while copied"
            )
    except BaseException as error:
        active_error = error
        raise
    finally:
        _close_descriptor(
            source_private_fd,
            active_error=active_error,
            label="publisher private-key directory",
        )
    return commitment.hexdigest()


def _is_gpg_lock_name(name: str) -> bool:
    return name == _GPG_AGENT_SENTINEL or _GPG_LOCK_NAME_RE.fullmatch(name) is not None


def _validate_gpg_lock_metadata(
    metadata: os.stat_result,
    *,
    path: Path,
) -> tuple[int, int]:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_size > _MAX_GPG_LOCK_BYTES
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise ConfigFreeKeyringError(
            f"publisher snapshot GPG lock policy is invalid: {path.name}"
        )
    return metadata.st_dev, metadata.st_ino


def _open_gpg_lock(
    temporary: temporary_paths.BoundTemporaryDirectory,
    name: str,
) -> _GpgLockBinding:
    path = temporary.path / name
    named = os.stat(name, dir_fd=temporary._child_fd, follow_symlinks=False)
    identity = _validate_gpg_lock_metadata(named, path=path)
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=temporary._child_fd,
        )
    except OSError as exc:
        raise ConfigFreeKeyringError(
            f"publisher snapshot GPG lock cannot be opened: {name}"
        ) from exc
    active_error: BaseException | None = None
    try:
        anchored = os.fstat(descriptor)
        if _validate_gpg_lock_metadata(anchored, path=path) != identity:
            raise ConfigFreeKeyringError(
                f"publisher snapshot GPG lock changed while opened: {name}"
            )
        if safe_io.descriptor_acl_policy_bytes(descriptor):
            raise ConfigFreeKeyringError(
                f"publisher snapshot GPG lock has an extended ACL: {name}"
            )
        return _GpgLockBinding(
            name=name,
            descriptor=descriptor,
            identity=identity,
            initial_link_count=anchored.st_nlink,
        )
    except BaseException as error:
        active_error = error
        raise
    finally:
        if active_error is not None:
            _close_descriptor(
                descriptor,
                active_error=active_error,
                label="publisher snapshot GPG lock",
            )


def _close_gpg_locks(
    locks: tuple[_GpgLockBinding, ...],
    *,
    active_error: BaseException | None,
) -> None:
    primary = active_error
    terminal_error: BaseException | None = None
    for lock in reversed(locks):
        try:
            _close_descriptor(
                lock.descriptor,
                active_error=primary,
                label="publisher snapshot GPG lock",
            )
        except BaseException as error:
            primary = error
            terminal_error = error
    if terminal_error is not None:
        raise terminal_error


def _remove_gpg_lock_files(
    temporary: temporary_paths.BoundTemporaryDirectory,
) -> None:
    temporary.revalidate()
    with os.scandir(temporary._child_fd) as entries:
        names = tuple(entry.name for entry in entries)
    if len(names) > _MAX_SNAPSHOT_TOP_LEVEL_ENTRIES:
        raise ConfigFreeKeyringError(
            "publisher snapshot top-level inventory exceeds its entry limit"
        )
    malformed = tuple(
        name
        for name in names
        if (name.startswith(".#lk") or name == _GPG_AGENT_SENTINEL)
        and not _is_gpg_lock_name(name)
    )
    if malformed:
        raise ConfigFreeKeyringError(
            "publisher snapshot contains a malformed GPG lock name"
        )
    lock_names = tuple(sorted(name for name in names if _is_gpg_lock_name(name)))
    if not lock_names:
        return
    if len(lock_names) > _MAX_GPG_LOCK_FILES:
        raise ConfigFreeKeyringError(
            "publisher snapshot GPG lock inventory exceeds its limit"
        )

    opened_locks: list[_GpgLockBinding] = []
    active_error: BaseException | None = None
    try:
        for name in lock_names:
            opened_locks.append(_open_gpg_lock(temporary, name))
        locks = tuple(opened_locks)
        links_by_identity: dict[tuple[int, int], int] = {}
        for lock in locks:
            links_by_identity[lock.identity] = (
                links_by_identity.get(lock.identity, 0) + 1
            )
        if any(
            lock.initial_link_count != links_by_identity[lock.identity]
            for lock in locks
        ):
            raise ConfigFreeKeyringError(
                "publisher snapshot GPG lock has an unbound hard link"
            )

        remaining = dict(links_by_identity)
        for lock in locks:
            temporary.revalidate()
            path = temporary.path / lock.name
            anchored = os.fstat(lock.descriptor)
            named = os.stat(
                lock.name,
                dir_fd=temporary._child_fd,
                follow_symlinks=False,
            )
            if (
                _validate_gpg_lock_metadata(anchored, path=path) != lock.identity
                or _validate_gpg_lock_metadata(named, path=path) != lock.identity
                or anchored.st_nlink != remaining[lock.identity]
            ):
                raise ConfigFreeKeyringError(
                    f"publisher snapshot GPG lock changed before cleanup: {lock.name}"
                )
            os.unlink(lock.name, dir_fd=temporary._child_fd)
            remaining[lock.identity] -= 1
            if os.fstat(lock.descriptor).st_nlink != remaining[lock.identity]:
                raise ConfigFreeKeyringError(
                    f"publisher snapshot GPG lock cleanup is unproved: {lock.name}"
                )
        temporary.revalidate()
    except BaseException as error:
        active_error = error
        raise
    finally:
        _close_gpg_locks(tuple(opened_locks), active_error=active_error)


def _recover_stale_snapshot(
    temporary: temporary_paths.BoundTemporaryDirectory,
) -> bool:
    if not gpg_snapshot_lease.stale_snapshot_is_recoverable(temporary):
        return False
    gpg_snapshot_recovery.stop_agent(temporary, allow_stale_listener=True)
    _remove_gpg_lock_files(temporary)
    gpg_snapshot_recovery.remove_stale_sockets(temporary)
    return True


def _clean_snapshot_after_use(
    temporary: temporary_paths.BoundTemporaryDirectory,
) -> None:
    gpg_snapshot_recovery.stop_agent(temporary)
    _remove_gpg_lock_files(temporary)
    if gpg_snapshot_recovery.socket_names(temporary):
        raise ConfigFreeKeyringError(
            "config-free publisher agent cleanup is incomplete"
        )


def _finish_snapshot_use(
    temporary: temporary_paths.BoundTemporaryDirectory,
    coordinator: temporary_recovery.RecoveryCoordinator,
    lease: gpg_snapshot_lease.ActiveSnapshotLease,
    *,
    operation_error: BaseException | None,
) -> None:
    cleanup_errors: list[tuple[str, BaseException]] = []
    try:
        coordinator.acquire()
    except BaseException as error:
        cleanup_errors.append(("root-coordination", error))
    try:
        _clean_snapshot_after_use(temporary)
        temporary.revalidate()
    except BaseException as error:
        cleanup_errors.append(("publisher-agent", error))
    if not cleanup_errors:
        try:
            lease.release(primary=operation_error)
        except BaseException as error:
            cleanup_errors.append(("active-lease", error))
    if not cleanup_errors:
        return
    primary = operation_error or cleanup_errors[0][1]
    temporary_paths.mark_incomplete_cleanup(
        primary,
        stage="publisher-snapshot-finalization",
    )
    for stage, error in cleanup_errors:
        if error is primary:
            continue
        primary.add_note(
            f"publisher snapshot cleanup failed at {stage}: {type(error).__name__}"
        )
    if operation_error is None:
        raise primary


@contextmanager
def config_free_keyring_snapshot_receipt(
    gnupg_home: str | os.PathLike[str],
) -> Iterator[ConfigFreeKeyringSnapshot]:
    """Yield a config-free keyring plus its exact selected-source commitment."""

    source = Path(gnupg_home).expanduser().absolute()
    try:
        source, source_fd = safe_io.open_owner_only_directory(
            source,
            reject_symlink_ancestors=True,
        )
    except (OSError, safe_io.UnsafePathError) as exc:
        raise ConfigFreeKeyringError("publisher GNUPGHOME is unavailable") from exc
    active_error: BaseException | None = None
    try:
        source_metadata = os.fstat(source_fd)
        source_identity = (source_metadata.st_dev, source_metadata.st_ino)
        _revalidate_keyring_directory(source_fd, source, source_identity)
        try:
            with temporary_recovery.serialized_stale_recovery(
                root=temporary_paths.PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT,
                prefix="g-",
                recover=_recover_stale_snapshot,
            ) as coordinator:
                lease: gpg_snapshot_lease.ActiveSnapshotLease | None = None
                snapshot_error: BaseException | None = None
                try:
                    with temporary_paths.owner_only_temporary_directory(
                        root=temporary_paths.PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT,
                        prefix="g-",
                    ) as temporary:
                        lease = gpg_snapshot_lease.acquire_active_lease(temporary)
                        coordinator.release()
                        operation_error: BaseException | None = None
                        try:
                            source_commitment = _copy_config_free_keyring(
                                source,
                                source_fd,
                                temporary.path,
                            )
                            temporary.revalidate()
                            if any(
                                (temporary.path / name).exists()
                                for name in (
                                    "common.conf",
                                    "gpg.conf",
                                    "gpg-agent.conf",
                                )
                            ):
                                raise ConfigFreeKeyringError(
                                    "config-free publisher keyring contains a "
                                    "configuration file"
                                )
                            yield ConfigFreeKeyringSnapshot(
                                path=temporary.path,
                                source_commitment=source_commitment,
                            )
                        except BaseException as error:
                            operation_error = error
                            raise
                        finally:
                            _finish_snapshot_use(
                                temporary,
                                coordinator,
                                lease,
                                operation_error=operation_error,
                            )
                except BaseException as error:
                    snapshot_error = error
                    raise
                finally:
                    if lease is not None and not lease.closed:
                        lease.close_after_tree_cleanup(primary=snapshot_error)
        except BaseException as error:
            active_error = error
            try:
                _revalidate_keyring_directory(source_fd, source, source_identity)
            except BaseException as validation_error:
                raise validation_error from error
            raise
        _revalidate_keyring_directory(source_fd, source, source_identity)
    except ConfigFreeKeyringError as exc:
        active_error = exc
        raise
    except (
        OSError,
        ValueError,
        gpg_snapshot_lease.GpgSnapshotLeaseError,
        gpg_snapshot_recovery.GpgSnapshotRecoveryError,
        safe_io.UnsafePathError,
        temporary_recovery.TemporaryRecoveryError,
    ) as exc:
        active_error = exc
        raise ConfigFreeKeyringError(
            "config-free publisher keyring could not be materialized"
        ) from exc
    finally:
        _close_descriptor(
            source_fd,
            active_error=active_error,
            label="publisher keyring",
        )


@contextmanager
def config_free_keyring_snapshot(
    gnupg_home: str | os.PathLike[str],
) -> Iterator[Path]:
    """Yield an owner-only keyring copy that excludes every GPG config file."""

    with config_free_keyring_snapshot_receipt(gnupg_home) as snapshot:
        yield snapshot.path


def publisher_keyring_source_commitment(
    gnupg_home: str | os.PathLike[str],
) -> str:
    """Return the commitment of the exact config-free selected key material."""

    with config_free_keyring_snapshot_receipt(gnupg_home) as snapshot:
        return snapshot.source_commitment
