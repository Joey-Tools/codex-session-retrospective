"""Exact immutable metadata builders for reduction jobs."""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence


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
