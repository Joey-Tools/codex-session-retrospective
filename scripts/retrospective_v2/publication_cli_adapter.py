"""Construct the formal publication adapter from persisted authority."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import executable_authority, finalize


class _UniqueCanonicalAbsolutePathAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str,
        option_string: str | None = None,
    ) -> None:
        del option_string
        if getattr(namespace, self.dest, None) is not None:
            parser.error("publisher executable argument is duplicated")
        if not executable_authority.is_canonical_absolute_executable_path(values):
            parser.error("publisher executable path is not canonical and absolute")
        setattr(namespace, self.dest, values)


def add_publisher_program_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--publisher-gpg-program",
        required=True,
        action=_UniqueCanonicalAbsolutePathAction,
    )


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
