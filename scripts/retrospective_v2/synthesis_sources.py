"""Resolve exact episode-review evidence for one synthesis subtree."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import agent_results, result_validation


_REWRITE_FIELDS = (
    "cause",
    "confidence",
    "expected_effect",
    "problem_statement",
    "rewritten_prompt",
    "turn_ref",
)


def _revision_index(state: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    revisions = state.get("episodes")
    if not isinstance(revisions, list) or any(
        not isinstance(revision, Mapping) for revision in revisions
    ):
        raise result_validation.ResultValidationError(
            "synthesis episode revision index is invalid"
        )
    index = {revision.get("episode_revision_ref"): revision for revision in revisions}
    if None in index or len(index) != len(revisions):
        raise result_validation.ResultValidationError(
            "synthesis episode revision index is ambiguous"
        )
    return index


def _topic_revision_episodes(
    topic_results: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    revision_episodes: dict[str, str] = {}
    for topic in topic_results:
        lineage = topic.get("episode_revision_lineage")
        if not isinstance(lineage, list):
            raise result_validation.ResultValidationError(
                "synthesis topic revision lineage is invalid"
            )
        for row in lineage:
            if not isinstance(row, Mapping):
                raise result_validation.ResultValidationError(
                    "synthesis topic revision lineage is invalid"
                )
            revision_ref = row.get("episode_revision_ref")
            episode_ref = row.get("episode_ref")
            if not isinstance(revision_ref, str) or not isinstance(episode_ref, str):
                raise result_validation.ResultValidationError(
                    "synthesis topic revision lineage is invalid"
                )
            previous = revision_episodes.setdefault(revision_ref, episode_ref)
            if previous != episode_ref:
                raise result_validation.ResultValidationError(
                    "synthesis topic revision lineage conflicts"
                )
    return revision_episodes


def prompt_rewrites(
    run_dir: Path,
    state: Mapping[str, Any],
    topic_results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Project every resolved high-impact turn into synthesis evidence."""

    revision_episodes = _topic_revision_episodes(topic_results)
    if not revision_episodes:
        return []
    resolved = state.get("resolved_reviews")
    jobs = state.get("jobs")
    if not isinstance(resolved, Mapping) or not isinstance(jobs, Mapping):
        raise result_validation.ResultValidationError(
            "synthesis resolved review index is invalid"
        )
    rewrites: dict[str, dict[str, Any]] = {}
    for revision_ref, episode_ref in sorted(revision_episodes.items()):
        binding = resolved.get(revision_ref)
        if not isinstance(binding, Mapping):
            raise result_validation.ResultValidationError(
                "synthesis source review is unavailable"
            )
        review = agent_results.from_reference(run_dir, jobs, binding)
        if (
            review.get("episode_revision_ref") != revision_ref
            or review.get("episode_ref") != episode_ref
        ):
            raise result_validation.ResultValidationError(
                "synthesis source review lineage changed"
            )
        for item in review.get("high_impact_turns", []):
            rewrite = {field: copy.deepcopy(item[field]) for field in _REWRITE_FIELDS}
            rewrite["evidence_refs"] = [episode_ref]
            turn_ref = rewrite["turn_ref"]
            previous = rewrites.setdefault(turn_ref, rewrite)
            if json.dumps(previous, sort_keys=True) != json.dumps(
                rewrite, sort_keys=True
            ):
                raise result_validation.ResultValidationError(
                    "synthesis source prompt rewrites conflict"
                )
    return [rewrites[turn_ref] for turn_ref in sorted(rewrites)]


def turn_refs(
    state: Mapping[str, Any],
    topic_results: Sequence[Mapping[str, Any]],
    independent_reviews: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Return only turn refs reachable from one synthesis subtree."""

    revision_refs = set(_topic_revision_episodes(topic_results))
    for review in independent_reviews:
        revision_ref = review.get("episode_revision_ref")
        if not isinstance(revision_ref, str):
            raise result_validation.ResultValidationError(
                "synthesis independent review lineage is invalid"
            )
        revision_refs.add(revision_ref)
    revisions = _revision_index(state)
    if not revision_refs <= set(revisions):
        raise result_validation.ResultValidationError(
            "synthesis subtree references an unknown episode revision"
        )
    return sorted(
        {
            turn_ref
            for revision_ref in revision_refs
            for turn_ref in revisions[revision_ref]["turn_refs"]
        }
    )
