"""Machine-readable result contracts embedded in every agent envelope."""

from __future__ import annotations

import copy
from typing import Any, Mapping


CONTRACT_SCHEMA = "coordinator_agent_result_contract_v2"
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_SHA_PATTERN = r"^[0-9a-f]{64}$"


def _array(
    items: Mapping[str, Any],
    *,
    maximum: int,
    minimum: int = 0,
    unique: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "items": copy.deepcopy(dict(items)),
        "maxItems": maximum,
        "minItems": minimum,
        "type": "array",
    }
    if unique:
        result["uniqueItems"] = True
    return result


def _object(
    required: Mapping[str, Any],
    optional: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    properties = {**required, **dict(optional or {})}
    return {
        "additionalProperties": False,
        "properties": copy.deepcopy(properties),
        "required": sorted(required),
        "type": "object",
    }


def _enum(values: Any) -> dict[str, Any]:
    return {"enum": sorted(values), "type": "string"}


def _ref(prefix: str) -> dict[str, Any]:
    return {
        "pattern": rf"^{prefix}_ref_v2:[0-9a-f]{{64}}$",
        "type": "string",
        "x-ref-prefix": prefix,
    }


def _refs(
    prefix: str, limits: Mapping[str, Any], *, minimum: int = 0
) -> dict[str, Any]:
    return _array(
        _ref(prefix),
        maximum=limits["max_refs_per_field"],
        minimum=minimum,
        unique=True,
    )


def _signal(kinds: Any, limits: Mapping[str, Any]) -> dict[str, Any]:
    return _object(
        {
            "confidence": _enum(limits["confidence_levels"]),
            "evidence_refs": _refs("evidence", limits, minimum=1),
            "kind": _enum(kinds),
        },
        {"severity": _enum(limits["severity_levels"])},
    )


def _signal_array(kinds: Any, limits: Mapping[str, Any]) -> dict[str, Any]:
    return _array(_signal(kinds, limits), maximum=limits["max_signals_per_kind"])


def _rewrite(limits: Mapping[str, Any], *, evidence_prefix: str) -> dict[str, Any]:
    text = {
        "maxLength": limits["max_rewrite_text_chars"],
        "minLength": 1,
        "type": "string",
    }
    return _object(
        {
            "cause": text,
            "confidence": _enum(limits["confidence_levels"]),
            "evidence_refs": _refs(evidence_prefix, limits, minimum=1),
            "expected_effect": text,
            "problem_statement": text,
            "rewritten_prompt": text,
            "turn_ref": _ref("turn"),
        },
        {"severity": _enum(limits["severity_levels"])},
    )


def _episode_lineage(limits: Mapping[str, Any], *, minimum: int = 1) -> dict[str, Any]:
    return _array(
        _object({"episode_ref": _ref("episode"), "session_ref": _ref("session")}),
        maximum=limits["max_refs_per_field"],
        minimum=minimum,
        unique=True,
    )


def _episode_revision_lineage(
    limits: Mapping[str, Any], *, minimum: int = 1
) -> dict[str, Any]:
    return _array(
        _object(
            {
                "episode_ref": _ref("episode"),
                "episode_revision_ref": _ref("episode_revision"),
                "session_ref": _ref("session"),
            }
        ),
        maximum=limits["max_refs_per_field"],
        minimum=minimum,
        unique=True,
    )


def _reduction_commitment(fields: Any, limits: Mapping[str, Any]) -> dict[str, Any]:
    count = {"maximum": 1_000_000, "minimum": 0, "type": "integer"}
    return _object(
        {
            "child_result_hashes": _array(
                {"pattern": _SHA_PATTERN, "type": "string"},
                maximum=limits["max_refs_per_field"],
                minimum=1,
            ),
            "schema": {"const": "hierarchical_reduction_commitment_v2"},
            "source_item_counts": _object({field: count for field in fields}),
            "source_result_count": {
                "maximum": 1_000_000,
                "minimum": 1,
                "type": "integer",
            },
            "source_tree_hash": {"pattern": _SHA_PATTERN, "type": "string"},
        }
    )


def _review_root(
    vocabulary: Mapping[str, Any], *, adjudication: bool
) -> dict[str, Any]:
    limits = vocabulary["limits"]
    required: dict[str, Any] = {
        "confidence": _enum(vocabulary["confidence_levels"]),
        "episode_ref": _ref("episode"),
        "episode_revision_ref": _ref("episode_revision"),
        "events": _signal_array(vocabulary["event_kinds"], limits),
        "evidence_refs": _refs("evidence", limits),
        "findings": _signal_array(vocabulary["finding_kinds"], limits),
        "high_impact_turns": _array(
            _rewrite(limits, evidence_prefix="evidence"),
            maximum=limits["max_turns_per_result"],
        ),
        "risk_flags": _array(
            _enum(vocabulary["risk_flags"]),
            maximum=len(vocabulary["risk_flags"]),
            unique=True,
        ),
        "schema": {
            "const": vocabulary[
                "adjudication_schema" if adjudication else "review_schema"
            ]
        },
        "strengths": _signal_array(vocabulary["strength_kinds"], limits),
    }
    optional = {
        "gap_reason": _enum(
            vocabulary[
                "adjudication_gap_reasons" if adjudication else "review_gap_reasons"
            ]
        )
    }
    if adjudication:
        decision = _object(
            {
                "candidate_result_hash": {"pattern": _SHA_PATTERN, "type": "string"},
                "decision_codes": {
                    "maxLength": limits["max_refs_per_field"],
                    "pattern": "^["
                    + "".join(sorted(vocabulary["adjudication_decision_codes"]))
                    + "]*$",
                    "type": "string",
                },
                "field": _enum(vocabulary["adjudication_item_fields"]),
                "reviewer_slot": _enum({"primary", "secondary"}),
            }
        )
        required.update(
            {
                "candidate_item_decisions": _array(
                    decision,
                    maximum=len(vocabulary["adjudication_item_fields"]) * 2,
                    minimum=len(vocabulary["adjudication_item_fields"]) * 2,
                ),
                "candidate_result_hashes": _array(
                    {"pattern": _SHA_PATTERN, "type": "string"},
                    maximum=2,
                    minimum=2,
                    unique=True,
                ),
                "resolution": _enum(
                    {
                        "merged_supported",
                        "primary_supported",
                        "review_gap",
                        "secondary_supported",
                    }
                ),
            }
        )
    else:
        optional["reduction_commitment"] = _reduction_commitment(
            vocabulary["review_reduction_fields"], limits
        )
        required.update(
            {
                "attempt_ref": _ref("attempt"),
                "conflicting_signals": {"type": "boolean"},
                "disposition": _enum({"review_gap", "reviewed"}),
                "reviewer_ref": _ref("reviewer"),
                "reviewer_slot": _enum({"primary", "secondary"}),
                "second_review_recommended": {"type": "boolean"},
            }
        )
    return _object(required, optional)


def _extractor_root(vocabulary: Mapping[str, Any]) -> dict[str, Any]:
    limits = vocabulary["limits"]
    text = {
        "maxLength": limits["max_generalized_text_chars"],
        "minLength": 1,
        "type": "string",
    }
    turn = _object(
        {
            "confidence": _enum(vocabulary["confidence_levels"]),
            "events": _signal_array(vocabulary["event_kinds"], limits),
            "evidence_refs": _refs("evidence", limits, minimum=1),
            "findings": _signal_array(vocabulary["finding_kinds"], limits),
            "generalized_working_text": text,
            "outcome": _enum(vocabulary["outcomes"]),
            "risk_flags": _array(
                _enum(vocabulary["risk_flags"]),
                maximum=len(vocabulary["risk_flags"]),
                unique=True,
            ),
            "span_commitments": _refs("span_commitment", limits, minimum=1),
            "strengths": _signal_array(vocabulary["strength_kinds"], limits),
            "turn_ref": _ref("turn"),
        },
        {
            "conflicting_signals": {"type": "boolean"},
            "goal_change": _enum(
                {"completed_then_new", "continues", "new_goal", "redirected", "unknown"}
            ),
            "goal_ref": _ref("goal"),
            "meaningfulness_hint": _enum({"context_only", "meaningful", "uncertain"}),
            "task_completed": {"type": "boolean"},
            "user_redirect": {"type": "boolean"},
            "workstream_change": {"type": "boolean"},
            "workstream_ref": _ref("workstream"),
        },
    )
    return _object(
        {
            "schema": {"const": vocabulary["extractor_schema"]},
            "turns": _array(turn, maximum=limits["max_turns_per_result"]),
        },
        {
            "gap_reason": _enum(vocabulary["extractor_gap_reasons"]),
            "source_unit_ref": _ref("source_unit"),
        },
    )


def _topic_semantic_properties(vocabulary: Mapping[str, Any]) -> dict[str, Any]:
    limits = vocabulary["limits"]

    def lineage_candidate(kinds: Any) -> dict[str, Any]:
        return _object(
            {
                "confidence": _enum(vocabulary["confidence_levels"]),
                "episode_lineage": _episode_lineage(limits),
                "evidence_refs": _refs("evidence", limits, minimum=1),
                "kind": _enum(kinds),
            }
        )

    recurrence = _object(
        {
            "confidence": _enum(vocabulary["confidence_levels"]),
            "episode_revision_refs": _refs("episode_revision", limits, minimum=2),
            "evidence_refs": _refs("evidence", limits, minimum=1),
            "kind": _enum(
                set(vocabulary["event_kinds"])
                | set(vocabulary["finding_kinds"])
                | set(vocabulary["strength_kinds"])
            ),
            "session_refs": _refs("session", limits, minimum=1),
            "signal_type": _enum({"event", "finding", "strength"}),
        }
    )
    follow_up = _object(
        {
            "confidence": _enum(vocabulary["confidence_levels"]),
            "evidence_refs": _refs("evidence", limits, minimum=1),
            "kind": _enum(vocabulary["follow_up_kinds"]),
        }
    )
    return {
        "guidance_candidates": _array(
            lineage_candidate(vocabulary["guidance_kinds"]), maximum=64
        ),
        "open_work": _array(follow_up, maximum=64),
        "prompt_rewrites": _array(
            _rewrite(limits, evidence_prefix="evidence"),
            maximum=limits["max_turns_per_result"],
        ),
        "recurrences": _array(recurrence, maximum=64),
        "skill_candidates": _array(
            lineage_candidate(vocabulary["skill_candidate_kinds"]), maximum=64
        ),
    }


def _topic_root(vocabulary: Mapping[str, Any]) -> dict[str, Any]:
    limits = vocabulary["limits"]
    required = {
        "confidence": _enum(vocabulary["confidence_levels"]),
        "cross_session": {"type": "boolean"},
        "episode_lineage": _episode_lineage(limits),
        "episode_revision_lineage": _episode_revision_lineage(limits),
        "episode_refs": _refs("episode", limits, minimum=1),
        "episode_revision_refs": _refs("episode_revision", limits, minimum=1),
        "events": _signal_array(vocabulary["event_kinds"], limits),
        "evidence_refs": _refs("evidence", limits),
        "findings": _signal_array(vocabulary["finding_kinds"], limits),
        "review_result_hashes": _array(
            {"pattern": _SHA_PATTERN, "type": "string"},
            maximum=limits["max_refs_per_field"],
            minimum=1,
        ),
        "risk_flags": _array(
            _enum(vocabulary["risk_flags"]),
            maximum=len(vocabulary["risk_flags"]),
            unique=True,
        ),
        "schema": {"const": vocabulary["topic_schema"]},
        "session_refs": _refs("session", limits, minimum=1),
        "strengths": _signal_array(vocabulary["strength_kinds"], limits),
        "topic_ref": _ref("topic"),
        "workstream_ref": _ref("workstream"),
        **_topic_semantic_properties(vocabulary),
    }
    return _object(
        required,
        {
            "reduction_commitment": _reduction_commitment(
                vocabulary["topic_reduction_fields"], limits
            ),
            "topic_candidate_ref": _ref("topic_candidate"),
        },
    )


def _synthesis_root(vocabulary: Mapping[str, Any]) -> dict[str, Any]:
    limits = vocabulary["limits"]
    question = _object(
        {
            "confidence": _enum(vocabulary["confidence_levels"]),
            "disposition": _enum({"not_observed", "observed", "unavailable"}),
            "event_kinds": _array(
                _enum(vocabulary["event_kinds"]),
                maximum=len(vocabulary["event_kinds"]),
                unique=True,
            ),
            "evidence_refs": _refs("episode", limits),
            "finding_kinds": _array(
                _enum(vocabulary["finding_kinds"]),
                maximum=len(vocabulary["finding_kinds"]),
                unique=True,
            ),
            "question_id": _enum(vocabulary["question_ids"]),
            "strength_kinds": _array(
                _enum(vocabulary["strength_kinds"]),
                maximum=len(vocabulary["strength_kinds"]),
                unique=True,
            ),
        }
    )

    def durable(kinds: Any) -> dict[str, Any]:
        return _object(
            {
                "confidence": _enum(vocabulary["confidence_levels"]),
                "episode_lineage": _episode_lineage(limits),
                "exception": _enum({"high_severity_safety", "none"}),
                "kind": _enum(kinds),
            },
            {"independent_review_hash": {"pattern": _SHA_PATTERN, "type": "string"}},
        )

    commitment = _object(
        {
            "canonical_count": {"minimum": 0, "type": "integer"},
            "canonical_hash": {"pattern": _SHA_PATTERN, "type": "string"},
        }
    )
    required = {
        "confidence": _object(
            {
                name: _enum(vocabulary["confidence_levels"])
                for name in ("comparability", "coverage", "extraction", "review")
            }
        ),
        "era_comparison": _object(
            {
                "change": _enum({"improved", "regressed", "unchanged", "unavailable"}),
                "status": _enum({"compatible", "incompatible", "unavailable"}),
            }
        ),
        "events": _signal_array(vocabulary["event_kinds"], limits),
        "evidence_refs": _refs("episode", limits),
        "findings": _signal_array(vocabulary["finding_kinds"], limits),
        "follow_up_actions": _array(
            _object(
                {
                    "confidence": _enum(vocabulary["confidence_levels"]),
                    "evidence_refs": _refs("episode", limits),
                    "kind": _enum(vocabulary["follow_up_kinds"]),
                }
            ),
            maximum=64,
        ),
        "guidance_candidates": _array(
            durable(vocabulary["guidance_kinds"]), maximum=64
        ),
        "prompt_rewrites": _array(
            _rewrite(limits, evidence_prefix="episode"),
            maximum=limits["max_turns_per_result"],
        ),
        "question_answers": _array(
            question,
            maximum=len(vocabulary["question_ids"]),
            minimum=len(vocabulary["question_ids"]),
        ),
        "schema": {"const": vocabulary["synthesis_schema"]},
        "signal_commitments": _object(
            {name: commitment for name in ("events", "findings", "strengths")}
        ),
        "skill_candidates": _array(
            durable(vocabulary["skill_candidate_kinds"]), maximum=64
        ),
        "strengths": _signal_array(vocabulary["strength_kinds"], limits),
        "topic_result_hashes": _array(
            {"pattern": _SHA_PATTERN, "type": "string"},
            maximum=128,
            unique=True,
        ),
    }
    return _object(required)


def contract_for_schema(
    result_schema: str,
    vocabulary: Mapping[str, Any],
) -> dict[str, Any]:
    builders = {
        vocabulary["extractor_schema"]: _extractor_root,
        vocabulary["review_schema"]: lambda value: _review_root(
            value, adjudication=False
        ),
        vocabulary["adjudication_schema"]: lambda value: _review_root(
            value, adjudication=True
        ),
        vocabulary["topic_schema"]: _topic_root,
        vocabulary["synthesis_schema"]: _synthesis_root,
    }
    try:
        root = builders[result_schema](vocabulary)
    except KeyError as error:
        raise ValueError(f"unsupported agent result schema: {result_schema}") from error
    return {
        "cross_field_rules": list(vocabulary["cross_field_rules"][result_schema]),
        "json_schema": {
            "$schema": JSON_SCHEMA_DIALECT,
            **root,
        },
        "privacy_rules": list(vocabulary["privacy_rules"]),
        "result_schema": result_schema,
        "runtime_bindings": list(vocabulary["runtime_bindings"][result_schema]),
        "schema": CONTRACT_SCHEMA,
        "serialization": copy.deepcopy(vocabulary["serialization"]),
    }
