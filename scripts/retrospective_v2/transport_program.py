"""Closed executable commitment for the private source transport worker."""

from __future__ import annotations

import base64
import hashlib
import os
import pathlib
import sys
import tempfile
from typing import Callable, Mapping, Sequence

try:
    from . import executable_authority
    from .contracts import JsonValue
    from .transport_contracts import SOURCE_TRANSPORT_WORKER_MODULE_MANIFEST
    from .transport_contracts import TransportValidationError, _canonical_commitment
    from .transport_program_components import (
        SOURCE_TRANSPORT_MAX_PROGRAM_COMPONENT_BYTES,
        _package_program_components,
        _program_component,
    )
except (ImportError, ModuleNotFoundError):
    import executable_authority  # type: ignore[no-redef]
    from contracts import JsonValue  # type: ignore[no-redef]
    from transport_contracts import (  # type: ignore[no-redef]
        SOURCE_TRANSPORT_WORKER_MODULE_MANIFEST,
        TransportValidationError,
        _canonical_commitment,
    )
    from transport_program_components import (  # type: ignore[no-redef]
        SOURCE_TRANSPORT_MAX_PROGRAM_COMPONENT_BYTES,
        _package_program_components,
        _program_component,
    )

SOURCE_TRANSPORT_MAX_INTERPRETER_BYTES = 64 * 1024 * 1024
SOURCE_TRANSPORT_BASE_PYTHON_FLAGS = (
    "-I",
    "-B",
    "-S",
    "-X",
    f"pycache_prefix={os.devnull}",
)
SOURCE_TRANSPORT_SNAPSHOT_SCHEMA = "source_transport_worker_snapshot_v2"
SOURCE_TRANSPORT_MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024
SOURCE_TRANSPORT_SNAPSHOT_CACHE = pathlib.Path(tempfile.gettempdir()) / (
    f"codex-session-retrospective-v2-program-{os.getuid()}"
)


def _python_executable_authority(
    executable: str | os.PathLike[str] | None = None,
) -> executable_authority.ExecutableAuthority:
    selected = pathlib.Path(sys.executable if executable is None else executable)
    resolved = pathlib.Path(os.path.realpath(selected))
    try:
        authority = executable_authority.resolve_executable(
            resolved,
            label="source transport Python",
        )
    except executable_authority.ExecutableAuthorityError as exc:
        raise TransportValidationError(
            "source transport Python executable path authority cannot be authenticated"
        ) from exc
    if authority.path != str(resolved):
        raise TransportValidationError(
            "source transport Python executable path authority changed"
        )
    return authority


def _path_object_authority_receipt(
    authority: executable_authority.PathObjectAuthority,
) -> dict[str, JsonValue]:
    return {
        "acl_sha256": "sha256:" + authority.acl_sha256,
        "device": authority.device,
        "group": authority.group,
        "inode": authority.inode,
        "mode": authority.mode,
        "owner": authority.owner,
        "path": authority.path,
    }


def _python_executable_authority_receipt(
    authority: executable_authority.ExecutableAuthority,
) -> dict[str, JsonValue]:
    return {
        "ancestors": [
            _path_object_authority_receipt(ancestor) for ancestor in authority.ancestors
        ],
        "authority_sha256": "sha256:"
        + executable_authority.authority_digest(authority),
        "content_sha256": "sha256:" + authority.sha256,
        "executable": _path_object_authority_receipt(authority.executable),
        "path": authority.path,
        "schema": "source_transport_python_executable_authority_v1",
        "size": authority.size,
    }


def _python_runtime_snapshot(
    authority: executable_authority.ExecutableAuthority,
) -> dict[str, JsonValue]:
    resolved = pathlib.Path(authority.path)
    return {
        "component": _program_component(
            resolved,
            role="python_interpreter",
            allow_missing=False,
            maximum_bytes=SOURCE_TRANSPORT_MAX_INTERPRETER_BYTES,
        ),
        "executable": str(resolved),
        "implementation": sys.implementation.name,
        "schema": "source_transport_python_runtime_v1",
        "version": list(sys.version_info),
    }


def _python_runtime_authority(
    executable: str | os.PathLike[str] | None = None,
) -> dict[str, JsonValue]:
    return _python_runtime_snapshot(_python_executable_authority(executable))


