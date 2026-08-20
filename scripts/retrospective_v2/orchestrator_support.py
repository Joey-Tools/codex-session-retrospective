"""Shared source-frame, readiness, and contract foundations for the v2 coordinator."""

from __future__ import annotations

import os
from pathlib import Path
import selectors
import subprocess
import time
from typing import Any, Mapping, Sequence

from . import (
    executable_authority,
    finalize,
    gpg_status,
    implementation_authority,
    process_lifecycle,
    publication_support,
    result_validation,
    safe_io,
    sharding,
    temporary_paths,
    transport as source_transport,
)
from .checkpoints import CheckpointIntegrityError, content_digest
from .contracts import JobKind
from .transport_host_inventory import AuthenticatedHostInventory

# Compatibility re-exports for callers that historically imported from this module.
from .orchestrator_core import (  # noqa: F401
    DEFAULT_AGENT_CLAIM_TTL_SECONDS,
    ENGINE_VERSION,
    EXTRACTOR_SHARD_MAX_BYTES,
    InvalidInputError,
    InvalidTransitionError,
    MAX_BASELINE_WINDOW_DAYS,
    MAX_EXPORT_RETENTION_HOURS,
    MAX_AGENT_CLAIM_TTL_SECONDS,
    MAX_AGENT_CLAIM_GENERATIONS,
    MAX_AGENT_ENVELOPE_BYTES,
    MAX_RETENTION_DAYS,
    MIN_AGENT_CLAIM_TTL_SECONDS,
    LEGACY_SHADOW_CLEANUP_ROOTS,
    RAW_INPUT_DIRECTORY,
    RAW_SHARD_DIRECTORY,
    REQUIRED_SOURCE_KINDS,
    STATE_SCHEMA_VERSION,
    SHADOW_CLEANUP_ROOTS,
    OrchestratorError,
    RunConflictError,
    RunNotStartedError,
    _NON_GAP_SOURCE_TERMINAL,
    _OPAQUE_REF_RE,
    _PUBLICATION_ATTEMPT_RE,
    _SAFE_ERA_RE,
    _SAFE_REASON_RE,
    _SHA256_RE,
    _SOURCE_TERMINAL,
    _STAGE_SEQUENCE,
    _TASK_TERMINAL,
    _KEY_ID_RE,
    _as_mapping,
    _format_timestamp,
    _json_copy,
    _normalize_hosts,
    _normalize_source_kinds,
    _normalize_timestamp,
    _parse_timestamp,
    _safe_reason,
)
from .orchestrator_execution_contract import (  # noqa: F401
    EXECUTION_CONTRACT_SCHEMA,
    EXECUTION_VERSION_CONTRACT,
    PROMPT_DIGEST,
    PROMPT_VERSION,
    _AGENT_INSTRUCTIONS,
    _require_current_execution_contract as _require_bound_execution_contract,
)
from .orchestrator_transport import (  # noqa: F401
    MAX_SESSION_SHARDS_RECORD_DATA_FRAMES,
    SESSION_SHARDS_CONSERVATION_SCHEMA,
    SESSION_SHARDS_FIXED_MEMORY_ENVELOPE_BYTES,
    SESSION_SHARDS_MAX_FRAME_CHARS,
    SESSION_SHARDS_MAX_JSON_NESTING_DEPTH,
    SESSION_SHARDS_PROTOCOL_FEATURES,
    SESSION_SHARDS_RECORD_FRAGMENT_BYTES,
    SOURCE_TRANSPORT_MAX_FRAME_BYTES,
    SOURCE_TRANSPORT_MAX_RECORDS,
    SOURCE_TRANSPORT_MAX_SOURCE_BYTES,
    SessionShardConsumption,
    SourcePreparation,
    _SessionShardStreamConsumer,
    _SOURCE_TOKEN_RE,
    _argv_option,
    _content_commitment,
    _decode_transport_payload,
    _frame_integer,
    _require_frame_keys,
    _source_record_pairs,
    _source_session_identifiers,
    _strict_source_record,
    _transport_accounting_bytes,
    consume_session_shard_frames,
)

