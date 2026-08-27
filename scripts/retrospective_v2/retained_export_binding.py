"""Bind retained exports to an authenticated publication plan."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .export import RETAINED_ARTIFACT_NAMES
from .publication_contracts import RetainedExportLifecycle


_RECEIPT_FIELDS = frozenset(
    {
        "artifact_names",
        "bundle_digest",
        "exported_at",
        "git_commit_created",
        "idempotent",
        "publication_attempt_ref",
        "publication_heartbeat_at",
        "retention_deadline",
        "schema_version",
        "staging_dir",
        "state_advanced",
        "status",
        "terminal_at",
        "terminal_disposition",
    }
)


def validate_retention_receipt_shape(
    receipt: Mapping[str, Any],
    *,
    conflict_error: type[Exception],
) -> None:
    expected = (_RECEIPT_FIELDS, 2, list(RETAINED_ARTIFACT_NAMES), False, False)
    observed = (
        set(receipt),
        receipt.get("schema_version"),
        receipt.get("artifact_names"),
        receipt.get("git_commit_created"),
        receipt.get("state_advanced"),
    )
    if observed != expected:
        raise conflict_error("retained export receipt has an unexpected shape")


def bind_publication_plan_export(
    lifecycle: RetainedExportLifecycle,
    bundle_dir: Path,
    *,
    attempt_ref: str,
    bundle_digest: str,
    conflict_error: type[Exception],
) -> None:
    expected = ("publication_bound", attempt_ref, bundle_digest, str(bundle_dir))

    def validate(receipt: Mapping[str, Any]) -> None:
        validate_retention_receipt_shape(receipt, conflict_error=conflict_error)
        observed = (
            receipt.get("status"),
            receipt.get("publication_attempt_ref"),
            receipt.get("bundle_digest"),
            receipt.get("staging_dir"),
        )
        if observed != expected:
            raise conflict_error(
                "retained export binding differs from the publication plan"
            )

    lifecycle.bind_staged_export(
        bundle_dir,
        attempt_ref,
        renew_heartbeat=False,
        allow_stale_bound=True,
        before_bind=validate,
    )
