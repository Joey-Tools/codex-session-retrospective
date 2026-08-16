"""Validate durable abort authority for current and legacy checkpoints."""

from __future__ import annotations

from collections.abc import Mapping
import copy
import hmac
from pathlib import Path
from typing import Any

from . import finalize
from .checkpoints import canonical_json_bytes
from .identity import IdentityKey
from .orchestrator_support import InvalidTransitionError, RunConflictError


_ABORT_TERMINAL_PHASES = frozenset(
    {"aborted", "expired_cleanup_claimed", "expired_cleanup_complete"}
)
_COMMIT_TERMINAL_PHASES = frozenset(
    {"published_cleanup_pending", "published_cleanup_claimed", "complete"}
)


def acknowledgement_is_idempotent(
    publication: Mapping[str, Any],
    acknowledged_phase: str,
) -> bool:
    current_phase = publication.get("phase")
    if current_phase in {"expired_cleanup_claimed", "expired_cleanup_complete"}:
        cleanup_claim = publication.get("expired_cleanup_claim")
        if not isinstance(cleanup_claim, Mapping):
            raise InvalidTransitionError(
                "finalize acknowledgement cannot rewrite expired cleanup"
            )
        if cleanup_claim.get("disposition") != "expired_aborted":
            raise InvalidTransitionError(
                "finalize acknowledgement cannot rewrite expired cleanup"
            )
    if current_phase in _ABORT_TERMINAL_PHASES:
        if acknowledged_phase != "aborted":
            raise InvalidTransitionError(
                "finalize acknowledgement cannot rewrite aborted publication"
            )
        return True
    if current_phase in _COMMIT_TERMINAL_PHASES:
        if acknowledged_phase != "committed":
            raise InvalidTransitionError(
                "finalize acknowledgement cannot rewrite committed publication"
            )
        return True
    return False


def validate(
    run_dir: Path,
    identity: IdentityKey,
    state: Mapping[str, Any],
    claim: Mapping[str, Any] | None,
) -> dict[str, Any]:
    journal = run_dir / finalize.PUBLICATION_JOURNAL_NAME
    try:
        transaction = finalize.PublicationTransaction.inspect_local(journal)
        if transaction.get("phase") != finalize.PublicationPhase.ABORTED.value:
            raise RunConflictError("publication abort journal is not durably complete")
        plan = transaction.get("plan")
        inventory_value = transaction.get("inventory")
        receipts = transaction.get("receipts")
        if not all(
            isinstance(value, Mapping) for value in (plan, inventory_value, receipts)
        ):
            raise RunConflictError(
                "publication abort journal lacks its durable plan or receipts"
            )
        assert isinstance(plan, Mapping)
        assert isinstance(inventory_value, Mapping)
        assert isinstance(receipts, Mapping)
        inventory = finalize.ArtifactInventory.from_dict(inventory_value)
        cleanup = receipts.get("cleanup")
        release = receipts.get("reservation_release")
        abort_commitment = receipts.get("abort_commitment")
        if not all(
            isinstance(value, Mapping) for value in (cleanup, release, abort_commitment)
        ):
            raise RunConflictError(
                "publication abort journal lacks complete cleanup evidence"
            )
        assert isinstance(cleanup, Mapping)
        assert isinstance(release, Mapping)
        assert isinstance(abort_commitment, Mapping)
        verified_abort = finalize.verify_publication_abort_commitment(
            identity,
            abort_commitment,
        )
    except (OSError, ValueError, finalize.PublicationError) as error:
        if isinstance(error, RunConflictError):
            raise
        raise RunConflictError("publication abort authority is invalid") from error

    publication = state["publication"]
    durable_state = publication.get("durable_state")
    publication_authority = plan.get("publication_authority")
    if not isinstance(durable_state, Mapping) or not isinstance(
        publication_authority, Mapping
    ):
        raise RunConflictError(
            "publication abort does not bind the complete durable candidate"
        )
    durable_state_digest = identity.derive_digest(
        "publication-claim-durable-state/v2",
        copy.deepcopy(dict(durable_state)),
    )
    if claim is None:
        claim = {
            "attempt_ref": verified_abort.get("attempt_ref"),
            "bundle_digest": publication.get("bundle_digest"),
            "durable_state_digest": durable_state_digest,
            "expected_history_commit": plan.get("expected_target_head"),
            "history_target_ref": plan.get("target_ref"),
            "plan_digest": verified_abort.get("plan_digest"),
            "receipt_ref": verified_abort.get("publication_claim_ref"),
        }
    if (
        transaction.get("attempt_ref") != claim.get("attempt_ref")
        or transaction.get("plan_digest") != claim.get("plan_digest")
        or plan.get("attempt_ref") != claim.get("attempt_ref")
        or plan.get("bundle_dir") != publication.get("staging_dir")
        or plan.get("expected_target_head") != claim.get("expected_history_commit")
        or plan.get("target_ref") != claim.get("history_target_ref")
        or plan.get("inventory_digest_v2") != inventory.inventory_digest_v2
        or inventory.retained_bundle_digest_v2 != claim.get("bundle_digest")
        or publication.get("bundle_digest") != claim.get("bundle_digest")
        or durable_state_digest != claim.get("durable_state_digest")
        or publication_authority.get("candidate_digest") != claim.get("bundle_digest")
        or publication_authority.get("run_dir") != str(run_dir)
        or publication_authority.get("identity_key_id") != identity.key_id
        or canonical_json_bytes(publication_authority.get("proposed_durable_state"))
        != canonical_json_bytes(dict(durable_state))
        or verified_abort.get("attempt_ref") != claim.get("attempt_ref")
        or verified_abort.get("plan_digest") != claim.get("plan_digest")
        or verified_abort.get("inventory_digest") != inventory.inventory_digest_v2
        or verified_abort.get("publication_claim_ref") != claim.get("receipt_ref")
        or verified_abort.get("run_ref") != state["run_ref"]
        or verified_abort.get("cleanup_receipt_ref") != cleanup.get("receipt_ref")
        or verified_abort.get("reservation_release_receipt_ref")
        != release.get("receipt_ref")
        or release.get("cleanup_receipt_ref") != cleanup.get("receipt_ref")
        or release.get("cleanup_claim_ref") != cleanup.get("cleanup_claim_ref")
        or release.get("reservations_released") is not True
        or cleanup.get("objects_cleaned") is not True
        or cleanup.get("formal_reachable") is not False
        or cleanup.get("provisional_reachable") is not False
    ):
        raise RunConflictError(
            "publication abort journal does not bind this exact run claim"
        )
    return copy.deepcopy(dict(claim))