PUBLISHER_FINGERPRINT = finalize.DEFAULT_PUBLISHER_FINGERPRINT
PUBLISHER_GNUPG_HOME = finalize.DEFAULT_PUBLISHER_GNUPG_HOME
PUBLISHER_UID = finalize.DEFAULT_PUBLISHER_UID
_RESULT_SCHEMA_BY_KIND = {
    JobKind.EXTRACTOR_REDACTOR.value: result_validation.EXTRACTOR_RESULT_SCHEMA,
    JobKind.EPISODE_REVIEWER.value: result_validation.EPISODE_REVIEW_RESULT_SCHEMA,
    JobKind.INDEPENDENT_RISK_REVIEWER.value: (
        result_validation.EPISODE_REVIEW_RESULT_SCHEMA
    ),
    JobKind.ADJUDICATOR.value: result_validation.ADJUDICATION_RESULT_SCHEMA,
    JobKind.TOPIC_REDUCER.value: result_validation.TOPIC_RESULT_SCHEMA,
    JobKind.GLOBAL_SYNTHESIS.value: result_validation.SYNTHESIS_RESULT_SCHEMA,
}

_MODEL_PARAMETER_KEYS = frozenset(
    {"reasoning_effort", "seed", "service_tier", "temperature", "top_p"}
)
_REASONING_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max", "ultra"})
_SERVICE_TIERS = frozenset({"default", "flex", "priority"})


def _current_coordinator_runtime() -> dict[str, Any]:
    try:
        return source_transport.source_transport_python_runtime_readiness()
    except (OSError, source_transport.TransportValidationError) as error:
        raise InvalidTransitionError(
            "coordinator Python runtime authority cannot be authenticated"
        ) from error


def _current_coordinator_implementation() -> dict[str, Any]:
    try:
        return implementation_authority.coordinator_implementation_readiness()
    except (OSError, implementation_authority.ImplementationAuthorityError) as error:
        raise InvalidTransitionError(
            "coordinator implementation authority cannot be authenticated"
        ) from error


