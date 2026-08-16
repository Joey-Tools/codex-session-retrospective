"""Descriptor-bound source transport program components."""

from __future__ import annotations

import base64
import hashlib
import os
import pathlib
import stat

try:
    from .contracts import JsonValue
    from .transport_contracts import SOURCE_TRANSPORT_WORKER_MODULE_MANIFEST
    from .transport_contracts import TransportValidationError
    from .transport_paths import (
        _program_named_identity,
        _program_stat_identity,
        _read_program_component,
        _require_program_component_policy,
    )
except (ImportError, ModuleNotFoundError):
    from contracts import JsonValue  # type: ignore[no-redef]
    from transport_contracts import (  # type: ignore[no-redef]
        SOURCE_TRANSPORT_WORKER_MODULE_MANIFEST,
        TransportValidationError,
    )
    from transport_paths import (  # type: ignore[no-redef]
        _program_named_identity,
        _program_stat_identity,
        _read_program_component,
        _require_program_component_policy,
    )

SOURCE_TRANSPORT_MAX_PROGRAM_COMPONENT_BYTES = 4 * 1024 * 1024


def _program_component(
    path: pathlib.Path,
    *,
    role: str,
    allow_missing: bool,
    maximum_bytes: int = SOURCE_TRANSPORT_MAX_PROGRAM_COMPONENT_BYTES,
    include_content: bool = False,
) -> dict[str, JsonValue]:
    path = pathlib.Path(os.path.abspath(os.fspath(path)))
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        parent_fd = os.open(path.parent, flags)
    except FileNotFoundError as exc:
        if allow_missing:
            return {"path": str(path), "role": role, "state": "absent"}
        raise TransportValidationError(
            f"source transport {role} is unavailable"
        ) from exc
    except OSError as exc:
        raise TransportValidationError(
            f"source transport {role} cannot be authenticated"
        ) from exc
    try:
        return _program_component_at(
            parent_fd,
            path.name,
            display_path=path,
            role=role,
            allow_missing=allow_missing,
            maximum_bytes=maximum_bytes,
            include_content=include_content,
        )
    finally:
        os.close(parent_fd)


def _program_component_at(
    parent_fd: int,
    name: str,
    *,
    display_path: pathlib.Path,
    role: str,
    allow_missing: bool,
    maximum_bytes: int = SOURCE_TRANSPORT_MAX_PROGRAM_COMPONENT_BYTES,
    include_content: bool = False,
) -> dict[str, JsonValue]:
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        raise TransportValidationError(
            f"source transport {role} has an invalid component name"
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError as exc:
        if allow_missing:
            return {"path": str(display_path), "role": role, "state": "absent"}
        raise TransportValidationError(
            f"source transport {role} is unavailable"
        ) from exc
    except OSError as exc:
        raise TransportValidationError(
            f"source transport {role} cannot be authenticated"
        ) from exc
    try:
        before = os.fstat(descriptor)
        _require_program_component_policy(before, descriptor, role)
        if before.st_size > maximum_bytes:
            raise TransportValidationError(
                f"source transport {role} exceeds the program component bound"
            )
        expected_identity = _program_stat_identity(before)
        if (
            _program_named_identity(parent_fd, name, role=role, phase="opened")
            != expected_identity
        ):
            raise TransportValidationError(
                f"source transport {role} changed while opened"
            )
        retained = _read_program_component(descriptor, maximum_bytes, role)
        changed_message = f"source transport {role} changed while read"
        if len(retained) != before.st_size:
            raise TransportValidationError(changed_message)
        os.lseek(descriptor, 0, os.SEEK_SET)
        if _read_program_component(descriptor, maximum_bytes, role) != retained:
            raise TransportValidationError(changed_message)
        after = os.fstat(descriptor)
        if (
            _program_stat_identity(after) != expected_identity
            or after.st_size != before.st_size
            or _program_named_identity(parent_fd, name, role=role, phase="read")
            != expected_identity
        ):
            raise TransportValidationError(changed_message)
        _require_program_component_policy(after, descriptor, role)
        component: dict[str, JsonValue] = {
            "content_commitment": "sha256:" + hashlib.sha256(retained).hexdigest(),
            "path": str(display_path),
            "role": role,
            "state": "present",
        }
        if include_content:
            component["content_b64"] = base64.b64encode(retained).decode("ascii")
        return component
    finally:
        os.close(descriptor)


def _package_program_components(
    package_dir: pathlib.Path,
    *,
    include_content: bool = False,
) -> list[dict[str, JsonValue]]:
    package_dir = pathlib.Path(os.path.abspath(os.fspath(package_dir)))
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_fd = os.open(package_dir, flags)
    except OSError as exc:
        raise TransportValidationError(
            "source transport package tree cannot be authenticated"
        ) from exc
    try:
        before = os.fstat(directory_fd)
        if not stat.S_ISDIR(before.st_mode):
            raise TransportValidationError(
                "source transport package tree must be a real directory"
            )
        manifest = SOURCE_TRANSPORT_WORKER_MODULE_MANIFEST
        if len(manifest) != len(set(manifest)) or any(
            not name.endswith(".py")
            or not name
            or name in {".", ".."}
            or "/" in name
            or "\x00" in name
            for name in manifest
        ):
            raise TransportValidationError(
                "source transport worker dependency manifest is invalid"
            )
        components = [
            _program_component_at(
                directory_fd,
                module_name,
                display_path=package_dir / module_name,
                role=f"package_module:{module_name}",
                allow_missing=False,
                include_content=include_content,
            )
            for module_name in manifest
        ]
        after = os.fstat(directory_fd)
        try:
            named_after = os.stat(package_dir, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise TransportValidationError(
                "source transport package tree changed while hashed"
            ) from exc
        if _program_stat_identity(after) != _program_stat_identity(before) or (
            named_after.st_dev,
            named_after.st_ino,
        ) != (before.st_dev, before.st_ino):
            raise TransportValidationError(
                "source transport package tree changed while hashed"
            )
        return components
    finally:
        os.close(directory_fd)
