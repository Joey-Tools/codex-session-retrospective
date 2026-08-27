"""Process-local publisher readiness cache bound to exact trusted inputs."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from . import executable_authority


_CACHE_LIMIT = 8
_CacheKey = tuple[str, str, str, str, str]
_CACHE: dict[_CacheKey, dict[str, Any]] = {}


@dataclass(frozen=True, slots=True)
class ReadinessProbe:
    home: Path
    gpg_authority: executable_authority.ExecutableAuthority
    authority_sha256: str
    cache_key: _CacheKey
    cached: dict[str, Any] | None


def probe(
    *,
    gnupg_home: str | os.PathLike[str],
    fingerprint: str,
    expected_uid: str,
    gpg_program: str | os.PathLike[str],
    keyring_commitment: str,
) -> ReadinessProbe:
    """Revalidate selected bytes and GPG authority before any cache hit."""

    if len(keyring_commitment) != 64 or any(
        character not in "0123456789abcdef" for character in keyring_commitment
    ):
        raise ValueError("publisher keyring commitment is invalid")
    home = Path(gnupg_home).expanduser().absolute()
    gpg_authority = executable_authority.resolve_executable(
        gpg_program,
        label="GPG",
    )
    authority_sha256 = executable_authority.authority_digest(gpg_authority)
    cache_key = (
        str(home),
        fingerprint,
        expected_uid,
        authority_sha256,
        keyring_commitment,
    )
    cached = _CACHE.get(cache_key)
    return ReadinessProbe(
        home=home,
        gpg_authority=gpg_authority,
        authority_sha256=authority_sha256,
        cache_key=cache_key,
        cached=None if cached is None else dict(cached),
    )


def record_ready(cache_key: _CacheKey, result: dict[str, Any]) -> None:
    """Retain one safe result under a bounded insertion-ordered cache."""

    if len(_CACHE) >= _CACHE_LIMIT:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[cache_key] = dict(result)


def clear() -> None:
    """Clear process-local state for an isolated test or process transition."""

    _CACHE.clear()