def _require_current_execution_contract(
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    return _require_bound_execution_contract(
        provenance,
        current_implementation=_current_coordinator_implementation(),
        current_runtime=_current_coordinator_runtime(),
    )


def _build_provenance(
    *,
    provenance: Mapping[str, Any] | None,
    policy: Mapping[str, Any] | str | None,
    model: Mapping[str, Any] | str | None,
    versions: Mapping[str, Any] | None,
    authenticated_host_inventory: AuthenticatedHostInventory,
) -> dict[str, Any]:
    if any(value is not None for value in (policy, model, versions)):
        raise InvalidInputError("legacy free-form provenance fields are not accepted")
    supplied = _as_mapping(provenance, label="execution provenance")
    if set(supplied) != {"model", "prompt", "schema", "transport", "versions"}:
        raise InvalidInputError("execution provenance must use the closed v2 contract")
    if supplied.get("schema") != EXECUTION_CONTRACT_SCHEMA:
        raise InvalidInputError("execution provenance schema is incompatible")

    model_value = supplied.get("model")
    if not isinstance(model_value, Mapping) or set(model_value) != {
        "model",
        "parameters",
        "provider",
    }:
        raise InvalidInputError("model provenance has an unexpected shape")
    provider = model_value.get("provider")
    model_name = model_value.get("model")
    if any(
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 128
        or any(ord(character) < 0x21 for character in value)
        for value in (provider, model_name)
    ):
        raise InvalidInputError("model provider and name must be explicit tokens")
    parameters = model_value.get("parameters")
    if (
        not isinstance(parameters, Mapping)
        or not set(parameters) <= _MODEL_PARAMETER_KEYS
    ):
        raise InvalidInputError("model parameters are outside the closed contract")
    if set(parameters) != {"reasoning_effort", "service_tier"}:
        raise InvalidInputError(
            "model reasoning_effort and service_tier must be explicit"
        )
    if parameters.get("reasoning_effort") not in _REASONING_EFFORTS:
        raise InvalidInputError("model reasoning_effort is invalid")
    if parameters.get("service_tier") not in _SERVICE_TIERS:
        raise InvalidInputError("model service_tier is invalid")

    prompt_value = supplied.get("prompt")
    if not isinstance(prompt_value, Mapping) or set(prompt_value) != {
        "digest",
        "version",
    }:
        raise InvalidInputError("prompt provenance has an unexpected shape")
    if (
        prompt_value.get("version") != PROMPT_VERSION
        or prompt_value.get("digest") != PROMPT_DIGEST
    ):
        raise InvalidInputError(
            "prompt provenance does not match the executable instructions"
        )

    versions_value = supplied.get("versions")
    if (
        not isinstance(versions_value, Mapping)
        or dict(versions_value) != EXECUTION_VERSION_CONTRACT
    ):
        raise InvalidInputError(
            "policy, redaction, detector, segmentation, or schema version is incompatible"
        )
    transport_value = supplied.get("transport")
    if not isinstance(transport_value, Mapping) or set(transport_value) != {
        "remote_host_context_helper_commitment",
        "source_transport_schema",
    }:
        raise InvalidInputError("source transport provenance has an unexpected shape")
    try:
        runtime_value = source_transport.source_transport_python_runtime_readiness()
    except (OSError, source_transport.TransportValidationError) as error:
        raise InvalidInputError(
            "coordinator Python runtime authority is incompatible"
        ) from error
    try:
        implementation_value = (
            implementation_authority.coordinator_implementation_readiness()
        )
    except (OSError, implementation_authority.ImplementationAuthorityError) as error:
        raise InvalidInputError(
            "coordinator implementation authority is incompatible"
        ) from error
    helper_commitment = authenticated_host_inventory.helper_commitment
    if not source_transport.REMOTE_HOST_CONTEXT_RETROSPECTIVE_COMMANDS.issubset(
        authenticated_host_inventory.helper_commands
    ):
        raise InvalidInputError(
            "remote-host-context helper lacks required retrospective capabilities"
        )
    if (
        transport_value.get("remote_host_context_helper_commitment")
        != helper_commitment
        or transport_value.get("source_transport_schema")
        != source_transport.SOURCE_TRANSPORT_STREAM_SCHEMA
    ):
        raise InvalidInputError(
            "source transport or remote-host-context helper commitment changed"
        )
    result = {
        "host_inventory": authenticated_host_inventory.inventory.to_dict(),
        "host_inventory_commitment": (
            authenticated_host_inventory.inventory_commitment
        ),
        "implementation": _json_copy(
            implementation_value, label="coordinator implementation provenance"
        ),
        "model": _json_copy(dict(model_value), label="model provenance"),
        "prompt": _json_copy(dict(prompt_value), label="prompt provenance"),
        "runtime": _json_copy(runtime_value, label="coordinator runtime provenance"),
        "schema": EXECUTION_CONTRACT_SCHEMA,
        "transport": _json_copy(
            dict(transport_value), label="source transport provenance"
        ),
        "versions": _json_copy(dict(versions_value), label="version provenance"),
    }
    result["configuration_root"] = content_digest(result)
    return result


def _checkpoint_key_id(run_dir: Path) -> str | None:
    checkpoint = run_dir / "checkpoint.json"
    try:
        envelope = safe_io.read_bounded_json(
            checkpoint,
            max_bytes=sharding.DEFAULT_RECORD_PROCESSING_BUDGET,
            require_owner_only=True,
        )
    except FileNotFoundError:
        return None
    if not isinstance(envelope, Mapping):
        raise CheckpointIntegrityError("checkpoint envelope must be an object")
    key_id = envelope.get("key_id")
    if not isinstance(key_id, str) or _KEY_ID_RE.fullmatch(key_id) is None:
        raise CheckpointIntegrityError("checkpoint key_id is invalid")
    return key_id


def _decode_gpg_colon_field(value: str) -> str:
    output = bytearray()
    index = 0
    while index < len(value):
        if value[index : index + 2] == "\\x" and index + 4 <= len(value):
            try:
                output.append(int(value[index + 2 : index + 4], 16))
            except ValueError:
                output.extend(value[index].encode("ascii"))
                index += 1
                continue
            index += 4
            continue
        output.extend(value[index].encode("utf-8"))
        index += 1
    return output.decode("utf-8")


def publisher_readiness(
    *,
    gnupg_home: str | os.PathLike[str] = PUBLISHER_GNUPG_HOME,
    fingerprint: str = PUBLISHER_FINGERPRINT,
    expected_uid: str = PUBLISHER_UID,
    gpg_program: str | os.PathLike[str] = executable_authority.DEFAULT_GPG_EXECUTABLE,
) -> dict[str, Any]:
    """Inspect only the dedicated publication keyring and return safe metadata."""

    safe_result = {"fingerprint": PUBLISHER_FINGERPRINT, "ready": False}
    if fingerprint != PUBLISHER_FINGERPRINT or expected_uid != PUBLISHER_UID:
        return safe_result
    try:
        identity = finalize.validate_publisher_keyring(
            gnupg_home=gnupg_home,
            fingerprint=fingerprint,
            expected_uid=expected_uid,
            gpg_program=gpg_program,
        )
    except finalize.LocalGitPublicationError as error:
        process_lifecycle.raise_if_incomplete_process_group_cleanup(error)
        return safe_result
    safe_result["ready"] = identity.get("fingerprint") == PUBLISHER_FINGERPRINT
    return safe_result


_PUBLISHER_CANARY_TIMEOUT_SECONDS = 15.0
_PUBLISHER_CANARY_STREAM_LIMIT_BYTES = 1024 * 1024
_PUBLISHER_CANARY_READ_CHUNK_BYTES = 64 * 1024
_PUBLISHER_CANARY_CLEANUP_SECONDS = 1.0


class _PublisherCanaryProcessError(RuntimeError):
    """Raised when a canary subprocess violates its execution envelope."""


def _run_bounded_publisher_canary_process(
    command: Sequence[str],
    *,
    environment: Mapping[str, str],
    timeout_seconds: float = _PUBLISHER_CANARY_TIMEOUT_SECONDS,
    max_stdout_bytes: int = _PUBLISHER_CANARY_STREAM_LIMIT_BYTES,
    max_stderr_bytes: int = _PUBLISHER_CANARY_STREAM_LIMIT_BYTES,
) -> subprocess.CompletedProcess[bytes]:
    """Capture a canary process without exceeding either stream envelope."""

    if timeout_seconds <= 0 or max_stdout_bytes <= 0 or max_stderr_bytes <= 0:
        raise ValueError("publisher canary bounds must be positive")
    try:
        process = subprocess.Popen(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(environment),
            close_fds=True,
            start_new_session=os.name == "posix",
        )
    except OSError as error:
        raise _PublisherCanaryProcessError(
            "cannot start publisher canary process"
        ) from error

    selector: selectors.BaseSelector | None = None
    stdout = bytearray()
    stderr = bytearray()
    deadline = time.monotonic() + timeout_seconds
    signal_retirement = process_lifecycle.GroupSignalRetirement()
    active_error: BaseException | None = None

    def close_process_group(
        child: subprocess.Popen[bytes], *, cleanup_deadline: float
    ) -> int:
        remaining = cleanup_deadline - time.monotonic()
        if remaining <= 0:
            raise _PublisherCanaryProcessError(
                "publisher canary process group cleanup exceeded its deadline"
            )
        return process_lifecycle.close_process_group(
            child,
            signal_retirement=signal_retirement,
            timeout_seconds=remaining,
            error_type=_PublisherCanaryProcessError,
            label="publisher canary",
            termination_message="publisher canary leader could not be reaped",
        )

    def reap_process_group(child: subprocess.Popen[bytes]) -> int:
        return process_lifecycle.reap_after_termination(
            child,
            timeout_seconds=_PUBLISHER_CANARY_CLEANUP_SECONDS,
            error_type=_PublisherCanaryProcessError,
            error_message="publisher canary leader could not be reaped",
        )

    try:
        if process.stdout is None or process.stderr is None:
            raise _PublisherCanaryProcessError(
                "publisher canary process streams are unavailable"
            )
        selector = selectors.DefaultSelector()
        for stream, target, limit in (
            (process.stdout, stdout, max_stdout_bytes),
            (process.stderr, stderr, max_stderr_bytes),
        ):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, (target, limit))

        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _PublisherCanaryProcessError(
                    "publisher canary process exceeded its deadline"
                )
            try:
                events = selector.select(min(remaining, 0.1))
            except InterruptedError:
                continue
            for key, _mask in events:
                stream = key.fileobj
                target, limit = key.data
                available = limit - len(target)
                try:
                    chunk = os.read(
                        stream.fileno(),
                        min(_PUBLISHER_CANARY_READ_CHUNK_BYTES, available + 1),
                    )
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                if len(chunk) > available:
                    raise _PublisherCanaryProcessError(
                        "publisher canary process exceeded a stream limit"
                    )
                target.extend(chunk)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _PublisherCanaryProcessError(
                "publisher canary process exceeded its deadline"
            )
        process_lifecycle.wait_for_unreaped_exit(
            process,
            deadline=deadline,
            error_type=_PublisherCanaryProcessError,
            deadline_message="publisher canary process exceeded its deadline",
            status_message="publisher canary leader status could not be observed",
        )
        return_code = close_process_group(process, cleanup_deadline=deadline)
        return subprocess.CompletedProcess(
            args=list(command),
            returncode=return_code,
            stdout=bytes(stdout),
            stderr=bytes(stderr),
        )
    except BaseException as error:
        active_error = error
        raise
    finally:
        resource_closers = tuple(
            closer
            for closer in (
                None if selector is None else selector.close,
                None if process.stdout is None else process.stdout.close,
                None if process.stderr is None else process.stderr.close,
            )
            if closer is not None
        )
        process_lifecycle.finish_cleanup_after_resource_teardown(
            process,
            resource_closers=resource_closers,
            resource_label="publisher canary resource teardown",
            signal_retirement=signal_retirement,
            terminate_and_reap=lambda child: close_process_group(
                child,
                cleanup_deadline=(time.monotonic() + _PUBLISHER_CANARY_CLEANUP_SECONDS),
            ),
            reap_only=reap_process_group,
            active_error=active_error,
        )


