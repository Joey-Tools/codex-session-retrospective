"""Publication preclaim validation shared by lifecycle transitions."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import datetime as dt
from pathlib import Path
from typing import Any

from . import export as retained_export_api, reporting
from .orchestrator_support import (
    InvalidInputError,
    InvalidTransitionError,
    RunConflictError,
    _parse_timestamp,
)


StateIdentityValidator = Callable[[Mapping[str, Any]], None]
PublicationClaimValidator = Callable[
    [Mapping[str, Any], object],
    dict[str, Any],
]


def validate_preclaim_export_binding(
    state: Mapping[str, Any],
    binding: Mapping[str, Any],
    *,
    attempt_ref: str,
    bundle_dir: Path,
) -> None:
    expected_fields = {
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
    expected_identity = (
        expected_fields,
        2,
        list(reporting.RETAINED_ARTIFACT_NAMES),
        state["publication"].get("bundle_digest"),
        attempt_ref,
        str(retained_export_api.normalize_retained_export_destination(bundle_dir)),
        "publication_bound",
        False,
        False,
        None,
        None,
    )
    observed_identity = (
        set(binding),
        binding.get("schema_version"),
        binding.get("artifact_names"),
        binding.get("bundle_digest"),
        binding.get("publication_attempt_ref"),
        binding.get("staging_dir"),
        binding.get("status"),
        binding.get("git_commit_created"),
        binding.get("state_advanced"),
        binding.get("terminal_at"),
        binding.get("terminal_disposition"),
    )
    if observed_identity != expected_identity:
        raise RunConflictError(
            "publication bootstrap binding does not match the retained run"
        )


def publication_retention_deadline(state: Mapping[str, Any]) -> dt.datetime:
    publication_deadline = state["publication"].get("retention_deadline")
    if not isinstance(publication_deadline, str):
        raise RunConflictError("publication retention deadline is invalid")
    return min(
        _parse_timestamp(state["deadlines"]["raw"], label="raw deadline"),
        _parse_timestamp(
            state["deadlines"]["working"],
            label="working deadline",
        ),
        _parse_timestamp(
            publication_deadline,
            label="export retention deadline",
        ),
    )


def validate_preclaim_expiry_recovery(
    state: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> None:
    publication = state["publication"]
    heartbeat = binding.get("publication_heartbeat_at")
    deadline = publication.get("retention_deadline")
    if binding.get("retention_deadline") != deadline:
        raise RunConflictError("publication bootstrap timing is invalid")
    try:
        heartbeat_time = _parse_timestamp(
            heartbeat,
            label="publication bootstrap heartbeat",
        )
        earliest_deadline = publication_retention_deadline(state)
    except InvalidInputError as error:
        raise RunConflictError("publication bootstrap timing is invalid") from error
    if heartbeat_time >= earliest_deadline:
        raise RunConflictError(
            "publication bootstrap did not start before retention expiry"
        )


def bind_preclaim_export(
    state: Mapping[str, Any],
    bundle_dir: Path,
    *,
    attempt_ref: str,
    clock: str,
) -> Mapping[str, Any]:
    binding_clock = _parse_timestamp(clock, label="publication bootstrap clock")
    observed = retained_export_api.inspect_staged_export_retention(bundle_dir)
    binding_write_clock = max(
        binding_clock,
        _parse_timestamp(
            observed["exported_at"],
            label="retained export timestamp",
        ),
        _parse_timestamp(
            observed.get("publication_heartbeat_at") or observed["exported_at"],
            label="retained export heartbeat",
        ),
    )
    if binding_clock >= publication_retention_deadline(state):
        validate_preclaim_export_binding(
            state,
            observed,
            attempt_ref=attempt_ref,
            bundle_dir=bundle_dir,
        )
        validate_preclaim_expiry_recovery(state, observed)
    return retained_export_api.bind_staged_export(
        bundle_dir,
        attempt_ref,
        now=binding_write_clock,
        renew_heartbeat=False,
    )


def publication_claim_context(
    state: Mapping[str, Any],
    *,
    attempt_ref: str,
    plan_digest: str,
    allowed_stages: frozenset[str],
    assert_state_identity: StateIdentityValidator,
    validate_claim: PublicationClaimValidator,
) -> tuple[Mapping[str, Any], dict[str, Any] | None]:
    assert_state_identity(state)
    if state.get("shadow") is True:
        raise InvalidTransitionError("shadow runs cannot claim publication")
    if state["stage"] not in allowed_stages:
        raise InvalidTransitionError("run is not in publication")
    publication = state["publication"]
    if publication.get("phase") in {
        "expired_cleanup_pending",
        "expired_cleanup_claimed",
    }:
        raise InvalidTransitionError("expired raw cleanup already owns the run")
    existing = publication.get("publication_claim")
    if existing is None:
        return publication, None
    verified = validate_claim(state, existing)
    if (verified["attempt_ref"], verified["plan_digest"]) != (
        attempt_ref,
        plan_digest,
    ):
        raise RunConflictError("run is already claimed by another publication attempt")
    return publication, verified
