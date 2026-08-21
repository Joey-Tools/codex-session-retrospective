"""Production startup path and publisher authorization gates."""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import authority, executable_authority
from .identity import IdentityKey
from .orchestrator_core import InvalidInputError
from .orchestrator_support import publisher_readiness, publisher_sign_verify_canary


def require_boolean(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise InvalidInputError(f"{label} must be a boolean")
    return value


def require_canonical_production_binding_paths(
    *,
    shadow: object,
    provider_state: str | os.PathLike[str] | None,
    production_marker: str | os.PathLike[str] | None,
) -> None:
    if shadow is True:
        return
    bindings = (
        (provider_state, authority.DEFAULT_PROVIDER_STATE, "provider state"),
        (production_marker, authority.DEFAULT_PRODUCTION_MARKER, "production marker"),
    )
    for supplied, expected, label in bindings:
        if supplied is None:
            continue
        try:
            selected = Path(supplied).expanduser().absolute()
        except (OSError, TypeError, ValueError) as error:
            raise InvalidInputError(f"production {label} path is invalid") from error
        if selected != expected.absolute():
            raise InvalidInputError(f"production {label} must use its fixed path")


def require_cutover_publisher_gpg_authority(
    marker: Mapping[str, Any],
    gpg_authority: executable_authority.ExecutableAuthority,
) -> None:
    try:
        cutover_record = marker["automation_cutover_record"]
        if not isinstance(cutover_record, Mapping):
            raise TypeError
        authorized_program = cutover_record["publisher_gpg_program"]
        if not executable_authority.is_canonical_absolute_executable_path(
            authorized_program
        ):
            raise TypeError
        authorized_target = os.path.realpath(authorized_program, strict=True)
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise authority.ProductionMarkerError(
            "production marker publisher GPG authority is invalid"
        ) from error
    if authorized_target != gpg_authority.path:
        raise authority.ProductionMarkerError(
            "production marker does not authorize the selected publisher GPG executable"
        )


def load_production_marker_for_publisher(
    marker_path: str | os.PathLike[str],
    *,
    identity: IdentityKey,
    canonical_hosts: Sequence[str],
    history_repo: str | os.PathLike[str],
    target_ref: str,
    configuration_root: str,
    configuration_ref: str,
    model_era: str,
    policy_era: str,
    gpg_authority: executable_authority.ExecutableAuthority | None,
) -> dict[str, Any]:
    marker = authority.load_production_marker(
        marker_path,
        identity=identity,
        canonical_hosts=canonical_hosts,
        history_repo=history_repo,
        target_ref=target_ref,
        configuration_root=configuration_root,
        configuration_ref=configuration_ref,
        model_era=model_era,
        policy_era=policy_era,
    )
    if gpg_authority is None:
        raise authority.ProductionMarkerError(
            "publisher GPG executable authority is unavailable"
        )
    require_cutover_publisher_gpg_authority(marker, gpg_authority)
    return marker


def publisher_readiness_report(
    *,
    gpg_authority: executable_authority.ExecutableAuthority | None,
    authority_sha256: str | None,
    fingerprint: str,
    gnupg_home: str | os.PathLike[str],
    publisher_probe: Callable[[], Mapping[str, Any]] | None,
    publisher_canary: Callable[[], bool] | None,
) -> dict[str, Any]:
    publisher: Mapping[str, Any] = {"fingerprint": None, "ready": False}
    canary_ready = False
    if gpg_authority is not None:
        try:
            with executable_authority.executable_invocation(gpg_authority):
                publisher = dict(
                    publisher_readiness(
                        gnupg_home=gnupg_home,
                        fingerprint=fingerprint,
                        gpg_program=gpg_authority.path,
                    )
                    if publisher_probe is None
                    else publisher_probe()
                )
                canary_ready = (
                    publisher_sign_verify_canary(
                        gnupg_home=gnupg_home,
                        fingerprint=fingerprint,
                        gpg_program=gpg_authority.path,
                    )
                    if publisher_canary is None and publisher_probe is None
                    else publisher.get("ready") is True
                    if publisher_canary is None
                    else publisher_canary()
                )
        except (
            OSError,
            TypeError,
            ValueError,
            executable_authority.ExecutableAuthorityError,
        ):
            pass
    return {
        "fingerprint": fingerprint,
        "gpg_authority_sha256": authority_sha256,
        "gpg_program": None if gpg_authority is None else gpg_authority.path,
        "ready": publisher.get("ready") is True
        and publisher.get("fingerprint") == fingerprint
        and canary_ready,
    }
