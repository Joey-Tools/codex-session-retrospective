"""Bounded agent job and execution-envelope construction."""

from __future__ import annotations
import copy
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from . import (
    agent_capacity,
    agent_claim_projection,
    agent_raw_artifacts,
    agent_task_inputs,
    extracted_turns,
    result_validation,
    safe_io,
    sharding,
)
from .checkpoints import canonical_json_bytes, content_digest
from .contracts import JobKind, RefType, RunStage
from .orchestrator_context import OrchestratorComponent, RuntimeContext
from .orchestrator_protocols import JobsProjectionPort

from .orchestrator_support import (
    InvalidInputError,
    InvalidTransitionError,
    RunConflictError,
    _AGENT_INSTRUCTIONS,
    _RESULT_SCHEMA_BY_KIND,
    _json_copy,
)


_READ_SEALED_RAW_ARTIFACT = object()
_AGENT_STAGE_BY_KIND = {
    JobKind.ADJUDICATOR.value: RunStage.EPISODE_REVIEW.value,
    JobKind.EPISODE_REVIEWER.value: RunStage.EPISODE_REVIEW.value,
    JobKind.GLOBAL_SYNTHESIS.value: RunStage.GLOBAL_SYNTHESIS.value,
    JobKind.INDEPENDENT_RISK_REVIEWER.value: RunStage.EPISODE_REVIEW.value,
    JobKind.TOPIC_REDUCER.value: RunStage.TOPIC_REDUCTION.value,
}


