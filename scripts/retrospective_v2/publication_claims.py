"""Durable publication claim validation shared by lifecycle transitions."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .orchestrator_support import (
    InvalidTransitionError,
    RunConflictError,
)


StateIdentityValidator = Callable[[Mapping[str, Any]], None]
PublicationClaimValidator = Callable[
    [Mapping[str, Any], object],
    dict[str, Any],
]


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
