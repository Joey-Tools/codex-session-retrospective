"""Bounded delegation through the canonical remote-host-context helper."""

from __future__ import annotations

import argparse
import base64
import binascii
import codecs
import hmac
import os
import pathlib
import pwd
import selectors
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence

try:
    from . import process_lifecycle, safe_io
    from .transport_contracts import (
        RemoteTransportCapabilityError,
        TransportValidationError,
        _canonical_commitment,
    )
    from .transport_host_inventory import (
        AuthenticatedHostInventory,
        HostInventoryError,
        _parse_authenticated_helper_contract,
    )
    from .transport_program_components import _program_component
    from .transport_snapshot import (
        REMOTE_HELPER_EXIT_AUTHENTICATION,
        REMOTE_HELPER_EXIT_EXECUTION,
        REMOTE_HOST_CONTEXT_SNAPSHOT_BOOTSTRAP,
        REMOTE_HOST_CONTEXT_SNAPSHOT_SCHEMA,
    )
except (ImportError, ModuleNotFoundError):
    import process_lifecycle  # type: ignore[no-redef]
    import safe_io  # type: ignore[no-redef]
    from transport_contracts import (  # type: ignore[no-redef]
        RemoteTransportCapabilityError,
        TransportValidationError,
        _canonical_commitment,
    )
    from transport_host_inventory import (  # type: ignore[no-redef]
        AuthenticatedHostInventory,
        HostInventoryError,
        _parse_authenticated_helper_contract,
    )
    from transport_program_components import _program_component  # type: ignore[no-redef]
    from transport_snapshot import (  # type: ignore[no-redef]
        REMOTE_HELPER_EXIT_AUTHENTICATION,
        REMOTE_HELPER_EXIT_EXECUTION,
        REMOTE_HOST_CONTEXT_SNAPSHOT_BOOTSTRAP,
        REMOTE_HOST_CONTEXT_SNAPSHOT_SCHEMA,
    )

REMOTE_HOST_CONTEXT_HELPER_RELATIVE_PATH = pathlib.PurePosixPath(
    ".codex/skills/remote-host-context/scripts/remote_codex_probe.py"
)
REMOTE_HOST_CONTEXT_COMMAND_TIMEOUT_SECONDS = 60
REMOTE_HOST_CONTEXT_FIXED_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
REMOTE_HOST_CONTEXT_AUTH_ENVIRONMENT_KEYS = ("SSH_AUTH_SOCK",)
REMOTE_HOST_CONTEXT_RETROSPECTIVE_COMMANDS = frozenset(
    {"session-shards", "source-transport"}
)


class RemoteTransportUnavailableError(RuntimeError):
    """Raised only when the helper transport could not produce a result."""


class RemoteTransportAuthenticationError(TransportValidationError):
    """Raised when the run-owned helper snapshot cannot be authenticated."""


class RemoteTransportExecutionError(RuntimeError):
    """Raised when authenticated helper code violates its execution contract."""


def remote_host_context_helper_path() -> pathlib.Path:
    return pathlib.Path.home().joinpath(*REMOTE_HOST_CONTEXT_HELPER_RELATIVE_PATH.parts)


def remote_host_context_helper_commitment(
    path: str | os.PathLike[str] | None = None,
) -> str:
    helper = remote_host_context_helper_path() if path is None else pathlib.Path(path)
    return remote_host_context_helper_component_commitment(
        _program_component(
            helper,
            role="remote_host_context_helper",
            allow_missing=False,
        )
    )


def remote_host_context_host_inventory(
    path: str | os.PathLike[str] | None = None,
) -> AuthenticatedHostInventory:
    """Read HOSTS from the descriptor-authenticated helper without executing it."""

    helper = remote_host_context_helper_path() if path is None else pathlib.Path(path)
    inventory, _runtime_commitment, helper_commitment, commands = _authenticated_hosts(
        helper
    )
    return AuthenticatedHostInventory(inventory, helper_commitment, commands)


