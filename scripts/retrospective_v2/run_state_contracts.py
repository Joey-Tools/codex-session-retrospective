"""Closed contracts shared by run-state authority validators."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import RefType, RunStage, SourceCellStatus, SourceKind
from .identity import IdentityKey
from .transport_host_inventory import (
    AuthenticatedHostInventory,
    HostInventory,
    HostInventoryError,
    require_inventory_commitment,
)


REQUIRED_RUN_SOURCE_KINDS = (
    SourceKind.SESSION_INDEX.value,
    SourceKind.HISTORY.value,
    SourceKind.ACTIVE_ROLLOUT.value,
    SourceKind.ARCHIVED_ROLLOUT.value,
)
FORMAL_STAGES = {
    RunStage.EXPORT.value,
    RunStage.FINALIZE.value,
    RunStage.COMPLETE.value,
}
TERMINAL_SOURCE_STATUSES = {item.value for item in SourceCellStatus}


class RunStateAuthorityError(ValueError):
    """Raised when authenticated checkpoint content lacks run authority."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RunStateAuthorityError(message)


def derive_ref(identity: IdentityKey, kind: RefType, *parts: object) -> str:
    return str(identity.derive_ref(kind, {"parts": list(parts)}))


def host_ref(identity: IdentityKey, host: str) -> str:
    return derive_ref(identity, RefType.HOST, host)


def frozen_host_inventory(state: Mapping[str, Any]) -> HostInventory:
    """Recover the normalized inventory bound into checkpoint and provenance."""

    provenance = state.get("provenance")
    require(isinstance(provenance, Mapping), "run host inventory provenance is missing")
    try:
        inventory = HostInventory.from_dict(state.get("host_inventory"))
        commitment = require_inventory_commitment(
            inventory,
            state.get("host_inventory_commitment"),
        )
    except (HostInventoryError, TypeError) as exc:
        raise RunStateAuthorityError("run host inventory is invalid") from exc
    require(
        provenance.get("host_inventory") == inventory.to_dict()
        and provenance.get("host_inventory_commitment") == commitment,
        "run host inventory differs from execution provenance",
    )
    return inventory


def frozen_authenticated_host_inventory(
    state: Mapping[str, Any],
) -> AuthenticatedHostInventory:
    """Recover inventory plus the exact helper source authority for the run."""

    inventory = frozen_host_inventory(state)
    provenance = state.get("provenance")
    transport = provenance.get("transport") if isinstance(provenance, Mapping) else None
    require(
        isinstance(transport, Mapping),
        "run host inventory transport provenance is missing",
    )
    try:
        return AuthenticatedHostInventory(
            inventory,
            transport.get("remote_host_context_helper_commitment"),
        )
    except (HostInventoryError, TypeError) as exc:
        raise RunStateAuthorityError(
            "run host inventory helper commitment is invalid"
        ) from exc
