from __future__ import annotations

import hashlib
import os
from pathlib import Path
import secrets
import stat

from . import safe_io


def _parent_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(stat.S_IFMT(metadata.st_mode)),
        int(metadata.st_uid),
        int(metadata.st_gid),
        int(stat.S_IMODE(metadata.st_mode)),
        safe_io.directory_access_policy_flags(metadata),
        int(getattr(metadata, "st_gen", -1)),
    )


def _file_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(stat.S_IFMT(metadata.st_mode)),
        int(metadata.st_uid),
        int(metadata.st_gid),
        int(stat.S_IMODE(metadata.st_mode)),
        int(metadata.st_nlink),
        int(metadata.st_size),
        int(getattr(metadata, "st_flags", 0)),
        int(getattr(metadata, "st_gen", -1)),
    )


def _validate_parent(
    descriptor: int,
    display_path: Path,
    *,
    expected_identity: tuple[int, ...] | None = None,
) -> tuple[int, ...]:
    before = os.fstat(descriptor)
    safe_io.validate_owner_only_directory_descriptor(
        descriptor,
        display_path,
        exact_mode=True,
    )
    after = os.fstat(descriptor)
    before_identity = _parent_identity(before)
    after_identity = _parent_identity(after)
    if before_identity != after_identity:
        raise safe_io.UnsafePathError(
            "private output parent identity or access policy changed"
        )
    if expected_identity is not None and after_identity != expected_identity:
        raise safe_io.UnsafePathError(
            "private output parent no longer matches its bound identity"
        )
    return after_identity


