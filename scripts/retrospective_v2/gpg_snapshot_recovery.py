"""Bounded GPG-agent shutdown for descriptor-bound keyring snapshots."""

from __future__ import annotations

import errno
import os
import socket
import stat
import time

from . import temporary_paths


_AGENT_SOCKET_NAMES = (
    "S.gpg-agent",
    "S.gpg-agent.browser",
    "S.gpg-agent.extra",
    "S.gpg-agent.ssh",
    "S.scdaemon",
)
MAX_SNAPSHOT_TOP_LEVEL_ENTRIES = 32
_MAX_ASSUAN_LINE_BYTES = 4096
_AGENT_SHUTDOWN_SECONDS = 5.0


class GpgSnapshotRecoveryError(RuntimeError):
    """Raised when a snapshot GPG agent cannot be stopped or cleaned safely."""


def _assuan_line(connection: socket.socket, *, deadline: float) -> bytes:
    payload = bytearray()
    while len(payload) <= _MAX_ASSUAN_LINE_BYTES:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise GpgSnapshotRecoveryError(
                "publisher agent response exceeded its deadline"
            )
        connection.settimeout(remaining)
        chunk = connection.recv(1)
        if not chunk or chunk == b"\n":
            return bytes(payload).rstrip(b"\r")
        payload.extend(chunk)
    raise GpgSnapshotRecoveryError("publisher agent response exceeds its byte limit")


def _socket_names(
    temporary: temporary_paths.BoundTemporaryDirectory,
) -> tuple[str, ...]:
    temporary.revalidate()
    names: list[str] = []
    with os.scandir(temporary._child_fd) as entries:
        for index, entry in enumerate(entries, start=1):
            if index > MAX_SNAPSHOT_TOP_LEVEL_ENTRIES:
                raise GpgSnapshotRecoveryError(
                    "publisher snapshot top-level inventory exceeds its entry limit"
                )
            if entry.name.startswith("S."):
                names.append(entry.name)
    names_tuple = tuple(sorted(names, key=os.fsencode))
    if any(name not in _AGENT_SOCKET_NAMES for name in names_tuple):
        raise GpgSnapshotRecoveryError(
            "publisher snapshot contains an unknown agent socket"
        )
    return names_tuple


def _send_assuan_command(
    connection: socket.socket,
    command: bytes,
    *,
    deadline: float,
    allow_eof: bool = False,
) -> None:
    connection.sendall(command)
    response = _assuan_line(connection, deadline=deadline)
    if not response and allow_eof:
        return
    if not response.startswith(b"OK"):
        raise GpgSnapshotRecoveryError("publisher agent rejected bounded shutdown")


def _socket_identity(
    temporary: temporary_paths.BoundTemporaryDirectory,
    name: str,
) -> tuple[int, int, int, int]:
    metadata = os.stat(name, dir_fd=temporary._child_fd, follow_symlinks=False)
    if (
        not stat.S_ISSOCK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise GpgSnapshotRecoveryError("publisher agent socket policy is invalid")
    return metadata.st_dev, metadata.st_ino, metadata.st_uid, metadata.st_mode


def stop_agent(
    temporary: temporary_paths.BoundTemporaryDirectory,
    *,
    allow_stale_listener: bool = False,
) -> None:
    """Stop one bound snapshot agent and prove that its sockets disappeared."""

    names = _socket_names(temporary)
    if not names:
        return
    primary = _AGENT_SOCKET_NAMES[0]
    if primary not in names:
        raise GpgSnapshotRecoveryError(
            "publisher agent auxiliary socket exists without its primary socket"
        )
    identities = {name: _socket_identity(temporary, name) for name in names}
    temporary.revalidate()
    deadline = time.monotonic() + _AGENT_SHUTDOWN_SECONDS
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(max(0.0, deadline - time.monotonic()))
            connection.connect(os.fspath(temporary.path / primary))
            greeting = _assuan_line(connection, deadline=deadline)
            if not greeting.startswith(b"OK"):
                raise GpgSnapshotRecoveryError(
                    "publisher agent returned an invalid greeting"
                )
            if "S.scdaemon" in names:
                _send_assuan_command(
                    connection,
                    b"SCD KILLSCD\n",
                    deadline=deadline,
                )
            _send_assuan_command(
                connection,
                b"KILLAGENT\n",
                deadline=deadline,
                allow_eof=True,
            )
    except (OSError, TimeoutError) as exc:
        if (
            allow_stale_listener
            and isinstance(exc, OSError)
            and exc.errno == errno.ECONNREFUSED
        ):
            return
        raise GpgSnapshotRecoveryError(
            "publisher agent could not be stopped safely"
        ) from exc
    while True:
        remaining = _socket_names(temporary)
        if not remaining:
            return
        for name in remaining:
            if name not in identities:
                raise GpgSnapshotRecoveryError(
                    "publisher agent socket appeared during shutdown"
                )
            try:
                identity = _socket_identity(temporary, name)
            except FileNotFoundError:
                continue
            if identity != identities[name]:
                raise GpgSnapshotRecoveryError(
                    "publisher agent socket changed during shutdown"
                )
        if time.monotonic() >= deadline:
            raise GpgSnapshotRecoveryError(
                "publisher agent cleanup did not remove every socket"
            )
        time.sleep(0.01)


def remove_stale_sockets(
    temporary: temporary_paths.BoundTemporaryDirectory,
) -> None:
    """Remove only stable, known sockets after a stale listener is absent."""

    names = _socket_names(temporary)
    for name in names:
        before = _socket_identity(temporary, name)
        after = _socket_identity(temporary, name)
        if before != after:
            raise GpgSnapshotRecoveryError(
                "stale publisher snapshot agent socket changed before cleanup"
            )
        os.unlink(name, dir_fd=temporary._child_fd)
    if names:
        os.fsync(temporary._child_fd)
    temporary.revalidate()


def socket_names(
    temporary: temporary_paths.BoundTemporaryDirectory,
) -> tuple[str, ...]:
    """Return the validated GPG-agent socket inventory for a bound snapshot."""

    return _socket_names(temporary)
