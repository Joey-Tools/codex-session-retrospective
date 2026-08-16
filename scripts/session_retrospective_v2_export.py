"""Durable retained-export destination binding for the v2 CLI."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import datetime as dt
from pathlib import Path
import os
from typing import Any

from retrospective_v2 import export as export_api, reporting as reporting_api, safe_io
from retrospective_v2.orchestrator_core import SHADOW_CLEANUP_ROOTS
import session_retrospective_v2_export_binding as binding
import session_retrospective_v2_export_legacy as legacy_binding
import session_retrospective_v2_export_records as records


EXPORT_DESTINATION_CLAIM_SCHEMA = records.EXPORT_DESTINATION_CLAIM_SCHEMA
EXPORT_DESTINATION_CLAIM_NAME = records.EXPORT_DESTINATION_CLAIM_NAME
EXPORT_DESCRIPTOR_SCHEMA = records.EXPORT_DESCRIPTOR_SCHEMA
EXPORT_DESCRIPTOR_NAME = records.EXPORT_DESCRIPTOR_NAME
EXPORT_RESERVATION_SCHEMA = records.EXPORT_RESERVATION_SCHEMA
LEGACY_EXPORT_DESCRIPTOR_NAME = records.LEGACY_EXPORT_DESCRIPTOR_NAME
ExportCliContractError = records.ExportCliContractError
JsonReader = records.JsonReader


def publication_attempt_ref(
    output: Path,
    *,
    new_attempt_ref: Callable[[], str],
) -> str:
    retention = export_api.inspect_staged_export_retention(output)
    status = retention["status"]
    if status == "exported":
        return new_attempt_ref()
    if status == "publication_bound":
        return retention["publication_attempt_ref"]
    records.raise_cli_error(
        "INVALID_STATE",
        "publication_not_resumable",
        "the retained export has a terminal publication disposition",
    )


def load_export_descriptor(
    run_dir: Path,
    *,
    read_json: JsonReader,
) -> dict[str, Any]:
    result_path = run_dir / EXPORT_DESCRIPTOR_NAME
    legacy_path = run_dir / LEGACY_EXPORT_DESCRIPTOR_NAME
    claim_path = run_dir / EXPORT_DESTINATION_CLAIM_NAME
    for path in (legacy_path, claim_path, result_path):
        safe_io.recover_atomic_create(path)
    if not os.path.lexists(legacy_path):
        records.invalid_descriptor("the retained export reservation is missing")
    legacy_claim, legacy_descriptor = records.load_legacy_binding(
        run_dir, read_json=read_json
    )
    claim = (
        records.load_destination_claim(run_dir, read_json=read_json)
        if os.path.lexists(claim_path)
        else legacy_claim
    )
    if legacy_descriptor is not None and not records.same(claim, legacy_claim):
        records.invalid_descriptor("the retained export destination binding conflicts")
    if os.path.lexists(result_path):
        result = records.load_descriptor_at(result_path, read_json=read_json)
        if not records.same(records.normalized_descriptor_claim(result), claim):
            records.invalid_descriptor("the retained export result binding conflicts")
        if legacy_descriptor is not None and not records.same(
            result, legacy_descriptor
        ):
            records.invalid_descriptor("the retained export results conflict")
        return result
    if legacy_descriptor is not None:
        return legacy_descriptor
    records.invalid_descriptor("the retained export result is not complete")


def require_export_destination_claim(
    run_dir: Path,
    output: Path,
    publication_role: str,
    *,
    read_json: JsonReader,
) -> None:
    output = export_api.normalize_retained_export_destination(output)
    expected = records.destination_claim(output, publication_role)
    legacy_claim, _legacy_descriptor = records.load_legacy_binding(
        run_dir, read_json=read_json
    )
    claim = records.load_destination_claim(run_dir, read_json=read_json)
    if not records.same(claim, expected) or (
        _legacy_descriptor is not None and not records.same(legacy_claim, expected)
    ):
        records.conflict()


def claim_export_destination(
    run_dir: Path,
    output: Path,
    publication_role: str,
    *,
    read_json: JsonReader,
    expected_descriptor: Mapping[str, Any],
) -> Path:
    return binding.claim_export_destination(
        run_dir,
        output,
        publication_role,
        cleanup_roots=SHADOW_CLEANUP_ROOTS,
        read_json=read_json,
        expected_descriptor=expected_descriptor,
    )


def claim_legacy_export_destination(
    run_dir: Path,
    output: Path,
    publication_role: str,
    *,
    read_json: JsonReader,
) -> Path:
    return legacy_binding.claim_export_destination(
        run_dir,
        output,
        publication_role,
        cleanup_roots=SHADOW_CLEANUP_ROOTS,
        read_json=read_json,
    )


def stage_claimed_export(
    run_dir: Path,
    output: Path,
    run_state: Mapping[str, Any],
    review_data: Mapping[str, Any],
    *,
    prior_period: Mapping[str, Any] | None,
    retention_deadline: str | None,
    missing_retention_deadline: str,
    now: dt.datetime,
    read_json: JsonReader,
    validate_retention_deadline: Callable[[str], str],
) -> tuple[Path, Mapping[str, Any]]:
    output = export_api.normalize_retained_export_destination(output)
    records.preflight_run_claim(
        run_dir, output, "standalone", SHADOW_CLEANUP_ROOTS, read_json
    )
    artifacts = reporting_api.assemble_retained_artifacts(
        run_state,
        review_data,
        prior_period=prior_period,
    )
    expected_digest = reporting_api.retained_bundle_digest(artifacts)

    def resolve_deadline(
        bundle_digest: str, requested_deadline: dt.datetime | str | None
    ) -> str:
        return binding.resolve_missing_retention_deadline(
            run_dir,
            output,
            "standalone",
            bundle_digest,
            missing_retention_deadline,
            None if requested_deadline is None else str(requested_deadline),
            cleanup_roots=SHADOW_CLEANUP_ROOTS,
            read_json=read_json,
            validate_retention_deadline=validate_retention_deadline,
        )

    def claim(receipt: Mapping[str, Any]) -> None:
        records.validate_claim_receipt(
            receipt, expected_digest, validate_retention_deadline
        )
        claim_export_destination(
            run_dir,
            output,
            "standalone",
            read_json=read_json,
            expected_descriptor=binding.descriptor(
                output,
                "standalone",
                expected_digest,
                str(receipt["retention_deadline"]),
            ),
        )

    try:
        receipt = export_api.stage_retained_artifacts(
            output,
            artifacts,
            retention_deadline=retention_deadline,
            now=now,
            resolve_missing_retention_deadline=resolve_deadline,
            before_unlock=claim,
        )
    except export_api.InvalidExistingExportError as error:
        raise records.ExportCliContractError(
            "INVALID_INPUT",
            "export_location_invalid",
            "the retained export destination is not an exact retained bundle",
        ) from error
    return output, receipt


def persist_export_descriptor(
    run_dir: Path,
    output: Path,
    receipt: Mapping[str, Any],
    publication_role: str,
    *,
    read_json: JsonReader,
) -> None:
    binding.persist_export_descriptor(
        run_dir,
        output,
        receipt,
        publication_role,
        cleanup_roots=SHADOW_CLEANUP_ROOTS,
        read_json=read_json,
    )
