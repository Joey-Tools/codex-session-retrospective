"""Content and access-policy authority for the coordinator implementation."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

from . import safe_io
from .checkpoints import canonical_json_bytes


IMPLEMENTATION_READINESS_SCHEMA = "coordinator_implementation_readiness_v2"
IMPLEMENTATION_ID = "session_retrospective_v2_python_source"
STARTUP_EVIDENCE_ATTRIBUTE = "_retrospective_v2_startup_authority_v2"
MAX_STARTUP_EVIDENCE_BYTES = 1024 * 1024
MAX_SOURCE_FILES = 160
MAX_SOURCE_FILE_BYTES = 2 * 1024 * 1024
MAX_SOURCE_TOTAL_BYTES = 32 * 1024 * 1024
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
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
    module: str,
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
            "module": module,
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
                _source_row(
                    scripts_fd,
                    name,
                    module=name.removesuffix(".py"),
                    relative_path=name,
                )
                for name in scripts_names
            ),
            *(
                _source_row(
                    package_fd,
                    name,
                    module=(
                        "retrospective_v2"
                        if name == "__init__.py"
                        else f"retrospective_v2.{name.removesuffix('.py')}"
                    ),
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
            {key: row[key] for key in ("module", "relative_path", "sha256", "size")}
            for row in rows
        ]
        access = {
            "ancestors": ancestor_policies,
            "files": [
                {
                    "access_policy": row["access_policy"],
                    "module": row["module"],
                    "relative_path": row["relative_path"],
                }
                for row in rows
            ],
            "package": package_policy,
        }
        authority = {
            "access": access,
            "manifest": [row["module"] for row in rows],
            "source": source,
        }
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


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ImplementationAuthorityError(
                "implementation startup evidence has duplicate keys"
            )
        result[key] = value
    return result


def _require_digest(value: object, *, prefixed: bool) -> str:
    if not isinstance(value, str):
        raise ImplementationAuthorityError(
            "implementation startup evidence has an invalid digest"
        )
    digest = value.removeprefix("sha256:") if prefixed else value
    if (prefixed and not value.startswith("sha256:")) or _SHA256_RE.fullmatch(
        digest
    ) is None:
        raise ImplementationAuthorityError(
            "implementation startup evidence has an invalid digest"
        )
    return value


def _require_integer(value: object, *, minimum: int, maximum: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise ImplementationAuthorityError(
            "implementation startup evidence has an invalid integer"
        )
    return value


def _validate_startup_policy(value: object, *, directory: bool) -> None:
    if not isinstance(value, dict) or set(value) != {
        "acl_sha256",
        "gid",
        "mode",
        "nlink",
        "type",
        "uid",
    }:
        raise ImplementationAuthorityError(
            "implementation startup access policy is invalid"
        )
    _require_digest(value["acl_sha256"], prefixed=False)
    _require_integer(value["gid"], minimum=0, maximum=(1 << 63) - 1)
    mode = _require_integer(value["mode"], minimum=0, maximum=0o7777)
    uid = _require_integer(value["uid"], minimum=0, maximum=(1 << 63) - 1)
    if uid not in {0, os.geteuid()} or mode & 0o022:
        raise ImplementationAuthorityError(
            "implementation startup access policy is unsafe"
        )
    if directory:
        if value["type"] != "directory" or value["nlink"] is not None:
            raise ImplementationAuthorityError(
                "implementation startup directory policy is invalid"
            )
    elif value["type"] != "regular-file" or value["nlink"] != 1:
        raise ImplementationAuthorityError(
            "implementation startup file policy is invalid"
        )


def validate_startup_receipt(evidence_bytes: bytes) -> dict[str, Any]:
    """Validate and return the descriptor-capture receipt installed at startup."""

    if (
        not isinstance(evidence_bytes, bytes)
        or not evidence_bytes
        or len(evidence_bytes) > MAX_STARTUP_EVIDENCE_BYTES
    ):
        raise ImplementationAuthorityError(
            "implementation startup evidence is unavailable"
        )
    try:
        evidence = json.loads(
            evidence_bytes.decode("ascii"),
            object_pairs_hook=_strict_json_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ImplementationAuthorityError(
            "implementation startup evidence is invalid"
        ) from error
    if not isinstance(evidence, dict) or set(evidence) != {
        "access",
        "manifest",
        "receipt",
        "source",
    }:
        raise ImplementationAuthorityError(
            "implementation startup evidence has an invalid shape"
        )
    manifest = evidence["manifest"]
    source = evidence["source"]
    access = evidence["access"]
    receipt = evidence["receipt"]
    if (
        not isinstance(manifest, list)
        or not 1 <= len(manifest) <= MAX_SOURCE_FILES
        or any(not isinstance(module, str) or not module for module in manifest)
        or len(manifest) != len(set(manifest))
        or not isinstance(source, list)
        or len(source) != len(manifest)
    ):
        raise ImplementationAuthorityError("implementation startup manifest is invalid")
    total_bytes = 0
    source_keys = {"module", "relative_path", "sha256", "size"}
    for module, row in zip(manifest, source, strict=True):
        if not isinstance(row, dict) or set(row) != source_keys:
            raise ImplementationAuthorityError(
                "implementation startup source row is invalid"
            )
        if module == "retrospective_v2":
            expected_path = "retrospective_v2/__init__.py"
        elif module.startswith("retrospective_v2.") and module.count(".") == 1:
            expected_path = "retrospective_v2/" + module.split(".", 1)[1] + ".py"
        elif module == "session_retrospective_v2":
            expected_path = "session_retrospective_v2.py"
        elif module.startswith("session_retrospective_v2_"):
            expected_path = module + ".py"
        else:
            raise ImplementationAuthorityError(
                "implementation startup module name is invalid"
            )
        if row["module"] != module or row["relative_path"] != expected_path:
            raise ImplementationAuthorityError(
                "implementation startup source binding is invalid"
            )
        _require_digest(row["sha256"], prefixed=False)
        total_bytes += _require_integer(
            row["size"], minimum=0, maximum=MAX_SOURCE_FILE_BYTES
        )
    if total_bytes > MAX_SOURCE_TOTAL_BYTES:
        raise ImplementationAuthorityError(
            "implementation startup source exceeds its byte bound"
        )
    if not isinstance(access, dict) or set(access) != {
        "ancestors",
        "files",
        "package",
    }:
        raise ImplementationAuthorityError(
            "implementation startup access evidence is invalid"
        )
    ancestors = access["ancestors"]
    files = access["files"]
    if not isinstance(ancestors, list) or not ancestors:
        raise ImplementationAuthorityError(
            "implementation startup ancestor evidence is invalid"
        )
    for policy in ancestors:
        _validate_startup_policy(policy, directory=True)
    _validate_startup_policy(access["package"], directory=True)
    if not isinstance(files, list) or len(files) != len(source):
        raise ImplementationAuthorityError(
            "implementation startup file evidence is invalid"
        )
    for source_row, access_row in zip(source, files, strict=True):
        if not isinstance(access_row, dict) or set(access_row) != {
            "access_policy",
            "module",
            "relative_path",
        }:
            raise ImplementationAuthorityError(
                "implementation startup file evidence is invalid"
            )
        if (
            access_row["module"] != source_row["module"]
            or access_row["relative_path"] != source_row["relative_path"]
        ):
            raise ImplementationAuthorityError(
                "implementation startup access binding is invalid"
            )
        _validate_startup_policy(access_row["access_policy"], directory=False)
    receipt_keys = {
        "access_policy_sha256",
        "authority_sha256",
        "file_count",
        "implementation",
        "schema",
        "source_sha256",
        "total_bytes",
    }
    if not isinstance(receipt, dict) or set(receipt) != receipt_keys:
        raise ImplementationAuthorityError("implementation startup receipt is invalid")
    for field in ("access_policy_sha256", "authority_sha256", "source_sha256"):
        _require_digest(receipt[field], prefixed=True)
    authority = {"access": access, "manifest": manifest, "source": source}
    expected = {
        "access_policy_sha256": "sha256:"
        + hashlib.sha256(canonical_json_bytes(access)).hexdigest(),
        "authority_sha256": "sha256:"
        + hashlib.sha256(canonical_json_bytes(authority)).hexdigest(),
        "file_count": len(source),
        "implementation": IMPLEMENTATION_ID,
        "schema": IMPLEMENTATION_READINESS_SCHEMA,
        "source_sha256": "sha256:"
        + hashlib.sha256(canonical_json_bytes(source)).hexdigest(),
        "total_bytes": total_bytes,
    }
    if receipt != expected:
        raise ImplementationAuthorityError(
            "implementation startup receipt does not match captured authority"
        )
    return dict(receipt)


def coordinator_implementation_readiness() -> dict[str, Any]:
    startup_evidence = getattr(sys, STARTUP_EVIDENCE_ATTRIBUTE, None)
    if startup_evidence is not None:
        return validate_startup_receipt(startup_evidence)
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
