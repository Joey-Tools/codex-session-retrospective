#!/usr/bin/env -S python3 -I -B -S
"""Descriptor-bound content receipts for canonical test source files."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat


class SourceSnapshotError(ValueError):
    """Raised when a test source cannot produce a stable content receipt."""


def validate_source_sha256(value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SourceSnapshotError("test source sha256 is invalid")
    return value


def _stat_receipt(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
    )


def hash_test_source(path: Path, *, maximum_bytes: int) -> tuple[str, int]:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SourceSnapshotError("cannot open a test source") from exc
    primary: BaseException | None = None
    try:
        before = os.fstat(descriptor)
        named_before = os.stat(path, follow_symlinks=False)
        receipt = _stat_receipt(before)
        if not stat.S_ISREG(before.st_mode) or receipt != _stat_receipt(named_before):
            raise SourceSnapshotError(
                "test source binding is not a stable regular file"
            )
        if before.st_size > maximum_bytes:
            raise SourceSnapshotError("test source exceeds the byte limit")
        digest = hashlib.sha256()
        observed = 0
        while True:
            chunk = os.read(
                descriptor,
                min(64 * 1024, maximum_bytes + 1 - observed),
            )
            if not chunk:
                break
            observed += len(chunk)
            if observed > maximum_bytes:
                raise SourceSnapshotError("test source exceeds the byte limit")
            digest.update(chunk)
        after = os.fstat(descriptor)
        named_after = os.stat(path, follow_symlinks=False)
        if (
            receipt != _stat_receipt(after)
            or receipt != _stat_receipt(named_after)
            or observed != before.st_size
        ):
            raise SourceSnapshotError("test source changed while it was read")
        return digest.hexdigest(), observed
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            os.close(descriptor)
        except OSError as close_error:
            if primary is not None:
                if hasattr(primary, "add_note"):
                    primary.add_note(
                        "test source descriptor close failed: "
                        f"{type(close_error).__name__}"
                    )
            else:
                raise SourceSnapshotError(
                    "cannot close a test source descriptor"
                ) from close_error
