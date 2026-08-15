"""Coordinate retained export sidecars with durable run state."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, nullcontext
import datetime as dt
from pathlib import Path
from typing import Any

from . import export as retained_export_api, retained_export_binding
from .contracts import RunStage
from .orchestrator_support import InvalidInputError, RunConflictError, _parse_timestamp


def raw_cleanup_ineligible(state: Mapping[str, Any], *, clock: str) -> bool:
    now = _parse_timestamp(clock, label="clock")
    deadline = _parse_timestamp(state["deadlines"]["raw"], label="raw deadline")
    return (
        now < deadline
        or state["stage"] == RunStage.COMPLETE.value
        or state["publication"].get("phase") in {"complete", "shadow_complete"}
    )


def lock_from_checkpoint(
    state: Mapping[str, Any],
) -> tuple[str | None, AbstractContextManager[Mapping[str, Any] | None]]:
    staging_dir = state["publication"].get("staging_dir")
    if isinstance(staging_dir, str):
        lock = retained_export_api.locked_staged_export_retention(
            staging_dir,
            allow_missing=True,
        )
        return staging_dir, lock
    return None, nullcontext(None)


def validate_retained_export_identity(
    state: Mapping[str, Any],
    binding: Mapping[str, Any],
    *,
    bundle_dir: Path,
) -> None:
    retained_export_binding.validate_retention_receipt_shape(
        binding,
        conflict_error=RunConflictError,
    )
    expected_identity = (
        state["publication"].get("bundle_digest"),
        str(retained_export_api.normalize_retained_export_destination(bundle_dir)),
        state["publication"].get("retention_deadline"),
        False,
        False,
    )
    observed_identity = (
        binding.get("bundle_digest"),
        binding.get("staging_dir"),
        binding.get("retention_deadline"),
        binding.get("git_commit_created"),
        binding.get("state_advanced"),
    )
    if observed_identity != expected_identity:
        raise RunConflictError(
            "publication bootstrap binding does not match the retained run"
        )


def validate_preclaim_export_binding(
    state: Mapping[str, Any],
    binding: Mapping[str, Any],
    *,
    attempt_ref: str,
    bundle_dir: Path,
) -> None:
    validate_retained_export_identity(state, binding, bundle_dir=bundle_dir)
    if (
        binding.get("publication_attempt_ref") != attempt_ref
        or binding.get("status") != "publication_bound"
        or binding.get("terminal_at") is not None
        or binding.get("terminal_disposition") is not None
    ):
        raise RunConflictError(
            "publication bootstrap binding does not match the retained run"
        )


def classify_retained_export_for_gc(
    state: Mapping[str, Any],
    binding: Mapping[str, Any],
    *,
    bundle_dir: Path,
) -> str:
    validate_retained_export_identity(state, binding, bundle_dir=bundle_dir)
    status = binding.get("status")
    if status == "exported":
        fields = (
            binding.get("publication_attempt_ref"),
            binding.get("publication_heartbeat_at"),
            binding.get("terminal_at"),
            binding.get("terminal_disposition"),
        )
        if fields != (None, None, None, None):
            raise RunConflictError("retained export state is not an unbound export")
        return "exported"
    if status == "publication_bound":
        validate_preclaim_expiry_recovery(state, binding)
        return "publication_preclaim"
    if status == "publication_terminal":
        return "publication_terminal"
    raise RunConflictError("retained export state is invalid during raw cleanup")


def validate_preclaim_transition(
    state: Mapping[str, Any],
    binding: Mapping[str, Any],
    *,
    attempt_ref: str,
    bundle_dir: Path,
    existing_claim: Mapping[str, Any] | None,
) -> None:
    classification = classify_retained_export_for_gc(
        state, binding, bundle_dir=bundle_dir
    )
    if classification == "publication_preclaim":
        validate_preclaim_export_binding(
            state,
            binding,
            attempt_ref=attempt_ref,
            bundle_dir=bundle_dir,
        )
    elif classification != "exported" or existing_claim is not None:
        raise RunConflictError("retained export cannot enter publication")


def publication_retention_deadline(state: Mapping[str, Any]) -> dt.datetime:
    publication_deadline = state["publication"].get("retention_deadline")
    if not isinstance(publication_deadline, str):
        raise RunConflictError("publication retention deadline is invalid")
    return min(
        _parse_timestamp(state["deadlines"]["raw"], label="raw deadline"),
        _parse_timestamp(state["deadlines"]["working"], label="working deadline"),
        _parse_timestamp(publication_deadline, label="export retention deadline"),
    )


def validate_preclaim_expiry_recovery(
    state: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> None:
    publication = state["publication"]
    if binding.get("retention_deadline") != publication.get("retention_deadline"):
        raise RunConflictError("publication bootstrap timing is invalid")
    try:
        heartbeat_time = _parse_timestamp(
            binding.get("publication_heartbeat_at"),
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
    before_bind: Callable[[Mapping[str, Any]], None],
) -> Mapping[str, Any]:
    binding_clock = _parse_timestamp(clock, label="publication bootstrap clock")
    observed = retained_export_api.inspect_staged_export_retention(bundle_dir)
    binding_write_clock = max(
        binding_clock,
        _parse_timestamp(observed["exported_at"], label="retained export timestamp"),
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
        allow_stale_bound=True,
        before_bind=before_bind,
    )
