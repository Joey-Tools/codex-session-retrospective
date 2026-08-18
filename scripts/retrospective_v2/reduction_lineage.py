"""Compact lineage commitments and bounded visible-reference projections."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import hashlib
from typing import Any

from .checkpoints import canonical_json_bytes


REF_SET_COMMITMENT_SCHEMA = "ref_set_commitment_v2"


def ref_set_commitment(refs: Iterable[str]) -> dict[str, Any]:
    """Commit an exact opaque-ref set without copying it into every task."""

    collected = list(refs)
    if any(not isinstance(ref, str) for ref in collected):
        raise ValueError("lineage refs must be strings")
    normalized = sorted(set(collected))
    payload = {
        "domain": REF_SET_COMMITMENT_SCHEMA,
        "refs": normalized,
    }
    return {
        "canonical_count": len(normalized),
        "canonical_sha256": hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
        "schema": REF_SET_COMMITMENT_SCHEMA,
    }


def result_turn_refs(results: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return only turn refs retained by bounded accepted result records."""

    refs: set[str] = set()
    for result in results:
        for field in ("high_impact_turns", "prompt_rewrites"):
            records = result.get(field, [])
            if not isinstance(records, list):
                raise ValueError(f"result {field} must be a list")
            for record in records:
                if not isinstance(record, Mapping) or not isinstance(
                    record.get("turn_ref"), str
                ):
                    raise ValueError(f"result {field} contains an invalid turn ref")
                refs.add(record["turn_ref"])
    return sorted(refs)


def topic_result_episode_revision_refs(
    results: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Return the bounded revision refs retained by child topic results."""

    refs: set[str] = set()
    for result in results:
        values = result.get("episode_revision_refs", [])
        if not isinstance(values, list) or any(
            not isinstance(value, str) for value in values
        ):
            raise ValueError("topic result episode revision refs are invalid")
        refs.update(values)
    return sorted(refs)


def topic_input_turn_refs(topic_input: Mapping[str, Any]) -> list[str]:
    """Project only previously accepted high-impact turns into a topic leaf."""

    results: list[Mapping[str, Any]] = []
    reviews = topic_input.get("episode_reviews", [])
    candidates = topic_input.get("adjudication_candidate_results", {})
    if not isinstance(reviews, list) or not isinstance(candidates, Mapping):
        raise ValueError("topic input review lineage is invalid")
    results.extend(reviews)
    for rows in candidates.values():
        if not isinstance(rows, list):
            raise ValueError("topic input adjudication candidates are invalid")
        results.extend(rows)
    return result_turn_refs(results)


def synthesis_visible_turn_refs(payload: Mapping[str, Any]) -> list[str]:
    """Project only bounded exemplars retained by a synthesis task payload."""

    results: list[Mapping[str, Any]] = []
    for field in (
        "child_synthesis_results",
        "independent_reviews",
        "prompt_rewrite_exemplars",
    ):
        values = payload.get(field, [])
        if not isinstance(values, list):
            raise ValueError(f"synthesis {field} must be a list")
        if field == "prompt_rewrite_exemplars":
            results.append({"prompt_rewrites": values})
        else:
            results.extend(values)
    return result_turn_refs(results)
