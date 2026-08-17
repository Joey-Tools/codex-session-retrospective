"""Deterministic compact evidence for bounded synthesis results."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Callable, Mapping, Sequence


def _canonical_value(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _commit(values: Sequence[Any]) -> dict[str, Any]:
    canonical_values = sorted({_canonical_value(value) for value in values})
    encoded = json.dumps(
        canonical_values,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "canonical_count": len(canonical_values),
        "canonical_hash": hashlib.sha256(encoded).hexdigest(),
    }


def build_synthesis_signal_commitments(
    topic_results: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Commit each complete canonical topic-signal union."""

    return {
        field: _commit(
            [item for topic in topic_results for item in topic.get(field, [])]
        )
        for field in ("events", "findings", "strengths")
    }


def build_synthesis_topic_result_commitment(
    topic_results: Sequence[Mapping[str, Any]],
    *,
    result_hasher: Callable[[Mapping[str, Any]], str],
) -> dict[str, Any]:
    """Commit the complete canonical topic-result multiset."""

    result_hashes = sorted(result_hasher(result) for result in topic_results)
    encoded = json.dumps(
        result_hashes,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "canonical_count": len(result_hashes),
        "canonical_hash": hashlib.sha256(encoded).hexdigest(),
    }


def _bounded_exemplars(
    values: Sequence[Mapping[str, Any]],
    *,
    maximum: int,
) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for item in values:
        canonical = _canonical_value(item)
        unique.setdefault(canonical, copy.deepcopy(dict(item)))
    ordered = sorted(
        unique.items(),
        key=lambda item: (
            0 if item[1].get("severity") in {"high", "critical"} else 1,
            item[0],
        ),
    )
    return [item for _canonical, item in ordered[:maximum]]


def build_synthesis_signal_exemplars(
    topic_results: Sequence[Mapping[str, Any]],
    *,
    maximum: int,
) -> dict[str, list[dict[str, Any]]]:
    """Select deterministic high-severity-first topic-signal exemplars."""

    return {
        field: _bounded_exemplars(
            [item for topic in topic_results for item in topic.get(field, [])],
            maximum=maximum,
        )
        for field in ("events", "findings", "strengths")
    }


def build_synthesis_prompt_rewrite_commitment(
    prompt_rewrites: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Commit every source-derived high-impact prompt rewrite."""

    return _commit(list(prompt_rewrites))


def build_synthesis_prompt_rewrite_exemplars(
    prompt_rewrites: Sequence[Mapping[str, Any]],
    *,
    maximum: int,
) -> list[dict[str, Any]]:
    """Select deterministic bounded prompt-rewrite exemplars."""

    return _bounded_exemplars(prompt_rewrites, maximum=maximum)


def retained_prompt_rewrite_evidence(
    turn_findings: Sequence[Mapping[str, Any]],
    *,
    maximum: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Rebuild synthesis rewrite evidence from retained high-impact turns."""

    fields = (
        "cause",
        "confidence",
        "expected_effect",
        "problem_statement",
        "rewritten_prompt",
        "turn_ref",
    )
    rewrites = [
        {
            **{field: copy.deepcopy(row[field]) for field in fields},
            "evidence_refs": [row["episode_ref"]],
        }
        for row in turn_findings
        if row["disposition"] == "high_impact"
    ]
    return (
        build_synthesis_prompt_rewrite_commitment(rewrites),
        build_synthesis_prompt_rewrite_exemplars(rewrites, maximum=maximum),
    )


def retained_prompt_rewrite_mismatch(
    turn_findings: Sequence[Mapping[str, Any]],
    synthesis: Mapping[str, Any],
    *,
    maximum: int,
) -> str | None:
    commitment, exemplars = retained_prompt_rewrite_evidence(
        turn_findings, maximum=maximum
    )
    if _canonical_value(synthesis.get("prompt_rewrite_commitment")) != (
        _canonical_value(commitment)
    ):
        return "commitment"
    if _canonical_value(synthesis.get("prompt_rewrites")) != _canonical_value(
        exemplars
    ):
        return "exemplars"
    return None


def result_prompt_rewrite_mismatch(
    source_prompt_rewrites: Sequence[Mapping[str, Any]],
    synthesis: Mapping[str, Any],
    *,
    maximum: int,
) -> str | None:
    expected_commitment = build_synthesis_prompt_rewrite_commitment(
        source_prompt_rewrites
    )
    if _canonical_value(synthesis["prompt_rewrite_commitment"]) != (
        _canonical_value(expected_commitment)
    ):
        return "commitment"
    expected_exemplars = build_synthesis_prompt_rewrite_exemplars(
        source_prompt_rewrites, maximum=maximum
    )
    if _canonical_value(synthesis["prompt_rewrites"]) != _canonical_value(
        expected_exemplars
    ):
        return "exemplars"
    return None