def remote_host_context_helper_component_commitment(
    component: Mapping[str, Any],
) -> str:
    committed_component = dict(component)
    committed_component.pop("content_b64", None)
    return _canonical_commitment(
        {
            "component": committed_component,
            "relative_contract": REMOTE_HOST_CONTEXT_HELPER_RELATIVE_PATH.as_posix(),
            "schema": "remote_host_context_helper_commitment_v2",
        }
    )


def _authenticated_hosts(
    helper: pathlib.Path,
    *,
    expected_commitment: str | None = None,
    content_snapshot: bool = False,
) -> tuple[Any, str, str, tuple[str, ...]]:
    component = _program_component(
        helper,
        role="remote_host_context_helper",
        allow_missing=False,
        include_content=True,
    )
    helper_commitment = remote_host_context_helper_component_commitment(component)
    observed_commitment = (
        str(component["content_commitment"]) if content_snapshot else helper_commitment
    )
    if expected_commitment is not None and (
        not isinstance(expected_commitment, str)
        or not hmac.compare_digest(observed_commitment, expected_commitment)
    ):
        raise TransportValidationError("remote-host-context helper snapshot changed")
    try:
        payload = base64.b64decode(str(component["content_b64"]), validate=True)
        inventory, runtime_commitment, commands = _parse_authenticated_helper_contract(
            payload
        )
    except (binascii.Error, KeyError, TypeError, ValueError, HostInventoryError) as exc:
        raise TransportValidationError(
            "remote-host-context helper HOSTS inventory is invalid"
        ) from exc
    return inventory, runtime_commitment, helper_commitment, commands


def _remote_helper_bootstrap_argv(
    helper: pathlib.Path,
    commitment: str,
    runtime_commitment: str,
    arguments: Sequence[str],
) -> tuple[str, ...]:
    return (
        sys.executable,
        "-I",
        "-B",
        "-S",
        "-X",
        f"pycache_prefix={os.devnull}",
        "-c",
        REMOTE_HOST_CONTEXT_SNAPSHOT_BOOTSTRAP,
        REMOTE_HOST_CONTEXT_SNAPSHOT_SCHEMA,
        commitment,
        str(helper),
        runtime_commitment,
        *arguments,
    )


def remote_host_context_snapshot_source_binding(
    snapshot_path: str | os.PathLike[str],
    snapshot_commitment: str,
    host: str,
) -> tuple[str, str]:
    """Derive route and lexical Codex root from an authenticated helper snapshot."""

    inventory, _runtime_commitment, _helper_commitment, _commands = (
        _authenticated_hosts(
            pathlib.Path(snapshot_path),
            expected_commitment=snapshot_commitment,
            content_snapshot=True,
        )
    )
    try:
        resolved = inventory.resolve(host)
    except HostInventoryError as exc:
        raise TransportValidationError(
            "remote-host-context helper snapshot does not define the requested host"
        ) from exc
    route = resolved.role
    codex_root = resolved.codex_root
    if route == "remote":
        lexical_root = pathlib.PurePosixPath(codex_root)
        if (
            not lexical_root.is_absolute()
            or lexical_root.parent == lexical_root
            or str(lexical_root) != codex_root
            or any(part in {"", ".", ".."} for part in lexical_root.parts[1:])
        ):
            raise TransportValidationError(
                "remote-host-context helper Codex root is not an exact lexical path"
            )
    return route, codex_root


def _remote_host_context_command(
    args: argparse.Namespace,
    command: str,
    command_arguments: Sequence[str],
) -> tuple[str, ...]:
    configured_helper = getattr(args, "remote_helper", None)
    helper_commitment = getattr(args, "remote_helper_commitment", None)
    helper = pathlib.Path(configured_helper or "")
    if (
        not configured_helper
        or not helper.is_absolute()
        or not isinstance(helper_commitment, str)
        or len(helper_commitment) != 71
        or not helper_commitment.startswith("sha256:")
        or any(
            character not in "0123456789abcdef" for character in helper_commitment[7:]
        )
    ):
        raise ValueError("remote-host-context helper snapshot binding is invalid")
    _inventory, runtime_hosts_commitment, _helper_commitment, commands = (
        _authenticated_hosts(
            helper,
            expected_commitment=helper_commitment,
            content_snapshot=True,
        )
    )
    if (
        command in REMOTE_HOST_CONTEXT_RETROSPECTIVE_COMMANDS
        and command not in commands
    ):
        raise RemoteTransportCapabilityError(
            "remote-host-context helper lacks the required retrospective command"
        )
    return _remote_helper_bootstrap_argv(
        helper,
        helper_commitment,
        runtime_hosts_commitment,
        (command, "--host", str(args.host), *command_arguments),
    )


