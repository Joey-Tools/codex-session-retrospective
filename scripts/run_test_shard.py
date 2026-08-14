#!/usr/bin/env -S python3 -I -B -S
"""Run one stable, disjoint shard of the repository's unittest inventory."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = ROOT / "tests"
MAX_SHARDS = 16


def shard_for_test_id(test_id: str, shard_count: int) -> int:
    if not isinstance(test_id, str) or not test_id:
        raise ValueError("test id must be a non-empty string")
    if not isinstance(shard_count, int) or isinstance(shard_count, bool):
        raise ValueError("shard count must be an integer")
    if not 2 <= shard_count <= MAX_SHARDS:
        raise ValueError("shard count is outside the supported range")
    digest = hashlib.sha256(test_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % shard_count


def _flatten(suite: unittest.TestSuite) -> list[unittest.TestCase]:
    tests: list[unittest.TestCase] = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            tests.extend(_flatten(item))
        else:
            tests.append(item)
    return tests


def select_test_shard(
    tests: list[unittest.TestCase],
    *,
    shard_index: int,
    shard_count: int,
) -> list[unittest.TestCase]:
    if not isinstance(shard_index, int) or isinstance(shard_index, bool):
        raise ValueError("shard index must be an integer")
    if not 0 <= shard_index < shard_count:
        raise ValueError("shard index is outside the shard count")
    ordered = sorted(tests, key=lambda test: test.id())
    test_ids = [test.id() for test in ordered]
    if len(test_ids) != len(set(test_ids)):
        raise ValueError("test discovery returned duplicate test ids")
    return [
        test
        for test in ordered
        if shard_for_test_id(test.id(), shard_count) == shard_index
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--list-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    if sys.version_info[:2] != (3, 13):
        raise SystemExit("test shards require Python 3.13")
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise SystemExit("invoke test shards with python3 -I -B -S")
    args = build_parser().parse_args(argv)
    sys.path.insert(0, str(ROOT))
    discovered = unittest.defaultTestLoader.discover(str(TEST_ROOT))
    all_tests = _flatten(discovered)
    selected = select_test_shard(
        all_tests,
        shard_index=args.shard_index,
        shard_count=args.shard_count,
    )
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
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