def validate_completed(
    run_dir: Path,
    identity: IdentityKey,
    state: Mapping[str, Any],
    cleanup_claim: Mapping[str, Any],
) -> dict[str, Any]:
    publication = state.get("publication")
    if (
        not isinstance(publication, Mapping)
        or publication.get("phase") != "expired_cleanup_complete"
        or publication.get("bundle_digest") is not None
        or publication.get("durable_state") is not None
        or cleanup_claim.get("disposition") != "expired_aborted"
        or cleanup_claim.get("phase_before") != "aborted"
    ):
        raise RunConflictError("completed abort cleanup authority is invalid")
    try:
        transaction = finalize.PublicationTransaction.inspect_local(
            run_dir / finalize.PUBLICATION_JOURNAL_NAME
        )
        plan = transaction.get("plan")
        publication_authority = (
            plan.get("publication_authority") if isinstance(plan, Mapping) else None
        )
        proposed_durable_state = (
            publication_authority.get("proposed_durable_state")
            if isinstance(publication_authority, Mapping)
            else None
        )
        if not isinstance(proposed_durable_state, Mapping):
            raise RunConflictError(
                "completed abort journal lacks its durable candidate"
            )
    except (OSError, ValueError, finalize.PublicationError) as error:
        if isinstance(error, RunConflictError):
            raise
        raise RunConflictError("completed abort authority is invalid") from error

    projected_state = copy.deepcopy(dict(state))
    projected_publication = projected_state["publication"]
    projected_publication["bundle_digest"] = cleanup_claim.get("bundle_digest")
    projected_publication["durable_state"] = copy.deepcopy(dict(proposed_durable_state))
    recovered = validate(run_dir, identity, projected_state, None)
    if cleanup_claim.get("bundle_digest") != recovered.get(
        "bundle_digest"
    ) or cleanup_claim.get("publication_claim_ref") != recovered.get("receipt_ref"):
        raise RunConflictError(
            "completed abort cleanup lost publication claim authority"
        )
    return recovered


def validate_acknowledgement(
    identity: IdentityKey,
    state: Mapping[str, Any],
    recovered: Mapping[str, Any],
    *,
    attempt_ref: str | None,
    claim_revision: int | None,
    plan_digest: str | None,
) -> None:
    if attempt_ref is None and claim_revision is None and plan_digest is None:
        return
    if (
        attempt_ref is None
        or plan_digest is None
        or attempt_ref != recovered.get("attempt_ref")
        or plan_digest != recovered.get("plan_digest")
    ):
        raise RunConflictError(
            "finalize acknowledgement does not match recovered abort authority"
        )
    if claim_revision is None:
        return
    if (
        not isinstance(claim_revision, int)
        or isinstance(claim_revision, bool)
        or claim_revision < 1
    ):
        raise RunConflictError(
            "finalize acknowledgement does not match recovered abort authority"
        )
    body = {
        "attempt_ref": attempt_ref,
        "bundle_digest": recovered.get("bundle_digest"),
        "checkpoint_revision": claim_revision,
        "durable_state_digest": recovered.get("durable_state_digest"),
        "expected_history_commit": recovered.get("expected_history_commit"),
        "history_target_ref": recovered.get("history_target_ref"),
        "identity_key_id": identity.key_id,
        "plan_digest": plan_digest,
        "run_ref": state["run_ref"],
        "schema": "publication_claim_v2",
    }
    candidate_ref = "publication_claim_v2:" + identity.derive_digest(
        "publication_claim_v2",
        body,
    )
    recovered_ref = recovered.get("receipt_ref")
    if not isinstance(recovered_ref, str) or not hmac.compare_digest(
        candidate_ref,
        recovered_ref,
    ):
        raise RunConflictError(
            "finalize acknowledgement does not match recovered abort authority"
        )
