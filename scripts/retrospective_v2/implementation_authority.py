"""Content and access-policy authority for the coordinator implementation."""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import stat
from typing import Any

from . import safe_io
from .checkpoints import canonical_json_bytes


IMPLEMENTATION_READINESS_SCHEMA = "coordinator_implementation_readiness_v1"
IMPLEMENTATION_ID = "session_retrospective_v2_python_source"
MAX_SOURCE_FILES = 128
MAX_SOURCE_FILE_BYTES = 2 * 1024 * 1024
MAX_SOURCE_TOTAL_BYTES = 32 * 1024 * 1024
_DIRECTORY_FLAGS = (
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
)
_FILE_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_CLOEXEC", 0)
)


class ImplementationAuthorityError(PermissionError):
    """The coordinator source content or access policy was not proved."""


def _policy(descriptor: int, *, directory: bool) -> dict[str, Any]:
    metadata = os.fstat(descriptor)
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(metadata.st_mode):
        raise ImplementationAuthorityError("implementation source has an invalid type")
    if metadata.st_uid not in {0, os.geteuid()}:
        raise ImplementationAuthorityError(
            "implementation source has an untrusted owner"
        )
    mode = stat.S_IMODE(metadata.st_mode)
    if mode & 0o022:
        raise ImplementationAuthorityError(
            "implementation source is writable by another user"
        )
    try:
        acl = safe_io.descriptor_acl_policy_bytes(descriptor)
    except safe_io.UnsafePathError as error:
        raise ImplementationAuthorityError(
            "implementation source ACL cannot be authenticated"
        ) from error
    entries = [
        line for line in acl.splitlines() if line and not line.startswith(b"!#acl")
    ]
    if any(b":allow:" in line or b":deny:" not in line for line in entries):
        raise ImplementationAuthorityError("implementation source ACL is unsafe")
    return {
        "acl_sha256": hashlib.sha256(acl).hexdigest(),
        "mode": mode,
        "owner": "root" if metadata.st_uid == 0 else "effective-user",
        "type": "directory" if directory else "regular-file",
    }


def _read_exact(descriptor: int, size: int) -> bytes:
    if size < 0 or size > MAX_SOURCE_FILE_BYTES:
        raise ImplementationAuthorityError(
            "implementation source exceeds its byte bound"
        )
    chunks: list[bytes] = []
    offset = 0
    while offset < size:
        chunk = os.pread(descriptor, min(64 * 1024, size - offset), offset)
        if not chunk:
            raise ImplementationAuthorityError(
                "implementation source changed while read"
            )
        chunks.append(chunk)
        offset += len(chunk)
    if os.pread(descriptor, 1, size):
        raise ImplementationAuthorityError("implementation source changed while read")
    return b"".join(chunks)


def _source_row(
    parent_fd: int,
    name: str,
    *,
    relative_path: str,
) -> dict[str, Any]:
    try:
        descriptor = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
    except OSError as error:
        raise ImplementationAuthorityError(
            "implementation source cannot be opened"
        ) from error
    primary: BaseException | None = None
    try:
        before = os.fstat(descriptor)
        first_policy = _policy(descriptor, directory=False)
        first = _read_exact(descriptor, before.st_size)
        middle = os.fstat(descriptor)
        second_policy = _policy(descriptor, directory=False)
        second = _read_exact(descriptor, before.st_size)
        after = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)

        def identity(value: os.stat_result) -> tuple[int, int, int]:
            return (value.st_dev, value.st_ino, value.st_size)

        if (
            identity(before) != identity(middle)
            or identity(before) != identity(after)
            or identity(before) != identity(named)
            or first_policy != second_policy
            or not hmac.compare_digest(first, second)
        ):
            raise ImplementationAuthorityError(
                "implementation source changed while read"
            )
        return {
            "access_policy": first_policy,
            "relative_path": relative_path,
            "sha256": hashlib.sha256(first).hexdigest(),
            "size": len(first),
        }
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            os.close(descriptor)
        except OSError as error:
            if primary is not None:
                primary.add_note("implementation source descriptor cleanup failed")
            else:
                raise ImplementationAuthorityError(
                    "implementation source descriptor cleanup failed"
                ) from error


def _selected_names(descriptor: int, *, package: bool) -> list[str]:
    try:
        names = os.listdir(descriptor)
    except OSError as error:
        raise ImplementationAuthorityError(
            "implementation inventory cannot be listed"
        ) from error
    if any(not isinstance(name, str) or "\x00" in name for name in names):
        raise ImplementationAuthorityError(
            "implementation inventory has an invalid name"
        )
    selected = sorted(
        name
        for name in names
        if name.endswith(".py")
        and (package or name.startswith("session_retrospective_v2"))
    )
    if len(selected) > MAX_SOURCE_FILES:
        raise ImplementationAuthorityError(
            "implementation inventory exceeds its file bound"
        )
    return selected


