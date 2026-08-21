"""Serve the bounded Assuan exchange used by stale-snapshot recovery tests."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import sys


def _read_command(connection: socket.socket) -> bytes:
    payload = bytearray()
    while len(payload) <= 4096:
        chunk = connection.recv(1)
        if not chunk:
            return bytes(payload)
        payload.extend(chunk)
        if chunk == b"\n":
            return bytes(payload)
    return bytes(payload)


def main() -> int:
    home = Path(sys.argv[1])
    primary = home / "S.gpg-agent"
    scdaemon = home / "S.scdaemon"
    with (
        socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener,
        socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as scdaemon_listener,
    ):
        listener.bind(os.fspath(primary))
        primary.chmod(0o600)
        scdaemon_listener.bind(os.fspath(scdaemon))
        scdaemon.chmod(0o600)
        listener.listen(1)
        listener.settimeout(30)
        print("ready", flush=True)
        connection, _address = listener.accept()
        with connection:
            connection.settimeout(5)
            connection.sendall(b"OK fake agent\n")
            if _read_command(connection) != b"SCD KILLSCD\n":
                return 2
            scdaemon_listener.close()
            scdaemon.unlink(missing_ok=True)
            connection.sendall(b"OK\n")
            if _read_command(connection) != b"KILLAGENT\n":
                return 3
            connection.sendall(b"OK\n")
    primary.unlink(missing_ok=True)
    scdaemon.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