def _descriptor_digest(descriptor: int, expected_size: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while offset < expected_size:
        chunk = os.pread(descriptor, min(64 * 1024, expected_size - offset), offset)
        if not chunk:
            raise OSError("private output content ended before its bound size")
        digest.update(chunk)
        offset += len(chunk)
    if os.pread(descriptor, 1, offset):
        raise OSError("private output content grew beyond its bound size")
    return digest.hexdigest()


def _require_name_matches_descriptor(
    descriptor: int,
    parent_descriptor: int,
    name: str,
    display_path: Path,
) -> None:
    descriptor_metadata = os.fstat(descriptor)
    try:
        named_metadata = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError as error:
        raise safe_io.UnsafePathError(
            f"private output directory entry disappeared: {display_path}"
        ) from error
    if (descriptor_metadata.st_dev, descriptor_metadata.st_ino) != (
        named_metadata.st_dev,
        named_metadata.st_ino,
    ):
        raise safe_io.UnsafePathError(
            f"private output directory entry changed: {display_path}"
        )


def _validate_bound_file(
    descriptor: int,
    parent_descriptor: int,
    name: str,
    display_path: Path,
    *,
    expected_identity: tuple[int, ...] | None = None,
    expected_digest: str | None = None,
) -> tuple[tuple[int, ...], str]:
    before = os.fstat(descriptor)
    _require_name_matches_descriptor(
        descriptor,
        parent_descriptor,
        name,
        display_path,
    )
    safe_io.validate_owner_only_file_descriptor(
        descriptor,
        display_path,
        directory_fd=parent_descriptor,
        name=name,
    )
    digest = _descriptor_digest(descriptor, int(before.st_size))
    safe_io.validate_owner_only_file_descriptor(
        descriptor,
        display_path,
        directory_fd=parent_descriptor,
        name=name,
    )
    _require_name_matches_descriptor(
        descriptor,
        parent_descriptor,
        name,
        display_path,
    )
    after = os.fstat(descriptor)
    before_identity = _file_identity(before)
    after_identity = _file_identity(after)
    if before_identity != after_identity:
        raise safe_io.UnsafePathError(
            "private output identity, size, or access policy changed"
        )
    if expected_identity is not None and after_identity != expected_identity:
        raise safe_io.UnsafePathError(
            "private output no longer matches its bound identity"
        )
    if expected_digest is not None and digest != expected_digest:
        raise safe_io.UnsafePathError("private output content digest changed")
    return after_identity, digest


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    offset = 0
    while offset < len(view):
        written = os.write(descriptor, view[offset:])
        if written <= 0:
            raise OSError("short write while persisting private output")
        offset += written


def _unlink_bound_temporary(
    parent_descriptor: int,
    descriptor: int,
    name: str,
    display_path: Path,
) -> None:
    try:
        _require_name_matches_descriptor(
            descriptor,
            parent_descriptor,
            name,
            display_path,
        )
        safe_io.validate_owner_only_file_descriptor(
            descriptor,
            display_path,
            directory_fd=parent_descriptor,
            name=name,
        )
    except (OSError, ValueError):
        return
    os.unlink(name, dir_fd=parent_descriptor)


def _validate_existing_target(parent_descriptor: int, output: Path) -> None:
    try:
        metadata = os.stat(
            output.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("output path exists and is not a regular file")


def _write_private_bytes_at(
    parent_descriptor: int,
    output: Path,
    data: bytes,
) -> None:
    parent_identity = _validate_parent(parent_descriptor, output.parent)
    _validate_existing_target(parent_descriptor, output)
    expected_digest = hashlib.sha256(data).hexdigest()
    target_token = hashlib.sha256(os.fsencode(output.name)).hexdigest()[:16]
    temporary_name: str | None = None
    descriptor: int | None = None
    last_error: FileExistsError | None = None

    for _attempt in range(32):
        candidate = f".private-output-{target_token}-{secrets.token_hex(16)}.tmp"
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            descriptor = os.open(
                candidate,
                flags,
                safe_io.OWNER_FILE_MODE,
                dir_fd=parent_descriptor,
            )
        except FileExistsError as error:
            last_error = error
            continue
        temporary_name = candidate
        break

    if descriptor is None or temporary_name is None:
        raise FileExistsError(
            f"could not create private temporary output for {output}"
        ) from last_error

    operation_error: BaseException | None = None
    try:
        temporary_path = output.parent / temporary_name
        safe_io.harden_created_owner_only_file_descriptor(
            descriptor,
            temporary_path,
        )
        _write_all(descriptor, data)
        os.fsync(descriptor)
        file_identity, file_digest = _validate_bound_file(
            descriptor,
            parent_descriptor,
            temporary_name,
            temporary_path,
            expected_digest=expected_digest,
        )
        _validate_parent(
            parent_descriptor,
            output.parent,
            expected_identity=parent_identity,
        )
        _validate_bound_file(
            descriptor,
            parent_descriptor,
            temporary_name,
            temporary_path,
            expected_identity=file_identity,
            expected_digest=file_digest,
        )
        os.replace(
            temporary_name,
            output.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_name = None
        os.fsync(parent_descriptor)
        _validate_parent(
            parent_descriptor,
            output.parent,
            expected_identity=parent_identity,
        )
        _validate_bound_file(
            descriptor,
            parent_descriptor,
            output.name,
            output,
            expected_identity=file_identity,
            expected_digest=file_digest,
        )
    except BaseException as error:
        operation_error = error
        raise
    finally:
        if temporary_name is not None:
            try:
                _unlink_bound_temporary(
                    parent_descriptor,
                    descriptor,
                    temporary_name,
                    output.parent / temporary_name,
                )
            except OSError as cleanup_error:
                if operation_error is None:
                    raise
                operation_error.add_note(
                    "private output temporary cleanup failed: "
                    f"{type(cleanup_error).__name__}"
                )
        try:
            os.close(descriptor)
        except OSError as close_error:
            if operation_error is None:
                raise
            operation_error.add_note(
                f"private output descriptor close failed: {type(close_error).__name__}"
            )


def write_private_bytes(path: str | os.PathLike[str], data: bytes) -> Path:
    if not isinstance(data, bytes):
        raise TypeError("private output data must be bytes")
    output = Path(path)
    if not output.is_absolute() or output.name in {"", ".", ".."}:
        raise ValueError("output path must name an absolute file")

    normalized_parent, parent_descriptor = safe_io.open_owner_only_directory(
        output.parent,
        create=True,
        reject_symlink_ancestors=True,
    )
    operation_error: BaseException | None = None
    try:
        if normalized_parent != output.parent:
            raise ValueError("output parent normalization changed the selected path")
        _write_private_bytes_at(parent_descriptor, output, data)
        return output
    except BaseException as error:
        operation_error = error
        raise
    finally:
        try:
            os.close(parent_descriptor)
        except OSError as close_error:
            if operation_error is None:
                raise
            operation_error.add_note(
                "private output parent descriptor close failed: "
                f"{type(close_error).__name__}"
            )