class AgentJobOperations(OrchestratorComponent):
    def __init__(
        self,
        context: RuntimeContext,
        *,
        projection: JobsProjectionPort,
    ) -> None:
        super().__init__(context)
        self._projection = projection
        self._task_input_staging: agent_task_inputs.Staging | None = None

    @contextmanager
    def _task_input_staging_scope(
        self,
        staging: agent_task_inputs.Staging,
    ) -> Iterable[None]:
        if self._task_input_staging is not None:
            raise InvalidTransitionError("agent task input staging is already active")
        self._task_input_staging = staging
        try:
            yield
        finally:
            self._task_input_staging = None

    def _stage_run_file(self, path: Path, payload: bytes) -> None:
        if self._task_input_staging is None:
            raise InvalidTransitionError("run file staging is not active")
        self._task_input_staging.add_file(path, payload)

    def _load_extracted_turns(
        self,
        value: Mapping[str, Any],
    ) -> dict[str, dict[str, Any]]:
        return extracted_turns.load(
            self.run_dir,
            value,
            staged_files=(
                None
                if self._task_input_staging is None
                else tuple(self._task_input_staging.files)
            ),
        )

    def _task_immutable(self, task: Mapping[str, Any]) -> dict[str, Any]:
        if self._task_input_staging is not None:
            return self._task_input_staging.for_task(self.run_dir, task)
        return agent_task_inputs.for_task(self.run_dir, task)

    def _agent_envelope(
        self,
        task: Mapping[str, Any],
        attempt: Mapping[str, Any],
        *,
        raw_artifact_override: object = _READ_SEALED_RAW_ARTIFACT,
        immutable_override: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        immutable = (
            dict(immutable_override)
            if immutable_override is not None
            else self._task_immutable(task)
        )
        sink_name = str(attempt["job_ref"]).replace(":", "-") + ".json"
        output_sink = attempt.get("output_sink")
        if not isinstance(output_sink, str):
            output_sink = str(self.run_dir / "agent-sinks" / sink_name)
        public_metadata = {
            "allowed_output_refs": copy.deepcopy(immutable["allowed_refs"]),
            "attempt_ref": attempt["attempt_ref"],
            "input_digest": task["input_digest"],
            "job_ref": attempt["job_ref"],
            "output_sink": output_sink,
            "retry_ordinal": attempt["ordinal"],
            "stage": task["stage"],
            "task_ref": task["task_ref"],
        }
        if attempt.get("claim_ref") is not None:
            public_metadata.update(
                {
                    "claim_ref": attempt["claim_ref"],
                    "dispatcher_ref": attempt["dispatcher_ref"],
                    "result_ref": attempt["result_ref"],
                }
            )
        if attempt.get("reviewer_ref") is not None:
            public_metadata.update(
                {
                    "reviewer_ref": attempt["reviewer_ref"],
                    "reviewer_slot": task["metadata"]["reviewer_slot"],
                }
            )
        raw_artifact = (
            agent_raw_artifacts.sealed(
                self.run_dir,
                immutable,
                restore_manifest=self._projection._restore_shard_manifest,
            )
            if raw_artifact_override is _READ_SEALED_RAW_ARTIFACT
            else raw_artifact_override
        )
        return {
            "execution_contract": copy.deepcopy(immutable["execution_contract"]),
            "framing": copy.deepcopy(immutable["framing"]),
            "instruction": _AGENT_INSTRUCTIONS[task["job_kind"]],
            "job_manifest": copy.deepcopy(attempt["job_manifest"]),
            "payload": {
                "input_payload": copy.deepcopy(immutable["input_payload"]),
                "input_refs": copy.deepcopy(immutable["input_refs"]),
                "raw_artifact": raw_artifact,
            },
            "public_metadata": public_metadata,
            "result_contract": result_validation.agent_result_contract(
                _RESULT_SCHEMA_BY_KIND[task["job_kind"]]
            ),
            "result_schema": _RESULT_SCHEMA_BY_KIND[task["job_kind"]],
            "schema": "coordinator_agent_envelope_v2",
        }

    def _materialize_agent_result_sink(self, attempt: Mapping[str, Any]) -> None:
        output_relative = attempt.get("output_sink_relative")
        output_sink = attempt.get("output_sink")
        if (
            not isinstance(output_relative, str)
            or Path(output_relative).parts[:1] != ("agent-sinks",)
            or len(Path(output_relative).parts) != 2
            or not isinstance(output_sink, str)
            or output_sink != str(self.run_dir / output_relative)
        ):
            raise InvalidTransitionError("agent result sink binding is invalid")
        output_path = self.run_dir / output_relative
        try:
            safe_io.ensure_owner_only_directory(output_path.parent)
            safe_io.atomic_create_bytes(
                output_path,
                b"",
                create_parents=False,
            )
        except FileExistsError:
            try:
                safe_io.check_owner_only_file(output_path)
            except (OSError, safe_io.UnsafePathError) as error:
                raise InvalidTransitionError(
                    "agent result sink cannot be authenticated"
                ) from error
        except (OSError, safe_io.UnsafePathError) as error:
            raise InvalidTransitionError(
                "agent result sink cannot be materialized"
            ) from error

    def _agent_input_fits(
        self,
        state: Mapping[str, Any],
        *,
        kind: str,
        input_payload: Mapping[str, Any] | None,
        input_refs: Iterable[str],
        allowed_refs: Iterable[str],
        allowed_turn_refs: Iterable[str] = (),
        host_refs: Iterable[str] = (),
        raw_artifact: str | None = None,
        raw_manifest: Mapping[str, Any] | None = None,
        framing: Mapping[str, Any] | None = None,
        reviewer_slot: Any = None,
        candidate_result_hashes: Iterable[str] = (),
        safety_review_hashes: Iterable[str] = (),
    ) -> bool:
        projected_metadata = {
            "candidate_result_hashes": list(candidate_result_hashes),
            "reviewer_slot": reviewer_slot,
            "safety_review_hashes": list(safety_review_hashes),
        }
        immutable = self._build_agent_task_immutable(
            state,
            stage=_AGENT_STAGE_BY_KIND[kind],
            kind=kind,
            partition_ref="run_input_ref_v2:" + "0" * 64,
            input_refs=input_refs,
            input_payload=input_payload,
            allowed_refs=allowed_refs,
            allowed_turn_refs=allowed_turn_refs,
            host_refs=host_refs,
            metadata=projected_metadata,
            raw_manifest=raw_manifest,
            raw_artifact=raw_artifact,
            framing=framing,
        )
        immutable_digest = content_digest(immutable)
        task_ref = self._ref(
            RefType.RUN_INPUT,
            state["run_ref"],
            "agent_task",
            immutable_digest,
        )
        input_digest = content_digest(
            {
                "input_payload": immutable["input_payload"],
                "input_refs": immutable["input_refs"],
                "raw_manifest": immutable["raw_manifest"],
            }
        )
        task = {
            "input_digest": input_digest,
            "job_kind": kind,
            "metadata": agent_task_inputs.checkpoint_metadata(immutable["metadata"]),
            "partition_ref": immutable["partition_ref"],
            "stage": immutable["stage"],
            "task_ref": task_ref,
        }
        return (
            len(
                canonical_json_bytes(
                    self._project_agent_envelope(
                        state,
                        task,
                        ordinal=1,
                        immutable_override=immutable,
                    )
                )
            )
            <= self._agent_envelope_limit()
        )

    def _build_agent_task_immutable(
        self,
        state: Mapping[str, Any],
        *,
        stage: str,
        kind: str,
        partition_ref: str,
        input_refs: Iterable[str],
        input_payload: Mapping[str, Any] | None,
        allowed_refs: Iterable[str],
        allowed_turn_refs: Iterable[str] = (),
        host_refs: Iterable[str] = (),
        metadata: Mapping[str, Any] | None = None,
        raw_manifest: Mapping[str, Any] | None = None,
        raw_artifact: str | None = None,
        framing: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "allowed_refs": sorted(set(allowed_refs)),
            "allowed_turn_refs": sorted(set(allowed_turn_refs)),
            "execution_contract": self._projection._execution_contract(state),
            "framing": _json_copy(dict(framing or {}), label="task framing"),
            "host_refs": sorted(set(host_refs)),
            "input_payload": (
                None
                if input_payload is None
                else _json_copy(dict(input_payload), label="task input payload")
            ),
            "input_refs": sorted(set(input_refs)),
            "job_kind": kind,
            "metadata": _json_copy(dict(metadata or {}), label="task metadata"),
            "partition_ref": partition_ref,
            "raw_artifact": raw_artifact,
            "raw_manifest": (
                None
                if raw_manifest is None
                else _json_copy(dict(raw_manifest), label="raw shard manifest")
            ),
            "stage": stage,
        }

    def _create_agent_task(
        self,
        state: dict[str, Any],
        *,
        stage: str,
        kind: str,
        partition_ref: str,
        input_refs: Sequence[str],
        input_payload: Mapping[str, Any] | None,
        allowed_refs: Iterable[str],
        allowed_turn_refs: Iterable[str] = (),
        host_refs: Iterable[str] = (),
        metadata: Mapping[str, Any] | None = None,
        raw_manifest: Mapping[str, Any] | None = None,
        raw_artifact: str | None = None,
        framing: Mapping[str, Any] | None = None,
    ) -> str:
        immutable = self._build_agent_task_immutable(
            state,
            stage=stage,
            kind=kind,
            partition_ref=partition_ref,
            input_refs=input_refs,
            input_payload=input_payload,
            allowed_refs=allowed_refs,
            allowed_turn_refs=allowed_turn_refs,
            host_refs=host_refs,
            metadata=metadata,
            raw_manifest=raw_manifest,
            raw_artifact=raw_artifact,
            framing=framing,
        )
        immutable_digest = content_digest(immutable)
        task_ref = self._ref(
            RefType.RUN_INPUT,
            state["run_ref"],
            "agent_task",
            immutable_digest,
        )
        existing = state["jobs"].get(task_ref)
        if existing is not None:
            if existing.get("immutable_digest") != immutable_digest:
                raise RunConflictError("deterministic task reference collision")
            reuse_count = existing.get("cache_reuse_count", 0)
            if (
                not isinstance(reuse_count, int)
                or isinstance(reuse_count, bool)
                or reuse_count < 0
            ):
                raise RunConflictError("agent task cache reuse count is invalid")
            metrics = state.setdefault("metrics", {})
            metrics["agent_task_cache_hits"] = (
                metrics.get("agent_task_cache_hits", 0) + 1
            )
            metrics["agent_task_reuses"] = metrics.get("agent_task_reuses", 0) + 1
            existing["cache_reuse_count"] = reuse_count + 1
            return task_ref
        metrics = state.setdefault("metrics", {})
        reservation = agent_capacity.reserve(state, kind)
        if self._task_input_staging is None:
            raise InvalidTransitionError("agent task input staging is not active")
        task_input_artifact = self._task_input_staging.prepare(
            self.run_dir,
            task_ref=task_ref,
            immutable=immutable,
            immutable_digest=immutable_digest,
        )
        task = {
            "active_attempt_ref": None,
            "active_job_ref": None,
            "attempts": [],
            "cache_reuse_count": 0,
            "category": "agent",
            "immutable_digest": immutable_digest,
            "input_digest": content_digest(
                {
                    "input_payload": immutable["input_payload"],
                    "input_refs": immutable["input_refs"],
                    "raw_manifest": immutable["raw_manifest"],
                }
            ),
            "host_refs": immutable["host_refs"],
            "job_kind": immutable["job_kind"],
            "metadata": agent_task_inputs.checkpoint_metadata(immutable["metadata"]),
            "partition_ref": immutable["partition_ref"],
            "stage": immutable["stage"],
            "status": "pending",
            "task_input_artifact": task_input_artifact,
            "task_ref": task_ref,
        }
        projected_envelope = self._project_agent_envelope(
            state,
            task,
            ordinal=1,
            immutable_override=immutable,
        )
        if len(canonical_json_bytes(projected_envelope)) > self._agent_envelope_limit():
            raise InvalidInputError("agent task exceeds the complete 512 KiB envelope")
        agent_capacity.validate_checkpoint_task(task)
        state["jobs"][task_ref] = task
        reservation.commit(metrics)
        return task_ref

    def _execution_manifest(
        self,
        state: Mapping[str, Any],
        task: Mapping[str, Any],
        retry_ordinal: int,
        *,
        immutable_override: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        kind = task["job_kind"]
        immutable = (
            dict(immutable_override)
            if immutable_override is not None
            else self._task_immutable(task)
        )
        execution_contract = copy.deepcopy(immutable["execution_contract"])
        if kind == JobKind.EXTRACTOR_REDACTOR.value:
            shard_manifest = self._projection._restore_shard_manifest(
                immutable["raw_manifest"]
            )
            framing = canonical_json_bytes(immutable["framing"])
            generated = sharding.build_job_manifest(
                shard_manifest,
                job_kind=JobKind.EXTRACTOR_REDACTOR,
                prompt_version=self._projection._version_token(
                    state, "prompt", "extractor_v2"
                ),
                result_schema_version=result_validation.EXTRACTOR_RESULT_SCHEMA,
                policy_version=self._projection._policy_token(
                    state, "policy", "source_policy_v2"
                ),
                framing=framing,
                job_key=self.identity,
                retry_ordinal=retry_ordinal,
            ).to_dict()
            body = {key: value for key, value in generated.items() if key != "job_ref"}
            body.update(
                {
                    "execution_contract": execution_contract,
                    "allowed_output_refs": copy.deepcopy(immutable["allowed_refs"]),
                    "result_schema": result_validation.EXTRACTOR_RESULT_SCHEMA,
                    "task_ref": task["task_ref"],
                }
            )
            return {
                "job_ref": self._ref(RefType.JOB, state["run_ref"], body),
                **body,
            }
        body = {
            "allowed_output_refs": copy.deepcopy(immutable["allowed_refs"]),
            "candidate_result_hashes": copy.deepcopy(
                task["metadata"].get("candidate_result_hashes", [])
            ),
            "input_digest": task["input_digest"],
            "input_refs": copy.deepcopy(immutable["input_refs"]),
            "execution_contract": execution_contract,
            "job_kind": kind,
            "result_schema": _RESULT_SCHEMA_BY_KIND[kind],
            "retry_ordinal": retry_ordinal,
            "schema": "coordinator_agent_job_v2",
            "safety_review_hashes": copy.deepcopy(
                task["metadata"].get("safety_review_hashes", [])
            ),
            "task_ref": task["task_ref"],
        }
        job_ref = self._ref(RefType.JOB, state["run_ref"], body)
        return {"job_ref": job_ref, **body}

    def _project_agent_envelope(
        self,
        state: Mapping[str, Any],
        task: Mapping[str, Any],
        *,
        ordinal: int,
        immutable_override: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        immutable = (
            dict(immutable_override)
            if immutable_override is not None
            else self._task_immutable(task)
        )
        job_manifest = self._execution_manifest(
            state,
            task,
            ordinal,
            immutable_override=immutable,
        )
        job_ref = job_manifest["job_ref"]
        attempt_ref = self._ref(
            RefType.ATTEMPT,
            state["run_ref"],
            job_ref,
            ordinal,
        )
        reviewer_slot = task["metadata"].get("reviewer_slot")
        projected_attempt = agent_claim_projection.projected_attempt(
            run_dir=self.run_dir,
            run_ref=state["run_ref"],
            job_ref=job_ref,
            attempt_ref=attempt_ref,
            ordinal=ordinal,
            partition_ref=task["partition_ref"],
            reviewer_slot=reviewer_slot,
            derive_ref=self._ref,
        )
        projected_attempt["job_manifest"] = job_manifest
        return self._agent_envelope(
            task,
            projected_attempt,
            raw_artifact_override=agent_raw_artifacts.projected(
                immutable,
                restore_manifest=self._projection._restore_shard_manifest,
            ),
            immutable_override=immutable,
        )
