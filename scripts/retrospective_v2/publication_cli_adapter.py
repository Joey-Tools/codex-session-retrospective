"""Construct the formal publication adapter from persisted authority."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import executable_authority, finalize


def build(
    binding: Mapping[str, Any],
    history_repo: Path,
    provider_state: Path,
) -> finalize.LocalGitPublicationAdapter:
    signing_program = str(binding["publisher_gpg_program"])
    expected_digest = str(binding["publisher_gpg_authority_sha256"])
    authority = executable_authority.resolve_executable(
        signing_program,
        label="GPG",
    )
    executable_authority.require_authority_digest(authority, expected_digest)
    gnupg_home = Path(str(binding["publisher_gnupg_home"]))
    if not gnupg_home.is_absolute():
        raise ValueError("persisted publisher GPG home is not absolute")
    return finalize.LocalGitPublicationAdapter(
        history_repo,
        provider_state,
        signing_key=str(binding["publisher_fingerprint"]),
        gnupg_home=gnupg_home,
        expected_signer_uid=finalize.DEFAULT_PUBLISHER_UID,
        signing_program=authority.path,
        expected_signing_authority_sha256=expected_digest,
    )
