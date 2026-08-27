"""Bounded synthesis hierarchy operations for the retrospective coordinator."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from . import (
    agent_results,
    result_validation,
    synthesis_lineage,
    synthesis_sources,
    synthesis_tasks,
)
from .contracts import JobKind, RefType, RunStage
from .orchestrator_support import InvalidTransitionError


def seed_task(owner: Any, state: dict[str, Any]) -> None:
    final_topic_tasks = owner._accepted_final_topic_tasks(state)
    if owner._projection._tasks_for_stage(state, RunStage.GLOBAL_SYNTHESIS.value):
        return
    topic_results = agent_results.copies_for_tasks(
        owner.run_dir, final_topic_tasks, label="accepted topic"
    )
    independent_reviews = []
    for task in owner._projection._tasks_for_stage(
        state, RunStage.EPISODE_REVIEW.value
    ):
        if (
            task["job_kind"] != JobKind.INDEPENDENT_RISK_REVIEWER.value
            or task["status"] != "accepted"
            or task["metadata"].get("hierarchy_final") is not True
        ):
            continue
        result = agent_results.for_task(owner.run_dir, task)
        if owner._projection._is_completed_episode_review(result):
            independent_reviews.append(result)
    root_ref = owner._ref(
        RefType.RUN_INPUT,
        state["run_ref"],
        "global_synthesis",
        [task["task_ref"] for task in final_topic_tasks],
    )
    owner._seed_synthesis_hierarchy(
        state,
        root_ref=root_ref,
        topic_results=topic_results,
        independent_reviews=independent_reviews,
    )


def accepted_final_topic_tasks(
    owner: Any,
    state: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    expected_roots = set(state["topic_inputs"])
    accepted = [
        task
        for task in state["jobs"].values()
        if task.get("stage") == RunStage.TOPIC_REDUCTION.value
        and task.get("status") == "accepted"
        and isinstance(task.get("metadata"), Mapping)
        and task["metadata"].get("hierarchy_final") is True
    ]
    roots: list[str] = []
    for task in accepted:
        root_ref = task["metadata"].get("hierarchy_root_ref")
        result = agent_results.for_task(owner.run_dir, task)
        if (
            not isinstance(root_ref, str)
            or not isinstance(result, Mapping)
            or result.get("topic_candidate_ref") != root_ref
        ):
            raise InvalidTransitionError(
                "accepted final topic result has invalid root binding"
            )
        roots.append(root_ref)
    root_counts = {root_ref: roots.count(root_ref) for root_ref in set(roots)}
    if set(root_counts) - expected_roots:
        raise InvalidTransitionError("extra accepted final topic result root")
    if any(count != 1 for count in root_counts.values()):
        raise InvalidTransitionError("duplicate accepted final topic result root")
    if expected_roots - set(root_counts):
        raise InvalidTransitionError("missing accepted final topic result root")
    return sorted(accepted, key=lambda task: task["metadata"]["hierarchy_root_ref"])


def seed_hierarchy(
    owner: Any,
    state: dict[str, Any],
    *,
    root_ref: str,
    topic_results: Sequence[Mapping[str, Any]],
    independent_reviews: Sequence[Mapping[str, Any]],
    coverage: Mapping[str, Any],
) -> None:
    prompt_rewrites = synthesis_sources.prompt_rewrites(
        owner.run_dir, state, topic_results
    )
    payload = synthesis_tasks.input_payload(
        coverage,
        topic_results,
        independent_reviews,
        prompt_rewrites,
    )
    allowed = sorted(owner._projection._collect_refs({"payload": payload}))
    direct_task_input = synthesis_tasks.task_input(
        kind=JobKind.GLOBAL_SYNTHESIS.value,
        root_ref=root_ref,
        partition_ref=root_ref,
        payload=payload,
        allowed_refs=allowed,
        topic_results=topic_results,
        independent_reviews=independent_reviews,
        level=0,
        final=True,
    )
    if owner._jobs._agent_input_fits(state, **direct_task_input):
        owner._create_synthesis_task(
            state,
            root_ref=root_ref,
            partition_ref=root_ref,
            payload=payload,
            topic_results=topic_results,
            independent_reviews=independent_reviews,
            level=0,
            final=True,
        )
        return
    items = [
        ("topic", result_validation.canonical_result_hash(item), item)
        for item in topic_results
    ] + [
        ("review", result_validation.canonical_result_hash(item), item)
        for item in independent_reviews
    ]
    items.sort(key=lambda item: (item[0], item[1]))
    groups: list[list[tuple[str, str, Mapping[str, Any]]]] = []
    for item in items:
        candidate = [*(groups[-1] if groups else []), item]
        topics = [value for kind, _digest, value in candidate if kind == "topic"]
        reviews = [value for kind, _digest, value in candidate if kind == "review"]
        candidate_rewrites = synthesis_sources.prompt_rewrites(
            owner.run_dir, state, topics
        )
        candidate_payload = synthesis_tasks.input_payload(
            coverage, topics, reviews, candidate_rewrites
        )
        candidate_allowed = sorted(
            owner._projection._collect_refs({"payload": candidate_payload})
        )
        candidate_index = max(len(groups) - 1, 0)
        candidate_partition_ref = owner._ref(
            RefType.RUN_INPUT, root_ref, "synthesis_leaf", candidate_index
        )
        candidate_fits = owner._jobs._agent_input_fits(
            state,
            **synthesis_tasks.task_input(
                kind=JobKind.GLOBAL_SYNTHESIS.value,
                root_ref=root_ref,
                partition_ref=candidate_partition_ref,
                payload=candidate_payload,
                allowed_refs=candidate_allowed,
                topic_results=topics,
                independent_reviews=reviews,
                level=0,
                final=False,
            ),
        )
        if not candidate_fits and not groups:
            raise InvalidTransitionError(
                "one synthesis source cannot fit its exact leaf task"
            )
        if groups and not candidate_fits:
            groups.append([item])
        elif groups:
            groups[-1] = candidate
        else:
            groups.append([item])
    if not groups:
        groups = [[]]
    for index, group in enumerate(groups):
        topics = [value for kind, _digest, value in group if kind == "topic"]
        reviews = [value for kind, _digest, value in group if kind == "review"]
        group_rewrites = synthesis_sources.prompt_rewrites(owner.run_dir, state, topics)
        owner._create_synthesis_task(
            state,
            root_ref=root_ref,
            partition_ref=owner._ref(
                RefType.RUN_INPUT, root_ref, "synthesis_leaf", index
            ),
            payload=synthesis_tasks.input_payload(
                coverage, topics, reviews, group_rewrites
            ),
            topic_results=topics,
            independent_reviews=reviews,
            level=0,
            final=False,
        )


def create_task(
    owner: Any,
    state: dict[str, Any],
    *,
    root_ref: str,
    partition_ref: str,
    payload: Mapping[str, Any],
    topic_results: Sequence[Mapping[str, Any]],
    independent_reviews: Sequence[Mapping[str, Any]],
    level: int,
    final: bool,
    validation_child_task_refs: Sequence[str] = (),
) -> None:
    allowed = sorted(owner._projection._collect_refs({"payload": payload}))
    task_input = synthesis_tasks.task_input(
        kind=JobKind.GLOBAL_SYNTHESIS.value,
        root_ref=root_ref,
        partition_ref=partition_ref,
        payload=payload,
        allowed_refs=allowed,
        topic_results=topic_results,
        independent_reviews=independent_reviews,
        level=level,
        final=final,
        validation_child_task_refs=validation_child_task_refs,
    )
    if not owner._jobs._agent_input_fits(state, **task_input):
        raise InvalidTransitionError("synthesis task exceeds its exact input bound")
    owner._jobs._create_agent_task(
        state,
        stage=RunStage.GLOBAL_SYNTHESIS.value,
        **task_input,
    )


def refresh_hierarchy(owner: Any, state: dict[str, Any]) -> None:
    tasks = owner._projection._tasks_for_stage(state, RunStage.GLOBAL_SYNTHESIS.value)
    if not tasks or any(
        task["metadata"].get("hierarchy_final") is True for task in tasks
    ):
        return
    level = max(int(task["metadata"]["hierarchy_level"]) for task in tasks)
    current = [task for task in tasks if task["metadata"]["hierarchy_level"] == level]
    if any(task["status"] != "accepted" for task in current):
        return
    if any(task["metadata"]["hierarchy_level"] == level + 1 for task in tasks):
        return
    root_ref = current[0]["metadata"]["hierarchy_root_ref"]
    groups: list[list[dict[str, Any]]] = []
    for task in sorted(current, key=lambda item: item["task_ref"]):
        candidate = [*(groups[-1] if groups else []), task]
        payload = owner._synthesis_reduce_payload(state, candidate)
        allowed = sorted(owner._projection._collect_refs({"payload": payload}))
        candidate_index = max(len(groups) - 1, 0)
        candidate_partition_ref = owner._ref(
            RefType.RUN_INPUT,
            root_ref,
            "synthesis_reduce",
            level + 1,
            candidate_index,
        )
        candidate_fits = owner._jobs._agent_input_fits(
            state,
            **synthesis_tasks.task_input(
                kind=JobKind.GLOBAL_SYNTHESIS.value,
                root_ref=root_ref,
                partition_ref=candidate_partition_ref,
                payload=payload,
                allowed_refs=allowed,
                topic_results=(),
                independent_reviews=(),
                level=level + 1,
                final=False,
                validation_child_task_refs=[child["task_ref"] for child in candidate],
            ),
        )
        if not candidate_fits and not groups:
            raise InvalidTransitionError(
                "one synthesis child cannot fit its exact reduction task"
            )
        if groups and not candidate_fits:
            groups.append([task])
        elif groups:
            groups[-1] = candidate
        else:
            groups.append([task])
    final_level = len(groups) == 1
    if len(groups) == len(current) and len(groups) > 1 and level > 0:
        raise InvalidTransitionError(
            "synthesis hierarchy cannot reduce its task count within the exact bound"
        )
    for index, group in enumerate(groups):
        payload = owner._synthesis_reduce_payload(state, group)
        intermediate_ref = owner._ref(
            RefType.RUN_INPUT,
            root_ref,
            "synthesis_reduce",
            level + 1,
            index,
        )
        selected_final = final_level
        if final_level:
            final_input = synthesis_tasks.task_input(
                kind=JobKind.GLOBAL_SYNTHESIS.value,
                root_ref=root_ref,
                partition_ref=root_ref,
                payload=payload,
                allowed_refs=sorted(
                    owner._projection._collect_refs({"payload": payload})
                ),
                topic_results=(),
                independent_reviews=(),
                level=level + 1,
                final=True,
                validation_child_task_refs=[task["task_ref"] for task in group],
            )
            if not owner._jobs._agent_input_fits(state, **final_input):
                if level > 0:
                    raise InvalidTransitionError(
                        "synthesis hierarchy cannot compact its final task within the exact bound"
                    )
                selected_final = False
        owner._create_synthesis_task(
            state,
            root_ref=root_ref,
            partition_ref=root_ref if selected_final else intermediate_ref,
            payload=payload,
            topic_results=(),
            independent_reviews=(),
            level=level + 1,
            final=selected_final,
            validation_child_task_refs=[task["task_ref"] for task in group],
        )


def validation_results(
    owner: Any,
    state: Mapping[str, Any],
    task: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    topics, reviews = synthesis_lineage.collect_validation_results(
        owner.run_dir, state, [task]
    )
    if task["metadata"].get("hierarchy_final") is not True:
        return topics, reviews
    try:
        source_tasks = owner._accepted_final_topic_tasks(state)
    except InvalidTransitionError as exc:
        raise result_validation.ResultValidationError(str(exc)) from exc
    source_results = agent_results.copies_for_tasks(
        owner.run_dir, source_tasks, label="accepted topic"
    )
    if result_validation.build_synthesis_topic_result_commitment(topics) != (
        result_validation.build_synthesis_topic_result_commitment(source_results)
    ):
        raise result_validation.ResultValidationError(
            "synthesis topic results do not exactly match accepted final roots"
        )
    return topics, reviews


def reduce_payload(
    owner: Any,
    state: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return synthesis_lineage.build_reduce_payload(owner.run_dir, state, tasks)
