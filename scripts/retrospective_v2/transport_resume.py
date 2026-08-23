"""Bounded source-object probes and canonical continuation positions."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import os
from typing import Mapping

try:
    from . import safe_io
    from .contracts import JsonValue, canonical_json_bytes, strict_json_loads
    from .transport_contracts import (
        SOURCE_TRANSPORT_BOUNDARY_PROBE_BYTES,
        SOURCE_TRANSPORT_RESUME_PROBE_BYTES,
        SOURCE_TRANSPORT_SCAN_CHUNK_BYTES,
        TransportValidationError,
        _canonical_commitment,
        _normalize_source_resume_position,
    )
except (ImportError, ModuleNotFoundError):
    import safe_io  # type: ignore[no-redef]
    from contracts import (  # type: ignore[no-redef]
        JsonValue,
        canonical_json_bytes,
        strict_json_loads,
    )
    from transport_contracts import (  # type: ignore[no-redef]
        SOURCE_TRANSPORT_BOUNDARY_PROBE_BYTES,
        SOURCE_TRANSPORT_RESUME_PROBE_BYTES,
        SOURCE_TRANSPORT_SCAN_CHUNK_BYTES,
        TransportValidationError,
        _canonical_commitment,
        _normalize_source_resume_position,
    )


_SOURCE_ACCESS_POLICY_FLAG_MASK = 0x001E0096  # BSD write/delete restriction flags.


def _source_object_generation(metadata: os.stat_result) -> tuple[int, int]:
    birthtime_ns = getattr(metadata, "st_birthtime_ns", None)
    if birthtime_ns is None:
        birthtime = getattr(metadata, "st_birthtime", None)
        birthtime_ns = (
            -1 if birthtime is None else int(round(float(birthtime) * 1_000_000_000))
        )
    return int(getattr(metadata, "st_gen", -1)), int(birthtime_ns)


def _source_transport_candidate_token(
    metadata: os.stat_result,
    access_policy_sha256: str = "sha256:" + hashlib.sha256(b"").hexdigest(),
) -> str:
    generation, birthtime_ns = _source_object_generation(metadata)
    policy_flags = (
        int(getattr(metadata, "st_flags", 0)) & _SOURCE_ACCESS_POLICY_FLAG_MASK
    )
    return _canonical_commitment(
        {
            "birthtime_ns": birthtime_ns,
            "access_policy_sha256": access_policy_sha256,
            "device": metadata.st_dev,
            "generation": generation,
            "gid": metadata.st_gid,
            "inode": metadata.st_ino,
            "link_count": metadata.st_nlink,
            "mode": metadata.st_mode,
            "policy_flags": policy_flags,
            "schema": "source_transport_candidate_v7",
            "uid": metadata.st_uid,
        }
    )


def _source_transport_file_identity(
    metadata: os.stat_result,
    access_policy_sha256: str = "sha256:" + hashlib.sha256(b"").hexdigest(),
) -> tuple[int | str, ...]:
    fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink")
    return tuple(int(getattr(metadata, field)) for field in fields) + (
        int(getattr(metadata, "st_flags", 0)) & _SOURCE_ACCESS_POLICY_FLAG_MASK,
        int(getattr(metadata, "st_gen", -1)),
        access_policy_sha256,
    )


def _source_transport_file_observation(
    descriptor: int,
) -> tuple[os.stat_result, str]:
    """Bind file identity and the descriptor's normalized ACL policy."""

    before = os.fstat(descriptor)
    access_policy_sha256 = (
        "sha256:"
        + hashlib.sha256(safe_io.descriptor_acl_policy_bytes(descriptor)).hexdigest()
    )
    after = os.fstat(descriptor)
    if _source_transport_file_identity(
        before, access_policy_sha256
    ) != _source_transport_file_identity(after, access_policy_sha256):
        raise ValueError("source entry changed while its access policy was inspected")
    return after, access_policy_sha256


def _source_transport_observed_candidate_token(descriptor: int) -> str:
    metadata, access_policy_sha256 = _source_transport_file_observation(descriptor)
    return _source_transport_candidate_token(metadata, access_policy_sha256)


