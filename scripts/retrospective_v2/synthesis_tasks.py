"""Exact immutable payload and metadata builders for synthesis jobs."""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

from . import result_validation


def input_payload(
    coverage: Mapping[str, Any],
    topic_results: Sequence[Mapping[str, Any]],
    independent_reviews: Sequence[Mapping[str, Any]],
    prompt_rewrites: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "coverage": copy.deepcopy(dict(coverage)),
        "independent_reviews": copy.deepcopy(list(independent_reviews)),
        "prompt_rewrite_commitment": (
            result_validation.build_synthesis_prompt_rewrite_commitment(prompt_rewrites)
        ),
        "prompt_rewrite_exemplars": (
            result_validation.build_synthesis_prompt_rewrite_exemplars(prompt_rewrites)
        ),
        "safety_review_hashes": sorted(
            result_validation.canonical_result_hash(review)
            for review in independent_reviews
        ),
        "schema": "global_synthesis_input_v2",
        "signal_commitments": result_validation.build_synthesis_signal_commitments(
            topic_results
        ),
        "signal_exemplars": result_validation.build_synthesis_signal_exemplars(
            topic_results
        ),
        "topic_result_commitment": (
            result_validation.build_synthesis_topic_result_commitment(topic_results)
        ),
        "topic_results": copy.deepcopy(list(topic_results)),
    }


def metadata(
    *,
    root_ref: str,
    payload: Mapping[str, Any],
    topic_results: Sequence[Mapping[str, Any]],
    independent_reviews: Sequence[Mapping[str, Any]],
    level: int,
    final: bool,
    validation_child_task_refs: Sequence[str] = (),
) -> dict[str, Any]:
    review_hashes = sorted(
        result_validation.canonical_result_hash(review)
        for review in independent_reviews
    )
    topic_commitment = copy.deepcopy(
        payload.get(
            "topic_result_commitment",
            result_validation.build_synthesis_topic_result_commitment(topic_results),
        )
    )
    return {
        "hierarchy_final": final,
        "hierarchy_level": level,
        "hierarchy_root_ref": root_ref,
        "safety_review_hashes": review_hashes,
        "topic_result_commitment": topic_commitment,
        "validation_child_task_refs": sorted(set(validation_child_task_refs)),
        "validation_independent_review_hashes": review_hashes,
        "validation_topic_result_commitment": topic_commitment,
    }
