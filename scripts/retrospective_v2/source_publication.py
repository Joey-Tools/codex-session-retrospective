"""Descriptor-bound publication for accepted source payloads."""

from __future__ import annotations

import os
from pathlib import Path

from . import safe_io, temporary_paths


def create_run_bytes_with_receipt(
    path: str | Path,
    data: bytes,
    receipt_slot: safe_io.AtomicCreateReceiptSlot,
) -> bool:
    """Create run bytes under held authority or validate the existing bytes."""
    normalized = temporary_paths.require_run_directory_outside_sources(path)
    parent_path, parent_descriptor = temporary_paths.open_run_directory(
        normalized.parent,
        create=True,
    )
    primary: BaseException | None = None
    try:
        try:
            safe_io.atomic_create_bytes_with_receipt(
                normalized,
                data,
                create_parents=False,
                receipt_slot=receipt_slot,
                bound_parent_descriptor=parent_descriptor,
            )
        except FileExistsError:
            existing = safe_io.read_bounded_bytes_at(
                parent_descriptor,
                normalized.name,
                display_path=normalized,
                max_bytes=max(1, len(data)),
                require_owner_only=True,
            )
            if existing != data:
                return False
        temporary_paths.require_bound_run_directory_outside_sources(
            parent_path,
            parent_descriptor,
        )
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            os.close(parent_descriptor)
        except OSError as close_error:
            if primary is None:
                raise
            primary.add_note(
                f"staged source parent close failed: {type(close_error).__name__}"
            )
    return True