def _open_scripts_chain() -> tuple[list[int], list[dict[str, Any]], Path]:
    scripts = Path(os.path.realpath(__file__)).parent.parent
    if not scripts.is_absolute() or scripts.name != "scripts":
        raise ImplementationAuthorityError("implementation scripts root is invalid")
    descriptors: list[int] = []
    policies: list[dict[str, Any]] = []
    try:
        current = os.open(scripts.anchor, _DIRECTORY_FLAGS)
        descriptors.append(current)
        policies.append(_policy(current, directory=True))
        for component in scripts.parts[1:]:
            child = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            descriptors.append(child)
            policies.append(_policy(child, directory=True))
            observed = os.stat(component, dir_fd=current, follow_symlinks=False)
            anchored = os.fstat(child)
            if (observed.st_dev, observed.st_ino) != (anchored.st_dev, anchored.st_ino):
                raise ImplementationAuthorityError(
                    "implementation path identity changed"
                )
            current = child
        return descriptors, policies, scripts
    except BaseException:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


def _readiness_from_bound_scripts(
    scripts_fd: int,
    *,
    ancestor_policies: list[dict[str, Any]],
) -> dict[str, Any]:
    scripts_policy = _policy(scripts_fd, directory=True)
    if not ancestor_policies or ancestor_policies[-1] != scripts_policy:
        raise ImplementationAuthorityError("implementation ancestor policy changed")
    package_fd = -1
    primary: BaseException | None = None
    try:
        try:
            package_fd = os.open(
                "retrospective_v2", _DIRECTORY_FLAGS, dir_fd=scripts_fd
            )
        except OSError as error:
            raise ImplementationAuthorityError(
                "implementation package cannot be opened"
            ) from error
        package_policy = _policy(package_fd, directory=True)
        scripts_names = _selected_names(scripts_fd, package=False)
        package_names = _selected_names(package_fd, package=True)
        if (
            "session_retrospective_v2.py" not in scripts_names
            or "__init__.py" not in package_names
        ):
            raise ImplementationAuthorityError("implementation inventory is incomplete")
        rows = [
            *(
                _source_row(scripts_fd, name, relative_path=name)
                for name in scripts_names
            ),
            *(
                _source_row(
                    package_fd,
                    name,
                    relative_path=f"retrospective_v2/{name}",
                )
                for name in package_names
            ),
        ]
        if (
            _selected_names(scripts_fd, package=False) != scripts_names
            or _selected_names(package_fd, package=True) != package_names
        ):
            raise ImplementationAuthorityError("implementation inventory changed")
        if (
            _policy(scripts_fd, directory=True) != scripts_policy
            or _policy(package_fd, directory=True) != package_policy
        ):
            raise ImplementationAuthorityError(
                "implementation directory access policy changed"
            )
        total_bytes = sum(row["size"] for row in rows)
        if total_bytes > MAX_SOURCE_TOTAL_BYTES:
            raise ImplementationAuthorityError(
                "implementation exceeds its aggregate byte bound"
            )
        source = [
            {key: row[key] for key in ("relative_path", "sha256", "size")}
            for row in rows
        ]
        access = {
            "ancestors": ancestor_policies,
            "files": [
                {
                    "access_policy": row["access_policy"],
                    "relative_path": row["relative_path"],
                }
                for row in rows
            ],
            "package": package_policy,
        }
        authority = {"access": access, "source": source}
        return {
            "access_policy_sha256": "sha256:"
            + hashlib.sha256(canonical_json_bytes(access)).hexdigest(),
            "authority_sha256": "sha256:"
            + hashlib.sha256(canonical_json_bytes(authority)).hexdigest(),
            "file_count": len(rows),
            "implementation": IMPLEMENTATION_ID,
            "schema": IMPLEMENTATION_READINESS_SCHEMA,
            "source_sha256": "sha256:"
            + hashlib.sha256(canonical_json_bytes(source)).hexdigest(),
            "total_bytes": total_bytes,
        }
    except BaseException as error:
        primary = error
        raise
    finally:
        if package_fd >= 0:
            try:
                os.close(package_fd)
            except OSError as error:
                if primary is not None:
                    primary.add_note(
                        "implementation authority descriptor cleanup failed"
                    )
                else:
                    raise ImplementationAuthorityError(
                        "implementation authority descriptor cleanup failed"
                    ) from error


def coordinator_implementation_readiness() -> dict[str, Any]:
    descriptors, ancestor_policies, _scripts = _open_scripts_chain()
    primary: BaseException | None = None
    try:
        readiness = _readiness_from_bound_scripts(
            descriptors[-1],
            ancestor_policies=ancestor_policies,
        )
        if [
            _policy(descriptor, directory=True) for descriptor in descriptors
        ] != ancestor_policies:
            raise ImplementationAuthorityError(
                "implementation ancestor access policy changed"
            )
        return readiness
    except BaseException as error:
        primary = error
        raise
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError as error:
                if primary is not None:
                    primary.add_note(
                        "implementation authority descriptor cleanup failed"
                    )
                else:
                    raise ImplementationAuthorityError(
                        "implementation authority descriptor cleanup failed"
                    ) from error