def _remote_host_context_environment() -> dict[str, str]:
    try:
        account = pwd.getpwuid(os.getuid())
    except (KeyError, OSError) as exc:
        raise RuntimeError("remote-host-context account identity unavailable") from exc
    if not account.pw_name or not account.pw_dir:
        raise RuntimeError("remote-host-context account identity unavailable")
    account_home = pathlib.PurePath(account.pw_dir)
    if not account_home.is_absolute() or "\x00" in account.pw_dir:
        raise RuntimeError("remote-host-context account home is invalid")

    environment = {
        "HOME": account.pw_dir,
        "LANG": "C",
        "LC_ALL": "C",
        "LOGNAME": account.pw_name,
        "PATH": REMOTE_HOST_CONTEXT_FIXED_PATH,
        "USER": account.pw_name,
    }
    for key in REMOTE_HOST_CONTEXT_AUTH_ENVIRONMENT_KEYS:
        value = os.environ.get(key)
        if value is None:
            continue
        if (
            not value
            or "\x00" in value
            or "\n" in value
            or "\r" in value
            or not pathlib.PurePath(value).is_absolute()
        ):
            raise RuntimeError(
                "remote-host-context authentication environment is invalid"
            )
        environment[key] = value
    return environment


def _relay_valid_utf8(output: Any) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    output.seek(0)
    while chunk := output.read(64 * 1024):
        decoder.decode(chunk, final=False)
    decoder.decode(b"", final=True)
    output.seek(0)
    binary_stdout = getattr(sys.stdout, "buffer", None)
    if binary_stdout is not None:
        while chunk := output.read(64 * 1024):
            binary_stdout.write(chunk)
        binary_stdout.flush()
        return
    text_decoder = codecs.getincrementaldecoder("utf-8")("strict")
    while chunk := output.read(64 * 1024):
        sys.stdout.write(text_decoder.decode(chunk, final=False))
    sys.stdout.write(text_decoder.decode(b"", final=True))
    sys.stdout.flush()


def _reap_remote_process_group(process: subprocess.Popen[bytes]) -> int:
    return process_lifecycle.reap_after_termination(
        process,
        timeout_seconds=5,
        error_type=RuntimeError,
        error_message="remote-host-context transport did not terminate",
    )


def _close_remote_process_group(
    process: subprocess.Popen[bytes],
    *,
    signal_retirement: process_lifecycle.GroupSignalRetirement,
) -> int:
    return process_lifecycle.close_process_group(
        process,
        signal_retirement=signal_retirement,
        timeout_seconds=5,
        error_type=RuntimeError,
        label="remote-host-context",
        termination_message="remote-host-context transport did not terminate",
    )


