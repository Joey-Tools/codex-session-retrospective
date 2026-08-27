#!/usr/bin/env -S python3 -I -B -S
"""Discover and run every marked Darwin security contract under Python 3.13."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = ROOT / "tests"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from ci_runtime import CiRuntimeError, require_owner_controlled_python  # noqa: E402
from test_inventory_loader import ClosedTestLoader  # noqa: E402
from tests.darwin_security import DARWIN_SECURITY_ATTRIBUTE  # noqa: E402


EXPECTED_DARWIN_SECURITY_TEST_IDS = (
    "tests.test_retrospective_v2_identity_io.SafeIoTests."
    "test_darwin_ancestor_acl_drift_during_open_is_rejected",
    "tests.test_retrospective_v2_identity_io.SafeIoTests."
    "test_darwin_bounded_read_rejects_late_acl_policy_change",
    "tests.test_retrospective_v2_identity_io.SafeIoTests."
    "test_darwin_creation_clears_inherited_extended_acls",
    "tests.test_retrospective_v2_identity_io.SafeIoTests."
    "test_darwin_existing_owner_only_paths_reject_extended_acls",
    "tests.test_retrospective_v2_identity_io.SafeIoTests."
    "test_darwin_writable_ancestor_acl_is_rejected",
    "tests.test_retrospective_v2_publication_transaction."
    "DurablePublicationTests."
    "test_history_reader_and_publisher_reject_config_extended_acl",
    "tests.test_retrospective_v2_publication_transaction."
    "DurablePublicationTests."
    "test_history_reader_and_publisher_reject_late_config_acl",
    "tests.test_retrospective_v2_source_transport.SourceTransportProtocolTests."
    "test_committed_program_snapshot_rejects_extended_acl",
    "tests.test_retrospective_v2_source_transport.SourceTransportProtocolTests."
    "test_program_hash_rejects_extended_acl_and_late_acl_drift",
    "tests.test_retrospective_v2_source_transport.SourceTransportProtocolTests."
    "test_remote_helper_launch_rejects_snapshot_extended_acl",
    "tests.test_retrospective_v2_source_transport.SourceTransportProtocolTests."
    "test_source_identity_ignores_non_policy_flags",
    "tests.test_retrospective_v2_source_transport.SourceTransportProtocolTests."
    "test_source_scan_rejects_acl_access_policy_change",
    "tests.test_session_retrospective.SessionRetrospectiveTests."
    "test_history_git_rejects_extended_acl_repository",
    "tests.test_session_retrospective.SessionRetrospectiveTests."
    "test_remote_probe_private_output_cleans_file_acl_drift_by_bound_identity",
    "tests.test_session_retrospective.SessionRetrospectiveTests."
    "test_remote_probe_private_output_rejects_extended_acl_parent",
    "tests.test_session_retrospective_v2_cli.CliContractTests."
    "test_cutover_record_rejects_extended_acl",
)


def _flatten(suite: unittest.TestSuite) -> list[unittest.TestCase]:
    tests: list[unittest.TestCase] = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            tests.extend(_flatten(item))
        else:
            tests.append(item)
    return tests


def discover_darwin_security_tests() -> list[unittest.TestCase]:
    """Return the exact discovered inventory carrying the shared marker."""

    discovered = ClosedTestLoader().discover(str(TEST_ROOT))
    selected = [
        test
        for test in _flatten(discovered)
        if getattr(
            getattr(test, test._testMethodName),  # noqa: SLF001
            DARWIN_SECURITY_ATTRIBUTE,
            False,
        )
    ]
    selected.sort(key=lambda test: test.id())
    test_ids = [test.id() for test in selected]
    if not test_ids:
        raise RuntimeError("Darwin security test inventory is empty")
    if len(test_ids) != len(set(test_ids)):
        raise RuntimeError("Darwin security test inventory contains duplicates")
    canonical_ids = tuple(
        test_id if test_id.startswith("tests.") else f"tests.{test_id}"
        for test_id in test_ids
    )
    if canonical_ids != EXPECTED_DARWIN_SECURITY_TEST_IDS:
        raise RuntimeError("Darwin security test inventory does not match policy")
    return selected


def result_is_complete(result: unittest.TestResult, *, expected_count: int) -> bool:
    """Accept only a fully executed, unskipped security inventory."""

    return (
        result.testsRun == expected_count
        and not result.skipped
        and not result.expectedFailures
        and not result.unexpectedSuccesses
        and result.wasSuccessful()
    )


def main() -> int:
    if sys.version_info[:2] != (3, 13):
        raise SystemExit("Darwin security tests require Python 3.13")
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise SystemExit("invoke Darwin security tests with python3 -I -B -S")
    if sys.platform != "darwin":
        raise SystemExit("Darwin security tests require macOS")
    try:
        require_owner_controlled_python()
    except CiRuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    selected = discover_darwin_security_tests()
    print(f"Selected {len(selected)} Darwin security tests", flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(selected))
    return 0 if result_is_complete(result, expected_count=len(selected)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
