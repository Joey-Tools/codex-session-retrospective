"""Deterministic source-lineage checks for hierarchical synthesis tasks."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import agent_results, agent_task_inputs, result_validation, synthesis_sources


def _mapping_list(value: Any, *, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise result_validation.ResultValidationError(f"{label} are invalid")
    return value


def _expected_source_fields(
    topics: Sequence[Mapping[str, Any]],
    prompt_rewrites: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "prompt_rewrite_commitment": (
            result_validation.build_synthesis_prompt_rewrite_commitment(prompt_rewrites)
        ),
        "prompt_rewrite_exemplars": (
            result_validation.build_synthesis_prompt_rewrite_exemplars(prompt_rewrites)
        ),
        "signal_commitments": result_validation.build_synthesis_signal_commitments(
            topics
        ),
        "signal_exemplars": result_validation.build_synthesis_signal_exemplars(topics),
        "topic_result_commitment": (
            result_validation.build_synthesis_topic_result_commitment(topics)
        ),
    }


def _validate_source_fields(
    payload: Mapping[str, Any],
    topics: Sequence[Mapping[str, Any]],
    prompt_rewrites: Sequence[Mapping[str, Any]],
) -> None:
    for field, expected in _expected_source_fields(topics, prompt_rewrites).items():
        if payload.get(field) != expected:
            raise result_validation.ResultValidationError(
                f"synthesis input {field} changed"
            )


def collect_validation_results(
    run_dir: Path,
    state: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the exact leaf sources committed by one synthesis subtree."""

    if not tasks:
        return [], []
    root_ref = tasks[0].get("metadata", {}).get("hierarchy_root_ref")
    if not isinstance(root_ref, str):
        raise result_validation.ResultValidationError(
            "synthesis validation root is invalid"
        )
    memo: dict[
        str, tuple[list[tuple[str, dict[str, Any]]], list[tuple[str, dict[str, Any]]]]
    ] = {}
    active: set[str] = set()

    def visit(
        task: Mapping[str, Any],
    ) -> tuple[list[tuple[str, dict[str, Any]]], list[tuple[str, dict[str, Any]]]]:
        task_ref = task.get("task_ref")
        metadata = task.get("metadata")
        if (
            not isinstance(task_ref, str)
            or not isinstance(metadata, Mapping)
            or metadata.get("hierarchy_root_ref") != root_ref
        ):
            raise result_validation.ResultValidationError(
                "synthesis validation lineage is invalid"
            )
        if task_ref in memo:
            topics, reviews = memo[task_ref]
            return copy.deepcopy(topics), copy.deepcopy(reviews)
        if task_ref in active:
            raise result_validation.ResultValidationError(
                "synthesis validation lineage contains a cycle"
            )
        active.add(task_ref)
        immutable = agent_task_inputs.for_task(run_dir, task)
        payload = immutable.get("input_payload")
        if not isinstance(payload, Mapping):
            raise result_validation.ResultValidationError(
                "synthesis validation input is invalid"
            )
        child_refs = metadata.get("validation_child_task_refs", [])
        if (
            not isinstance(child_refs, list)
            or any(not isinstance(ref, str) for ref in child_refs)
            or child_refs != sorted(set(child_refs))
        ):
            raise result_validation.ResultValidationError(
                "synthesis validation child task refs are invalid"
            )
        topic_rows: list[tuple[str, dict[str, Any]]] = []
        review_rows: list[tuple[str, dict[str, Any]]] = []
        if child_refs:
            if payload.get("schema") != "global_synthesis_hierarchical_input_v2":
                raise result_validation.ResultValidationError(
                    "synthesis validation parent input is invalid"
                )
            children: list[Mapping[str, Any]] = []
            for child_ref in child_refs:
                child = state.get("jobs", {}).get(child_ref)
                if not isinstance(child, Mapping) or child.get("status") != "accepted":
                    raise result_validation.ResultValidationError(
                        "synthesis validation child task is unavailable"
                    )
                children.append(child)
                child_topics, child_reviews = visit(child)
                topic_rows.extend(child_topics)
                review_rows.extend(child_reviews)
            child_results = agent_results.copies_for_tasks(
                run_dir, children, label="accepted synthesis"
            )
            if payload.get("child_synthesis_results") != child_results or payload.get(
                "child_result_hashes"
            ) != [
                result_validation.canonical_result_hash(result)
                for result in child_results
            ]:
                raise result_validation.ResultValidationError(
                    "synthesis validation child results changed"
                )
        else:
            if payload.get("schema") != "global_synthesis_input_v2":
                raise result_validation.ResultValidationError(
                    "synthesis validation leaf input is invalid"
                )
            leaf_topics = _mapping_list(
                payload.get("topic_results"), label="synthesis validation leaf topics"
            )
            leaf_reviews = _mapping_list(
                payload.get("independent_reviews"),
                label="synthesis validation leaf reviews",
            )
            topic_rows = [
                (
                    result_validation.canonical_result_hash(result),
                    copy.deepcopy(dict(result)),
                )
                for result in leaf_topics
            ]
            review_rows = [
                (
                    result_validation.canonical_result_hash(result),
                    copy.deepcopy(dict(result)),
                )
                for result in leaf_reviews
            ]
            if metadata.get("validation_topic_result_commitment") != (
                result_validation.build_synthesis_topic_result_commitment(leaf_topics)
            ) or metadata.get("validation_independent_review_hashes") != sorted(
                digest for digest, _result in review_rows
            ):
                raise result_validation.ResultValidationError(
                    "synthesis validation leaf commitments changed"
                )
        topic_hashes = [digest for digest, _result in topic_rows]
        review_hashes = [digest for digest, _result in review_rows]
        if len(topic_hashes) != len(set(topic_hashes)) or len(review_hashes) != len(
            set(review_hashes)
        ):
            raise result_validation.ResultValidationError(
                "synthesis validation hierarchy contains duplicate results"
            )
        topics = [result for _digest, result in sorted(topic_rows)]
        reviews = [result for _digest, result in sorted(review_rows)]
        _validate_source_fields(
            payload,
            topics,
            synthesis_sources.prompt_rewrites(run_dir, state, topics),
        )
        active.remove(task_ref)
        memo[task_ref] = (copy.deepcopy(topic_rows), copy.deepcopy(review_rows))
        return topic_rows, review_rows

    all_topics: list[tuple[str, dict[str, Any]]] = []
    all_reviews: list[tuple[str, dict[str, Any]]] = []
    for task in tasks:
        topics, reviews = visit(task)
        all_topics.extend(topics)
        all_reviews.extend(reviews)
    topic_hashes = [digest for digest, _result in all_topics]
    review_hashes = [digest for digest, _result in all_reviews]
    if len(topic_hashes) != len(set(topic_hashes)) or len(review_hashes) != len(
        set(review_hashes)
    ):
        raise result_validation.ResultValidationError(
            "synthesis validation hierarchy contains duplicate results"
        )
    return (
        [result for _digest, result in sorted(all_topics)],
        [result for _digest, result in sorted(all_reviews)],
    )


def build_reduce_payload(
    run_dir: Path,
    state: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    topics, _reviews = collect_validation_results(run_dir, state, tasks)
    prompt_rewrites = synthesis_sources.prompt_rewrites(run_dir, state, topics)
    results = agent_results.copies_for_tasks(run_dir, tasks, label="accepted synthesis")
    return {
        "child_result_hashes": [
            result_validation.canonical_result_hash(result) for result in results
        ],
        "child_synthesis_results": results,
        "schema": "global_synthesis_hierarchical_input_v2",
        **_expected_source_fields(topics, prompt_rewrites),
    }