def _program_snapshot_protocol():
    try:
        from . import transport_snapshot
    except ImportError:
        import transport_snapshot  # type: ignore[no-redef]
    return transport_snapshot


def source_transport_python_command(
    snapshot_cache: pathlib.Path | None = None,
    *,
    stage_file: Callable[[pathlib.Path, bytes], None] | None = None,
    executable: str | os.PathLike[str] | None = None,
) -> tuple[str, ...]:
    python_authority = _python_executable_authority(executable)
    python_runtime = _python_runtime_snapshot(python_authority)
    package_dir = pathlib.Path(
        os.path.abspath(os.fspath(pathlib.Path(__file__).parent))
    )
    return (
        str(python_runtime["executable"]),
        *_program_snapshot_protocol()._source_transport_snapshot_flags(
            package_dir=package_dir,
            components=_package_program_components(package_dir, include_content=True),
            module_manifest=SOURCE_TRANSPORT_WORKER_MODULE_MANIFEST,
            python_executable_authority=_python_executable_authority_receipt(
                python_authority
            ),
            python_runtime=python_runtime,
            base_flags=SOURCE_TRANSPORT_BASE_PYTHON_FLAGS,
            schema=SOURCE_TRANSPORT_SNAPSHOT_SCHEMA,
            cache=pathlib.Path(snapshot_cache or SOURCE_TRANSPORT_SNAPSHOT_CACHE),
            maximum_bytes=SOURCE_TRANSPORT_MAX_SNAPSHOT_BYTES,
            stage_file=stage_file,
        ),
    )


def _decode_program_snapshot(
    argv: tuple[str, ...],
    *,
    snapshot_cache: pathlib.Path,
    prepared_files: Mapping[pathlib.Path, bytes] | None = None,
    recover: bool = True,
) -> tuple[dict[str, JsonValue], int, str]:
    if not argv:
        raise TransportValidationError("source transport command is incomplete")
    executable = pathlib.Path(argv[0])
    canonical = pathlib.Path(os.path.realpath(executable))
    if not executable.is_absolute() or executable != canonical:
        raise TransportValidationError("source transport Python path is not canonical")
    protocol = _program_snapshot_protocol()
    prefix = (
        str(executable),
        *SOURCE_TRANSPORT_BASE_PYTHON_FLAGS,
        "-c",
        protocol.SOURCE_TRANSPORT_SNAPSHOT_BOOTSTRAP,
        SOURCE_TRANSPORT_SNAPSHOT_SCHEMA,
    )
    return protocol._source_transport_decode_snapshot(
        argv,
        prefix=prefix,
        cache=snapshot_cache,
        maximum_bytes=SOURCE_TRANSPORT_MAX_SNAPSHOT_BYTES,
        component_reader=_program_component,
        prepared_files=prepared_files,
        recover=recover,
    )


