"""Exact immutable metadata builders for reduction jobs."""

from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping, Sequence


def review_metadata(
    base: Mapping[str, Any],
    *,
    root_ref: str,
    turn_ref_commitment: Mapping[str, Any],
    level: int,
    final: bool,
    child_result_hashes: Sequence[str] | None = None,
) -> dict[str, Any]:
    result = {
        **copy.deepcopy(dict(base)),
        "hierarchy_final": final,
        "hierarchy_level": level,
        "hierarchy_root_ref": root_ref,
        "turn_ref_commitment": copy.deepcopy(dict(turn_ref_commitment)),
    }
    if child_result_hashes is not None:
        result["candidate_result_hashes"] = list(child_result_hashes)
    return result


def review_reduction_task_input(
    base: Mapping[str, Any],
    *,
    kind: str,
    final_partition_ref: str,
    intermediate_partition_ref: str,
    payload: Mapping[str, Any],
    input_refs: Sequence[str],
    allowed_refs: Iterable[str],
    turn_refs: Sequence[str],
    turn_ref_commitment: Mapping[str, Any],
    level: int,
    final: bool,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "partition_ref": (final_partition_ref if final else intermediate_partition_ref),
        "input_refs": list(input_refs),
        "input_payload": dict(payload),
        "allowed_refs": list(allowed_refs),
        "allowed_turn_refs": list(turn_refs),
        "metadata": review_metadata(
            base,
            root_ref=final_partition_ref,
            turn_ref_commitment=turn_ref_commitment,
            level=level,
            final=final,
            child_result_hashes=payload["child_result_hashes"],
        ),
    }


def adjudication_task_input(
    *,
    episode_ref: str,
    revision_ref: str,
    payload: Mapping[str, Any],
    allowed_refs: Iterable[str],
    turn_refs: Sequence[str],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "kind": "adjudicator",
        "partition_ref": revision_ref,
        "input_refs": [episode_ref, revision_ref],
        "input_payload": dict(payload),
        "allowed_refs": list(allowed_refs),
        "allowed_turn_refs": list(turn_refs),
        "metadata": copy.deepcopy(dict(metadata)),
    }


def topic_leaf_task_input(
    *,
    final_partition_ref: str,
    intermediate_partition_ref: str,
    topic_ref: str,
    workstream_ref: str,
    topic_input: Mapping[str, Any],
    allowed_refs: Iterable[str],
    turn_refs: Sequence[str],
    episode_revision_commitment: Mapping[str, Any],
    level: int,
    final: bool,
) -> dict[str, Any]:
    episode_refs = list(topic_input["expected_episode_revision_refs"])
    return {
        "kind": "topic_reducer",
        "partition_ref": (final_partition_ref if final else intermediate_partition_ref),
        "input_refs": [final_partition_ref, *episode_refs],
        "input_payload": dict(topic_input),
        "allowed_refs": list(allowed_refs),
        "allowed_turn_refs": list(turn_refs),
        "metadata": {
            "episode_revision_commitment": copy.deepcopy(
                dict(episode_revision_commitment)
            ),
            "hierarchy_final": final,
            "hierarchy_level": level,
            "hierarchy_root_ref": final_partition_ref,
            "topic_candidate_ref": final_partition_ref,
            "topic_ref": topic_ref,
            "workstream_ref": workstream_ref,
        },
    }


def topic_reduction_task_input(
    *,
    kind: str,
    final_partition_ref: str,
    intermediate_partition_ref: str,
    topic_ref: str,
    workstream_ref: str,
    payload: Mapping[str, Any],
    episode_refs: Sequence[str],
    allowed_refs: Iterable[str],
    turn_refs: Sequence[str],
    episode_revision_commitment: Mapping[str, Any],
    level: int,
    final: bool,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "partition_ref": (final_partition_ref if final else intermediate_partition_ref),
        "input_refs": [final_partition_ref, *episode_refs],
        "input_payload": dict(payload),
        "allowed_refs": list(allowed_refs),
        "allowed_turn_refs": list(turn_refs),
        "metadata": {
            "child_result_hashes": payload["child_result_hashes"],
            "episode_revision_commitment": copy.deepcopy(
                dict(episode_revision_commitment)
            ),
            "hierarchy_final": final,
            "hierarchy_level": level,
            "hierarchy_root_ref": final_partition_ref,
            "topic_candidate_ref": final_partition_ref,
            "topic_ref": topic_ref,
            "workstream_ref": workstream_ref,
        },
    }
