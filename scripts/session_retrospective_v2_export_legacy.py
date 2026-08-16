"""Path-only retained-export migration compatibility."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import os

from retrospective_v2 import export as export_api, safe_io
import session_retrospective_v2_export_records as records


def claim_export_destination(
    run_dir: Path,
    output: Path,
    publication_role: str,
    *,
    cleanup_roots: Sequence[str],
    read_json: records.JsonReader,
) -> Path:
    """Preserve path-only migration behavior outside the strict export path."""

    output = export_api.normalize_retained_export_destination(output)
    records.reject_destination(run_dir, output, cleanup_roots=cleanup_roots)
    requested = records.destination_claim(output, publication_role)
    legacy_path = run_dir / records.LEGACY_EXPORT_DESCRIPTOR_NAME
    claim_path = run_dir / records.EXPORT_DESTINATION_CLAIM_NAME
    result_path = run_dir / records.EXPORT_DESCRIPTOR_NAME
    for path in (legacy_path, claim_path, result_path):
        safe_io.recover_atomic_create(path)
    claimed = (
        records.load_destination_claim(run_dir, read_json=read_json)
        if os.path.lexists(claim_path)
        else requested
    )
    if not os.path.lexists(legacy_path):
        try:
            safe_io.atomic_create_json(
                legacy_path,
                records.reservation(
                    export_api.normalize_retained_export_destination(claimed["output"]),
                    claimed["publication_role"],
                ),
            )
        except FileExistsError:
            pass
    legacy_claim, legacy_descriptor = records.load_legacy_binding(
        run_dir, read_json=read_json
    )
    if os.path.lexists(claim_path):
        claimed = records.load_destination_claim(run_dir, read_json=read_json)
    else:
        try:
            safe_io.atomic_create_json(claim_path, legacy_claim)
        except FileExistsError:
            claimed = records.load_destination_claim(run_dir, read_json=read_json)
        else:
            claimed = legacy_claim
    if legacy_descriptor is not None and not records.same(claimed, legacy_claim):
        records.conflict()
    if not records.same(claimed, requested):
        records.conflict()
    if os.path.lexists(result_path):
        existing = records.load_descriptor_at(result_path, read_json=read_json)
        if not records.same(records.normalized_descriptor_claim(existing), requested):
            records.conflict()
    return output