def publisher_sign_verify_canary(
    *,
    gnupg_home: str | os.PathLike[str] = PUBLISHER_GNUPG_HOME,
    fingerprint: str = PUBLISHER_FINGERPRINT,
    gpg_program: str | os.PathLike[str] = executable_authority.DEFAULT_GPG_EXECUTABLE,
) -> bool:
    """Sign and verify one temporary payload with only the dedicated keyring."""

    if fingerprint != PUBLISHER_FINGERPRINT:
        return False
    home = Path(gnupg_home).expanduser().absolute()
    environment = publication_support._strict_subprocess_environment(home=home)
    environment["GNUPGHOME"] = str(home)
    try:
        gpg_authority = executable_authority.resolve_executable(
            gpg_program,
            label="GPG",
        )
        with temporary_paths.owner_only_temporary_directory(
            root=temporary_paths.PUBLISHER_CANARY_TEMP_ROOT,
            prefix="retrospective-publisher-canary-",
        ) as temporary:
            directory = temporary.path
            temporary.revalidate()
            environment["TEMP"] = environment["TMP"] = environment["TMPDIR"] = str(
                directory
            )
            payload = directory / "payload"
            signature = directory / "payload.sig"
            safe_io.atomic_create_bytes(
                payload, b"session-retrospective-publisher-canary-v2\n"
            )
            temporary.revalidate()
            with executable_authority.executable_invocation(gpg_authority):
                signed = _run_bounded_publisher_canary_process(
                    gpg_status.no_options_argv(
                        gpg_authority.path,
                        "--homedir",
                        str(home),
                        "--batch",
                        "--yes",
                        "--local-user",
                        fingerprint,
                        "--detach-sign",
                        "--output",
                        str(signature),
                        str(payload),
                    ),
                    environment=environment,
                )
            temporary.revalidate()
            if signed.returncode != 0 or not signature.is_file():
                return False
            temporary.harden_file(signature.name)
            with executable_authority.executable_invocation(gpg_authority):
                verified = _run_bounded_publisher_canary_process(
                    gpg_status.no_options_argv(
                        gpg_authority.path,
                        "--homedir",
                        str(home),
                        "--batch",
                        "--status-fd",
                        "1",
                        "--verify",
                        str(signature),
                        str(payload),
                    ),
                    environment=environment,
                )
            temporary.revalidate()
    except (
        OSError,
        _PublisherCanaryProcessError,
        executable_authority.ExecutableAuthorityError,
    ) as error:
        process_lifecycle.raise_if_incomplete_process_group_cleanup(error)
        return False
    if verified.returncode != 0:
        return False
    try:
        valid = gpg_status.validsig_primary_fingerprints(verified.stdout)
    except ValueError:
        return False
    return valid == [fingerprint.upper()]
