"""Exact immutable metadata builders for reduction jobs."""

from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping, Sequence


def review_metadata(
    base: Mapping[str, Any],
    *,
    root_ref: str,
    turn_refs: Sequence[str],
    level: int,
    final: bool,
    child_result_hashes: Sequence[str] | None = None,
) -> dict[str, Any]:
    result = {
        **copy.deepcopy(dict(base)),
        "hierarchy_final": final,
        "hierarchy_level": level,
        "hierarchy_root_ref": root_ref,
        "underlying_turn_refs": list(turn_refs),
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
            turn_refs=turn_refs,
            level=level,
            final=final,
            child_result_hashes=payload["child_result_hashes"],
        ),
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
            "hierarchy_final": final,
            "hierarchy_level": level,
            "hierarchy_root_ref": final_partition_ref,
            "topic_candidate_ref": final_partition_ref,
            "topic_ref": topic_ref,
            "underlying_episode_refs": list(episode_refs),
            "workstream_ref": workstream_ref,
        },
    }
