"""Worst-case fixed-shape claim metadata used for envelope capacity checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .agent_claim_artifacts import artifact_name
from .contracts import (
    MAX_AGENT_CLAIM_GENERATIONS_PER_ATTEMPT,
    RefType,
    format_typed_ref,
)


def projected_attempt(
    *,
    run_dir: Path,
    run_ref: str,
    job_ref: str,
    attempt_ref: str,
    ordinal: int,
    partition_ref: str,
    reviewer_slot: str | None,
    derive_ref: Callable[..., str],
) -> dict[str, Any]:
    generation = MAX_AGENT_CLAIM_GENERATIONS_PER_ATTEMPT
    dispatcher_ref = format_typed_ref(RefType.LEASE, "f" * 64)
    claim_ref = derive_ref(
        RefType.CLAIM,
        run_ref,
        job_ref,
        attempt_ref,
        generation,
        dispatcher_ref,
    )
    output_relative = f"agent-sinks/{artifact_name(attempt_ref, generation, 'result')}"
    reviewer_ref = (
        None
        if reviewer_slot is None
        else derive_ref(RefType.REVIEWER, partition_ref, reviewer_slot, ordinal)
    )
    return {
        "attempt_ref": attempt_ref,
        "claim_ref": claim_ref,
        "dispatcher_ref": dispatcher_ref,
        "job_ref": job_ref,
        "ordinal": ordinal,
        "output_sink": str(run_dir / output_relative),
        "result_ref": derive_ref(
            RefType.RESULT,
            run_ref,
            job_ref,
            attempt_ref,
            claim_ref,
            output_relative,
        ),
        "reviewer_ref": reviewer_ref,
    }