def _source_transport_scan_is_stable(
    *,
    before: os.stat_result,
    before_access_policy: str,
    proof_before: os.stat_result,
    proof_access_policy: str,
    after: os.stat_result,
    after_access_policy: str,
    source_size: int,
    scanned: int,
    scanned_range_commitment: str | None,
    read_range_commitment: str,
    resume_probe_stable: bool,
    terminal_status: str | None,
    terminal_reason: str | None,
) -> bool:
    identities_stable = (
        _source_transport_file_identity(before, before_access_policy)
        == _source_transport_file_identity(proof_before, proof_access_policy)
        == _source_transport_file_identity(after, after_access_policy)
        and before.st_nlink == proof_before.st_nlink == after.st_nlink == 1
    )
    bounded_stop = terminal_status == "gap" and terminal_reason in {
        "source_byte_limit_reached",
        "source_record_limit_reached",
    }
    return (
        identities_stable
        and after.st_size >= source_size
        and scanned_range_commitment == read_range_commitment
        and resume_probe_stable
        and (scanned == source_size or bounded_stop)
    )


def _source_transport_range_digest(descriptor: int, start: int, end: int) -> str:
    digest = hashlib.sha256()
    scanned = start
    while scanned < end:
        chunk = os.pread(
            descriptor,
            min(SOURCE_TRANSPORT_SCAN_CHUNK_BYTES, end - scanned),
            scanned,
        )
        if not chunk:
            raise ValueError("source transport committed range is truncated")
        digest.update(chunk)
        scanned += len(chunk)
    return "sha256:" + digest.hexdigest()


def _source_transport_boundary_probe(
    descriptor: int,
    byte_offset: int,
) -> tuple[int, str]:
    probe_start = max(0, byte_offset - SOURCE_TRANSPORT_BOUNDARY_PROBE_BYTES)
    return probe_start, _source_transport_range_digest(
        descriptor, probe_start, byte_offset
    )


class _SourceTransportResumeProbeBudgetExhausted(ValueError):
    pass


@dataclass(slots=True)
class _SourceTransportResumeProbeBudget:
    limit: int
    used: int = 0

    def read(self, descriptor: int, *, start: int, end: int) -> bytes:
        if start < 0 or end < start:
            raise ValueError("source transport resume probe range is invalid")
        requested = end - start
        if requested > SOURCE_TRANSPORT_RESUME_PROBE_BYTES:
            raise ValueError("source transport resume probe exceeds 64 KiB")
        if self.used + requested > self.limit:
            raise _SourceTransportResumeProbeBudgetExhausted(
                "source transport resume probe budget is exhausted"
            )
        self.used += requested
        retained = bytearray()
        scanned = start
        while scanned < end:
            chunk = os.pread(
                descriptor,
                min(SOURCE_TRANSPORT_SCAN_CHUNK_BYTES, end - scanned),
                scanned,
            )
            if not chunk:
                raise ValueError("source transport resume probe is truncated")
            retained.extend(chunk)
            scanned += len(chunk)
        return bytes(retained)


def encode_source_resume_position(value: Mapping[str, object]) -> str:
    normalized = _normalize_source_resume_position(value)
    if normalized is None:
        raise TransportValidationError("source transport resume position is missing")
    return (
        base64.urlsafe_b64encode(canonical_json_bytes(normalized))
        .decode("ascii")
        .rstrip("=")
    )


def decode_source_resume_position(value: str) -> dict[str, JsonValue]:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise TransportValidationError("source transport resume position is invalid")
    try:
        payload = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
        decoded = strict_json_loads(payload)
    except (binascii.Error, ValueError) as exc:
        raise TransportValidationError(
            "source transport resume position is invalid"
        ) from exc
    if not isinstance(decoded, Mapping):
        raise TransportValidationError("source transport resume position is invalid")
    normalized = _normalize_source_resume_position(decoded)
    if normalized is None or canonical_json_bytes(normalized) != payload:
        raise TransportValidationError(
            "source transport resume position is not canonical"
        )
    return normalized
