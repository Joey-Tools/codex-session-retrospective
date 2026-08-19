"""Strict GPG invocation and status policy shared by publication probes."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re

from . import executable_authority


_FINGERPRINT_RE = re.compile(r"[0-9A-F]{40}\Z")
GPG_PROGRAM_ENV = "CODEX_SESSION_RETROSPECTIVE_GPG_PROGRAM"
_NO_OPTIONS_LAUNCHER = (
    b"#!/bin/sh\n"
    b"set -eu\n"
    b': "${CODEX_SESSION_RETROSPECTIVE_GPG_PROGRAM:?}"\n'
    b'exec "$CODEX_SESSION_RETROSPECTIVE_GPG_PROGRAM" --no-options "$@"\n'
)
_NO_OPTIONS_LAUNCHER_SHA256 = hashlib.sha256(_NO_OPTIONS_LAUNCHER).hexdigest()
_NO_OPTIONS_LAUNCHER_PATH = (
    Path(__file__).resolve().parents[1] / "retrospective_v2_gpg_no_options"
)


def no_options_argv(program: str, *arguments: str) -> tuple[str, ...]:
    """Put GPG's default-option suppression before every other argument."""

    return (program, "--no-options", *arguments)


def authority_program(
    authority: executable_authority.ExecutableAuthority | None,
) -> str:
    return "/usr/bin/false" if authority is None else authority.path


def no_options_launcher_authority() -> executable_authority.ExecutableAuthority:
    """Authenticate the installed fixed launcher that inserts ``--no-options``."""

    launcher = _NO_OPTIONS_LAUNCHER_PATH
    authority = executable_authority.resolve_executable(
        launcher,
        label="GPG no-options launcher",
    )
    if (
        authority.path != os.path.realpath(launcher)
        or authority.size != len(_NO_OPTIONS_LAUNCHER)
        or authority.sha256 != _NO_OPTIONS_LAUNCHER_SHA256
    ):
        raise executable_authority.ExecutableAuthorityError(
            "GPG no-options launcher authority is invalid"
        )
    return authority


def validsig_primary_fingerprints(status: bytes) -> list[str]:
    """Return the primary-key fingerprint from each complete GPG VALIDSIG row."""

    fingerprints: list[str] = []
    marker = b"[GNUPG:] VALIDSIG "
    for line in status.splitlines():
        index = line.find(marker)
        if index < 0:
            continue
        fields = line[index + len(marker) :].split()
        if len(fields) not in {9, 10}:
            raise ValueError("GPG VALIDSIG row has an unexpected shape")
        try:
            signing_fingerprint = fields[0].decode("ascii", errors="strict").upper()
            primary_fingerprint = (
                fields[9].decode("ascii", errors="strict").upper()
                if len(fields) == 10
                else signing_fingerprint
            )
        except UnicodeDecodeError as exc:
            raise ValueError("GPG VALIDSIG fingerprint is not ASCII") from exc
        if (
            _FINGERPRINT_RE.fullmatch(signing_fingerprint) is None
            or _FINGERPRINT_RE.fullmatch(primary_fingerprint) is None
        ):
            raise ValueError("GPG VALIDSIG fingerprint is invalid")
        fingerprints.append(primary_fingerprint)
    return fingerprints
