"""Strict parsing for GPG status records shared by publication probes."""

from __future__ import annotations

import re


_FINGERPRINT_RE = re.compile(r"[0-9A-F]{40}\Z")


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
