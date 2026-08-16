"""Recover idempotent CLI responses for durably aborted publications."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from . import finalize
from .orchestrator_support import RunConflictError


FinalizeCallback = Callable[..., Mapping[str, Any]]


def run_with_terminal_retry(
    operation: Callable[[bool], Any],
    recoverable_errors: tuple[type[BaseException], ...],
) -> Any:
    try:
        return operation(False)
    except recoverable_errors as primary_error:
        try:
            replay = operation(True)
        except Exception as retry_error:
            primary_error.add_note(
                "terminal retry failed; original error remains primary"
            )
            raise primary_error from retry_error
        if replay is None:
            raise
        return replay


def replay_terminal_finalize(
    run_dir: Path,
    run_state: Mapping[str, Any],
    *,
    mark_finalized: FinalizeCallback,
) -> dict[str, Any] | None:
    publication = run_state["publication"]
    recovered = replay_terminal_abort(
        run_dir,
        publication,
        mark_finalized=mark_finalized,
    )
    if recovered is not None or run_state.get("stage") != "complete":
        return recovered
    return {
        "action": "finalize",
        "cleanup_pending": False,
        "idempotent": True,
        "publication_phase": publication.get("phase"),
        "run_ref": run_state.get("run_ref"),
        "stage": run_state.get("stage"),
    }


def replay_terminal_abort(
    run_dir: Path,
    publication: Mapping[str, Any],
    *,
    mark_finalized: FinalizeCallback,
) -> dict[str, Any] | None:
    cleanup_claim = publication.get("expired_cleanup_claim")
    phase = publication.get("phase")
    recoverable = phase == "aborted" or (
        phase in {"expired_cleanup_claimed", "expired_cleanup_complete"}
        and isinstance(cleanup_claim, Mapping)
        and cleanup_claim.get("disposition") == "expired_aborted"
    )
    if not recoverable:
        return None
    transaction = finalize.PublicationTransaction.inspect_local(
        run_dir / finalize.PUBLICATION_JOURNAL_NAME
    )
    publication_claim = publication.get("publication_claim")
    if isinstance(publication_claim, Mapping):
        attempt_ref = publication_claim.get("attempt_ref")
        claim_revision = publication_claim.get("checkpoint_revision")
        plan_digest = publication_claim.get("plan_digest")
    else:
        attempt_ref = transaction["attempt_ref"]
        claim_revision = None
        plan_digest = transaction["plan_digest"]
    run_result = mark_finalized(
        "aborted",
        attempt_ref=attempt_ref,
        claim_revision=claim_revision,
        defer_cleanup=True,
        plan_digest=plan_digest,
    )
    validated_attempt_ref = run_result.get("attempt_ref")
    validated_transaction_phase = run_result.get("transaction_phase")
    if (
        not isinstance(validated_attempt_ref, str)
        or validated_transaction_phase != "aborted"
    ):
        raise RunConflictError("abort replay lacks validated response authority")
    run_publication = run_result.get("publication")
    publication_phase = (
        run_publication.get("phase") if isinstance(run_publication, Mapping) else None
    )
    return {
        "action": "finalize",
        "attempt_ref": validated_attempt_ref,
        "cleanup_pending": False,
        "idempotent": True,
        "publication_phase": publication_phase,
        "run_ref": run_result.get("run_ref"),
        "stage": run_result.get("stage"),
        "transaction_phase": validated_transaction_phase,
    }
