"""Immutable run-side binding for one retained export transaction."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
import os
from typing import Any

from retrospective_v2 import export as export_api, safe_io
import session_retrospective_v2_export_records as records


def descriptor(
    output: Path,
    publication_role: str,
    bundle_digest: str,
    retention_deadline: str,
) -> dict[str, str]:
    return {
        "bundle_digest": bundle_digest,
        "output": str(export_api.normalize_retained_export_destination(output)),
        "publication_role": publication_role,
        "retention_deadline": retention_deadline,
        "schema": records.EXPORT_DESCRIPTOR_SCHEMA,
    }


def _existing_descriptors(
    run_dir: Path,
    *,
    read_json: records.JsonReader,
) -> tuple[dict[str, Any], ...]:
    values: list[dict[str, Any]] = []
    legacy_path = run_dir / records.LEGACY_EXPORT_DESCRIPTOR_NAME
    result_path = run_dir / records.EXPORT_DESCRIPTOR_NAME
    if os.path.lexists(legacy_path):
        _claim, legacy = records.load_legacy_binding(run_dir, read_json=read_json)
        if legacy is not None:
            values.append(legacy)
    if os.path.lexists(result_path):
        values.append(records.load_descriptor_at(result_path, read_json=read_json))
    return tuple(values)


def resolve_missing_retention_deadline(
    run_dir: Path,
    output: Path,
    publication_role: str,
    expected_bundle_digest: str,
    default_deadline: str,
    requested_deadline: str | None,
    *,
    cleanup_roots: Sequence[str],
    read_json: records.JsonReader,
    validate_retention_deadline: Callable[[str], str],
) -> str:
    """Resolve a missing sidecar deadline before any destination mutation."""

    output = export_api.normalize_retained_export_destination(output)
    records.preflight_run_claim(
        run_dir, output, publication_role, cleanup_roots, read_json
    )
    existing = _existing_descriptors(run_dir, read_json=read_json)
    candidate = requested_deadline or default_deadline
    validated_candidate = validate_retention_deadline(candidate)
    if validated_candidate != candidate:
        records.invalid_descriptor("the retained export deadline is not canonical")
    if existing:
        expected_claim = records.destination_claim(output, publication_role)
        for value in existing:
            if (
                not records.same(
                    records.normalized_descriptor_claim(value), expected_claim
                )
                or value["bundle_digest"] != expected_bundle_digest
            ):
                records.conflict()
        first = existing[0]
        if any(not records.same(first, value) for value in existing[1:]):
            records.conflict()
        deadline = first["retention_deadline"]
        if requested_deadline is not None and deadline != validated_candidate:
            records.conflict()
    else:
        deadline = validated_candidate
    validated = validate_retention_deadline(deadline)
    if validated != deadline:
        records.invalid_descriptor("the retained export deadline is not canonical")
    return validated


def _persist_result(
    run_dir: Path,
    expected: Mapping[str, Any],
    *,
    read_json: records.JsonReader,
) -> None:
    result_path = run_dir / records.EXPORT_DESCRIPTOR_NAME
    try:
        safe_io.atomic_create_json(result_path, expected)
    except FileExistsError:
        existing = records.load_descriptor_at(result_path, read_json=read_json)
        if not records.same(existing, expected):
            records.conflict()


def claim_export_destination(
    run_dir: Path,
    output: Path,
    publication_role: str,
    *,
    cleanup_roots: Sequence[str],
    read_json: records.JsonReader,
    expected_descriptor: Mapping[str, Any],
) -> Path:
    """Bind all full commitments before publishing the path-only claim."""

    output = export_api.normalize_retained_export_destination(output)
    records.reject_destination(run_dir, output, cleanup_roots=cleanup_roots)
    requested = records.destination_claim(output, publication_role)
    legacy_path = run_dir / records.LEGACY_EXPORT_DESCRIPTOR_NAME
    claim_path = run_dir / records.EXPORT_DESTINATION_CLAIM_NAME
    result_path = run_dir / records.EXPORT_DESCRIPTOR_NAME
    for path in (legacy_path, result_path):
        safe_io.recover_atomic_create(path)
    if not os.path.lexists(legacy_path) and (
        os.path.lexists(claim_path) or os.path.lexists(result_path)
    ):
        records.invalid_descriptor("the retained export reservation is missing")
    claimed = (
        records.load_destination_claim(run_dir, read_json=read_json)
        if os.path.lexists(claim_path)
        else requested
    )
    if not os.path.lexists(legacy_path):
        try:
            safe_io.atomic_create_json(
                legacy_path,
                records.reservation(
                    export_api.normalize_retained_export_destination(claimed["output"]),
                    claimed["publication_role"],
                ),
            )
        except FileExistsError:
            pass
    legacy_claim, legacy_descriptor = records.load_legacy_binding(
        run_dir, read_json=read_json
    )
    if not records.same(legacy_claim, requested):
        records.conflict()
    if legacy_descriptor is not None and not records.same(
        legacy_descriptor, expected_descriptor
    ):
        records.conflict()
    if not records.same(
        records.normalized_descriptor_claim(expected_descriptor), requested
    ):
        records.conflict()
    _persist_result(run_dir, expected_descriptor, read_json=read_json)
    safe_io.recover_atomic_create(claim_path)
    if os.path.lexists(claim_path):
        claimed = records.load_destination_claim(run_dir, read_json=read_json)
    else:
        try:
            safe_io.atomic_create_json(claim_path, legacy_claim)
        except FileExistsError:
            claimed = records.load_destination_claim(run_dir, read_json=read_json)
        else:
            claimed = legacy_claim
    if not records.same(claimed, requested):
        records.conflict()
    return output


def persist_export_descriptor(
    run_dir: Path,
    output: Path,
    receipt: Mapping[str, Any],
    publication_role: str,
    *,
    cleanup_roots: Sequence[str],
    read_json: records.JsonReader,
) -> None:
    output = export_api.normalize_retained_export_destination(output)
    expected_claim = records.destination_claim(output, publication_role)
    claim = records.load_destination_claim(run_dir, read_json=read_json)
    legacy_claim, legacy_descriptor = records.load_legacy_binding(
        run_dir, read_json=read_json
    )
    if not records.same(claim, expected_claim) or (
        legacy_descriptor is not None and not records.same(legacy_claim, expected_claim)
    ):
        records.conflict()
    bundle_digest = receipt.get("bundle_digest")
    retention_deadline = receipt.get("retention_deadline")
    if (
        not isinstance(bundle_digest, str)
        or records.SHA256_RE.fullmatch(bundle_digest) is None
        or not isinstance(retention_deadline, str)
    ):
        records.raise_cli_error(
            "INVALID_STATE",
            "invalid_export_receipt",
            "the retained export receipt is invalid",
        )
    expected = descriptor(output, publication_role, bundle_digest, retention_deadline)
    if legacy_descriptor is not None and not records.same(legacy_descriptor, expected):
        records.conflict()
    _persist_result(run_dir, expected, read_json=read_json)
