"""Parent-owned snapshots of the canonical remote transport helper."""

from __future__ import annotations

import base64
import hashlib
import hmac
import pathlib
from typing import Callable, Sequence

try:
    from . import safe_io, temporary_paths
    from .transport_contracts import TransportValidationError
    from .transport_program import (
        SOURCE_TRANSPORT_MAX_PROGRAM_COMPONENT_BYTES,
        _program_component,
    )
    from .transport_snapshot import _source_transport_external_snapshot_path
    from .transport_remote import (
        _authenticated_hosts,
        _relay_remote_host_context_command,
        _remote_helper_bootstrap_argv,
        remote_host_context_helper_commitment,
        remote_host_context_helper_component_commitment,
        remote_host_context_helper_path,
    )
except (ImportError, ModuleNotFoundError):
    import safe_io  # type: ignore[no-redef]
    import temporary_paths  # type: ignore[no-redef]
    from transport_contracts import (  # type: ignore[no-redef]
        TransportValidationError,
    )
    from transport_program import (  # type: ignore[no-redef]
        SOURCE_TRANSPORT_MAX_PROGRAM_COMPONENT_BYTES,
        _program_component,
    )
    from transport_snapshot import (  # type: ignore[no-redef]
        _source_transport_external_snapshot_path,
    )
    from transport_remote import (  # type: ignore[no-redef]
        _authenticated_hosts,
        _relay_remote_host_context_command,
        _remote_helper_bootstrap_argv,
        remote_host_context_helper_commitment,
        remote_host_context_helper_component_commitment,
        remote_host_context_helper_path,
    )


REMOTE_HOST_CONTEXT_LEGACY_COMMANDS = frozenset(
    {"fetch-rollout", "preflight", "rollout-summary", "session-meta"}
)


def snapshot_remote_host_context_helper(
    path: pathlib.Path,
    snapshot_cache: pathlib.Path,
    *,
    expected_source_commitment: str | None = None,
    stage_file: Callable[[pathlib.Path, bytes], None] | None = None,
) -> tuple[pathlib.Path, str]:
    component = _program_component(
        pathlib.Path(path),
        role="remote_host_context_helper",
        allow_missing=False,
        maximum_bytes=SOURCE_TRANSPORT_MAX_PROGRAM_COMPONENT_BYTES,
        include_content=True,
    )
    observed_source_commitment = remote_host_context_helper_component_commitment(
        component
    )
    if expected_source_commitment is not None and (
        not isinstance(expected_source_commitment, str)
        or not hmac.compare_digest(
            observed_source_commitment,
            expected_source_commitment,
        )
    ):
        raise TransportValidationError(
            "remote-host-context helper differs from the run provenance"
        )
    payload = base64.b64decode(str(component["content_b64"]), validate=True)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    snapshot_path = _source_transport_external_snapshot_path(
        pathlib.Path(snapshot_cache), digest
    )
    if stage_file is not None:
        stage_file(snapshot_path, payload)
    else:
        safe_io.ensure_owner_only_directory(snapshot_path.parent)
        safe_io.recover_atomic_create(snapshot_path)
        try:
            safe_io.atomic_create_bytes(snapshot_path, payload, create_parents=False)
        except FileExistsError:
            existing = safe_io.read_bounded_bytes(
                snapshot_path,
                max_bytes=SOURCE_TRANSPORT_MAX_PROGRAM_COMPONENT_BYTES,
                require_owner_only=True,
            )
            if not hmac.compare_digest(existing, payload):
                raise TransportValidationError(
                    "source transport external snapshot changed"
                )
    return snapshot_path, digest


def _create_legacy_helper_snapshot(
    helper: pathlib.Path,
    cache: pathlib.Path,
    expected_commitment: str,
) -> tuple[pathlib.Path, str]:
    component = _program_component(
        helper,
        role="remote_host_context_helper",
        allow_missing=False,
        include_content=True,
    )
    if not hmac.compare_digest(
        remote_host_context_helper_component_commitment(component),
        expected_commitment,
    ):
        raise TransportValidationError("remote-host-context helper snapshot changed")
    payload = base64.b64decode(str(component["content_b64"]), validate=True)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    snapshot = cache / f"remote-helper-{digest[7:]}.py"
    safe_io.atomic_create_bytes(snapshot, payload, create_parents=False)
    return snapshot, digest


def relay_remote_host_context_cli(
    arguments: Sequence[str],
    *,
    max_output_bytes: int,
) -> None:
    """Relay one bounded legacy CLI request through an owner-private snapshot."""

    normalized = tuple(arguments)
    if (
        not normalized
        or normalized[0] not in REMOTE_HOST_CONTEXT_LEGACY_COMMANDS
        or any(
            not isinstance(value, str)
            or not value
            or "\x00" in value
            or "\r" in value
            or "\n" in value
            for value in normalized
        )
    ):
        raise ValueError("remote-host-context legacy request is invalid")
    helper = remote_host_context_helper_path()
    helper_commitment = remote_host_context_helper_commitment(helper)
    with temporary_paths.owner_only_temporary_directory(
        root=temporary_paths.REMOTE_HELPER_TEMP_ROOT,
        prefix="remote-helper-",
    ) as temporary:
        snapshot_cache = temporary.path
        temporary.revalidate()
        snapshot, snapshot_commitment = _create_legacy_helper_snapshot(
            helper,
            snapshot_cache,
            helper_commitment,
        )
        temporary.revalidate()
        _inventory, runtime_commitment, _component, _commands = _authenticated_hosts(
            snapshot,
            expected_commitment=snapshot_commitment,
            content_snapshot=True,
        )
        temporary.revalidate()
        argv = _remote_helper_bootstrap_argv(
            snapshot,
            snapshot_commitment,
            runtime_commitment,
            normalized,
        )
        _relay_remote_host_context_command(argv, max_output_bytes=max_output_bytes)
        temporary.revalidate()