def _filter_remote_output(stream_filter: Any, chunk: bytes | None = None) -> bytes:
    try:
        if chunk is None:
            return stream_filter.finish()
        return chunk if stream_filter is None else stream_filter.feed(chunk)
    except (TransportValidationError, UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError(
            "remote-host-context transport emitted an invalid protocol stream"
        ) from exc


def _relay_remote_host_context_command(
    argv: Sequence[str],
    *,
    max_output_bytes: int,
    validator: Callable[[Any], None] | None = None,
    stream_filter: Any | None = None,
    publisher: Callable[[Any], None] | None = None,
) -> None:
    """Run the canonical helper with bounded, content-free failure handling."""

    if max_output_bytes < 1:
        raise RuntimeError("remote-host-context output envelope is invalid")
    signal_retirement = process_lifecycle.GroupSignalRetirement()
    selector: selectors.BaseSelector | None = None
    active_error: BaseException | None = None
    try:
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_remote_host_context_environment(),
            close_fds=True,
            start_new_session=os.name == "posix",
        )
    except OSError as exc:
        raise RemoteTransportUnavailableError(
            "remote-host-context transport unavailable"
        ) from exc

    try:
        if process.stdout is None:
            raise RemoteTransportUnavailableError(
                "remote-host-context transport unavailable"
            )
        selector = selectors.DefaultSelector()
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + REMOTE_HOST_CONTEXT_COMMAND_TIMEOUT_SECONDS
        with tempfile.TemporaryFile(mode="w+b") as output:
            try:
                safe_io.harden_created_owner_only_file_descriptor(
                    output.fileno(),
                    pathlib.Path("remote-host-context-output-spool"),
                    single_link=False,
                )
            except OSError as exc:
                raise RuntimeError(
                    "remote-host-context output spool is unavailable"
                ) from exc
            input_bytes = 0
            output_bytes = 0
            timed_out = False
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                if not selector.select(remaining):
                    timed_out = True
                    break
                try:
                    chunk = os.read(process.stdout.fileno(), 64 * 1024)
                except BlockingIOError:
                    continue
                if not chunk:
                    break
                input_bytes += len(chunk)
                if input_bytes > max_output_bytes:
                    raise RuntimeError(
                        "remote-host-context transport exceeded its output envelope"
                    )
                filtered = _filter_remote_output(stream_filter, chunk)
                output_bytes += len(filtered)
                if output_bytes > max_output_bytes:
                    raise RuntimeError(
                        "remote-host-context transport exceeded its output envelope"
                    )
                output.write(filtered)
            if timed_out:
                raise RemoteTransportUnavailableError(
                    "remote-host-context transport unavailable"
                )
            process_lifecycle.wait_for_unreaped_exit(
                process,
                deadline=deadline,
                error_type=RemoteTransportUnavailableError,
                deadline_message="remote-host-context transport unavailable",
                status_message="remote-host-context transport unavailable",
            )
            # Close the task-owned group while the unreaped leader still pins
            # its PID/PGID. Reaping first would open a reuse race.
            return_code = _close_remote_process_group(
                process,
                signal_retirement=signal_retirement,
            )
            if return_code == REMOTE_HELPER_EXIT_AUTHENTICATION:
                raise RemoteTransportAuthenticationError(
                    "remote-host-context helper authentication failed"
                )
            if return_code == REMOTE_HELPER_EXIT_EXECUTION:
                raise RemoteTransportExecutionError(
                    "remote-host-context helper execution failed"
                )
            if return_code != 0:
                raise RemoteTransportUnavailableError(
                    "remote-host-context transport unavailable"
                )
            if stream_filter is not None:
                filtered = _filter_remote_output(stream_filter)
                output_bytes += len(filtered)
                if output_bytes > max_output_bytes:
                    raise RuntimeError(
                        "remote-host-context transport exceeded its output envelope"
                    )
                output.write(filtered)
            if validator is not None:
                try:
                    validator(output)
                except (OSError, TransportValidationError, ValueError) as exc:
                    raise RuntimeError(
                        "remote-host-context transport emitted an invalid protocol stream"
                    ) from exc
            try:
                if publisher is None:
                    _relay_valid_utf8(output)
                else:
                    output.seek(0)
                    publisher(output)
            except (TransportValidationError, UnicodeDecodeError, ValueError) as exc:
                raise RuntimeError(
                    "remote-host-context transport emitted an invalid protocol stream"
                ) from exc
    except BaseException as exc:
        active_error = exc
        raise
    finally:
        resource_closers = tuple(
            closer
            for closer in (
                None if selector is None else selector.close,
                None if process.stdout is None else process.stdout.close,
            )
            if closer is not None
        )
        process_lifecycle.finish_cleanup_after_resource_teardown(
            process,
            resource_closers=resource_closers,
            resource_label="remote transport resource teardown",
            signal_retirement=signal_retirement,
            terminate_and_reap=lambda child: _close_remote_process_group(
                child,
                signal_retirement=signal_retirement,
            ),
            reap_only=_reap_remote_process_group,
            active_error=active_error,
        )
