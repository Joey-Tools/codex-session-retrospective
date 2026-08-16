"""Point-in-time executable identity, content, and access-policy authority."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat

from . import safe_io


MAX_EXECUTABLE_BYTES = 256 * 1024 * 1024
DEFAULT_GIT_EXECUTABLE = "/usr/bin/git"
DEFAULT_GPG_EXECUTABLE = "gpg"
_SHARED_OPEN_FLAGS = (
    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
)
_DIRECTORY_FLAGS = _SHARED_OPEN_FLAGS | getattr(os, "O_DIRECTORY", 0)
_FILE_FLAGS = _SHARED_OPEN_FLAGS | getattr(os, "O_NONBLOCK", 0)


def is_canonical_absolute_executable_path(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and "\x00" not in value
        and not value.startswith("//")
        and Path(value).is_absolute()
        and os.path.abspath(value) == value
    )


class ExecutableAuthorityError(PermissionError):
    """The selected executable's protected properties were not proved."""


@dataclass(frozen=True, slots=True)
class PathObjectAuthority:
    path: str
    device: int
    inode: int
    owner: int
    group: int
    mode: int
    acl_sha256: str


@dataclass(frozen=True, slots=True)
class ExecutableAuthority:
    label: str
    path: str
    ancestors: tuple[PathObjectAuthority, ...]
    executable: PathObjectAuthority
    size: int
    sha256: str


