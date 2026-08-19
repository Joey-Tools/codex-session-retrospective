#!/usr/bin/env -S python3 -I -B -S
"""Build and verify the closed unittest inventory shared by CI shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import keyword
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import NamedTuple
import unittest
from collections.abc import Iterable, Sequence

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
TEST_ROOT = ROOT / "tests"
sys.path.insert(0, str(SCRIPTS))

from test_inventory_loader import ClosedTestDiscoveryError, ClosedTestLoader  # noqa: E402
from test_inventory_source import (  # noqa: E402
    SourceSnapshotError,
    hash_test_source,
    validate_source_sha256,
)


DARWIN_SECURITY_ATTRIBUTE = "_codex_darwin_security_contract"
MANIFEST_SCHEMA = "codex-session-retrospective-test-inventory-v3"
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_TEST_COUNT = 10_000
MAX_TEST_ID_BYTES = 1_024
MAX_TEST_SOURCE_COUNT = 512
MAX_SOURCE_PATH_BYTES = 512
MAX_MODULE_NAME_BYTES = 512
MAX_TEST_SOURCE_BYTES = 4 * 1024 * 1024
MAX_TEST_SOURCE_TOTAL_BYTES = 64 * 1024 * 1024
MAX_SOURCE_TREE_ENTRIES = 20_000
MAX_SUITE_NODES = 20_000
MAX_SHARDS = 16


class TestInventoryError(ValueError):
    """Raised when discovery or a persisted inventory violates the contract."""


class TestSource(NamedTuple):
    path: str
    module: str
    sha256: str


def _bounded_utf8(value: object, *, label: str, limit: int) -> str:
    if type(value) is not str or not value:
        raise TestInventoryError(f"{label} must be a non-empty string")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise TestInventoryError(f"{label} must be valid UTF-8") from exc
    if len(encoded) > limit:
        raise TestInventoryError(f"{label} exceeds the byte limit")
    return value


def _validate_test_id(test_id: object) -> str:
    return _bounded_utf8(test_id, label="test id", limit=MAX_TEST_ID_BYTES)


def _validate_module_name(module: object) -> str:
    value = _bounded_utf8(module, label="test module", limit=MAX_MODULE_NAME_BYTES)
    parts = value.split(".")
    if any(not part.isidentifier() or keyword.iskeyword(part) for part in parts):
        raise TestInventoryError("test source path is not a valid module path")
    return value


def _source_from_path(path: object, sha256: object) -> TestSource:
    value = _bounded_utf8(path, label="test source path", limit=MAX_SOURCE_PATH_BYTES)
    pure = PurePosixPath(value)
    if (
        pure.is_absolute()
        or pure.as_posix() != value
        or any(part in {"", ".", ".."} for part in pure.parts)
        or pure.suffix != ".py"
        or not pure.name.startswith("test_")
    ):
        raise TestInventoryError("test source path is not canonical test_*.py")
    module = _validate_module_name(".".join((*pure.parts[:-1], pure.stem)))
    try:
        digest = validate_source_sha256(sha256)
    except SourceSnapshotError as exc:
        raise TestInventoryError(str(exc)) from exc
    return TestSource(value, module, digest)


def validate_test_ids(value: object) -> tuple[str, ...]:
    if type(value) not in (list, tuple):
        raise TestInventoryError("test_ids must be an array")
    if not value or len(value) > MAX_TEST_COUNT:
        raise TestInventoryError("test_ids count is outside the supported range")
    test_ids = tuple(_validate_test_id(item) for item in value)
    if len(test_ids) != len(set(test_ids)):
        raise TestInventoryError("test_ids contains duplicates")
    if test_ids != tuple(sorted(test_ids)):
        raise TestInventoryError("test_ids must be sorted")
    return test_ids


def validate_test_sources(value: object) -> tuple[TestSource, ...]:
    if type(value) not in (list, tuple):
        raise TestInventoryError("test_sources must be an array")
    if not value or len(value) > MAX_TEST_SOURCE_COUNT:
        raise TestInventoryError("test_sources count is outside the supported range")
    sources: list[TestSource] = []
    for item in value:
        if isinstance(item, TestSource):
            path, module, sha256 = item
        elif type(item) is dict and set(item) == {"path", "module", "sha256"}:
            path, module, sha256 = item["path"], item["module"], item["sha256"]
        else:
            raise TestInventoryError("test_sources does not use the closed schema")
        expected = _source_from_path(path, sha256)
        if module != expected.module:
            raise TestInventoryError("test source path and module disagree")
        sources.append(expected)
    normalized = tuple(sources)
    if len({source.path for source in normalized}) != len(normalized):
        raise TestInventoryError("test_sources contains duplicate paths")
    if len({source.module for source in normalized}) != len(normalized):
        raise TestInventoryError("test_sources contains duplicate modules")
    if normalized != tuple(sorted(normalized)):
        raise TestInventoryError("test_sources must be sorted")
    return normalized


def _validate_modules(value: object) -> tuple[str, ...]:
    if type(value) not in (list, tuple) or not value or len(value) > MAX_TEST_COUNT:
        raise TestInventoryError("discovered test modules must be a non-empty array")
    modules = tuple(_validate_module_name(item) for item in value)
    if len(modules) != len(set(modules)) or modules != tuple(sorted(modules)):
        raise TestInventoryError("discovered test modules must be sorted and unique")
    return modules


def discover_test_sources(test_root: Path = TEST_ROOT) -> tuple[TestSource, ...]:
    try:
        root_metadata = test_root.lstat()
    except OSError as exc:
        raise TestInventoryError("cannot inspect the test source root") from exc
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise TestInventoryError("test source root must be a real directory")

    sources: list[TestSource] = []
    entry_count = 0
    source_bytes = 0
    pending = [test_root]
    while pending:
        current = pending.pop()
        directories: list[Path] = []
        try:
            iterator = os.scandir(current)
        except OSError as exc:
            raise TestInventoryError("cannot enumerate the test source tree") from exc
        with iterator:
            for entry in iterator:
                entry_count += 1
                if entry_count > MAX_SOURCE_TREE_ENTRIES:
                    raise TestInventoryError("test source tree exceeds the entry limit")
                try:
                    if entry.is_symlink():
                        raise TestInventoryError(
                            "test source tree contains a symlink entry"
                        )
                    if entry.is_dir(follow_symlinks=False):
                        directories.append(Path(entry.path))
                        continue
                    is_file = entry.is_file(follow_symlinks=False)
                except OSError as exc:
                    raise TestInventoryError(
                        "cannot inspect a test source entry"
                    ) from exc
                if not (entry.name.startswith("test_") and entry.name.endswith(".py")):
                    continue
                if not is_file:
                    raise TestInventoryError("test source must be a regular file")
                path = Path(entry.path)
                relative = path.relative_to(test_root)
                try:
                    digest, size = hash_test_source(
                        path, maximum_bytes=MAX_TEST_SOURCE_BYTES
                    )
                except SourceSnapshotError as exc:
                    raise TestInventoryError(str(exc)) from exc
                source_bytes += size
                if source_bytes > MAX_TEST_SOURCE_TOTAL_BYTES:
                    raise TestInventoryError(
                        "test source inventory exceeds the aggregate byte limit"
                    )
                source = _source_from_path(relative.as_posix(), digest)
                for depth in range(1, len(relative.parts)):
                    package = (
                        test_root.joinpath(*relative.parts[:depth]) / "__init__.py"
                    )
                    try:
                        package_metadata = package.lstat()
                    except OSError as exc:
                        raise TestInventoryError(
                            "nested test source directory is not a package"
                        ) from exc
                    if not stat.S_ISREG(package_metadata.st_mode):
                        raise TestInventoryError(
                            "nested test source package marker must be a regular file"
                        )
                sources.append(source)
                if len(sources) > MAX_TEST_SOURCE_COUNT:
                    raise TestInventoryError(
                        "test source inventory exceeds the source limit"
                    )
        pending.extend(sorted(directories, reverse=True))
    sources.sort()
    return validate_test_sources(sources)


def _flatten_suite(suite: unittest.TestSuite) -> tuple[unittest.TestCase, ...]:
    tests: list[unittest.TestCase] = []
    stack = [iter(suite)]
    suite_nodes = 1
    while stack:
        try:
            item = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        if isinstance(item, unittest.TestSuite):
            suite_nodes += 1
            if suite_nodes > MAX_SUITE_NODES:
                raise TestInventoryError("test suite nesting exceeds the node limit")
            stack.append(iter(item))
            continue
        if not isinstance(item, unittest.TestCase):
            raise TestInventoryError("test discovery returned an unsupported object")
        if isinstance(item, unittest.loader._FailedTest):
            raise TestInventoryError("test discovery returned unittest _FailedTest")
        tests.append(item)
        if len(tests) > MAX_TEST_COUNT:
            raise TestInventoryError("test discovery exceeds the test count limit")
    return tuple(tests)


def _test_method(test: unittest.TestCase) -> object | None:
    method_name = getattr(test, "_testMethodName", None)
    return getattr(test, method_name, None) if type(method_name) is str else None


def _is_darwin_security_test(test: unittest.TestCase) -> bool:
    return getattr(_test_method(test), DARWIN_SECURITY_ATTRIBUTE, False) is True


def _is_skip_placeholder(test: unittest.TestCase) -> bool:
    return bool(
        getattr(type(test), "__unittest_skip__", False)
        or getattr(_test_method(test), "__unittest_skip__", False)
    )


def _inventory_details(
    tests: Iterable[unittest.TestCase], *, platform: str | None = None
) -> tuple[tuple[unittest.TestCase, ...], tuple[str, ...], tuple[str, ...]]:
    active_platform = sys.platform if platform is None else platform
    pairs: list[tuple[str, unittest.TestCase]] = []
    modules: set[str] = set()
    observed_count = 0
    for test in tests:
        if not isinstance(test, unittest.TestCase):
            raise TestInventoryError("test discovery returned an unsupported object")
        observed_count += 1
        if observed_count > MAX_TEST_COUNT:
            raise TestInventoryError("test discovery exceeds the test count limit")
        modules.add(_validate_module_name(type(test).__module__))
        if active_platform != "darwin" and _is_darwin_security_test(test):
            continue
        if _is_skip_placeholder(test):
            raise TestInventoryError(
                "test discovery returned a skipped test placeholder"
            )
        pairs.append((_validate_test_id(test.id()), test))
    pairs.sort(key=lambda pair: pair[0])
    test_ids = validate_test_ids([test_id for test_id, _ in pairs])
    discovered_modules = _validate_modules(sorted(modules))
    return tuple(test for _, test in pairs), test_ids, discovered_modules


def inventory_from_tests(
    tests: Iterable[unittest.TestCase], *, platform: str | None = None
) -> tuple[tuple[unittest.TestCase, ...], tuple[str, ...]]:
    ordered, test_ids, _ = _inventory_details(tests, platform=platform)
    return ordered, test_ids


def inventory_from_suite(
    suite: unittest.TestSuite, *, platform: str | None = None
) -> tuple[tuple[unittest.TestCase, ...], tuple[str, ...]]:
    return inventory_from_tests(_flatten_suite(suite), platform=platform)


def require_source_module_coverage(
    observed_modules: Sequence[str], sources: Sequence[TestSource]
) -> None:
    observed = _validate_modules(observed_modules)
    expected = tuple(source.module for source in validate_test_sources(sources))
    if observed != expected:
        missing = len(set(expected) - set(observed))
        unexpected = len(set(observed) - set(expected))
        raise TestInventoryError(
            "test source modules do not match discovery "
            f"(missing={missing}, unexpected={unexpected})"
        )


def discover_test_inventory(
    test_root: Path = TEST_ROOT, *, platform: str | None = None
) -> tuple[tuple[unittest.TestCase, ...], tuple[str, ...], tuple[TestSource, ...]]:
    sources = discover_test_sources(test_root)
    try:
        suite = ClosedTestLoader().discover(str(test_root))
    except ClosedTestDiscoveryError as exc:
        raise TestInventoryError(str(exc)) from exc
    tests, test_ids, modules = _inventory_details(
        _flatten_suite(suite), platform=platform
    )
    require_source_module_coverage(modules, sources)
    if discover_test_sources(test_root) != sources:
        raise TestInventoryError("test source inventory changed during discovery")
    return tests, test_ids, sources


def manifest_bytes(
    test_ids: Sequence[str], test_sources: Sequence[TestSource]
) -> bytes:
    validated_ids = validate_test_ids(test_ids)
    validated_sources = validate_test_sources(test_sources)
    payload = {
        "schema": MANIFEST_SCHEMA,
        "test_ids": list(validated_ids),
        "test_sources": [source._asdict() for source in validated_sources],
    }
    encoded = (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("ascii")
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise TestInventoryError("test inventory manifest exceeds the byte limit")
    return encoded


def write_test_manifest(
    test_ids: Sequence[str],
    test_sources: Sequence[TestSource],
    manifest_path: Path,
    digest_path: Path,
) -> str:
    encoded = manifest_bytes(test_ids, test_sources)
    digest = hashlib.sha256(encoded).hexdigest()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(encoded)
    digest_path.write_bytes(digest.encode("ascii") + b"\n")
    return digest


def _read_bounded(path: Path, limit: int, label: str) -> bytes:
    try:
        with path.open("rb") as handle:
            value = handle.read(limit + 1)
    except OSError as exc:
        raise TestInventoryError(f"cannot read {label}") from exc
    if len(value) > limit:
        raise TestInventoryError(f"{label} exceeds the byte limit")
    return value


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise TestInventoryError("test inventory contains duplicate JSON keys")
        result[key] = value
    return result


def load_test_manifest(
    manifest_path: Path, digest_path: Path
) -> tuple[tuple[str, ...], tuple[TestSource, ...]]:
    encoded = _read_bounded(manifest_path, MAX_MANIFEST_BYTES, "test manifest")
    digest_bytes = _read_bounded(digest_path, 65, "test manifest digest")
    if (
        len(digest_bytes) != 65
        or digest_bytes[-1:] != b"\n"
        or any(byte not in b"0123456789abcdef" for byte in digest_bytes[:-1])
    ):
        raise TestInventoryError("test manifest digest is not canonical SHA-256")
    if hashlib.sha256(encoded).hexdigest().encode("ascii") != digest_bytes[:-1]:
        raise TestInventoryError("test manifest digest does not match")
    try:
        payload = json.loads(encoded.decode("ascii"), object_pairs_hook=_closed_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TestInventoryError("test inventory is not valid canonical JSON") from exc
    expected_keys = {"schema", "test_ids", "test_sources"}
    if type(payload) is not dict or set(payload) != expected_keys:
        raise TestInventoryError("test inventory does not use the closed schema")
    if payload["schema"] != MANIFEST_SCHEMA:
        raise TestInventoryError("test inventory schema is unsupported")
    test_ids = validate_test_ids(payload["test_ids"])
    test_sources = validate_test_sources(payload["test_sources"])
    if encoded != manifest_bytes(test_ids, test_sources):
        raise TestInventoryError("test inventory JSON is not canonical")
    return test_ids, test_sources


def require_matching_inventory(
    observed_ids: Sequence[str], expected_ids: Sequence[str]
) -> None:
    observed = validate_test_ids(observed_ids)
    expected = validate_test_ids(expected_ids)
    if observed != expected:
        missing = len(set(expected) - set(observed))
        unexpected = len(set(observed) - set(expected))
        raise TestInventoryError(
            "test discovery diverges from manifest "
            f"(missing={missing}, unexpected={unexpected})"
        )


def require_matching_sources(
    observed_sources: Sequence[TestSource], expected_sources: Sequence[TestSource]
) -> None:
    observed = validate_test_sources(observed_sources)
    expected = validate_test_sources(expected_sources)
    if observed != expected:
        missing = len(set(expected) - set(observed))
        unexpected = len(set(observed) - set(expected))
        raise TestInventoryError(
            "test source inventory diverges from manifest "
            f"(missing={missing}, unexpected={unexpected})"
        )


def result_is_complete(result: unittest.TestResult, *, expected_count: int) -> bool:
    return (
        result.testsRun == expected_count
        and not result.skipped
        and not result.expectedFailures
        and not result.unexpectedSuccesses
        and result.wasSuccessful()
    )


def validate_shard_dimensions(shard_index: int, shard_count: int) -> None:
    if not isinstance(shard_count, int) or isinstance(shard_count, bool):
        raise TestInventoryError("shard count must be an integer")
    if not 2 <= shard_count <= MAX_SHARDS:
        raise TestInventoryError("shard count is outside the supported range")
    if not isinstance(shard_index, int) or isinstance(shard_index, bool):
        raise TestInventoryError("shard index must be an integer")
    if not 0 <= shard_index < shard_count:
        raise TestInventoryError("shard index is outside the shard count")


def shard_for_test_id(test_id: str, shard_count: int) -> int:
    validated = _validate_test_id(test_id)
    validate_shard_dimensions(0, shard_count)
    digest = hashlib.sha256(validated.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % shard_count


def select_test_shard(
    tests: Sequence[unittest.TestCase],
    test_ids: Sequence[str],
    *,
    shard_index: int,
    shard_count: int,
) -> list[unittest.TestCase]:
    validate_shard_dimensions(shard_index, shard_count)
    ordered = tuple(tests)
    captured_ids = validate_test_ids(test_ids)
    if len(ordered) != len(captured_ids):
        raise TestInventoryError("captured test IDs do not match test objects")
    return [
        test
        for test_id, test in zip(captured_ids, ordered, strict=True)
        if shard_for_test_id(test_id, shard_count) == shard_index
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--digest", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if sys.version_info[:2] != (3, 13):
        raise SystemExit("test inventory generation requires Python 3.13")
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise SystemExit("invoke test inventory generation with python3 -I -B -S")
    args = build_parser().parse_args(argv)
    sys.path.insert(0, str(ROOT))
    try:
        _, test_ids, test_sources = discover_test_inventory()
        digest = write_test_manifest(test_ids, test_sources, args.manifest, args.digest)
    except TestInventoryError as exc:
        raise SystemExit(str(exc)) from None
    print(
        f"Wrote {len(test_ids)} test IDs from {len(test_sources)} sources "
        f"with SHA-256 {digest}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