def transport_program_commitment(
    command_argv: Sequence[str],
    *,
    snapshot_cache: pathlib.Path | None = None,
    prepared_files: Mapping[pathlib.Path, bytes] | None = None,
    recover: bool = True,
) -> str:
    """Commit every executable component used by one source transport lease."""
    argv = tuple(command_argv)
    snapshot, worker_index, snapshot_commitment = _decode_program_snapshot(
        argv,
        snapshot_cache=pathlib.Path(snapshot_cache or SOURCE_TRANSPORT_SNAPSHOT_CACHE),
        prepared_files=prepared_files,
        recover=recover,
    )
    worker = pathlib.Path(argv[worker_index])
    if not worker.is_absolute():
        raise TransportValidationError("source transport worker path must be absolute")
    package_dir = pathlib.Path(
        os.path.abspath(os.fspath(pathlib.Path(__file__).parent))
    )
    expected_worker = package_dir / "transport_worker.py"
    if worker != expected_worker:
        raise TransportValidationError(
            "source transport worker is outside the closed package dependency manifest"
        )
    modules = snapshot.get("modules")
    current_python_authority = _python_executable_authority(argv[0])
    snapshot_authority = (
        set(snapshot),
        snapshot.get("schema"),
        snapshot.get("package_dir"),
        snapshot.get("python_executable_authority"),
        snapshot.get("python_runtime"),
        type(modules),
        tuple(getattr(modules, "keys", lambda: ())()),
    )
    expected_authority = (
        {
            "modules",
            "package_dir",
            "python_executable_authority",
            "python_runtime",
            "schema",
        },
        SOURCE_TRANSPORT_SNAPSHOT_SCHEMA,
        str(package_dir),
        _python_executable_authority_receipt(current_python_authority),
        _python_runtime_snapshot(current_python_authority),
        dict,
        SOURCE_TRANSPORT_WORKER_MODULE_MANIFEST,
    )
    if snapshot_authority != expected_authority:
        raise TransportValidationError("source transport snapshot authority changed")
    components: list[dict[str, JsonValue]] = []
    for module_name, content in modules.items():
        if not isinstance(content, str):
            raise TransportValidationError(
                "source transport snapshot component is invalid"
            )
        try:
            decoded = base64.b64decode(content, validate=True)
        except ValueError as exc:
            raise TransportValidationError(
                "source transport snapshot component is invalid"
            ) from exc
        if len(decoded) > SOURCE_TRANSPORT_MAX_PROGRAM_COMPONENT_BYTES:
            raise TransportValidationError(
                "source transport snapshot component is too large"
            )
        components.append(
            {
                "content_commitment": "sha256:" + hashlib.sha256(decoded).hexdigest(),
                "path": str(package_dir / module_name),
                "role": f"package_module:{module_name}",
                "state": "present",
            }
        )
    helper_count = argv.count("--remote-helper")
    commitment_count = argv.count("--remote-helper-commitment")
    if helper_count or commitment_count:
        if helper_count != 1 or commitment_count != 1:
            raise TransportValidationError(
                "source transport remote helper binding is invalid"
            )
        helper_index = argv.index("--remote-helper")
        commitment_index = argv.index("--remote-helper-commitment")
        if helper_index + 1 >= len(argv) or commitment_index + 1 >= len(argv):
            raise TransportValidationError(
                "source transport remote helper binding is invalid"
            )
        helper = pathlib.Path(argv[helper_index + 1])
        helper_commitment = argv[commitment_index + 1]
        expected_helper = (
            _program_snapshot_protocol()._source_transport_external_snapshot_path(
                pathlib.Path(snapshot_cache or SOURCE_TRANSPORT_SNAPSHOT_CACHE),
                helper_commitment,
            )
        )
        if not helper.is_absolute() or helper != expected_helper:
            raise TransportValidationError(
                "source transport remote helper snapshot path is invalid"
            )
        prepared_helper = None if prepared_files is None else prepared_files.get(helper)
        if prepared_helper is None:
            helper_component = _program_component(
                helper,
                role="remote_host_context_helper",
                allow_missing=False,
            )
        else:
            if (
                not isinstance(prepared_helper, bytes)
                or len(prepared_helper) > SOURCE_TRANSPORT_MAX_PROGRAM_COMPONENT_BYTES
            ):
                raise TransportValidationError(
                    "source transport remote helper snapshot is invalid"
                )
            helper_component = {
                "content_commitment": "sha256:"
                + hashlib.sha256(prepared_helper).hexdigest(),
                "path": str(helper),
                "role": "remote_host_context_helper",
                "state": "present",
            }
        if helper_component["content_commitment"] != helper_commitment:
            raise TransportValidationError(
                "source transport remote helper snapshot changed"
            )
        components.append(helper_component)
    protocol = _program_snapshot_protocol()
    bootstrap = protocol.SOURCE_TRANSPORT_SNAPSHOT_BOOTSTRAP.encode("utf-8")
    return _canonical_commitment(
        {
            "components": components,
            "module_manifest": list(SOURCE_TRANSPORT_WORKER_MODULE_MANIFEST),
            "python_flags": list(SOURCE_TRANSPORT_BASE_PYTHON_FLAGS),
            "python_executable_authority": snapshot["python_executable_authority"],
            "python_runtime": snapshot["python_runtime"],
            "snapshot_bootstrap_commitment": "sha256:"
            + hashlib.sha256(bootstrap).hexdigest(),
            "remote_helper_bootstrap_commitment": "sha256:"
            + hashlib.sha256(
                protocol.REMOTE_HOST_CONTEXT_SNAPSHOT_BOOTSTRAP.encode("utf-8")
            ).hexdigest(),
            "snapshot_commitment": snapshot_commitment,
            "schema": "source_transport_worker_program_v9",
        }
    )