def authority_digest(authority: ExecutableAuthority) -> str:
    """Commit to the executable's identity, content, and access-policy receipt."""

    payload = json.dumps(
        asdict(authority),
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def require_authority_digest(
    authority: ExecutableAuthority,
    expected_digest: str,
) -> None:
    if authority_digest(authority) != expected_digest:
        raise ExecutableAuthorityError(
            f"{authority.label} executable authority digest changed"
        )


def _close_descriptors(
    descriptors: Sequence[int],
    label: str,
    *,
    primary: BaseException | None = None,
) -> None:
    failures: list[OSError] = []
    for descriptor in reversed(descriptors):
        try:
            os.close(descriptor)
        except OSError as error:
            failures.append(error)
    if not failures:
        return
    message = f"{label} executable descriptor cleanup failed"
    if primary is not None:
        primary.add_note(message)
        return
    raise ExecutableAuthorityError(message) from failures[0]


def _can_execute(metadata: os.stat_result) -> bool:
    mode = stat.S_IMODE(metadata.st_mode)
    effective_uid = os.geteuid()
    if effective_uid == 0:
        return bool(mode & 0o111)
    if metadata.st_uid == effective_uid:
        return bool(mode & stat.S_IXUSR)
    groups = {os.getegid(), *os.getgroups()}
    if metadata.st_gid in groups:
        return bool(mode & stat.S_IXGRP)
    return bool(mode & stat.S_IXOTH)


def _authority_for_descriptor(
    descriptor: int,
    path: Path,
    *,
    directory: bool,
) -> tuple[PathObjectAuthority, os.stat_result]:
    metadata = os.fstat(descriptor)
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    kind = "ancestor" if directory else "executable"
    if not expected_type(metadata.st_mode):
        raise ExecutableAuthorityError(f"{kind} is not the required object type")
    if metadata.st_uid not in {0, os.geteuid()}:
        raise ExecutableAuthorityError(f"{kind} has an untrusted owner")
    mode = stat.S_IMODE(metadata.st_mode)
    if mode & 0o022:
        raise ExecutableAuthorityError(f"{kind} is writable by another user")
    acl_policy = safe_io.descriptor_acl_policy_bytes(descriptor)
    acl_entries = [
        line
        for line in acl_policy.splitlines()
        if line and not line.startswith(b"!#acl")
    ]
    if any(b":allow:" in line or b":deny:" not in line for line in acl_entries):
        raise ExecutableAuthorityError(f"{kind} has an unsafe extended access policy")
    if not _can_execute(metadata):
        raise ExecutableAuthorityError(f"{kind} is not executable by this process")
    return (
        PathObjectAuthority(
            path=os.fspath(path),
            device=metadata.st_dev,
            inode=metadata.st_ino,
            owner=metadata.st_uid,
            group=metadata.st_gid,
            mode=mode,
            acl_sha256=hashlib.sha256(acl_policy).hexdigest(),
        ),
        metadata,
    )


def _require_named_object(
    parent_descriptor: int,
    name: str,
    descriptor: int,
    expected: PathObjectAuthority,
    *,
    directory: bool,
) -> os.stat_result:
    current, metadata = _authority_for_descriptor(
        descriptor, Path(expected.path), directory=directory
    )
    named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    named_authority = PathObjectAuthority(
        path=expected.path,
        device=named.st_dev,
        inode=named.st_ino,
        owner=named.st_uid,
        group=named.st_gid,
        mode=stat.S_IMODE(named.st_mode),
        acl_sha256=current.acl_sha256,
    )
    if current != expected or named_authority != expected:
        raise ExecutableAuthorityError("executable path object changed")
    return metadata


def _content_digest(descriptor: int, expected_size: int) -> str:
    if expected_size < 0 or expected_size > MAX_EXECUTABLE_BYTES:
        raise ExecutableAuthorityError("executable exceeds its byte bound")
    digest = hashlib.sha256()
    offset = 0
    while offset < expected_size:
        chunk = os.pread(
            descriptor,
            min(1024 * 1024, expected_size - offset),
            offset,
        )
        if not chunk:
            raise ExecutableAuthorityError("executable changed while read")
        digest.update(chunk)
        offset += len(chunk)
    if os.pread(descriptor, 1, offset):
        raise ExecutableAuthorityError("executable changed while read")
    return digest.hexdigest()


def _capture_exact_path(path: Path, *, label: str) -> ExecutableAuthority:
    if not path.is_absolute() or path == Path(path.anchor) or not path.name:
        raise ExecutableAuthorityError(f"{label} executable path is invalid")
    descriptors: list[int] = []
    directory_rows: list[tuple[str, int, int, PathObjectAuthority]] = []
    primary: BaseException | None = None
    try:
        parent_descriptor = os.open(path.anchor, _DIRECTORY_FLAGS)
        descriptors.append(parent_descriptor)
        current_path = Path(path.anchor)
        root_authority, _metadata = _authority_for_descriptor(
            parent_descriptor, current_path, directory=True
        )
        ancestors = [root_authority]
        for component in path.parts[1:-1]:
            child_descriptor = os.open(
                component, _DIRECTORY_FLAGS, dir_fd=parent_descriptor
            )
            descriptors.append(child_descriptor)
            current_path /= component
            child_authority, _metadata = _authority_for_descriptor(
                child_descriptor, current_path, directory=True
            )
            _require_named_object(
                parent_descriptor,
                component,
                child_descriptor,
                child_authority,
                directory=True,
            )
            directory_rows.append(
                (component, parent_descriptor, child_descriptor, child_authority)
            )
            ancestors.append(child_authority)
            parent_descriptor = child_descriptor

        executable_descriptor = os.open(
            path.name, _FILE_FLAGS, dir_fd=parent_descriptor
        )
        descriptors.append(executable_descriptor)
        executable_authority, metadata = _authority_for_descriptor(
            executable_descriptor, path, directory=False
        )
        metadata = _require_named_object(
            parent_descriptor,
            path.name,
            executable_descriptor,
            executable_authority,
            directory=False,
        )
        executable_size = metadata.st_size
        first_digest = _content_digest(executable_descriptor, executable_size)
        metadata = _require_named_object(
            parent_descriptor,
            path.name,
            executable_descriptor,
            executable_authority,
            directory=False,
        )
        if metadata.st_size != executable_size:
            raise ExecutableAuthorityError("executable size changed while read")
        second_digest = _content_digest(executable_descriptor, executable_size)
        metadata = _require_named_object(
            parent_descriptor,
            path.name,
            executable_descriptor,
            executable_authority,
            directory=False,
        )
        if metadata.st_size != executable_size or first_digest != second_digest:
            raise ExecutableAuthorityError("executable content changed while read")
        current_root, _metadata = _authority_for_descriptor(
            descriptors[0], Path(path.anchor), directory=True
        )
        if current_root != root_authority:
            raise ExecutableAuthorityError("executable path root changed")
        for component, parent_fd, child_fd, expected in directory_rows:
            _require_named_object(
                parent_fd, component, child_fd, expected, directory=True
            )
        return ExecutableAuthority(
            label=label,
            path=os.fspath(path),
            ancestors=tuple(ancestors),
            executable=executable_authority,
            size=executable_size,
            sha256=first_digest,
        )
    except ExecutableAuthorityError as error:
        primary = error
        raise
    except (OSError, safe_io.UnsafePathError) as error:
        mapped = ExecutableAuthorityError(f"cannot authenticate the {label} executable")
        primary = mapped
        raise mapped from error
    except BaseException as error:
        primary = error
        raise
    finally:
        _close_descriptors(descriptors, label, primary=primary)


def resolve_executable(
    value: str | os.PathLike[str], *, label: str
) -> ExecutableAuthority:
    candidate = os.fspath(value)
    if not candidate or "\x00" in candidate:
        raise ExecutableAuthorityError(f"{label} executable is unavailable")
    resolved = shutil.which(candidate, path=os.environ.get("PATH", os.defpath))
    if resolved is None:
        raise ExecutableAuthorityError(f"{label} executable is unavailable")
    return _capture_exact_path(Path(os.path.realpath(resolved)), label=label)


def revalidate_executable(authority: ExecutableAuthority) -> None:
    try:
        current = _capture_exact_path(Path(authority.path), label=authority.label)
    except ExecutableAuthorityError as error:
        raise ExecutableAuthorityError(
            f"{authority.label} executable authority is no longer valid"
        ) from error
    if current != authority:
        raise ExecutableAuthorityError(
            f"{authority.label} executable authority changed after validation"
        )


@contextmanager
def executable_invocation(
    *authorities: ExecutableAuthority,
) -> Iterator[None]:
    for authority in authorities:
        revalidate_executable(authority)
    try:
        yield
    except BaseException as operation_error:
        try:
            for authority in authorities:
                revalidate_executable(authority)
        except BaseException as validation_error:
            raise validation_error from operation_error
        raise
    for authority in authorities:
        revalidate_executable(authority)
