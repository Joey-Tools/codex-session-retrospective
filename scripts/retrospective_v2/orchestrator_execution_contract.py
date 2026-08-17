"""Executable agent prompt and policy contract for new and resumed runs."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from .checkpoints import canonical_json_bytes, content_digest
from .contracts import JobKind
from .orchestrator_core import InvalidTransitionError, _json_copy


_AGENT_INSTRUCTIONS = {
    JobKind.EXTRACTOR_REDACTOR.value: (
        "Read only the listed bounded raw shard and control manifest. Return one "
        "extractor_result_v2 JSON object using only allowed_output_refs."
    ),
    JobKind.EPISODE_REVIEWER.value: (
        "Review exactly the listed redacted episode revision as the primary reviewer. "
        "Return one episode_review_result_v2 JSON object bound to attempt_ref and "
        "reviewer_ref."
    ),
    JobKind.INDEPENDENT_RISK_REVIEWER.value: (
        "Independently review the listed redacted episode revision without using the "
        "primary result. Return one episode_review_result_v2 JSON object bound to the "
        "secondary reviewer identity."
    ),
    JobKind.ADJUDICATOR.value: (
        "Adjudicate only the two candidate reviews and bind their canonical hashes. "
        "Account for every candidate item as selected, merged, or explicitly rejected "
        "with its exact provenance. Return episode_review_adjudication_result_v2 JSON."
    ),
    JobKind.TOPIC_REDUCER.value: (
        "Aggregate exactly the resolved topic_input_v2 payload across its bound "
        "episodes and sessions. Return one topic_reduction_result_v2 object."
    ),
    JobKind.GLOBAL_SYNTHESIS.value: (
        "Synthesize only the validated topic results, episode reviews, coverage, and "
        "bound independent safety reviews. Return one global_synthesis_result_v2 "
        "JSON object."
    ),
}

EXECUTION_CONTRACT_SCHEMA = "retrospective_execution_contract_v2"
PROMPT_VERSION = "session_retrospective_agent_prompts_v2"
PROMPT_DIGEST = hashlib.sha256(canonical_json_bytes(_AGENT_INSTRUCTIONS)).hexdigest()
EXECUTION_VERSION_CONTRACT = {
    "detector": "episode_detector_v2",
    "policy": "source_and_partial_policy_v2",
    "redaction": "extractor_redaction_v2",
    "schema": "retrospective_schema_v2",
    "segmentation": "episode_segmentation_v2",
}


def _require_current_execution_contract(
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Reject resumed model work whose executable prompt contract drifted."""

    if not isinstance(provenance, Mapping):
        raise InvalidTransitionError("run execution provenance is missing")
    configuration_root = provenance.get("configuration_root")
    contract = {
        key: _json_copy(value, label=f"execution provenance {key}")
        for key, value in provenance.items()
        if key != "configuration_root"
    }
    if (
        not isinstance(configuration_root, str)
        or content_digest(contract) != configuration_root
    ):
        raise InvalidTransitionError("run execution provenance changed")
    prompt, versions = contract.get("prompt"), contract.get("versions")
    if (
        contract.get("schema") != EXECUTION_CONTRACT_SCHEMA
        or not isinstance(prompt, Mapping)
        or dict(prompt) != {"digest": PROMPT_DIGEST, "version": PROMPT_VERSION}
        or not isinstance(versions, Mapping)
        or dict(versions) != EXECUTION_VERSION_CONTRACT
    ):
        raise InvalidTransitionError(
            "run execution provenance no longer matches the executable contract"
        )
    return contract
