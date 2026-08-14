"""Session-mode source classification policy."""

from __future__ import annotations

from . import catalog
from .contracts import RefType
from .identity import IdentityKey
from .orchestrator_support import InvalidInputError


_UNRESOLVED_CLASSIFICATION = (
    catalog.AccountingClass.EXPLICIT_GAP,
    None,
    "session_identity_unresolved",
    "source_transport",
)
_NON_TARGET_CLASSIFICATION = (
    catalog.AccountingClass.STRUCTURALLY_EXCLUDED,
    catalog.StructuralExclusionReason.SOURCE_POLICY_EXCLUDED,
    None,
    None,
)
_TARGET_FORBIDDEN_GAP_REASONS = frozenset(
    {"session_identity_unresolved", "session_target_mismatch"}
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidInputError(message)


def _validate_inactive(*_args: object, **_kwargs: object) -> None:
    return


def _validate_active(
    identity: IdentityKey,
    *,
    host_ref: str,
    session_target: str | None,
    session_selector_commitment: str | None,
    record: catalog.CatalogRecord,
) -> None:
    _require(session_target is not None, "session_target source binding is incomplete")
    _require(
        session_selector_commitment is not None,
        "session_target selector binding is incomplete",
    )
    witness = record.session_identity
    _require(
        witness is not None,
        "session_target source record lacks receipt-bound identity evidence",
    )
    assert witness is not None
    effective = witness.effective_commitments
    _require(
        record.content_commitment is not None,
        "session_target source record lacks a content commitment",
    )
    if len(effective) != 1:
        identity_case = "unresolved"
        expected_ref = str(
            identity.derive_ref(
                RefType.SESSION,
                {
                    "host_ref": host_ref,
                    "unresolved_record_commitment": record.content_commitment,
                },
            )
        )
    elif effective[0] != session_selector_commitment:
        identity_case = "non_target"
        expected_ref = str(identity.derive_session_ref(effective[0]))
    else:
        identity_case = "target"
        expected_ref = session_target
    _require(
        record.coordinate.source_ref == expected_ref,
        "session_target source record identity does not match receipt-bound evidence",
    )
    observed = (
        record.accounting_class,
        record.exclusion_reason,
        getattr(record.gap, "reason", None),
        getattr(record.gap, "stage", None),
    )
    if identity_case == "unresolved":
        classification_ok = observed == _UNRESOLVED_CLASSIFICATION
    elif identity_case == "non_target":
        classification_ok = observed == _NON_TARGET_CLASSIFICATION
    else:
        classification_ok = not (
            (
                record.accounting_class is catalog.AccountingClass.STRUCTURALLY_EXCLUDED
                and record.exclusion_reason
                is catalog.StructuralExclusionReason.SOURCE_POLICY_EXCLUDED
            )
            or (
                record.accounting_class is catalog.AccountingClass.EXPLICIT_GAP
                and record.gap is not None
                and record.gap.reason in _TARGET_FORBIDDEN_GAP_REASONS
            )
        )
    _require(
        classification_ok,
        "session_target source record has an identity-inconsistent classification",
    )


def validate_session_record_binding(
    identity: IdentityKey,
    *,
    active: bool,
    host_ref: str,
    session_target: str | None,
    session_selector_commitment: str | None,
    record: catalog.CatalogRecord,
) -> None:
    validator = {False: _validate_inactive, True: _validate_active}[active]
    validator(
        identity,
        host_ref=host_ref,
        session_target=session_target,
        session_selector_commitment=session_selector_commitment,
        record=record,
    )
