"""Durable publication claim validation shared by lifecycle transitions."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import copy
import hmac
from pathlib import Path
from typing import Any

from .checkpoints import AtomicCheckpointStore, canonical_json_bytes
from .identity import IdentityKey
from .orchestrator_core import InvalidTransitionError, RunConflictError
from .publication_contracts import (
    PUBLICATION_CLAIM_SCHEMA,
    PublicationRejected,
    _PUBLICATION_CLAIM_AUTH_RE,
    _PUBLICATION_CLAIM_REF_RE,
)
from .run_state_authority import validate_run_source_authority
from .run_state_contracts import RunStateAuthorityError


StateIdentityValidator = Callable[[Mapping[str, Any]], None]
PublicationClaimValidator = Callable[
    [Mapping[str, Any], object],
    dict[str, Any],
]
GenericValidator = Callable[..., dict[str, Any] | None]
AbortAuthorityResolver = Callable[[Mapping[str, Any]], dict[str, Any]]
_TERMINAL_TRANSACTION_PHASES = {
    "aborted": frozenset({"abort_pending", "aborted"}),
    "expired_cleanup_claimed": frozenset(),
    "expired_cleanup_complete": frozenset(),
    "expired_cleanup_pending": frozenset(),
    "published_cleanup_claimed": frozenset({"committed"}),
    "published_cleanup_pending": frozenset({"committed"}),
}


def validate_persistent_publication_claim(
    *,
    run_dir: Path,
    identity_path: Path,
    transaction_state: Mapping[str, Any],
) -> dict[str, Any]:
    attempt_ref = transaction_state["attempt_ref"]
    plan_digest = transaction_state["plan_digest"]
    transaction_phase = transaction_state["phase"]
    identity = IdentityKey.load(identity_path)
    snapshot = AtomicCheckpointStore(run_dir, identity=identity).read()
    run_state = snapshot.state
    publication = run_state.get("publication")
    authority_binding = run_state.get("authority")
    if not isinstance(publication, Mapping) or not isinstance(
        authority_binding, Mapping
    ):
        raise PublicationRejected("run lacks a persistent publication claim")
    compatible_phases = _TERMINAL_TRANSACTION_PHASES.get(publication.get("phase"))
    if compatible_phases is not None and transaction_phase not in compatible_phases:
        raise PublicationRejected(
            "terminal checkpoint cannot authorize an active publication transaction"
        )
    try:
        validate_run_source_authority(
            identity,
            run_state,
        )
    except RunStateAuthorityError as exc:
        raise PublicationRejected(str(exc)) from exc
    claim = publication.get("publication_claim")
    fields = {
        "attempt_ref",
        "authentication_tag",
        "bundle_digest",
        "checkpoint_revision",
        "durable_state_digest",
        "expected_history_commit",
        "history_target_ref",
        "identity_key_id",
        "plan_digest",
        "receipt_ref",
        "run_ref",
        "schema",
    }
    if not isinstance(claim, Mapping) or set(claim) != fields:
        raise PublicationRejected("run lacks a valid persistent publication claim")
    checkpoint_revision = claim.get("checkpoint_revision")
    durable_state = publication.get("durable_state")
    history_snapshot = authority_binding.get("history_snapshot")
    if (
        not isinstance(checkpoint_revision, int)
        or isinstance(checkpoint_revision, bool)
        or checkpoint_revision < 1
        or checkpoint_revision > snapshot.revision
        or not isinstance(durable_state, Mapping)
        or not isinstance(history_snapshot, Mapping)
        or not isinstance(history_snapshot.get("history_commit"), str)
    ):
        raise PublicationRejected("publication claim checkpoint fence is invalid")
    body = {
        "attempt_ref": attempt_ref,
        "bundle_digest": publication.get("bundle_digest"),
        "checkpoint_revision": checkpoint_revision,
        "durable_state_digest": identity.derive_digest(
            "publication-claim-durable-state/v2",
            dict(durable_state),
        ),
        "expected_history_commit": history_snapshot["history_commit"],
        "history_target_ref": authority_binding.get("history_target_ref"),
        "identity_key_id": identity.key_id,
        "plan_digest": plan_digest,
        "run_ref": run_state.get("run_ref"),
        "schema": PUBLICATION_CLAIM_SCHEMA,
    }
    expected_ref = "publication_claim_v2:" + identity.derive_digest(
        "publication_claim_v2", body
    )
    expected_auth = "publication_claim_auth_v2:" + identity.derive_digest(
        "publication_claim_auth_v2", body
    )
    expected = {
        **body,
        "authentication_tag": expected_auth,
        "receipt_ref": expected_ref,
    }
    if (
        claim.get("attempt_ref") != attempt_ref
        or claim.get("plan_digest") != plan_digest
        or not isinstance(claim.get("receipt_ref"), str)
        or _PUBLICATION_CLAIM_REF_RE.fullmatch(claim["receipt_ref"]) is None
        or not isinstance(claim.get("authentication_tag"), str)
        or _PUBLICATION_CLAIM_AUTH_RE.fullmatch(claim["authentication_tag"]) is None
        or not hmac.compare_digest(
            canonical_json_bytes(dict(claim)),
            canonical_json_bytes(expected),
        )
    ):
        raise PublicationRejected(
            "publication claim does not match this checkpoint revision and transaction"
        )
    return copy.deepcopy(expected)


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
    if publication.get("phase") == "aborted":
        raise InvalidTransitionError("aborted publication cannot be claimed")
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


def completed_expired_cleanup_disposition(
    publication: Mapping[str, Any],
) -> str:
    completed_claim = publication.get("expired_cleanup_claim")
    if not isinstance(completed_claim, Mapping):
        raise RunConflictError("expired cleanup claim is malformed")
    disposition = completed_claim.get("disposition")
    if disposition not in {"expired_aborted", "expired_unpublished"}:
        raise RunConflictError("expired cleanup claim disposition is invalid")
    return disposition


def validate_aborted_cleanup_authority(
    state: Mapping[str, Any],
    *,
    locked_staging_dir: str | None,
    retention_binding: Mapping[str, Any] | None,
    resolve_abort: AbortAuthorityResolver,
    validate_binding: GenericValidator,
) -> dict[str, Any]:
    publication = state["publication"]
    claim = resolve_abort(state)
    if (
        not isinstance(locked_staging_dir, str)
        or publication.get("staging_dir") != locked_staging_dir
    ):
        raise RunConflictError("aborted publication staging binding changed")
    if retention_binding is not None:
        validate_binding(
            state,
            retention_binding,
            bundle_dir=Path(locked_staging_dir),
            publication_claim=claim,
        )
    return claim


def validate_expired_cleanup_replay(
    state: Mapping[str, Any],
    claim: Mapping[str, Any],
    *,
    locked_staging_dir: str | None,
    retention_binding: Mapping[str, Any] | None,
    resolve_abort: AbortAuthorityResolver,
    validate_binding: GenericValidator,
    validate_raw_cleanup: GenericValidator,
) -> dict[str, Any]:
    disposition = claim.get("disposition")
    publication_claim_ref = None
    if disposition == "expired_aborted":
        publication_claim = validate_aborted_cleanup_authority(
            state,
            locked_staging_dir=locked_staging_dir,
            retention_binding=retention_binding,
            resolve_abort=resolve_abort,
            validate_binding=validate_binding,
        )
        publication_claim_ref = publication_claim["receipt_ref"]
        if claim.get("publication_claim_ref") != publication_claim_ref:
            raise RunConflictError("expired abort cleanup lost publication authority")
    elif disposition != "expired_unpublished":
        raise RunConflictError("expired cleanup claim disposition is invalid")
    verified = validate_raw_cleanup(
        state,
        claim,
        disposition=disposition,
        durable_commit=None,
        phase_before=str(claim.get("phase_before")),
        publication_claim_ref=publication_claim_ref,
    )
    assert isinstance(verified, dict)
    return verified


def claim_expired_aborted_cleanup(
    state: dict[str, Any],
    *,
    locked_staging_dir: str | None,
    retention_binding: Mapping[str, Any] | None,
    inventory: Mapping[str, Any],
    resolve_abort: AbortAuthorityResolver,
    validate_binding: GenericValidator,
    build_raw_cleanup_claim: GenericValidator,
) -> dict[str, Any]:
    publication_claim = validate_aborted_cleanup_authority(
        state,
        locked_staging_dir=locked_staging_dir,
        retention_binding=retention_binding,
        resolve_abort=resolve_abort,
        validate_binding=validate_binding,
    )
    claim = build_raw_cleanup_claim(
        state,
        disposition="expired_aborted",
        durable_commit=None,
        phase_before="aborted",
        publication_claim_ref=publication_claim["receipt_ref"],
        inventory=inventory,
    )
    assert isinstance(claim, dict)
    state["publication"].update(
        {
            "expired_cleanup_claim": claim,
            "phase": "expired_cleanup_claimed",
        }
    )
    return copy.deepcopy(claim)


def validate_aborted_cleanup_close(
    state: Mapping[str, Any],
    claim: Mapping[str, Any],
    *,
    resolve_abort: AbortAuthorityResolver,
) -> None:
    if claim.get("disposition") != "expired_aborted":
        return
    publication_claim = resolve_abort(state)
    if claim.get("publication_claim_ref") != publication_claim["receipt_ref"]:
        raise RunConflictError("expired abort cleanup lost publication authority")
