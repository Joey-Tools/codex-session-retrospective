"""State mutation and terminal validation for expired raw cleanup."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .contracts import RunStage, SourceCellStatus
from .orchestrator_support import InvalidTransitionError


def complete_expired_raw_cleanup(
    state: dict[str, Any],
    *,
    cleanup_receipt: Mapping[str, Any],
    finalized_at: str,
) -> None:
    state["jobs"] = {}
    state["extracted_turns"] = {}
    state["episodes"] = []
    state["retained_export"] = None
    state["actions"] = {}
    state["source"].update(
        {
            "catalog": None,
            "materialization": None,
            "model_era_by_unit": {},
            "model_eras_by_session": {},
            "reassembly": {},
            "shards": {},
        }
    )
    for cells in state["source"]["cells"].values():
        for cell in cells.values():
            cell.pop("accepted_input_digest", None)
            cell.update(
                {
                    "lease_ref": None,
                    "manifest": None,
                    "metrics": {"byte_count": 0, "record_count": 0},
                    "payloads": {},
                    "snapshot_ref": None,
                    "status": SourceCellStatus.GAP.value,
                    "transport_receipt": None,
                    "transport_receipt_ref": None,
                    "transport_status": SourceCellStatus.GAP.value,
                }
            )
    publication = state["publication"]
    publication.update(
        {
            "bundle_digest": None,
            "cleanup_receipt": dict(cleanup_receipt),
            "durable_state": None,
            "exported_at": None,
            "finalized_at": finalized_at,
            "phase": "expired_cleanup_complete",
            "retention_deadline": None,
        }
    )
    publication.pop("publication_claim", None)


def validate_completed_aborted_cleanup_claim(claim: Mapping[str, Any]) -> None:
    bundle_digest = claim.get("bundle_digest")
    publication_claim_ref = claim.get("publication_claim_ref")
    if (
        claim.get("durable_commit") is not None
        or claim.get("phase_before") != "aborted"
        or claim.get("stage") != RunStage.EXPORT.value
        or not isinstance(bundle_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", bundle_digest) is None
        or not isinstance(publication_claim_ref, str)
        or re.fullmatch(
            r"publication_claim_v2:[0-9a-f]{64}",
            publication_claim_ref,
        )
        is None
    ):
        raise InvalidTransitionError("aborted cleanup claim lost publication authority")
