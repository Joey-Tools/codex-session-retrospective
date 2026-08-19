#!/usr/bin/env -S python3 -I -B -S
"""Run one verified shard of the canonical repository test inventory."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from test_inventory import (  # noqa: E402
    TestInventoryError,
    discover_test_inventory,
    load_test_manifest,
    require_matching_inventory,
    require_matching_sources,
    result_is_complete,
    select_test_shard,
    validate_shard_dimensions,
)


def harden_child_python_environment() -> None:
    """Prevent subprocess tests from writing bytecode into the source tree."""

    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--digest", type=Path, required=True)
    parser.add_argument("--list-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    if sys.version_info[:2] != (3, 13):
        raise SystemExit("test shards require Python 3.13")
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise SystemExit("invoke test shards with python3 -I -B -S")
    harden_child_python_environment()
    args = build_parser().parse_args(argv)
    try:
        validate_shard_dimensions(args.shard_index, args.shard_count)
        expected_ids, expected_sources = load_test_manifest(args.manifest, args.digest)
    except TestInventoryError as exc:
        raise SystemExit(str(exc)) from None
    sys.path.insert(0, str(ROOT))
    try:
        all_tests, observed_ids, observed_sources = discover_test_inventory()
        require_matching_inventory(observed_ids, expected_ids)
        require_matching_sources(observed_sources, expected_sources)
        selected = select_test_shard(
            all_tests,
            observed_ids,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
        )
    except TestInventoryError as exc:
        raise SystemExit(str(exc)) from None
    if not selected:
        raise SystemExit("selected test shard is empty")
    print(
        f"Selected {len(selected)} of {len(all_tests)} tests for "
        f"shard {args.shard_index}/{args.shard_count}",
        flush=True,
    )
    if args.list_only:
        return 0
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(selected))
    return 0 if result_is_complete(result, expected_count=len(selected)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
