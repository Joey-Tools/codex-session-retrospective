from __future__ import annotations

import argparse
from collections.abc import Callable
import copy
from contextlib import nullcontext
from dataclasses import replace
import datetime as dt
import errno
import hashlib
import json
import os
from pathlib import Path
import selectors
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from typing import Mapping
import unittest
from unittest import mock

from tests.darwin_security import darwin_security_test


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import session_retrospective_v2 as cli_module  # noqa: E402
import session_retrospective_v2_export as export_cli_api  # noqa: E402
from retrospective_v2 import (  # noqa: E402
    automation_cutover_files,
    authority,
    calibration,
    controlled_gaps,
    executable_authority,
    finalize as finalize_module,
    git_safety,
    gpg_keyring_snapshot,
    gpg_snapshot_lease,
    gpg_snapshot_recovery,
    gpg_status,
    orchestrator as orchestrator_module,
    orchestrator_support,
    process_lifecycle,
    publication_abort_authority,
    publication_abort_replay,
    publication_git_commits,
    publication_git_storage,
    publication_support,
    reporting,
    retained_export_binding,
    retained_export_coordination,
    safe_io,
    temporary_paths,
    temporary_recovery,
    transport,
)
from retrospective_v2.contracts import (  # noqa: E402
    RefType,
    RunStage,
    SourceCellStatus,
    SourceKind,
)
from retrospective_v2.checkpoints import CheckpointIntegrityError  # noqa: E402
from retrospective_v2.export import (  # noqa: E402
    ExportConflictError,
    RetainedExportError,
    export_retained_bundle,
    garbage_collect_expired_exports,
    inspect_staged_export_retention,
    release_committed_staged_export,
)
from retrospective_v2.finalize import (  # noqa: E402
    AttemptMismatchError,
    DEFAULT_PUBLISHER_UID,
    StateCorruptionError,
    LocalGitPublicationAdapter,
    PublicationRejected,
    PublicationTransaction,
    build_artifact_inventory,
)
from retrospective_v2.identity import IdentityKey  # noqa: E402
from retrospective_v2.orchestrator import (  # noqa: E402
    RetrospectiveOrchestrator,
    RunConflictError,
)
from tests.test_retrospective_v2_orchestrator import (  # noqa: E402
    TEST_HOSTS,
    authenticated_receipt,
    bind_remote_host_context_helper_fixture,
    execution_provenance,
    no_activity_manifest,
    synthesis_result,
)
from tests.test_retrospective_v2_lifecycle_calibration import (  # noqa: E402
    passing_corpus,
)


WINDOW_START = "2026-07-06T00:00:00Z"
WINDOW_END = "2026-07-07T00:00:00Z"
TARGET_REF = "refs/heads/main"


def _publication_test_temp_parent() -> str:
    private_tmp = Path("/private/tmp")
    if private_tmp.is_dir():
        return os.fspath(private_tmp)
    return tempfile.gettempdir()


def _write_synthetic_publisher_keyring(home: Path) -> None:
    """Create the smallest source keyring admitted by the snapshot contract."""

    public_keyring = home / "pubring.kbx"
    public_keyring.write_bytes(b"synthetic public keyring")
    public_keyring.chmod(0o600)
    private_keys = home / "private-keys-v1.d"
    private_keys.mkdir(mode=0o700)
    private_key = private_keys / ("A" * 40 + ".key")
    private_key.write_bytes(b"synthetic private key")
    private_key.chmod(0o600)


def run_command(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        input=input_text,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _read_process_line(
    process: subprocess.Popen[str],
    *,
    timeout_seconds: float = 10.0,
) -> str:
    assert process.stdout is not None
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout_seconds):
            raise AssertionError("fixture process did not publish its receipt")
        line = process.stdout.readline()
    if not line:
        raise AssertionError("fixture process exited before publishing its receipt")
    return line.rstrip("\r\n")


class _BoundedScandirFixture:
    def __init__(self, names: tuple[str, ...], *, max_reads: int) -> None:
        self._names = names
        self._max_reads = max_reads
        self.reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def __iter__(self):
        return self

    def __next__(self):
        if self.reads >= self._max_reads:
            raise AssertionError("directory inventory read beyond its N+1 bound")
        if self.reads >= len(self._names):
            raise StopIteration
        name = self._names[self.reads]
        self.reads += 1
        return SimpleNamespace(name=name)


class PublicationInvariantUnitTests(unittest.TestCase):
    def test_lease_setup_failure_is_not_cleanup_failure_after_bound_removal(
        self,
    ) -> None:
        failures = (
            (
                "hardening",
                mock.patch.object(
                    gpg_snapshot_lease.safe_io,
                    "harden_created_owner_only_file_descriptor",
                    side_effect=OSError(errno.EIO, "fixture hardening failed"),
                ),
            ),
            (
                "directory-fsync",
                mock.patch.object(
                    gpg_snapshot_lease.os,
                    "fsync",
                    side_effect=OSError(errno.EIO, "fixture fsync failed"),
                ),
            ),
        )
        for label, failure in failures:
            with (
                self.subTest(label=label),
                tempfile.TemporaryDirectory(
                    prefix="r-", dir=_publication_test_temp_parent()
                ) as raw,
            ):
                root = Path(raw)
                snapshot_root = root / "snapshots"
                source_root = root / "source"
                source_root.mkdir(mode=0o700)
                temporary_path: Path | None = None
                with (
                    mock.patch.object(
                        temporary_paths,
                        "local_codex_root",
                        return_value=source_root,
                    ),
                    self.assertRaises(OSError) as caught,
                ):
                    with temporary_paths.owner_only_temporary_directory(
                        root=snapshot_root,
                        prefix="g-",
                    ) as temporary:
                        temporary_path = temporary.path
                        with failure:
                            gpg_snapshot_lease.acquire_active_lease(temporary)

                self.assertIsNotNone(temporary_path)
                assert temporary_path is not None
                self.assertFalse(temporary_path.exists())
                self.assertEqual([], list(snapshot_root.iterdir()))
                self.assertIsNone(
                    temporary_paths.incomplete_cleanup_primary(caught.exception)
                )

    def test_publication_index_ignores_ambient_temporary_roots(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as raw:
            root = Path(raw)
            source_root = root / "poisoned-codex-source"
            source_root.mkdir(mode=0o700)
            source_sentinel = source_root / "source-sentinel"
            source_sentinel.write_text("unchanged", encoding="ascii")
            index_root = root / "publication-index-root"
            observed_index_paths: list[Path] = []

            subject = publication_git_commits.LocalGitCommitOperations()
            subject._signing_key = "fixture-signing-key"
            subject._expected_signer_uid = "Fixture <fixture@example.invalid>"
            subject._validate_signing_identity = lambda: None
            subject._validate_publication_commit = lambda **_kwargs: None

            def fake_git(arguments, **kwargs):
                command = arguments[0]
                index_environment = kwargs.get("extra_env", {})
                if "GIT_INDEX_FILE" in index_environment:
                    index_path = Path(index_environment["GIT_INDEX_FILE"])
                    index_path.unlink(missing_ok=True)
                    index_path.write_bytes(b"fixture index\n")
                    os.chmod(index_path, 0o644)
                    observed_index_paths.append(index_path)
                outputs = {
                    "hash-object": ("a" * 40 + "\n").encode("ascii"),
                    "write-tree": ("b" * 40 + "\n").encode("ascii"),
                    "commit-tree": ("c" * 40 + "\n").encode("ascii"),
                }
                return subprocess.CompletedProcess(
                    arguments,
                    0,
                    stdout=outputs.get(command, b""),
                    stderr=b"",
                )

            subject._git = fake_git
            unit = {
                "artifacts": {
                    name: b"{}\n"
                    for name in publication_support.ARTIFACT_NAMES_BYTEWISE
                },
                "destination": "runs/weekly/window/run",
                "publication_role": "standalone",
            }
            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "TEMP": str(source_root),
                        "TMP": str(source_root),
                        "TMPDIR": str(source_root),
                    },
                ),
                mock.patch.object(tempfile, "tempdir", str(source_root)),
                mock.patch.object(
                    temporary_paths,
                    "PUBLICATION_INDEX_TEMP_ROOT",
                    index_root,
                ),
                mock.patch.object(
                    temporary_paths,
                    "local_codex_root",
                    return_value=source_root,
                ),
            ):
                commit = subject._create_signed_publication_commit(
                    parent="d" * 40,
                    unit=unit,
                    ordinal=0,
                    attempt_ref="attempt_ref_v2:" + "e" * 64,
                    plan_digest="f" * 64,
                )

            self.assertEqual("c" * 40, commit)
            self.assertTrue(observed_index_paths)
            self.assertTrue(
                all(path.parent.parent == index_root for path in observed_index_paths)
            )
            self.assertTrue(all(not path.exists() for path in observed_index_paths))
            self.assertEqual("unchanged", source_sentinel.read_text(encoding="ascii"))
            self.assertEqual([source_sentinel], list(source_root.iterdir()))

    def test_gpg_no_options_launcher_is_fixed_and_executable(self) -> None:
        launcher = gpg_status.no_options_launcher_authority()

        self.assertEqual(
            hashlib.sha256(gpg_status._NO_OPTIONS_LAUNCHER).hexdigest(),
            launcher.sha256,
        )
        self.assertEqual(0, launcher.executable.mode & 0o022)
        self.assertNotEqual(0, launcher.executable.mode & 0o100)

    def test_config_free_keyring_snapshot_excludes_source_configuration(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as raw:
            root = Path(raw)
            source = root / "publisher-keyring"
            source.mkdir(mode=0o700)
            (source / "pubring.kbx").write_bytes(b"synthetic public keyring")
            private = source / "private-keys-v1.d"
            private.mkdir(mode=0o700)
            private_key = private / ("A" * 40 + ".key")
            private_key.write_bytes(b"synthetic private key")
            private_key.chmod(0o600)
            for name in ("common.conf", "gpg.conf", "gpg-agent.conf"):
                (source / name).write_text("malicious fixture\n", encoding="ascii")
            snapshot_root = root / "snapshot-root"
            source_root = root / "retrospective-source-root"

            with (
                mock.patch.object(
                    temporary_paths,
                    "PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT",
                    snapshot_root,
                ),
                mock.patch.object(
                    temporary_paths,
                    "local_codex_root",
                    return_value=source_root,
                ),
            ):
                with gpg_keyring_snapshot.config_free_keyring_snapshot(
                    source
                ) as snapshot:
                    snapshot_path = snapshot
                    self.assertEqual(
                        b"synthetic public keyring",
                        (snapshot / "pubring.kbx").read_bytes(),
                    )
                    self.assertEqual(
                        b"synthetic private key",
                        (
                            snapshot / "private-keys-v1.d" / private_key.name
                        ).read_bytes(),
                    )
                    self.assertTrue(
                        all(
                            not (snapshot / name).exists()
                            for name in ("common.conf", "gpg.conf", "gpg-agent.conf")
                        )
                    )

            self.assertFalse(snapshot_path.exists())
            self.assertEqual(
                [".recovery.lock"],
                sorted(path.name for path in snapshot_root.iterdir()),
            )

    @unittest.skipUnless(os.name == "posix", "requires POSIX process cleanup")
    def test_crash_retained_keyring_and_agent_are_recovered_on_restart(self) -> None:
        with (
            tempfile.TemporaryDirectory(
                prefix="r-",
                dir=_publication_test_temp_parent(),
            ) as raw,
            tempfile.TemporaryDirectory(prefix="r-", dir="/tmp") as snapshot_raw,
        ):
            root = Path(raw)
            source = root / "k"
            source.mkdir(mode=0o700)
            _write_synthetic_publisher_keyring(source)
            snapshot_root = Path(snapshot_raw)
            source_root = root / "c"
            source_root.mkdir(mode=0o700)
            holder: subprocess.Popen[str] | None = None
            agent: subprocess.Popen[str] | None = None
            try:
                holder = subprocess.Popen(
                    [
                        sys.executable,
                        "-I",
                        "-B",
                        "-S",
                        os.fspath(ROOT / "tests/fixtures/hold_keyring_snapshot.py"),
                        os.fspath(source),
                        os.fspath(snapshot_root),
                        os.fspath(source_root),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
                stale_path = Path(_read_process_line(holder))
                self.assertTrue((stale_path / "private-keys-v1.d").is_dir())

                agent = subprocess.Popen(
                    [
                        sys.executable,
                        "-I",
                        "-B",
                        "-S",
                        os.fspath(ROOT / "tests/fixtures/fake_gpg_agent.py"),
                        os.fspath(stale_path),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
                self.assertEqual("ready", _read_process_line(agent))
                self.assertTrue((stale_path / "S.gpg-agent").is_socket())
                self.assertTrue((stale_path / "S.scdaemon").is_socket())

                os.kill(holder.pid, signal.SIGKILL)
                self.assertLess(holder.wait(timeout=5), 0)

                with (
                    mock.patch.object(
                        temporary_paths,
                        "PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT",
                        snapshot_root,
                    ),
                    mock.patch.object(
                        temporary_paths,
                        "local_codex_root",
                        return_value=source_root,
                    ),
                ):
                    with gpg_keyring_snapshot.config_free_keyring_snapshot(
                        source
                    ) as current:
                        self.assertNotEqual(stale_path, current)
                        self.assertTrue((current / "private-keys-v1.d").is_dir())

                self.assertEqual(0, agent.wait(timeout=5))
                self.assertFalse(stale_path.exists())
                self.assertEqual(
                    [".recovery.lock"],
                    sorted(path.name for path in snapshot_root.iterdir()),
                )
            finally:
                for process in (agent, holder):
                    if process is not None and process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                    if process is not None:
                        for stream in (process.stdout, process.stderr):
                            if stream is not None:
                                stream.close()

    @unittest.skipUnless(os.name == "posix", "requires POSIX lease cleanup")
    def test_active_keyring_snapshots_overlap_without_holding_the_root_lock(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory(
                prefix="r-",
                dir=_publication_test_temp_parent(),
            ) as raw,
            tempfile.TemporaryDirectory(prefix="r-", dir="/tmp") as snapshot_raw,
        ):
            root = Path(raw)
            source = root / "k"
            source.mkdir(mode=0o700)
            _write_synthetic_publisher_keyring(source)
            snapshot_root = Path(snapshot_raw)
            source_root = root / "c"
            source_root.mkdir(mode=0o700)
            holder: subprocess.Popen[str] | None = None
            try:
                holder = subprocess.Popen(
                    [
                        sys.executable,
                        "-I",
                        "-B",
                        "-S",
                        os.fspath(ROOT / "tests/fixtures/hold_keyring_snapshot.py"),
                        os.fspath(source),
                        os.fspath(snapshot_root),
                        os.fspath(source_root),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
                active_path = Path(_read_process_line(holder))
                self.assertTrue(
                    (active_path / gpg_snapshot_lease.ACTIVE_LEASE_NAME).is_file()
                )

                with (
                    mock.patch.object(
                        temporary_paths,
                        "PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT",
                        snapshot_root,
                    ),
                    mock.patch.object(
                        temporary_paths,
                        "local_codex_root",
                        return_value=source_root,
                    ),
                    mock.patch.object(
                        temporary_recovery,
                        "_RECOVERY_LOCK_SECONDS",
                        0.25,
                    ),
                ):
                    with gpg_keyring_snapshot.config_free_keyring_snapshot(
                        source
                    ) as concurrent:
                        self.assertNotEqual(active_path, concurrent)
                        self.assertTrue(active_path.is_dir())
                        self.assertTrue(
                            (
                                concurrent / gpg_snapshot_lease.ACTIVE_LEASE_NAME
                            ).is_file()
                        )
                    self.assertTrue(active_path.is_dir())

                    os.kill(holder.pid, signal.SIGKILL)
                    self.assertLess(holder.wait(timeout=5), 0)
                    with self.assertRaises(gpg_keyring_snapshot.ConfigFreeKeyringError):
                        with gpg_keyring_snapshot.config_free_keyring_snapshot(source):
                            self.fail("an unproved pre-agent crash was recovered")

                self.assertTrue(active_path.is_dir())
                self.assertFalse(
                    (active_path / gpg_snapshot_recovery.CLEANUP_PROOF_NAME).exists()
                )
            finally:
                if holder is not None and holder.poll() is None:
                    holder.kill()
                    holder.wait(timeout=5)
                if holder is not None:
                    for stream in (holder.stdout, holder.stderr):
                        if stream is not None:
                            stream.close()

    def test_snapshot_finalization_failure_is_retained_until_restart(self) -> None:
        for failure_stage in ("root-coordination", "publisher-agent"):
            with self.subTest(failure_stage=failure_stage):
                with tempfile.TemporaryDirectory(dir=ROOT) as raw:
                    root = Path(raw)
                    source = root / "publisher-keyring"
                    source.mkdir(mode=0o700)
                    _write_synthetic_publisher_keyring(source)
                    snapshot_root = root / "snapshot-root"
                    source_root = root / "source-root"
                    source_root.mkdir(mode=0o700)
                    retained: Path | None = None
                    if failure_stage == "root-coordination":
                        failure = mock.patch.object(
                            temporary_recovery.RecoveryCoordinator,
                            "acquire",
                            side_effect=temporary_recovery.TemporaryRecoveryError(
                                "fixture root coordination failed"
                            ),
                        )
                    else:
                        failure = mock.patch.object(
                            gpg_keyring_snapshot,
                            "_clean_snapshot_after_use",
                            side_effect=gpg_keyring_snapshot.ConfigFreeKeyringError(
                                "fixture publisher cleanup failed"
                            ),
                        )

                    with (
                        mock.patch.object(
                            temporary_paths,
                            "PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT",
                            snapshot_root,
                        ),
                        mock.patch.object(
                            temporary_paths,
                            "local_codex_root",
                            return_value=source_root,
                        ),
                        failure,
                        self.assertRaises(
                            gpg_keyring_snapshot.ConfigFreeKeyringError
                        ) as caught,
                    ):
                        with gpg_keyring_snapshot.config_free_keyring_snapshot(
                            source
                        ) as snapshot:
                            retained = snapshot

                    self.assertIsNotNone(retained)
                    assert retained is not None
                    self.assertTrue(retained.is_dir())
                    self.assertTrue((retained / "private-keys-v1.d").is_dir())
                    self.assertTrue(
                        (retained / gpg_snapshot_lease.ACTIVE_LEASE_NAME).is_file()
                    )
                    proof = retained / gpg_snapshot_recovery.CLEANUP_PROOF_NAME
                    self.assertEqual(
                        failure_stage == "root-coordination",
                        proof.is_file(),
                    )
                    self.assertIsNotNone(
                        temporary_paths.incomplete_cleanup_primary(caught.exception)
                    )

                    recovery_context = (
                        mock.patch.object(
                            temporary_paths,
                            "PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT",
                            snapshot_root,
                        ),
                        mock.patch.object(
                            temporary_paths,
                            "local_codex_root",
                            return_value=source_root,
                        ),
                    )
                    with recovery_context[0], recovery_context[1]:
                        if failure_stage == "root-coordination":
                            with gpg_keyring_snapshot.config_free_keyring_snapshot(
                                source
                            ):
                                pass
                        else:
                            with self.assertRaises(
                                gpg_keyring_snapshot.ConfigFreeKeyringError
                            ):
                                with gpg_keyring_snapshot.config_free_keyring_snapshot(
                                    source
                                ):
                                    self.fail(
                                        "an unproved publisher cleanup was recovered"
                                    )

                    if failure_stage == "root-coordination":
                        self.assertFalse(retained.exists())
                        self.assertEqual(
                            [".recovery.lock"],
                            sorted(path.name for path in snapshot_root.iterdir()),
                        )
                    else:
                        self.assertTrue(retained.is_dir())
                        self.assertFalse(proof.exists())

    def test_recovery_rejects_a_symlinked_activity_lease(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as raw:
            root = Path(raw)
            source = root / "publisher-keyring"
            source.mkdir(mode=0o700)
            _write_synthetic_publisher_keyring(source)
            snapshot_root = root / "snapshot-root"
            snapshot_root.mkdir(mode=0o700)
            source_root = root / "source-root"
            source_root.mkdir(mode=0o700)
            stale = snapshot_root / ("g-" + "d" * 64)
            stale.mkdir(mode=0o700)
            outside = root / "outside-lock"
            outside.write_bytes(b"outside")
            outside.chmod(0o600)
            (stale / gpg_snapshot_lease.ACTIVE_LEASE_NAME).symlink_to(outside)

            with (
                mock.patch.object(
                    temporary_paths,
                    "PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT",
                    snapshot_root,
                ),
                mock.patch.object(
                    temporary_paths,
                    "local_codex_root",
                    return_value=source_root,
                ),
                self.assertRaises(
                    gpg_keyring_snapshot.ConfigFreeKeyringError
                ) as caught,
            ):
                with gpg_keyring_snapshot.config_free_keyring_snapshot(source):
                    self.fail("a symlinked activity lease was accepted")

            self.assertTrue(stale.is_dir())
            self.assertTrue((stale / gpg_snapshot_lease.ACTIVE_LEASE_NAME).is_symlink())
            self.assertEqual(b"outside", outside.read_bytes())
            self.assertIsNotNone(
                temporary_paths.incomplete_cleanup_primary(caught.exception)
            )

    def test_restart_retains_socket_that_can_listen_after_refusal(self) -> None:
        with (
            tempfile.TemporaryDirectory(
                prefix="r-",
                dir=_publication_test_temp_parent(),
            ) as raw,
            tempfile.TemporaryDirectory(prefix="r-", dir="/tmp") as snapshot_raw,
        ):
            root = Path(raw)
            source = root / "k"
            source.mkdir(mode=0o700)
            _write_synthetic_publisher_keyring(source)
            snapshot_root = Path(snapshot_raw)
            source_root = root / "c"
            source_root.mkdir(mode=0o700)
            stale = snapshot_root / ("g-" + "a" * 64)
            stale.mkdir(mode=0o700)
            socket_path = stale / "S.gpg-agent"
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(os.fspath(socket_path))
                socket_path.chmod(0o600)

                with (
                    mock.patch.object(
                        temporary_paths,
                        "PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT",
                        snapshot_root,
                    ),
                    mock.patch.object(
                        temporary_paths,
                        "local_codex_root",
                        return_value=source_root,
                    ),
                    self.assertRaises(gpg_keyring_snapshot.ConfigFreeKeyringError),
                ):
                    with gpg_keyring_snapshot.config_free_keyring_snapshot(source):
                        self.fail("a refused socket authorized stale cleanup")

                listener.listen(4)
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                    probe.settimeout(1)
                    probe.connect(os.fspath(socket_path))
                self.assertTrue(stale.is_dir())
                self.assertTrue(socket_path.is_socket())

    def test_restart_retains_a_live_scdaemon_when_primary_is_stale(self) -> None:
        with (
            tempfile.TemporaryDirectory(dir=ROOT) as raw,
            tempfile.TemporaryDirectory(prefix="r-", dir="/tmp") as snapshot_raw,
        ):
            root = Path(raw)
            source = root / "publisher-keyring"
            source.mkdir(mode=0o700)
            _write_synthetic_publisher_keyring(source)
            snapshot_root = Path(snapshot_raw)
            source_root = root / "source-root"
            source_root.mkdir(mode=0o700)
            stale = snapshot_root / ("g-" + "d" * 64)
            stale.mkdir(mode=0o700)
            primary = stale / "S.gpg-agent"
            scdaemon = stale / "S.scdaemon"
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stale_primary:
                stale_primary.bind(os.fspath(primary))
                primary.chmod(0o600)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(os.fspath(scdaemon))
                scdaemon.chmod(0o600)
                listener.listen(4)

                with (
                    mock.patch.object(
                        temporary_paths,
                        "PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT",
                        snapshot_root,
                    ),
                    mock.patch.object(
                        temporary_paths,
                        "local_codex_root",
                        return_value=source_root,
                    ),
                    self.assertRaises(
                        gpg_keyring_snapshot.ConfigFreeKeyringError
                    ) as caught,
                ):
                    with gpg_keyring_snapshot.config_free_keyring_snapshot(source):
                        self.fail("a live auxiliary listener was abandoned")

                self.assertTrue(stale.is_dir())
                self.assertTrue(primary.is_socket())
                self.assertTrue(scdaemon.is_socket())
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                    probe.settimeout(1)
                    probe.connect(os.fspath(scdaemon))
                self.assertIsNotNone(
                    temporary_paths.incomplete_cleanup_primary(caught.exception)
                )

    def test_recovery_rejects_an_unrecognized_root_entry_without_new_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as raw:
            root = Path(raw)
            source = root / "publisher-keyring"
            source.mkdir(mode=0o700)
            _write_synthetic_publisher_keyring(source)
            snapshot_root = root / "snapshot-root"
            snapshot_root.mkdir(mode=0o700)
            source_root = root / "source-root"
            source_root.mkdir(mode=0o700)
            unexpected = snapshot_root / "unexpected"
            unexpected.write_bytes(b"retained")
            unexpected.chmod(0o600)

            with (
                mock.patch.object(
                    temporary_paths,
                    "PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT",
                    snapshot_root,
                ),
                mock.patch.object(
                    temporary_paths,
                    "local_codex_root",
                    return_value=source_root,
                ),
                self.assertRaises(
                    gpg_keyring_snapshot.ConfigFreeKeyringError
                ) as caught,
            ):
                with gpg_keyring_snapshot.config_free_keyring_snapshot(source):
                    self.fail("an unrecognized recovery entry was accepted")

            self.assertTrue(unexpected.is_file())
            self.assertEqual([], list(snapshot_root.glob("g-*")))
            self.assertIsNotNone(
                temporary_paths.incomplete_cleanup_primary(caught.exception)
            )

    def test_recovery_rejects_an_unknown_agent_socket_without_new_snapshot(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory(dir=ROOT) as raw,
            tempfile.TemporaryDirectory(prefix="r-", dir="/tmp") as snapshot_raw,
        ):
            root = Path(raw)
            source = root / "publisher-keyring"
            source.mkdir(mode=0o700)
            _write_synthetic_publisher_keyring(source)
            snapshot_root = Path(snapshot_raw)
            source_root = root / "source-root"
            source_root.mkdir(mode=0o700)
            stale = snapshot_root / ("g-" + "c" * 64)
            stale.mkdir(mode=0o700)
            unknown_socket = stale / "S.unknown-agent"
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(os.fspath(unknown_socket))
                unknown_socket.chmod(0o600)

            with (
                mock.patch.object(
                    temporary_paths,
                    "PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT",
                    snapshot_root,
                ),
                mock.patch.object(
                    temporary_paths,
                    "local_codex_root",
                    return_value=source_root,
                ),
                self.assertRaises(
                    gpg_keyring_snapshot.ConfigFreeKeyringError
                ) as caught,
            ):
                with gpg_keyring_snapshot.config_free_keyring_snapshot(source):
                    self.fail("an unknown agent socket was accepted")

            self.assertTrue(stale.is_dir())
            self.assertTrue(unknown_socket.is_socket())
            self.assertIsNotNone(
                temporary_paths.incomplete_cleanup_primary(caught.exception)
            )

    def test_recovery_root_inventory_stops_at_n_plus_one(self) -> None:
        entries = _BoundedScandirFixture(
            (
                ".recovery.lock",
                "g-" + "a" * 64,
                "g-" + "b" * 64,
                "must-not-be-read",
            ),
            max_reads=3,
        )
        with (
            mock.patch.object(temporary_recovery.os, "scandir", return_value=entries),
            mock.patch.object(temporary_recovery, "_RECOVERY_MAX_ENTRIES", 2),
            self.assertRaisesRegex(
                temporary_recovery.TemporaryRecoveryError,
                "inventory is too large",
            ),
        ):
            temporary_recovery._stale_names(91, prefix="g-")
        self.assertEqual(3, entries.reads)

    def test_snapshot_inventory_stops_at_n_plus_one(self) -> None:
        entries = _BoundedScandirFixture(
            ("pubring.kbx", "private-keys-v1.d", "S.gpg-agent", "must-not-be-read"),
            max_reads=3,
        )
        temporary = mock.Mock(_child_fd=92)
        with (
            mock.patch.object(
                gpg_snapshot_recovery.os,
                "scandir",
                return_value=entries,
            ),
            mock.patch.object(
                gpg_snapshot_recovery,
                "MAX_SNAPSHOT_TOP_LEVEL_ENTRIES",
                2,
            ),
            self.assertRaisesRegex(
                gpg_snapshot_recovery.GpgSnapshotRecoveryError,
                "top-level inventory exceeds",
            ),
        ):
            gpg_snapshot_recovery.socket_names(temporary)
        self.assertEqual(3, entries.reads)

    def test_recovery_never_deletes_a_replacement_stale_directory(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as raw:
            root = Path(raw)
            source = root / "publisher-keyring"
            source.mkdir(mode=0o700)
            _write_synthetic_publisher_keyring(source)
            snapshot_root = root / "snapshot-root"
            snapshot_root.mkdir(mode=0o700)
            source_root = root / "source-root"
            source_root.mkdir(mode=0o700)
            stale = snapshot_root / ("g-" + "b" * 64)
            stale.mkdir(mode=0o700)
            (stale / "original").write_bytes(b"original")
            displaced = root / "displaced"

            def replace_before_revalidation(_binding) -> None:
                stale.rename(displaced)
                stale.mkdir(mode=0o700)
                (stale / "replacement").write_bytes(b"replacement")

            with (
                mock.patch.object(
                    temporary_paths,
                    "PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT",
                    snapshot_root,
                ),
                mock.patch.object(
                    temporary_paths,
                    "local_codex_root",
                    return_value=source_root,
                ),
                mock.patch.object(
                    gpg_keyring_snapshot,
                    "_recover_stale_snapshot",
                    side_effect=replace_before_revalidation,
                ),
                self.assertRaises(
                    gpg_keyring_snapshot.ConfigFreeKeyringError
                ) as caught,
            ):
                with gpg_keyring_snapshot.config_free_keyring_snapshot(source):
                    self.fail("a replaced recovery entry was accepted")

            self.assertEqual(b"original", (displaced / "original").read_bytes())
            self.assertEqual(b"replacement", (stale / "replacement").read_bytes())
            self.assertIsNotNone(
                temporary_paths.incomplete_cleanup_primary(caught.exception)
            )

    def test_keyring_snapshot_rejects_private_inventory_churn(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as raw:
            root = Path(raw)
            source = root / "publisher-keyring"
            source.mkdir(mode=0o700)
            (source / "pubring.kbx").write_bytes(b"synthetic public keyring")
            private = source / "private-keys-v1.d"
            private.mkdir(mode=0o700)
            private_key = private / ("A" * 40 + ".key")
            private_key.write_bytes(b"synthetic private key")
            private_key.chmod(0o600)
            snapshot_root = root / "snapshot-root"
            source_root = root / "source-root"
            original_create = gpg_keyring_snapshot.safe_io.atomic_create_bytes

            def add_private_key_after_copy(path, payload, **kwargs):
                result = original_create(path, payload, **kwargs)
                if Path(path).name == private_key.name:
                    added = private / ("B" * 40 + ".key")
                    added.write_bytes(b"added private key")
                    added.chmod(0o600)
                return result

            with (
                mock.patch.object(
                    temporary_paths,
                    "PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT",
                    snapshot_root,
                ),
                mock.patch.object(
                    temporary_paths,
                    "local_codex_root",
                    return_value=source_root,
                ),
                mock.patch.object(
                    gpg_keyring_snapshot.safe_io,
                    "atomic_create_bytes",
                    side_effect=add_private_key_after_copy,
                ),
                self.assertRaisesRegex(
                    gpg_keyring_snapshot.ConfigFreeKeyringError,
                    "private-key inventory changed",
                ),
            ):
                with gpg_keyring_snapshot.config_free_keyring_snapshot(source):
                    self.fail("unstable private-key inventory was accepted")

            self.assertEqual(
                [".recovery.lock"],
                sorted(path.name for path in snapshot_root.iterdir()),
            )

    def test_assuan_read_uses_one_monotonic_deadline(self) -> None:
        connection = mock.Mock()
        connection.recv.return_value = b"x"

        with (
            mock.patch.object(
                gpg_snapshot_recovery.time,
                "monotonic",
                side_effect=(10.0, 16.0),
            ),
            self.assertRaisesRegex(
                gpg_snapshot_recovery.GpgSnapshotRecoveryError,
                "response exceeded its deadline",
            ),
        ):
            gpg_snapshot_recovery._assuan_line(connection, deadline=15.0)

        connection.settimeout.assert_called_once_with(5.0)
        connection.recv.assert_called_once_with(1)

    def test_cleanup_proof_requires_exact_owner_only_regular_file(self) -> None:
        for condition in ("valid", "malformed", "mode", "replaced", "symlink"):
            with self.subTest(condition=condition):
                with (
                    tempfile.TemporaryDirectory(dir=ROOT) as raw,
                    tempfile.TemporaryDirectory(
                        prefix="r-", dir="/tmp"
                    ) as snapshot_raw,
                ):
                    root = Path(raw)
                    snapshot_root = Path(snapshot_raw)
                    source_root = root / "source-root"
                    source_root.mkdir(mode=0o700)
                    with mock.patch.object(
                        temporary_paths,
                        "local_codex_root",
                        return_value=source_root,
                    ):
                        with temporary_paths.owner_only_temporary_directory(
                            root=snapshot_root,
                            prefix="g-",
                        ) as temporary:
                            proof = (
                                temporary.path
                                / gpg_snapshot_recovery.CLEANUP_PROOF_NAME
                            )
                            if condition == "valid":
                                gpg_snapshot_recovery.record_cleanup_proof(temporary)
                                self.assertTrue(
                                    gpg_snapshot_recovery.cleanup_proof_exists(
                                        temporary
                                    )
                                )
                                continue
                            if condition == "replaced":
                                gpg_snapshot_recovery.record_cleanup_proof(temporary)
                                payload = proof.read_bytes()
                                displaced = temporary.path / "displaced-proof"
                                original_read = safe_io._read_bounded_descriptor_pass
                                pass_count = 0

                                def replace_after_first_read(*args, **kwargs):
                                    nonlocal pass_count
                                    result = original_read(*args, **kwargs)
                                    pass_count += 1
                                    if pass_count == 1:
                                        proof.rename(displaced)
                                        proof.write_bytes(payload)
                                        proof.chmod(0o600)
                                    return result

                                with (
                                    mock.patch.object(
                                        safe_io,
                                        "_read_bounded_descriptor_pass",
                                        side_effect=replace_after_first_read,
                                    ),
                                    self.assertRaises(
                                        gpg_snapshot_recovery.GpgSnapshotRecoveryError
                                    ),
                                ):
                                    gpg_snapshot_recovery.cleanup_proof_exists(
                                        temporary
                                    )
                                continue
                            if condition == "symlink":
                                outside = root / "outside-proof"
                                outside.write_bytes(b"outside\n")
                                outside.chmod(0o600)
                                proof.symlink_to(outside)
                            else:
                                proof.write_bytes(b"invalid\n")
                                proof.chmod(0o644 if condition == "mode" else 0o600)
                            with self.assertRaises(
                                gpg_snapshot_recovery.GpgSnapshotRecoveryError
                            ):
                                gpg_snapshot_recovery.cleanup_proof_exists(temporary)
                            if proof.is_symlink():
                                proof.unlink()
                            elif proof.exists():
                                proof.chmod(0o600)

    def test_agent_shutdown_accepts_a_bound_socket_disappearing_after_inventory(
        self,
    ) -> None:
        temporary = mock.Mock(
            path=Path("/publisher-snapshot"),
            _child_fd=92,
        )
        primary = (1, 2, os.getuid(), stat.S_IFSOCK | 0o600)
        browser = (1, 3, os.getuid(), stat.S_IFSOCK | 0o600)
        connection = mock.MagicMock()
        socket_context = mock.MagicMock()
        socket_context.__enter__.return_value = connection

        with (
            mock.patch.object(
                gpg_snapshot_recovery,
                "_socket_names",
                side_effect=(
                    ("S.gpg-agent", "S.gpg-agent.browser"),
                    ("S.gpg-agent.browser",),
                    (),
                ),
            ) as socket_names,
            mock.patch.object(
                gpg_snapshot_recovery,
                "_socket_identity",
                side_effect=(
                    primary,
                    browser,
                    FileNotFoundError("expected shutdown disappearance"),
                ),
            ) as socket_identity,
            mock.patch.object(
                gpg_snapshot_recovery.socket,
                "socket",
                return_value=socket_context,
            ),
            mock.patch.object(
                gpg_snapshot_recovery,
                "_assuan_line",
                return_value=b"OK",
            ),
            mock.patch.object(
                gpg_snapshot_recovery,
                "_send_assuan_command",
            ) as send_command,
        ):
            gpg_snapshot_recovery.stop_agent(temporary)

        self.assertEqual(3, socket_names.call_count)
        self.assertEqual(3, socket_identity.call_count)
        send_command.assert_called_once_with(
            connection,
            b"KILLAGENT\n",
            deadline=mock.ANY,
            allow_eof=True,
        )

    def test_keyring_file_close_failure_preserves_primary_policy_error(self) -> None:
        with (
            mock.patch.object(
                gpg_keyring_snapshot.os,
                "stat",
                return_value=mock.Mock(
                    st_dev=1,
                    st_ino=2,
                    st_uid=os.getuid(),
                    st_mode=stat.S_IFREG | 0o600,
                    st_nlink=1,
                    st_size=1,
                ),
            ),
            mock.patch.object(
                gpg_keyring_snapshot.safe_io,
                "open_checked_file_at",
                return_value=91,
            ),
            mock.patch.object(
                gpg_keyring_snapshot.safe_io,
                "descriptor_acl_policy_bytes",
                return_value=b"extended-acl",
            ),
            mock.patch.object(
                gpg_keyring_snapshot.os,
                "close",
                side_effect=OSError("close failed"),
            ),
            self.assertRaisesRegex(
                gpg_keyring_snapshot.ConfigFreeKeyringError,
                "extended ACL",
            ) as raised,
        ):
            gpg_keyring_snapshot._read_keyring_file_at(
                17,
                "pubring.kbx",
                display_path=Path("/publisher/pubring.kbx"),
                max_bytes=1024,
                private=False,
            )

        self.assertIn(
            "publisher keyring file descriptor cleanup failed",
            "\n".join(getattr(raised.exception, "__notes__", ())),
        )

    def test_snapshot_cleanup_removes_only_fully_bound_gpg_lock_links(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as raw:
            root = Path(raw)
            snapshot_root = root / "snapshot-root"
            source_root = root / "source-root"
            with (
                mock.patch.object(
                    temporary_paths,
                    "PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT",
                    snapshot_root,
                ),
                mock.patch.object(
                    temporary_paths,
                    "local_codex_root",
                    return_value=source_root,
                ),
                temporary_paths.owner_only_temporary_directory(
                    root=snapshot_root,
                    prefix="g-",
                ) as temporary,
            ):
                lock = temporary.path / ".#lk0x0000000100f9e600.HOST-NAME.12345"
                sentinel = temporary.path / "gnupg_spawn_agent_sentinel.lock"
                lock.write_bytes(b"bounded GPG lock\n")
                lock.chmod(0o644)
                os.link(lock, sentinel)

                gpg_keyring_snapshot._remove_gpg_lock_files(temporary)

                self.assertFalse(lock.exists())
                self.assertFalse(sentinel.exists())

            self.assertEqual([], list(snapshot_root.iterdir()))

    def test_snapshot_cleanup_rejects_a_gpg_lock_with_an_external_link(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as raw:
            root = Path(raw)
            snapshot_root = root / "snapshot-root"
            source_root = root / "source-root"
            external = root / "external-lock-link"
            with (
                mock.patch.object(
                    temporary_paths,
                    "PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT",
                    snapshot_root,
                ),
                mock.patch.object(
                    temporary_paths,
                    "local_codex_root",
                    return_value=source_root,
                ),
                temporary_paths.owner_only_temporary_directory(
                    root=snapshot_root,
                    prefix="g-",
                ) as temporary,
            ):
                lock = temporary.path / ".#lk0x0000000100f9e600.HOST-NAME.12345"
                lock.write_bytes(b"bounded GPG lock\n")
                lock.chmod(0o644)
                os.link(lock, external)

                with self.assertRaisesRegex(
                    gpg_keyring_snapshot.ConfigFreeKeyringError,
                    "unbound hard link",
                ):
                    gpg_keyring_snapshot._remove_gpg_lock_files(temporary)

                self.assertTrue(lock.exists())
                self.assertTrue(external.exists())
                external.unlink()
                lock.unlink()

            self.assertEqual([], list(snapshot_root.iterdir()))

    def test_snapshot_context_cleans_gpg_locks_after_operation_error(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as raw:
            root = Path(raw)
            source = root / "publisher-keyring"
            source.mkdir(mode=0o700)
            (source / "pubring.kbx").write_bytes(b"synthetic public keyring")
            private = source / "private-keys-v1.d"
            private.mkdir(mode=0o700)
            private_key = private / ("A" * 40 + ".key")
            private_key.write_bytes(b"synthetic private key")
            private_key.chmod(0o600)
            snapshot_root = root / "snapshot-root"
            source_root = root / "source-root"

            with (
                mock.patch.object(
                    temporary_paths,
                    "PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT",
                    snapshot_root,
                ),
                mock.patch.object(
                    temporary_paths,
                    "local_codex_root",
                    return_value=source_root,
                ),
                self.assertRaisesRegex(RuntimeError, "fixture operation failed"),
            ):
                with gpg_keyring_snapshot.config_free_keyring_snapshot(
                    source
                ) as snapshot:
                    lock = snapshot / ".#lk0x0000000100f9e600.HOST-NAME.12345"
                    sentinel = snapshot / "gnupg_spawn_agent_sentinel.lock"
                    lock.write_bytes(b"bounded GPG lock\n")
                    lock.chmod(0o644)
                    os.link(lock, sentinel)
                    raise RuntimeError("fixture operation failed")

            self.assertEqual(
                [".recovery.lock"],
                sorted(path.name for path in snapshot_root.iterdir()),
            )

    def test_abort_replay_response_uses_lifecycle_authority(self) -> None:
        def mark_finalized(*_args, **_kwargs):
            return {
                "attempt_ref": "publication_attempt_v2:validated",
                "publication": {"phase": "aborted"},
                "run_ref": "run_v2:validated",
                "stage": "export",
                "transaction_phase": "aborted",
            }

        with mock.patch.object(
            finalize_module.PublicationTransaction,
            "inspect_local",
            return_value={
                "attempt_ref": "publication_attempt_v2:stale",
                "phase": "created",
                "plan_digest": "a" * 64,
            },
        ):
            replay = publication_abort_replay.replay_terminal_abort(
                Path("/private/tmp/retrospective-abort-replay"),
                {"phase": "aborted"},
                mark_finalized=mark_finalized,
            )

        assert replay is not None
        self.assertEqual("publication_attempt_v2:validated", replay["attempt_ref"])
        self.assertEqual("aborted", replay["transaction_phase"])

    def test_terminal_retry_failure_preserves_original_error(self) -> None:
        primary_error = cli_module.CliContractError(
            exit_code=cli_module.ExitCode.CONFLICT,
            code="publication_conflict",
            message="original publication conflict",
        )
        retry_error = RunConflictError("terminal replay failed")
        calls: list[bool] = []

        def operation(terminal_only: bool):
            calls.append(terminal_only)
            if terminal_only:
                raise retry_error
            raise primary_error

        with self.assertRaises(cli_module.CliContractError) as caught:
            publication_abort_replay.run_with_terminal_retry(
                operation,
                (cli_module.CliContractError,),
            )

        self.assertIs(primary_error, caught.exception)
        self.assertEqual(cli_module.ExitCode.CONFLICT, caught.exception.exit_code)
        self.assertEqual("publication_conflict", caught.exception.code)
        self.assertIs(retry_error, caught.exception.__cause__)
        self.assertIn(
            "terminal retry failed; original error remains primary",
            caught.exception.__notes__,
        )
        self.assertEqual([False, True], calls)

    def test_terminal_publication_acknowledgements_are_monotonic(self) -> None:
        for current_phase, matching_acknowledgement in (
            ("aborted", "aborted"),
            ("expired_cleanup_claimed", "aborted"),
            ("expired_cleanup_complete", "aborted"),
            ("published_cleanup_pending", "committed"),
            ("published_cleanup_claimed", "committed"),
            ("complete", "committed"),
        ):
            with self.subTest(current_phase=current_phase):
                publication = {"phase": current_phase}
                if current_phase.startswith("expired_cleanup_"):
                    publication["expired_cleanup_claim"] = {
                        "disposition": "expired_aborted"
                    }
                self.assertTrue(
                    publication_abort_authority.acknowledgement_is_idempotent(
                        publication,
                        matching_acknowledgement,
                    )
                )
                stale = (
                    "prepared" if matching_acknowledgement == "aborted" else "aborted"
                )
                with self.assertRaises(orchestrator_module.InvalidTransitionError):
                    publication_abort_authority.acknowledgement_is_idempotent(
                        publication,
                        stale,
                    )
        self.assertFalse(
            publication_abort_authority.acknowledgement_is_idempotent(
                {"phase": "staged"},
                "sealed",
            )
        )
        for current_phase in (
            "expired_cleanup_claimed",
            "expired_cleanup_complete",
        ):
            with self.subTest(ordinary_cleanup=current_phase):
                with self.assertRaisesRegex(
                    orchestrator_module.InvalidTransitionError,
                    "cannot rewrite expired cleanup",
                ):
                    publication_abort_authority.acknowledgement_is_idempotent(
                        {
                            "expired_cleanup_claim": {
                                "disposition": "expired_unpublished"
                            },
                            "phase": current_phase,
                        },
                        "aborted",
                    )

    def test_retained_export_binding_receipt_schema_is_closed(self) -> None:
        receipt = {
            "artifact_names": list(reporting.RETAINED_ARTIFACT_NAMES),
            "bundle_digest": "b" * 64,
            "exported_at": "2026-07-15T00:00:00Z",
            "git_commit_created": False,
            "idempotent": True,
            "publication_attempt_ref": "attempt_ref_v2:" + "a" * 64,
            "publication_heartbeat_at": "2026-07-15T00:00:00Z",
            "retention_deadline": "2026-07-15T01:00:00Z",
            "schema_version": 2,
            "staging_dir": "/private/tmp/retained-v2",
            "state_advanced": False,
            "status": "publication_bound",
            "terminal_at": None,
            "terminal_disposition": None,
        }
        retained_export_binding.validate_retention_receipt_shape(
            receipt,
            conflict_error=StateCorruptionError,
        )
        receipt["unexpected"] = True
        with self.assertRaisesRegex(StateCorruptionError, "unexpected shape"):
            retained_export_binding.validate_retention_receipt_shape(
                receipt,
                conflict_error=StateCorruptionError,
            )

    def test_aborted_retained_export_binding_is_attempt_and_disposition_bound(
        self,
    ) -> None:
        attempt_ref = "attempt_ref_v2:" + "a" * 64
        state = {
            "publication": {
                "bundle_digest": "b" * 64,
                "retention_deadline": "2026-07-15T01:00:00Z",
            }
        }
        binding = {
            "artifact_names": list(reporting.RETAINED_ARTIFACT_NAMES),
            "bundle_digest": "b" * 64,
            "exported_at": "2026-07-15T00:00:00Z",
            "git_commit_created": False,
            "idempotent": True,
            "publication_attempt_ref": attempt_ref,
            "publication_heartbeat_at": "2026-07-15T00:00:00Z",
            "retention_deadline": "2026-07-15T01:00:00Z",
            "schema_version": 2,
            "state_advanced": False,
            "status": "publication_terminal",
            "terminal_at": "2026-07-15T00:01:00Z",
            "terminal_disposition": "aborted",
            "staging_dir": "/private/tmp/.codex-local/test/retained-v2",
        }
        retained_export_coordination.validate_aborted_export_binding(
            state,
            binding,
            bundle_dir=Path(binding["staging_dir"]),
            publication_claim={"attempt_ref": attempt_ref},
        )
        for field, value in (
            ("publication_attempt_ref", "attempt_ref_v2:" + "c" * 64),
            ("terminal_disposition", "committed"),
            ("terminal_at", None),
        ):
            with self.subTest(field=field):
                changed = {**binding, field: value}
                with self.assertRaisesRegex(
                    RunConflictError,
                    "does not match the authenticated run claim",
                ):
                    retained_export_coordination.validate_aborted_export_binding(
                        state,
                        changed,
                        bundle_dir=Path(binding["staging_dir"]),
                        publication_claim={"attempt_ref": attempt_ref},
                    )

    def test_history_target_ref_requires_a_valid_fully_qualified_branch(self) -> None:
        observed: list[tuple[str, ...]] = []

        def run(arguments: tuple[str, ...]) -> subprocess.CompletedProcess[bytes]:
            observed.append(arguments)
            return subprocess.CompletedProcess(
                arguments,
                1 if arguments[-1] == "refs/heads/main..bad" else 0,
                b"",
                b"",
            )

        self.assertEqual(
            "refs/heads/main",
            git_safety.validate_history_target_ref(run, "refs/heads/main"),
        )
        self.assertEqual([("check-ref-format", "refs/heads/main")], observed)

        for target_ref in ("HEAD", "refs/tags/release", "refs/heads/main..bad"):
            with self.subTest(target_ref=target_ref):
                with self.assertRaises(authority.HistoryValidationError):
                    git_safety.validate_history_target_ref(run, target_ref)
        self.assertEqual([("check-ref-format", "refs/heads/main")], observed)

    def test_invalid_history_target_stops_before_repository_admission(self) -> None:
        for target_ref in ("HEAD", "refs/tags/release", "refs/heads/main..bad"):
            with self.subTest(target_ref=target_ref):
                with mock.patch.object(authority, "_GitRepository") as repository:
                    with self.assertRaisesRegex(
                        authority.HistoryValidationError,
                        "branch ref",
                    ):
                        authority.load_durable_history(
                            "/unreached/history",
                            target_ref,
                            identity=mock.sentinel.identity,
                        )
                    repository.assert_not_called()

                with mock.patch.object(authority, "_GitRepository") as repository:
                    with self.assertRaisesRegex(
                        authority.HistoryValidationError,
                        "branch ref",
                    ):
                        authority.history_repository_binding(
                            "/unreached/history",
                            target_ref,
                            identity=mock.sentinel.identity,
                        )
                    repository.assert_not_called()

    def test_executable_authority_rejects_writable_ancestor(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=_publication_test_temp_parent()
        ) as temporary_directory:
            executable = Path(temporary_directory) / "untrusted-tool"
            executable.write_bytes(b"#!/bin/sh\nexit 0\n")
            executable.chmod(0o700)

            with self.assertRaisesRegex(
                executable_authority.ExecutableAuthorityError,
                "writable by another user",
            ):
                executable_authority.resolve_executable(executable, label="Fixture")

    def test_executable_authority_ignores_timestamps_and_detects_content(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            executable = Path(temporary_directory) / "trusted-tool"
            executable.write_bytes(b"#!/bin/sh\nexit 0\n")
            executable.chmod(0o700)
            authority_receipt = executable_authority.resolve_executable(
                executable, label="Fixture"
            )

            metadata = executable.stat()
            os.utime(
                executable,
                ns=(metadata.st_atime_ns + 1, metadata.st_mtime_ns + 1),
            )
            executable_authority.revalidate_executable(authority_receipt)

            executable.write_bytes(b"#!/bin/sh\nexit 1\n")
            with self.assertRaisesRegex(
                executable_authority.ExecutableAuthorityError,
                "changed after validation",
            ):
                executable_authority.revalidate_executable(authority_receipt)

    def test_executable_authority_digest_binds_content_identity_and_policy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            executable = Path(temporary_directory) / "trusted-tool"
            executable.write_bytes(b"#!/bin/sh\nexit 0\n")
            executable.chmod(0o700)
            initial = executable_authority.resolve_executable(
                executable,
                label="Fixture",
            )
            initial_digest = executable_authority.authority_digest(initial)

            metadata = executable.stat()
            os.utime(executable, ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1))
            timestamp_only = executable_authority.resolve_executable(
                executable,
                label="Fixture",
            )
            self.assertEqual(
                initial_digest,
                executable_authority.authority_digest(timestamp_only),
            )

            executable.chmod(0o500)
            policy_changed = executable_authority.resolve_executable(
                executable,
                label="Fixture",
            )
            self.assertNotEqual(
                initial_digest,
                executable_authority.authority_digest(policy_changed),
            )

            executable.chmod(0o700)
            executable.write_bytes(b"#!/bin/sh\nexit 1\n")
            content_changed = executable_authority.resolve_executable(
                executable,
                label="Fixture",
            )
            self.assertNotEqual(
                initial_digest,
                executable_authority.authority_digest(content_changed),
            )

    def test_keyring_probe_rejects_changed_expected_gpg_before_home_access(
        self,
    ) -> None:
        expected = executable_authority.resolve_executable(
            "/usr/bin/true",
            label="GPG",
        )
        replacement = executable_authority.resolve_executable(
            "/usr/bin/false",
            label="GPG",
        )
        with (
            mock.patch.object(
                publication_support.executable_authority,
                "resolve_executable",
                return_value=replacement,
            ),
            mock.patch.object(
                gpg_keyring_snapshot,
                "config_free_keyring_snapshot",
            ) as keyring_snapshot,
            self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "GPG executable is not trusted",
            ),
        ):
            publication_support.validate_publisher_keyring(
                gnupg_home="/private/tmp/not-opened-publisher-home",
                fingerprint="A" * 40,
                expected_uid=DEFAULT_PUBLISHER_UID,
                gpg_program=expected.path,
                expected_gpg_authority_sha256=(
                    executable_authority.authority_digest(expected)
                ),
            )
        keyring_snapshot.assert_not_called()

    def test_executable_invocation_detects_post_resolution_replacement(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            root = Path(temporary_directory)
            executable = root / "trusted-tool"
            displaced = root / "trusted-tool-original"
            executable.write_bytes(b"#!/bin/sh\nexit 0\n")
            executable.chmod(0o700)
            authority_receipt = executable_authority.resolve_executable(
                executable, label="Fixture"
            )

            with self.assertRaisesRegex(
                executable_authority.ExecutableAuthorityError,
                "changed after validation",
            ):
                with executable_authority.executable_invocation(authority_receipt):
                    executable.rename(displaced)
                    executable.write_bytes(b"#!/bin/sh\nexit 0\n")
                    executable.chmod(0o700)

    def test_executable_authority_detects_ancestor_policy_change(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            root = Path(temporary_directory)
            executable = root / "trusted-tool"
            executable.write_bytes(b"#!/bin/sh\nexit 0\n")
            executable.chmod(0o700)
            authority_receipt = executable_authority.resolve_executable(
                executable, label="Fixture"
            )

            root.chmod(0o722)
            try:
                with self.assertRaisesRegex(
                    executable_authority.ExecutableAuthorityError,
                    "no longer valid",
                ):
                    executable_authority.revalidate_executable(authority_receipt)
            finally:
                root.chmod(0o700)

    def test_bound_git_invocation_authenticates_python(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            root = Path(temporary_directory)
            repository = root / "repository"
            run_command(["git", "init", "-q", str(repository)])
            environment = git_safety.history_git_environment(
                home=str(root), gnupg_home=str(root)
            )

            def run(arguments):
                return subprocess.run(
                    ["git", "-C", str(repository), *arguments],
                    check=False,
                    capture_output=True,
                    env=environment,
                    timeout=30,
                )

            admission = git_safety.admit_local_repository(
                repository,
                run,
                safe_io.owner_controlled_directory_identity,
            )
            python = root / "python-fixture"
            displaced = root / "python-fixture-original"
            python.write_bytes(b"#!/bin/sh\nexit 0\n")
            python.chmod(0o700)

            with (
                mock.patch.object(git_safety.sys, "executable", str(python)),
                self.assertRaisesRegex(
                    executable_authority.ExecutableAuthorityError,
                    "changed after validation",
                ),
            ):
                with git_safety.repository_git_invocation(
                    admission,
                    repository,
                    "/usr/bin/git",
                    ("status", "--short"),
                    environment,
                    safe_io.owner_controlled_directory_identity,
                ) as (command, _environment, _descriptors):
                    self.assertEqual(os.path.realpath(python), command[0])
                    python.rename(displaced)
                    python.write_bytes(b"#!/bin/sh\nexit 0\n")
                    python.chmod(0o700)

    def test_descriptor_bound_subprocess_rejects_untrusted_python(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=_publication_test_temp_parent()
        ) as temporary_directory:
            root = Path(temporary_directory)
            python = root / "python-fixture"
            python.write_bytes(b"#!/bin/sh\nexit 0\n")
            python.chmod(0o700)
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with (
                    mock.patch.object(
                        publication_support.sys, "executable", str(python)
                    ),
                    self.assertRaisesRegex(
                        executable_authority.ExecutableAuthorityError,
                        "writable by another user",
                    ),
                ):
                    publication_support._run_bounded_subprocess(
                        ["/usr/bin/true"],
                        cwd_descriptor=descriptor,
                        environment={},
                        timeout_seconds=5,
                        max_output_bytes=1024,
                    )
            finally:
                os.close(descriptor)

    def test_descriptor_bound_subprocess_revalidates_python(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            root = Path(temporary_directory)
            python = root / "python-fixture"
            displaced = root / "python-fixture-original"
            python.write_text(
                "#!/bin/sh\n"
                f'/bin/mv "$0" "{displaced}"\n'
                "/usr/bin/printf '#!/bin/sh\\nexit 0\\n' > \"$0\"\n"
                '/bin/chmod 700 "$0"\n'
                "exit 0\n",
                encoding="ascii",
            )
            python.chmod(0o700)
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)

            try:
                with (
                    mock.patch.object(
                        publication_support.sys, "executable", str(python)
                    ),
                    self.assertRaisesRegex(
                        executable_authority.ExecutableAuthorityError,
                        "changed after validation",
                    ),
                ):
                    publication_support._run_bounded_subprocess(
                        ["/usr/bin/true"],
                        cwd_descriptor=descriptor,
                        environment={},
                        timeout_seconds=5,
                        max_output_bytes=1024,
                    )
            finally:
                os.close(descriptor)

    def test_publisher_keyring_revalidates_gpg_executable_content(self) -> None:
        with (
            tempfile.TemporaryDirectory(dir=ROOT) as tool_directory,
            tempfile.TemporaryDirectory(
                dir=_publication_test_temp_parent()
            ) as temporary_directory,
        ):
            executable = Path(tool_directory) / "gpg-fixture"
            executable.write_bytes(b"#!/bin/sh\nexit 0\n")
            executable.chmod(0o700)
            home = Path(temporary_directory) / "gnupg"
            home.mkdir(mode=0o700)
            _write_synthetic_publisher_keyring(home)

            def mutate_executable(*_args, **_kwargs):
                executable.write_bytes(b"#!/bin/sh\nexit 1\n")
                return subprocess.CompletedProcess([], 0, b"", b"")

            with (
                mock.patch.object(
                    publication_support,
                    "_run_bounded_subprocess",
                    side_effect=mutate_executable,
                ),
                self.assertRaisesRegex(
                    publication_support.LocalGitPublicationError,
                    "GPG executable authority changed",
                ),
            ):
                publication_support.validate_publisher_keyring(
                    gnupg_home=home,
                    fingerprint="A" * 40,
                    expected_uid=DEFAULT_PUBLISHER_UID,
                    gpg_program=executable,
                )

    def test_local_git_completeness_policy_is_closed(self) -> None:
        git_safety.validate_complete_local_repository(
            b"false\n",
            b"core.repositoryformatversion\nremote.origin.url\n",
        )
        for shallow, keys in (
            (b"true\n", b"core.repositoryformatversion\n"),
            (b"false\n", b"extensions.partialClone\n"),
            (b"false\n", b"extensions.worktreeConfig\n"),
            (b"false\n", b"include.path\n"),
            (b"false\n", b"includeIf.gitdir:example.path\n"),
            (b"false\n", b"remote.origin.promisor\n"),
            (b"false\n", b"remote.origin.partialCloneFilter\n"),
            (b"false\n", b"remote.origin.promisor\x00suffix\n"),
        ):
            with self.subTest(shallow=shallow, keys=keys):
                with self.assertRaises(ValueError):
                    git_safety.validate_complete_local_repository(shallow, keys)

    def test_bound_git_descriptor_close_preserves_primary_and_fails_closed(
        self,
    ) -> None:
        try:
            raise RuntimeError("ambient outer failure")
        except RuntimeError:
            with (
                mock.patch.object(
                    git_safety.os,
                    "close",
                    side_effect=OSError("synthetic Git close failure"),
                ),
                self.assertRaisesRegex(
                    git_safety.LocalRepositorySafetyError,
                    "ambient Git descriptor close failed",
                ),
            ):
                git_safety.close_repository_descriptors(
                    (123,),
                    "ambient Git",
                )

        try:
            raise RuntimeError("ambient outer failure")
        except RuntimeError:
            with (
                mock.patch.object(
                    executable_authority.os,
                    "close",
                    side_effect=OSError("synthetic executable close failure"),
                ),
                self.assertRaisesRegex(
                    executable_authority.ExecutableAuthorityError,
                    "Fixture executable descriptor cleanup failed",
                ),
            ):
                executable_authority._close_descriptors((123,), "Fixture")

        with tempfile.TemporaryDirectory(
            dir=_publication_test_temp_parent()
        ) as temporary_directory:
            root = Path(temporary_directory)
            root.chmod(0o700)
            repository = root / "repository"
            run_command(["git", "init", "-q", str(repository)])
            environment = git_safety.history_git_environment(
                home=str(root), gnupg_home=str(root)
            )

            def run(arguments):
                return subprocess.run(
                    ["git", "-C", str(repository), *arguments],
                    check=False,
                    capture_output=True,
                    env=environment,
                    timeout=30,
                )

            admission = git_safety.admit_local_repository(
                repository,
                run,
                safe_io.owner_controlled_directory_identity,
            )
            real_close = os.close
            target: int | None = None

            def close_then_fail(descriptor):
                real_close(descriptor)
                if descriptor == target:
                    raise OSError("synthetic descriptor close failure")

            with (
                mock.patch.object(git_safety.os, "close", side_effect=close_then_fail),
                self.assertRaisesRegex(
                    git_safety.LocalRepositorySafetyError,
                    "Git metadata descriptor close failed",
                ),
            ):
                with git_safety.bind_local_repository_command(
                    admission, safe_io.owner_controlled_directory_identity
                ) as binding:
                    target = binding.object_store_fd

            target = None
            with mock.patch.object(git_safety.os, "close", side_effect=close_then_fail):
                with self.assertRaisesRegex(RuntimeError, "primary failure") as raised:
                    with git_safety.bind_local_repository_command(
                        admission, safe_io.owner_controlled_directory_identity
                    ) as binding:
                        target = binding.object_store_fd
                        raise RuntimeError("primary failure")
            self.assertIn(
                "Git metadata descriptor close failed",
                getattr(raised.exception, "__notes__", ()),
            )

    def test_publication_temp_parent_uses_portable_fallback(self) -> None:
        with mock.patch.object(Path, "is_dir", return_value=True):
            self.assertEqual("/private/tmp", _publication_test_temp_parent())
        with (
            mock.patch.object(Path, "is_dir", return_value=False),
            mock.patch.object(tempfile, "gettempdir", return_value="/tmp"),
        ):
            self.assertEqual("/tmp", _publication_test_temp_parent())

    def test_bounded_subprocess_uses_held_working_directory_after_replacement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=_publication_test_temp_parent()
        ) as temporary_directory:
            root = Path(temporary_directory)
            original = root / "publisher-home"
            displaced = root / "publisher-home-original"
            original.mkdir(mode=0o700)
            original.joinpath("marker").write_text("anchored", encoding="ascii")
            descriptor = os.open(original, os.O_RDONLY | os.O_DIRECTORY)
            original.rename(displaced)
            original.mkdir(mode=0o700)
            original.joinpath("marker").write_text("replacement", encoding="ascii")
            try:
                result = publication_support._run_bounded_subprocess(
                    [
                        sys.executable,
                        "-I",
                        "-B",
                        "-S",
                        "-c",
                        "import pathlib; print(pathlib.Path('marker').read_text())",
                    ],
                    cwd_descriptor=descriptor,
                    environment=publication_support._strict_subprocess_environment(
                        home=original
                    ),
                    max_output_bytes=1024,
                    timeout_seconds=5,
                )
            finally:
                os.close(descriptor)

            self.assertEqual(0, result.returncode)
            self.assertEqual(b"anchored\n", result.stdout)

    def test_publisher_keyring_uses_descriptor_binding_across_path_aba(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=_publication_test_temp_parent()
        ) as temporary_directory:
            root = Path(temporary_directory)
            home = root / "gnupg"
            moved_home = root / "gnupg-original"
            replacement_home = root / "gnupg-replacement"
            home.mkdir(mode=0o700)
            _write_synthetic_publisher_keyring(home)
            original_identity = home.stat()
            fingerprint = "A" * 40

            def inventory(primary: str) -> bytes:
                rows = (
                    ":".join((primary, *("" for _ in range(9)))),
                    ":".join(("fpr", *("" for _ in range(8)), fingerprint)),
                    ":".join(("uid", *("" for _ in range(8)), DEFAULT_PUBLISHER_UID)),
                )
                return ("\n".join(rows) + "\n").encode("ascii")

            calls = 0

            def replace_restore_and_list(command, **kwargs):
                nonlocal calls
                calls += 1
                self.assertEqual("--no-options", command[1])
                descriptor_path = command[command.index("--homedir") + 1]
                self.assertEqual(
                    descriptor_path,
                    kwargs["environment"]["GNUPGHOME"],
                )
                self.assertTrue(Path(descriptor_path).is_absolute())
                self.assertNotEqual(home, Path(descriptor_path))
                self.assertTrue(Path(descriptor_path).name.startswith("g-"))
                self.assertNotIn("cwd_descriptor", kwargs)
                if calls == 1:
                    home.rename(moved_home)
                    replacement_home.mkdir(mode=0o700)
                    replacement_home.rename(home)
                    anchored = Path(descriptor_path).stat()
                    self.assertNotEqual(
                        (original_identity.st_dev, original_identity.st_ino),
                        (anchored.st_dev, anchored.st_ino),
                    )
                    self.assertEqual(0, stat.S_IMODE(anchored.st_mode) & 0o077)
                    self.assertEqual(
                        b"synthetic public keyring",
                        (Path(descriptor_path) / "pubring.kbx").read_bytes(),
                    )
                    home.rename(replacement_home)
                    moved_home.rename(home)
                primary = "sec" if command[-1] == "--list-secret-keys" else "pub"
                return subprocess.CompletedProcess(
                    args=command,
                    returncode=0,
                    stdout=inventory(primary),
                    stderr=b"",
                )

            with mock.patch.object(
                publication_support,
                "_run_bounded_subprocess",
                side_effect=replace_restore_and_list,
            ):
                identity = publication_support.validate_publisher_keyring(
                    gnupg_home=home,
                    fingerprint=fingerprint,
                    expected_uid=DEFAULT_PUBLISHER_UID,
                    gpg_program="/usr/bin/true",
                )

            self.assertEqual(fingerprint, identity["fingerprint"])
            self.assertEqual(2, calls)

    def test_publisher_keyring_rejects_secret_inventory_before_public_listing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=_publication_test_temp_parent()
        ) as temporary_directory:
            home = Path(temporary_directory) / "gnupg"
            home.mkdir(mode=0o700)
            _write_synthetic_publisher_keyring(home)
            calls = 0

            def secret_listing_only(command, **_kwargs):
                nonlocal calls
                calls += 1
                if calls != 1:
                    raise AssertionError("public listing must not start")
                return subprocess.CompletedProcess(
                    args=command,
                    returncode=0,
                    stdout=b"",
                    stderr=b"",
                )

            with (
                mock.patch.object(
                    publication_support,
                    "_run_bounded_subprocess",
                    side_effect=secret_listing_only,
                ),
                self.assertRaisesRegex(
                    publication_support.LocalGitPublicationError,
                    "exactly the configured secret primary key",
                ),
            ):
                publication_support.validate_publisher_keyring(
                    gnupg_home=home,
                    fingerprint="A" * 40,
                    expected_uid=DEFAULT_PUBLISHER_UID,
                    gpg_program="/usr/bin/true",
                )

            self.assertEqual(1, calls)

    def test_publisher_keyring_rejects_path_replacement_during_gpg(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=_publication_test_temp_parent()
        ) as temporary_directory:
            root = Path(temporary_directory)
            home = root / "gnupg"
            moved_home = root / "gnupg-original"
            home.mkdir(mode=0o700)
            _write_synthetic_publisher_keyring(home)

            def replace_keyring(*_args, **_kwargs):
                home.rename(moved_home)
                home.mkdir(mode=0o700)
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout=b"",
                    stderr=b"",
                )

            with (
                mock.patch.object(
                    publication_support,
                    "_run_bounded_subprocess",
                    side_effect=replace_keyring,
                ),
                self.assertRaisesRegex(
                    publication_support.LocalGitPublicationError,
                    "publisher keyring directory identity changed",
                ),
            ):
                publication_support.validate_publisher_keyring(
                    gnupg_home=home,
                    fingerprint="A" * 40,
                    expected_uid=DEFAULT_PUBLISHER_UID,
                    gpg_program="/usr/bin/true",
                )

    def test_publisher_keyring_prioritizes_revalidation_after_listing_error(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=_publication_test_temp_parent()
        ) as temporary_directory:
            root = Path(temporary_directory)
            home = root / "gnupg"
            moved_home = root / "gnupg-original"
            home.mkdir(mode=0o700)
            _write_synthetic_publisher_keyring(home)
            operation_error = publication_support.LocalGitPublicationError(
                "subprocess exceeded its deadline"
            )
            calls = 0

            def replace_keyring_and_fail(*_args, **_kwargs):
                nonlocal calls
                calls += 1
                home.rename(moved_home)
                home.mkdir(mode=0o700)
                raise operation_error

            with mock.patch.object(
                publication_support,
                "_run_bounded_subprocess",
                side_effect=replace_keyring_and_fail,
            ):
                with self.assertRaisesRegex(
                    publication_support.LocalGitPublicationError,
                    "publisher keyring directory identity changed",
                ) as raised:
                    publication_support.validate_publisher_keyring(
                        gnupg_home=home,
                        fingerprint="A" * 40,
                        expected_uid=DEFAULT_PUBLISHER_UID,
                        gpg_program="/usr/bin/true",
                    )

            self.assertIs(operation_error, raised.exception.__cause__.__cause__)
            self.assertEqual(1, calls)

    def test_bounded_subprocesses_close_group_after_leader_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            helper = root / "leader-exits.py"
            helper.write_text(
                "import subprocess, sys\n"
                "child = subprocess.Popen(\n"
                "    [sys.executable, '-I', '-c', "
                "'import time; time.sleep(60)'],\n"
                "    stdout=sys.stdout,\n"
                "    stderr=sys.stderr,\n"
                ")\n"
                "with open(sys.argv[1], 'w', encoding='ascii') as stream:\n"
                "    stream.write(str(child.pid))\n"
                "    stream.flush()\n",
                encoding="ascii",
            )

            def assert_child_closed(pid_path: Path) -> None:
                child_pid = int(pid_path.read_text(encoding="ascii"))
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    try:
                        os.kill(child_pid, 0)
                    except ProcessLookupError:
                        return
                    time.sleep(0.02)
                self.fail(f"bounded subprocess descendant survived: {child_pid}")

            publication_pid = root / "publication.pid"
            started = time.monotonic()
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "subprocess exceeded its deadline",
            ):
                publication_support._run_bounded_subprocess(
                    [sys.executable, "-I", str(helper), str(publication_pid)],
                    environment=dict(os.environ),
                    timeout_seconds=0.25,
                    max_output_bytes=1024,
                )
            self.assertLess(time.monotonic() - started, 2)
            assert_child_closed(publication_pid)

            authority_pid = root / "authority.pid"
            started = time.monotonic()
            with self.assertRaisesRegex(
                authority.HistoryValidationError,
                "history command exceeded its deadline",
            ):
                authority._run_bounded(
                    [sys.executable, "-I", str(helper), str(authority_pid)],
                    env=dict(os.environ),
                    timeout_seconds=0.25,
                    max_output_bytes=1024,
                )
            self.assertLess(time.monotonic() - started, 2)
            assert_child_closed(authority_pid)

            detached_helper = root / "leader-exits-with-detached-output.py"
            detached_helper.write_text(
                "import subprocess, sys\n"
                "child = subprocess.Popen(\n"
                "    [sys.executable, '-I', '-c', "
                "'import time; time.sleep(60)'],\n"
                "    stdin=subprocess.DEVNULL,\n"
                "    stdout=subprocess.DEVNULL,\n"
                "    stderr=subprocess.DEVNULL,\n"
                ")\n"
                "with open(sys.argv[1], 'w', encoding='ascii') as stream:\n"
                "    stream.write(str(child.pid))\n",
                encoding="ascii",
            )

            publication_detached_pid = root / "publication-detached.pid"
            publication_result = publication_support._run_bounded_subprocess(
                [
                    sys.executable,
                    "-I",
                    str(detached_helper),
                    str(publication_detached_pid),
                ],
                environment=dict(os.environ),
                timeout_seconds=2,
                max_output_bytes=1024,
            )
            self.assertEqual(0, publication_result.returncode)
            assert_child_closed(publication_detached_pid)

            authority_detached_pid = root / "authority-detached.pid"
            authority_result = authority._run_bounded(
                [
                    sys.executable,
                    "-I",
                    str(detached_helper),
                    str(authority_detached_pid),
                ],
                env=dict(os.environ),
                timeout_seconds=2,
                max_output_bytes=1024,
            )
            self.assertEqual(0, authority_result.returncode)
            assert_child_closed(authority_detached_pid)

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_bounded_subprocesses_surface_group_signal_failures(self) -> None:
        real_killpg = os.killpg

        for runner, error_type, arguments in (
            (
                publication_support._run_bounded_subprocess,
                publication_support.LocalGitPublicationError,
                {"environment": dict(os.environ)},
            ),
            (
                authority._run_bounded,
                authority.HistoryValidationError,
                {"env": dict(os.environ)},
            ),
        ):
            with self.subTest(error_type=error_type.__name__):
                attempted_signals: list[int] = []

                def fail_once(process_group_id: int, selected_signal: int) -> None:
                    attempted_signals.append(selected_signal)
                    if len(attempted_signals) == 1:
                        raise OSError(errno.EIO, "simulated group signal failure")
                    real_killpg(process_group_id, selected_signal)

                with (
                    mock.patch.object(
                        publication_support.process_lifecycle.os,
                        "killpg",
                        side_effect=fail_once,
                    ),
                    self.assertRaisesRegex(error_type, "could not be signaled"),
                ):
                    runner(
                        [sys.executable, "-I", "-B", "-S", "-c", "pass"],
                        timeout_seconds=2,
                        max_output_bytes=1024,
                        **arguments,
                    )
                self.assertEqual(signal.SIGKILL, attempted_signals[0])
                self.assertTrue(attempted_signals[1:])
                self.assertEqual({0}, set(attempted_signals[1:]))

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_bounded_subprocesses_surface_reap_timeouts(self) -> None:
        real_reap = publication_support.process_lifecycle.reap_after_termination

        for runner, error_type, arguments in (
            (
                publication_support._run_bounded_subprocess,
                publication_support.LocalGitPublicationError,
                {"environment": dict(os.environ)},
            ),
            (
                authority._run_bounded,
                authority.HistoryValidationError,
                {"env": dict(os.environ)},
            ),
        ):
            with self.subTest(error_type=error_type.__name__):
                reap_calls = 0

                def time_out_once(*args, **kwargs):
                    nonlocal reap_calls
                    reap_calls += 1
                    if reap_calls == 1:
                        timeout = subprocess.TimeoutExpired(args[0].args, 1)
                        raise kwargs["error_type"](kwargs["error_message"]) from timeout
                    return real_reap(*args, **kwargs)

                with (
                    mock.patch.object(
                        publication_support.process_lifecycle,
                        "reap_after_termination",
                        side_effect=time_out_once,
                    ),
                    self.assertRaisesRegex(error_type, "did not terminate"),
                ):
                    runner(
                        [sys.executable, "-I", "-B", "-S", "-c", "pass"],
                        timeout_seconds=2,
                        max_output_bytes=1024,
                        **arguments,
                    )
                self.assertEqual(2, reap_calls)

    def test_active_primary_records_persistent_group_cleanup_failure(self) -> None:
        for signal_retired in (False, True):
            with self.subTest(signal_retired=signal_retired):
                signal_retirement = process_lifecycle.GroupSignalRetirement()
                if signal_retired:
                    signal_retirement.retire()
                    signal_retirement.prove_group_absence()
                primary = publication_support.LocalGitPublicationError(
                    "simulated primary deadline"
                )

                def cleanup_failure(_process) -> int:
                    raise publication_support.LocalGitPublicationError(
                        "simulated persistent cleanup failure"
                    )

                process_lifecycle.finish_cleanup(
                    mock.Mock(spec=subprocess.Popen),
                    signal_retirement=signal_retirement,
                    terminate_and_reap=cleanup_failure,
                    reap_only=cleanup_failure,
                    active_error=primary,
                )

                self.assertTrue(
                    process_lifecycle.has_incomplete_process_group_cleanup(primary)
                )
                self.assertIn(
                    "simulated persistent cleanup failure",
                    getattr(primary, "__notes__", []),
                )

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_successful_group_signal_still_requires_group_absence(self) -> None:
        process = mock.Mock(spec=subprocess.Popen)
        process.pid = 4242
        process.wait.return_value = 0
        attempted_signals: list[int] = []

        def group_remains(_process_group_id: int, selected_signal: int) -> None:
            attempted_signals.append(selected_signal)

        with (
            mock.patch.object(
                process_lifecycle.os,
                "killpg",
                side_effect=group_remains,
            ),
            mock.patch.object(
                process_lifecycle.time,
                "monotonic",
                side_effect=(0.0, 0.1, 0.1, 0.1, 2.0),
            ),
            self.assertRaisesRegex(RuntimeError, "closure is unproven"),
        ):
            process_lifecycle.close_process_group(
                process,
                signal_retirement=process_lifecycle.GroupSignalRetirement(),
                timeout_seconds=1,
                error_type=RuntimeError,
                label="test process",
                termination_message="test process did not terminate",
            )

        self.assertEqual([signal.SIGKILL, 0], attempted_signals)
        process.wait.assert_called_once()

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_interrupted_signal_attempt_retries_only_group_absence(self) -> None:
        process = mock.Mock(spec=subprocess.Popen)
        process.pid = 4241
        process.wait.return_value = 0
        retirement = process_lifecycle.GroupSignalRetirement()
        attempted_signals: list[int] = []

        def interrupt_then_prove_absent(
            _process_group_id: int, selected_signal: int
        ) -> None:
            attempted_signals.append(selected_signal)
            if len(attempted_signals) == 1:
                raise KeyboardInterrupt
            raise OSError(errno.ESRCH, "group absent")

        def close(child: subprocess.Popen[bytes]) -> int:
            return process_lifecycle.close_process_group(
                child,
                signal_retirement=retirement,
                timeout_seconds=1,
                error_type=RuntimeError,
                label="test process",
                termination_message="test process did not terminate",
            )

        with mock.patch.object(
            process_lifecycle.os,
            "killpg",
            side_effect=interrupt_then_prove_absent,
        ):
            with self.assertRaises(KeyboardInterrupt):
                close(process)
            primary = KeyboardInterrupt()
            process_lifecycle.finish_cleanup(
                process,
                signal_retirement=retirement,
                terminate_and_reap=close,
                reap_only=mock.Mock(
                    side_effect=AssertionError("unsafe reap-only retry")
                ),
                active_error=primary,
            )

        self.assertEqual([signal.SIGKILL, 0], attempted_signals)
        self.assertTrue(retirement.retired)
        self.assertTrue(retirement.group_absence_proven)
        self.assertFalse(
            process_lifecycle.has_incomplete_process_group_cleanup(primary)
        )

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_retired_cleanup_retries_group_absence_without_resignaling(self) -> None:
        process = mock.Mock(spec=subprocess.Popen)
        process.pid = 4242
        process.wait.return_value = 0
        retirement = process_lifecycle.GroupSignalRetirement()
        attempted_signals: list[int] = []

        def interrupted_probe(_process_group_id: int, selected_signal: int) -> None:
            attempted_signals.append(selected_signal)
            if len(attempted_signals) == 2:
                raise KeyboardInterrupt
            if selected_signal == 0:
                raise OSError(errno.ESRCH, "group absent")

        def close(child: subprocess.Popen[bytes]) -> int:
            return process_lifecycle.close_process_group(
                child,
                signal_retirement=retirement,
                timeout_seconds=1,
                error_type=RuntimeError,
                label="test process",
                termination_message="test process did not terminate",
            )

        with mock.patch.object(
            process_lifecycle.os,
            "killpg",
            side_effect=interrupted_probe,
        ):
            with self.assertRaises(KeyboardInterrupt):
                close(process)
            primary = KeyboardInterrupt()
            process_lifecycle.finish_cleanup(
                process,
                signal_retirement=retirement,
                terminate_and_reap=close,
                reap_only=mock.Mock(
                    side_effect=AssertionError("unsafe reap-only retry")
                ),
                active_error=primary,
            )

        self.assertEqual([signal.SIGKILL, 0, 0], attempted_signals)
        self.assertTrue(retirement.retired)
        self.assertTrue(retirement.group_absence_proven)
        self.assertFalse(
            process_lifecycle.has_incomplete_process_group_cleanup(primary)
        )

    def test_resource_teardown_failure_cannot_skip_process_cleanup(self) -> None:
        calls: list[str] = []

        def fail_close() -> None:
            calls.append("failed-close")
            raise OSError(errno.EIO, "simulated selector close failure")

        def later_close() -> None:
            calls.append("later-close")

        def terminate_and_reap(_process) -> int:
            calls.append("process-cleanup")
            return 0

        with self.assertRaisesRegex(OSError, "selector close failure"):
            process_lifecycle.finish_cleanup_after_resource_teardown(
                mock.Mock(spec=subprocess.Popen),
                resource_closers=(fail_close, later_close),
                resource_label="test resource teardown",
                signal_retirement=process_lifecycle.GroupSignalRetirement(),
                terminate_and_reap=terminate_and_reap,
                reap_only=terminate_and_reap,
                active_error=None,
            )

        self.assertEqual(
            ["failed-close", "later-close", "process-cleanup"],
            calls,
        )

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_bounded_selector_setup_failure_reaps_started_process(self) -> None:
        real_popen = subprocess.Popen
        for module, runner, error_type, arguments in (
            (
                publication_support,
                publication_support._run_bounded_subprocess,
                OSError,
                {"environment": dict(os.environ)},
            ),
            (
                authority,
                authority._run_bounded,
                OSError,
                {"env": dict(os.environ)},
            ),
        ):
            with self.subTest(module=module.__name__):
                spawned: list[subprocess.Popen[bytes]] = []

                def capture_popen(*args, **kwargs):
                    process = real_popen(*args, **kwargs)
                    spawned.append(process)
                    return process

                with (
                    mock.patch.object(
                        module.subprocess,
                        "Popen",
                        side_effect=capture_popen,
                    ),
                    mock.patch.object(
                        module.selectors,
                        "DefaultSelector",
                        side_effect=OSError(errno.EMFILE, "selector unavailable"),
                    ),
                    self.assertRaises(error_type),
                ):
                    runner(
                        [
                            sys.executable,
                            "-I",
                            "-B",
                            "-S",
                            "-c",
                            "import time; time.sleep(60)",
                        ],
                        timeout_seconds=2,
                        max_output_bytes=1024,
                        **arguments,
                    )

                self.assertEqual(1, len(spawned))
                self.assertIsNotNone(spawned[0].poll())

    def test_bounded_subprocesses_wait_for_leader_after_output_eof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            helper = root / "close-output-before-side-effect.py"
            helper.write_text(
                "import os, pathlib, sys, time\n"
                "pathlib.Path(sys.argv[1]).write_text('ready', encoding='ascii')\n"
                "os.close(1)\n"
                "os.close(2)\n"
                "while not pathlib.Path(sys.argv[2]).exists(): time.sleep(0.01)\n"
                "pathlib.Path(sys.argv[3]).write_text('complete', encoding='ascii')\n",
                encoding="ascii",
            )
            pending_releases: list[tuple[Path, Path]] = []
            wait_for_exit = publication_support.process_lifecycle.wait_for_unreaped_exit

            def release_after_wait_entry(*args, **kwargs) -> None:
                ready, release = pending_releases.pop(0)
                self.assertEqual("ready", ready.read_text(encoding="ascii"))
                release.write_text("release", encoding="ascii")
                wait_for_exit(*args, **kwargs)

            publication_marker = root / "publication-complete"
            publication_ready = root / "publication-ready"
            publication_release = root / "publication-release"
            authority_marker = root / "authority-complete"
            authority_ready = root / "authority-ready"
            authority_release = root / "authority-release"
            pending_releases.extend(
                (
                    (publication_ready, publication_release),
                    (authority_ready, authority_release),
                )
            )
            with mock.patch.object(
                publication_support.process_lifecycle,
                "wait_for_unreaped_exit",
                side_effect=release_after_wait_entry,
            ):
                publication_result = publication_support._run_bounded_subprocess(
                    [
                        sys.executable,
                        "-I",
                        "-B",
                        "-S",
                        str(helper),
                        str(publication_ready),
                        str(publication_release),
                        str(publication_marker),
                    ],
                    environment=dict(os.environ),
                    timeout_seconds=2,
                    max_output_bytes=1024,
                )
                authority_result = authority._run_bounded(
                    [
                        sys.executable,
                        "-I",
                        "-B",
                        "-S",
                        str(helper),
                        str(authority_ready),
                        str(authority_release),
                        str(authority_marker),
                    ],
                    env=dict(os.environ),
                    timeout_seconds=2,
                    max_output_bytes=1024,
                )

            self.assertEqual([], pending_releases)
            self.assertEqual(0, publication_result.returncode)
            self.assertEqual("complete", publication_marker.read_text(encoding="ascii"))
            self.assertEqual(0, authority_result.returncode)
            self.assertEqual("complete", authority_marker.read_text(encoding="ascii"))

    def test_bounded_subprocess_post_eof_wait_obeys_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            helper = root / "close-output-and-stall.py"
            helper.write_text(
                "import os, pathlib, sys, time\n"
                "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()), encoding='ascii')\n"
                "os.close(1)\n"
                "os.close(2)\n"
                "time.sleep(60)\n",
                encoding="ascii",
            )
            wait_entries = 0
            wait_for_exit = publication_support.process_lifecycle.wait_for_unreaped_exit

            def expire_inside_wait(*args, **kwargs) -> None:
                nonlocal wait_entries
                wait_entries += 1
                kwargs["deadline"] = time.monotonic() - 1
                wait_for_exit(*args, **kwargs)

            publication_pid = root / "publication.pid"
            with (
                mock.patch.object(
                    publication_support.process_lifecycle,
                    "wait_for_unreaped_exit",
                    side_effect=expire_inside_wait,
                ),
                self.assertRaisesRegex(
                    publication_support.LocalGitPublicationError,
                    "deadline",
                ),
            ):
                publication_support._run_bounded_subprocess(
                    [
                        sys.executable,
                        "-I",
                        "-B",
                        "-S",
                        str(helper),
                        str(publication_pid),
                    ],
                    environment=dict(os.environ),
                    timeout_seconds=2,
                    max_output_bytes=1024,
                )

            authority_pid = root / "authority.pid"
            with (
                mock.patch.object(
                    publication_support.process_lifecycle,
                    "wait_for_unreaped_exit",
                    side_effect=expire_inside_wait,
                ),
                self.assertRaisesRegex(
                    authority.HistoryValidationError,
                    "deadline",
                ),
            ):
                authority._run_bounded(
                    [sys.executable, "-I", "-B", "-S", str(helper), str(authority_pid)],
                    env=dict(os.environ),
                    timeout_seconds=2,
                    max_output_bytes=1024,
                )

            self.assertEqual(2, wait_entries)
            for pid_path in (publication_pid, authority_pid):
                pid = int(pid_path.read_text(encoding="ascii"))
                with self.assertRaises(ProcessLookupError):
                    os.kill(pid, 0)

    def test_retained_export_lifecycle_is_injected_through_narrow_protocol(
        self,
    ) -> None:
        calls: list[tuple[str, Path, str, str | None]] = []

        class FakeRetainedExportLifecycle:
            def bind_staged_export(
                self,
                output_dir: Path,
                attempt_ref: str,
                *,
                renew_heartbeat: bool,
                allow_stale_bound: bool,
                before_bind,
            ) -> dict:
                if (renew_heartbeat, allow_stale_bound) != (False, True):
                    raise AssertionError("adapter did not request bound recovery")
                before_bind(
                    {
                        "artifact_names": list(reporting.RETAINED_ARTIFACT_NAMES),
                        "bundle_digest": "b" * 64,
                        "exported_at": "2026-07-15T00:00:00Z",
                        "git_commit_created": False,
                        "idempotent": True,
                        "publication_attempt_ref": attempt_ref,
                        "publication_heartbeat_at": "2026-07-15T00:00:00Z",
                        "retention_deadline": "2026-07-15T01:00:00Z",
                        "schema_version": 2,
                        "staging_dir": str(output_dir),
                        "state_advanced": False,
                        "status": "publication_bound",
                        "terminal_at": None,
                        "terminal_disposition": None,
                    }
                )
                calls.append(("bind", Path(output_dir), attempt_ref, None))
                return {}

            def release_staged_export(
                self,
                output_dir: Path,
                attempt_ref: str,
                disposition: str,
            ) -> dict:
                calls.append(("release", Path(output_dir), attempt_ref, disposition))
                return {}

            def release_staged_export_if_bound(
                self,
                output_dir: Path,
                attempt_ref: str,
                disposition: str,
            ) -> dict:
                calls.append(
                    ("release-if-bound", Path(output_dir), attempt_ref, disposition)
                )
                return {}

        with tempfile.TemporaryDirectory() as raw:
            bundle = Path(raw) / "retained"
            bundle.mkdir()
            bundle.with_name(f".{bundle.name}.retention-v2.json").write_text(
                "{}\n",
                encoding="ascii",
            )
            adapter = object.__new__(LocalGitPublicationAdapter)
            adapter._retained_export_lifecycle = FakeRetainedExportLifecycle()
            request = mock.Mock(attempt_ref="attempt_ref_v2:" + "a" * 64)
            units = (
                {
                    "bundle_dir": str(bundle),
                    "inventory": {"retained_bundle_digest_v2": "b" * 64},
                },
            )

            self.assertEqual(
                1,
                adapter._bind_export_retention_sidecars(request, units),
            )
            adapter._release_export_retention_sidecars(
                request,
                units,
                disposition="aborted",
            )
            bundle.rmdir()
            bundle.with_name(f".{bundle.name}.retention-v2.json").unlink()
            adapter._release_export_retention_sidecars(
                request,
                units,
                disposition="aborted",
            )

        self.assertEqual(
            calls,
            [
                ("bind", bundle, request.attempt_ref, None),
                ("release-if-bound", bundle, request.attempt_ref, "aborted"),
                ("release-if-bound", bundle, request.attempt_ref, "aborted"),
            ],
        )

    def test_episode_successor_cannot_change_predecessor_session(self) -> None:
        previous = {
            "episode_ref": "episode_ref_v2:" + "a" * 64,
            "episode_revision_ref": "episode_revision_ref_v2:" + "b" * 64,
            "revision_ordinal": 1,
            "session_ref": "session_ref_v2:" + "c" * 64,
            "supersedes_episode_revision_ref": None,
        }
        successor = {
            **previous,
            "episode_revision_ref": "episode_revision_ref_v2:" + "d" * 64,
            "revision_ordinal": 2,
            "session_ref": "session_ref_v2:" + "e" * 64,
            "supersedes_episode_revision_ref": previous["episode_revision_ref"],
        }

        with self.assertRaisesRegex(
            publication_support.AppendOnlyViolation,
            "authenticated successor",
        ):
            publication_support._validate_append_only_episode_heads(
                [previous],
                [successor],
            )

    def test_validsig_uses_primary_fingerprint_for_signing_subkey(self) -> None:
        signing_subkey = "A" * 40
        primary_key = "B" * 40
        status = (
            "[GNUPG:] VALIDSIG "
            f"{signing_subkey} 2026-07-16 1784160000 0 4 0 22 8 00 {primary_key}\n"
        ).encode("ascii")

        self.assertEqual(
            authority.validsig_primary_fingerprints(status),
            [primary_key],
        )

    def test_ref_creation_uses_object_format_width_for_zero_oid(self) -> None:
        adapter = object.__new__(LocalGitPublicationAdapter)
        adapter._git = mock.Mock(
            return_value=subprocess.CompletedProcess([], 0, b"", b"")
        )
        value = "a" * 64

        adapter._update_ref("refs/session-retrospective/test", value, expected=None)

        adapter._git.assert_called_once_with(
            (
                "update-ref",
                "refs/session-retrospective/test",
                value,
                "0" * 64,
            ),
            check=False,
        )


class DurablePublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source_gpg = shutil.which("gpg")
        source_gpgconf = shutil.which("gpgconf")
        if source_gpg is None or source_gpgconf is None:
            raise unittest.SkipTest(
                "gpg and gpgconf are required for signed publication tests"
            )
        cls.key_fixture = tempfile.TemporaryDirectory(
            dir=_publication_test_temp_parent()
        )
        cls.tool_fixture = tempfile.TemporaryDirectory(dir=ROOT)
        trusted_bin = Path(cls.tool_fixture.name) / "trusted-bin"
        trusted_bin.mkdir(mode=0o700)
        cls.gpg = os.fspath(trusted_bin / "gpg")
        cls.gpgconf = os.fspath(trusted_bin / "gpgconf")
        shutil.copyfile(source_gpg, cls.gpg)
        shutil.copyfile(source_gpgconf, cls.gpgconf)
        os.chmod(cls.gpg, 0o700)
        os.chmod(cls.gpgconf, 0o700)
        cls.path_patch = mock.patch.dict(
            os.environ,
            {"PATH": f"{trusted_bin}{os.pathsep}{os.environ.get('PATH', os.defpath)}"},
        )
        cls.path_patch.start()
        cls.gnupg_home = Path(cls.key_fixture.name) / "gnupg"
        cls.gnupg_home.mkdir(mode=0o700)
        run_command(
            [
                cls.gpg,
                "--homedir",
                str(cls.gnupg_home),
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-generate-key",
                DEFAULT_PUBLISHER_UID,
                "ed25519",
                "sign",
                "1d",
            ]
        )
        listing = run_command(
            [
                cls.gpg,
                "--homedir",
                str(cls.gnupg_home),
                "--batch",
                "--with-colons",
                "--list-secret-keys",
            ]
        ).stdout.splitlines()
        cls.fingerprint = next(
            line.split(":")[9]
            for previous, line in zip(listing, listing[1:])
            if previous.startswith("sec:") and line.startswith("fpr:")
        )

    @classmethod
    def tearDownClass(cls) -> None:
        gpgconf = shutil.which("gpgconf")
        if gpgconf is not None:
            subprocess.run(
                [
                    cls.gpgconf,
                    "--homedir",
                    str(cls.gnupg_home),
                    "--kill",
                    "gpg-agent",
                ],
                check=False,
                capture_output=True,
            )
        cls.path_patch.stop()
        cls.tool_fixture.cleanup()
        cls.key_fixture.cleanup()

    def setUp(self) -> None:
        bind_remote_host_context_helper_fixture(self)
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        os.chmod(self.root, 0o700)
        self.identity_path = self.root / "identity-v2.key"
        self.identity = IdentityKey.create(self.identity_path)
        self.provider_state = self.root / "provider-state"
        self.marker_path = self.root / "production-marker.json"
        self.production_path_patches = (
            mock.patch.object(
                authority,
                "DEFAULT_PROVIDER_STATE",
                self.provider_state,
            ),
            mock.patch.object(
                authority,
                "DEFAULT_PRODUCTION_MARKER",
                self.marker_path,
            ),
        )
        for patcher in self.production_path_patches:
            patcher.start()
        self.repo = self.root / "history"
        run_command(["git", "init", "-q", "-b", "main", str(self.repo)])
        (self.repo / "README.md").write_text("# Private history\n", encoding="ascii")
        run_command(["git", "add", "README.md"], cwd=self.repo)
        run_command(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-q",
                "-m",
                "Initialize history",
            ],
            cwd=self.repo,
        )
        self.base_head = self.head()
        self.automation_cutover_record = self.build_automation_cutover_record()
        self.initial_history = self.load_history()
        authority.initialize_provider_cache(
            self.provider_state,
            history=self.initial_history,
            expected_revision=0,
            identity=self.identity,
        )
        probe = RetrospectiveOrchestrator(
            self.root / "configuration-probe",
            identity_path=self.identity_path,
            require_existing_identity=True,
        )
        self.host_inventory = transport.remote_host_context_host_inventory()
        self.provenance = execution_provenance()
        provenance = orchestrator_module._build_provenance(
            provenance=self.provenance,
            policy=None,
            model=None,
            versions=None,
            authenticated_host_inventory=self.host_inventory,
        )
        self.configuration_ref = probe._ref(
            RefType.CONFIGURATION, provenance["configuration_root"]
        )
        self.configuration_root = provenance["configuration_root"]
        era_state = {"provenance": provenance}
        self.model_era = probe._model_era(era_state)
        self.policy_era = probe._policy_token(
            era_state,
            "policy",
            "source_policy_v2",
        )
        self.calibration_receipt = calibration.evaluate_calibration_corpus(
            self.identity,
            passing_corpus(),
            production_configuration_root=self.configuration_root,
            model_era=self.model_era,
            policy_era=self.policy_era,
        )
        self.shadow_evidence = self.build_shadow_gate_evidence()
        self.marker = authority.issue_production_marker(
            self.marker_path,
            identity=self.identity,
            canonical_hosts=TEST_HOSTS,
            history_repo=self.repo,
            target_ref=TARGET_REF,
            configuration_root=self.configuration_root,
            configuration_ref=self.configuration_ref,
            model_era=self.model_era,
            policy_era=self.policy_era,
            calibration_receipt=self.calibration_receipt,
            accepted_shadow_evidence=self.shadow_evidence,
            automation_cutover_record=self.automation_cutover_record,
            installed_commits=(self.base_head,),
        )
        self.adapter = LocalGitPublicationAdapter(
            self.repo,
            self.provider_state,
            signing_key=self.fingerprint,
            gnupg_home=self.gnupg_home,
            expected_signer_uid=DEFAULT_PUBLISHER_UID,
            signing_program=self.gpg,
        )

    def tearDown(self) -> None:
        for patcher in reversed(self.production_path_patches):
            patcher.stop()
        self.temporary.cleanup()

    def _add_darwin_acl(self, path: Path, entry: str = "everyone allow write") -> None:
        subprocess.run(
            ["/bin/chmod", "+a", entry, os.fspath(path)],
            check=True,
            capture_output=True,
        )

    def _remove_darwin_acl(self, path: Path) -> None:
        subprocess.run(
            ["/bin/chmod", "-N", os.fspath(path)],
            check=True,
            capture_output=True,
        )

    def test_history_authority_and_provider_reject_non_branch_targets(self) -> None:
        run_command(["git", "tag", "release"], cwd=self.repo)
        for target_ref in ("HEAD", "refs/tags/release", "refs/heads/main..bad"):
            with self.subTest(target_ref=target_ref, boundary="authority"):
                with self.assertRaisesRegex(
                    authority.HistoryValidationError,
                    "branch ref",
                ):
                    authority.load_durable_history(
                        self.repo,
                        target_ref,
                        identity=self.identity,
                        expected_fingerprint=self.fingerprint,
                        gnupg_home=self.gnupg_home,
                        gpg_program=self.gpg,
                    )
            with self.subTest(target_ref=target_ref, boundary="provider"):
                with self.assertRaisesRegex(
                    publication_support.LocalGitPublicationError,
                    "branch ref",
                ):
                    self.adapter.inspect_target_state(target_ref)

    def test_production_marker_rejects_invalid_history_target(self) -> None:
        with self.assertRaisesRegex(
            authority.HistoryValidationError,
            "branch ref",
        ):
            authority.issue_production_marker(
                self.root / "invalid-target-marker.json",
                identity=self.identity,
                canonical_hosts=TEST_HOSTS,
                history_repo=self.repo,
                target_ref="HEAD",
                configuration_root=self.configuration_root,
                configuration_ref=self.configuration_ref,
                model_era=self.model_era,
                policy_era=self.policy_era,
                calibration_receipt=self.calibration_receipt,
                accepted_shadow_evidence=self.shadow_evidence,
                automation_cutover_record=self.automation_cutover_record,
                installed_commits=(self.base_head,),
            )

    def build_automation_cutover_record(
        self,
        *,
        publisher_gpg_program: str | None = None,
        fixture_name: str = "default",
    ) -> dict[str, object]:
        selected_gpg_program = publisher_gpg_program or self.gpg
        suffix = "" if fixture_name == "default" else f"-{fixture_name}"
        automation_root = self.root / ".codex" / "automations"
        automation_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(automation_root, 0o700)
        snapshot = authority.capture_automation_cutover_snapshot(
            self.root / f"automation-cutover-pre-update-v2{suffix}.json",
            identity=self.identity,
            automation_root=automation_root,
        )
        installed_cli = authority.installed_v2_cli_path()
        installed_python = authority.installed_runtime_python_path()
        prior_records = {
            str(row["automation_id"]): row for row in snapshot["automation_records"]
        }
        operations: list[dict[str, object]] = []
        for automation_id, mode in authority.STABLE_AUTOMATION_MODES.items():
            record_dir = automation_root / automation_id
            record_dir.mkdir(parents=True, exist_ok=True)
            schedule = (
                "FREQ=DAILY;BYHOUR=3" if mode == "daily" else "FREQ=WEEKLY;BYDAY=MO"
            )
            prompt = automation_cutover_files.build_production_prompt(
                cli_path=installed_cli,
                python_path=installed_python,
                expected_mode=mode,
                publisher_gpg_program=selected_gpg_program,
                provider_state_path=authority.DEFAULT_PROVIDER_STATE,
                production_marker_path=authority.DEFAULT_PRODUCTION_MARKER,
            )
            (record_dir / "automation.toml").write_text(
                "\n".join(
                    (
                        "version = 1",
                        f'id = "{automation_id}"',
                        'kind = "cron"',
                        f'name = "Session Retrospective {mode.title()}"',
                        f"prompt = {json.dumps(prompt)}",
                        'status = "ACTIVE"',
                        f'rrule = "{schedule}"',
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            previous = prior_records[automation_id]
            operations.append(
                {
                    "automation_id": automation_id,
                    "operation": (
                        "register" if previous["state"] == "absent" else "update"
                    ),
                    "previous_record_sha256": previous["record_sha256"],
                    "record_sha256": hashlib.sha256(
                        (record_dir / "automation.toml").read_bytes()
                    ).hexdigest(),
                    "status": "success",
                }
            )
        capability_result = {
            "available": True,
            "capability": "automation_update",
            "operations": operations,
            "pre_update_snapshot_ref": snapshot["snapshot_ref"],
            "schema": authority.AUTOMATION_UPDATE_RESULT_SCHEMA,
        }
        return authority.issue_automation_cutover_record(
            self.root / f"automation-cutover-v2{suffix}.json",
            identity=self.identity,
            capability_result=capability_result,
            pre_update_snapshot=snapshot,
            installed_commit=self.base_head,
            publisher_gpg_program=selected_gpg_program,
            automation_root=automation_root,
        )

    def issue_production_marker_for_publisher(
        self,
        publisher_gpg_program: str,
        *,
        fixture_name: str,
    ) -> dict[str, object]:
        cutover_record = self.build_automation_cutover_record(
            publisher_gpg_program=publisher_gpg_program,
            fixture_name=fixture_name,
        )
        return authority.issue_production_marker(
            self.marker_path,
            identity=self.identity,
            canonical_hosts=TEST_HOSTS,
            history_repo=self.repo,
            target_ref=TARGET_REF,
            configuration_root=self.configuration_root,
            configuration_ref=self.configuration_ref,
            model_era=self.model_era,
            policy_era=self.policy_era,
            calibration_receipt=self.calibration_receipt,
            accepted_shadow_evidence=self.shadow_evidence,
            automation_cutover_record=cutover_record,
            installed_commits=(self.base_head,),
        )

    def head(self) -> str:
        return run_command(
            ["git", "rev-parse", TARGET_REF], cwd=self.repo
        ).stdout.strip()

    def load_history(self) -> authority.DurableHistoryState:
        return authority.load_durable_history(
            self.repo,
            TARGET_REF,
            identity=self.identity,
            expected_fingerprint=self.fingerprint,
            gnupg_home=self.gnupg_home,
            gpg_program=self.gpg,
        )

    def commit_signed_fixture(self, message: str) -> str:
        environment = dict(os.environ)
        environment["GNUPGHOME"] = str(self.gnupg_home)
        run_command(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "gpg.format=openpgp",
                "-c",
                f"user.signingkey={self.fingerprint}",
                "-c",
                f"gpg.program={self.gpg}",
                "commit",
                "-q",
                "-S",
                "-m",
                message,
            ],
            cwd=self.repo,
            env=environment,
        )
        return self.head()

    def commit_signed_tree_fixture(
        self,
        tree: str,
        *,
        parents: tuple[str, ...],
        message: str,
        update_target: bool = True,
    ) -> str:
        environment = dict(os.environ)
        environment["GNUPGHOME"] = str(self.gnupg_home)
        arguments = [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "gpg.format=openpgp",
            "-c",
            f"user.signingkey={self.fingerprint}",
            "-c",
            f"gpg.program={self.gpg}",
            "commit-tree",
            tree,
            f"-S{self.fingerprint}",
            "-m",
            message,
        ]
        for parent in parents:
            arguments.extend(("-p", parent))
        commit = run_command(
            arguments,
            cwd=self.repo,
            env=environment,
        ).stdout.strip()
        if update_target:
            run_command(
                ["git", "update-ref", TARGET_REF, commit, self.head()],
                cwd=self.repo,
            )
        return commit

    def replace_tip_with_tampered_signature(self, commit: str) -> str:
        raw_commit = run_command(
            ["git", "cat-file", "commit", commit], cwd=self.repo
        ).stdout
        lines = raw_commit.splitlines(keepends=True)
        in_signature = False
        changed = False
        for index, line in enumerate(lines):
            if line.startswith("gpgsig -----BEGIN PGP SIGNATURE-----"):
                in_signature = True
                continue
            if in_signature and line.startswith(" -----END PGP SIGNATURE-----"):
                break
            payload = line[1:].rstrip("\n") if in_signature else ""
            if len(payload) > 16 and not payload.startswith("-----"):
                replacement = "A" if payload[0] != "A" else "B"
                newline = "\n" if line.endswith("\n") else ""
                lines[index] = f" {replacement}{payload[1:]}{newline}"
                changed = True
                break
        self.assertTrue(changed, "fixture commit lacked a mutable signature line")
        tampered = run_command(
            ["git", "hash-object", "-t", "commit", "-w", "--stdin"],
            cwd=self.repo,
            input_text="".join(lines),
        ).stdout.strip()
        run_command(
            ["git", "update-ref", TARGET_REF, tampered, commit],
            cwd=self.repo,
        )
        return tampered

    def build_shadow_evidence_run(
        self,
        name: str,
        *,
        mode: str,
        window_start: str,
        window_end: str,
        hosts: tuple[str, ...],
        allow_partial: bool = False,
        holdout_host: str | None = None,
        backfill_of: str | None = None,
        controlled_gap_receipt: Mapping[str, object] | None = None,
        shadow_successor: Mapping[str, object] | None = None,
        history: authority.DurableHistoryState | None = None,
    ) -> tuple[
        RetrospectiveOrchestrator,
        dict[str, object],
        dict[str, object],
    ]:
        coordinator = RetrospectiveOrchestrator(
            self.root / "shadow-gate-runs" / name,
            clock=lambda: "2026-07-15T00:00:00Z",
            identity_path=self.identity_path,
            require_existing_identity=True,
        )
        start = {
            "allow_partial": allow_partial,
            "backfill_of": backfill_of,
            "controlled_gap_receipt": controlled_gap_receipt,
            "created_at": "2026-07-15T00:00:00Z",
            "end": window_end,
            "history_repo": self.repo,
            "history_target_ref": TARGET_REF,
            "hosts": hosts,
            "mode": mode,
            "publisher_fingerprint": self.fingerprint,
            "publisher_gpg_program": self.gpg,
            "publisher_gnupg_home": self.gnupg_home,
            "provenance": self.provenance,
            "shadow": True,
            "shadow_successor": shadow_successor,
            "start": window_start,
        }
        if history is None:
            coordinator.start(**start)
        else:
            with mock.patch.object(
                orchestrator_module.authority,
                "load_durable_history",
                return_value=history,
            ):
                coordinator.start(**start)
        if holdout_host is not None:
            coordinator.holdout_host(
                holdout_host,
                reason="shadow_missing_host_holdout",
            )
        for _ in range(80):
            status = coordinator.status()
            if status["stage"] == RunStage.EXPORT.value:
                break
            leases = status["active_source_leases"]
            if leases:
                for lease in leases:
                    manifest = no_activity_manifest(lease)
                    coordinator.accept_source(
                        lease["lease_ref"],
                        manifest.to_dict(),
                        transport_receipt=authenticated_receipt(
                            coordinator,
                            lease,
                            manifest,
                        ),
                    )
            else:
                agent_jobs = [
                    job for job in status["runnable_jobs"] if job["category"] == "agent"
                ]
                if agent_jobs:
                    for job in agent_jobs:
                        dispatcher_ref = str(
                            self.identity.derive_ref(
                                RefType.LEASE,
                                {
                                    "parts": [
                                        "shadow-gate-dispatcher",
                                        job["job_ref"],
                                    ]
                                },
                            )
                        )
                        claimed = coordinator.claim_agent_job(
                            job["job_ref"],
                            job["active_attempt_ref"],
                            dispatcher_ref,
                        )
                        coordinator.accept_agent_result(
                            job["job_ref"],
                            job["active_attempt_ref"],
                            synthesis_result(),
                            claim_ref=claimed["claim_ref"],
                            result_ref=claimed["result_ref"],
                        )
                    continue
                coordinator.advance()
        else:
            self.fail(
                "shadow evidence run did not become exportable: "
                f"stage={status['stage']} blocked={status['blocked_reason']} "
                f"next={status['next_actions']}"
            )

        state = coordinator.load_state()
        run_state, review_data = cli_module._retained_inputs(coordinator, state)
        bundle = (
            self.root / ".codex-local" / "shadow-gate-exports" / name / "retained-v2"
        )
        export_retained_bundle(bundle, run_state, review_data)
        marked = coordinator.mark_shadow_exported(bundle)
        coverage = marked["publication"]["coverage_receipt"]
        completed = coordinator.complete_shadow_export()
        cleanup = completed["publication"]["cleanup_receipt"]
        return coordinator, coverage, cleanup

    def build_shadow_gate_evidence(self) -> list[dict[str, object]]:
        production_hosts = TEST_HOSTS
        weekly_evidence: list[dict[str, object]] = []
        for index, start, end in (
            (1, "2026-06-22T00:00:00Z", "2026-06-29T00:00:00Z"),
            (2, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z"),
        ):
            _run, coverage, cleanup = self.build_shadow_evidence_run(
                f"weekly-{index}",
                mode="weekly",
                window_start=start,
                window_end=end,
                hosts=production_hosts,
            )
            weekly_evidence.append(
                authority.issue_shadow_gate_receipt(
                    self.identity,
                    canonical_hosts=TEST_HOSTS,
                    calibration_receipt=self.calibration_receipt,
                    mode="weekly",
                    coverage_receipts=(coverage,),
                    cleanup_receipts=(cleanup,),
                )
            )

        partial, partial_coverage, partial_cleanup = self.build_shadow_evidence_run(
            "daily-partial",
            mode="daily",
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            hosts=production_hosts,
            allow_partial=True,
            holdout_host="miku-bot-dev",
        )
        successor = partial.shadow_daily_successor()
        backfill, backfill_coverage, backfill_cleanup = self.build_shadow_evidence_run(
            "daily-backfill",
            mode="daily",
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            hosts=(successor["host"],),
            backfill_of=successor["backfill_of"],
            controlled_gap_receipt=successor["controlled_gap_receipt"],
            shadow_successor=successor,
        )
        lineage = backfill.load_state()["lineage"]["backfill_lineage_receipt"]
        daily = authority.issue_shadow_gate_receipt(
            self.identity,
            canonical_hosts=TEST_HOSTS,
            calibration_receipt=self.calibration_receipt,
            mode="daily",
            coverage_receipts=(partial_coverage, backfill_coverage),
            cleanup_receipts=(partial_cleanup, backfill_cleanup),
            controlled_gap_receipt=successor["controlled_gap_receipt"],
            backfill_lineage_receipt=lineage,
            backfill_run_ref=backfill_coverage["run_ref"],
        )
        return [*weekly_evidence, daily]

    def build_exportable_run(
        self,
        name: str,
        *,
        shadow: bool = False,
        allow_partial: bool = False,
        holdout_host: str | None = None,
        hosts: tuple[str, ...] = TEST_HOSTS,
        backfill_of: str | None = None,
        controlled_gap_receipt: Mapping[str, object] | None = None,
        bind_export: bool = True,
        persist_descriptor: bool = False,
        publisher_gpg_program: str | None = None,
        export_now: dt.datetime | None = None,
        export_retention_deadline: str | None = None,
    ) -> tuple[RetrospectiveOrchestrator, Path]:
        selected_gpg_program = publisher_gpg_program or self.gpg
        if (
            not shadow
            and publisher_gpg_program is not None
            and os.path.realpath(selected_gpg_program, strict=True)
            != os.path.realpath(self.gpg, strict=True)
        ):
            self.marker = self.issue_production_marker_for_publisher(
                selected_gpg_program,
                fixture_name=name,
            )
        coordinator = RetrospectiveOrchestrator(
            self.root / "runs" / name,
            clock=lambda: "2026-07-15T00:00:00Z",
            identity_path=self.identity_path,
            require_existing_identity=True,
        )
        coordinator.start(
            mode="daily",
            start=WINDOW_START,
            end=WINDOW_END,
            hosts=hosts,
            allow_partial=allow_partial,
            backfill_of=backfill_of,
            controlled_gap_receipt=controlled_gap_receipt,
            provenance=self.provenance,
            shadow=shadow,
            created_at="2026-07-15T00:00:00Z",
            history_repo=self.repo,
            history_target_ref=TARGET_REF,
            provider_state=self.provider_state,
            production_marker=self.marker_path,
            publisher_fingerprint=self.fingerprint,
            publisher_gpg_program=selected_gpg_program,
            publisher_gnupg_home=self.gnupg_home,
        )
        if holdout_host is not None:
            coordinator.holdout_host(
                holdout_host,
                reason=(
                    "shadow_missing_host_holdout" if shadow else "missing_host_holdout"
                ),
            )
        for _ in range(80):
            status = coordinator.status()
            if status["stage"] == RunStage.EXPORT.value:
                break
            leases = status["active_source_leases"]
            if leases:
                for lease in leases:
                    manifest = no_activity_manifest(lease)
                    coordinator.accept_source(
                        lease["lease_ref"],
                        manifest.to_dict(),
                        transport_receipt=authenticated_receipt(
                            coordinator, lease, manifest
                        ),
                    )
            else:
                agent_jobs = [
                    job for job in status["runnable_jobs"] if job["category"] == "agent"
                ]
                if agent_jobs:
                    for job in agent_jobs:
                        dispatcher_ref = str(
                            self.identity.derive_ref(
                                RefType.LEASE,
                                {
                                    "parts": [
                                        "publication-test-dispatcher",
                                        job["job_ref"],
                                    ]
                                },
                            )
                        )
                        claimed = coordinator.claim_agent_job(
                            job["job_ref"],
                            job["active_attempt_ref"],
                            dispatcher_ref,
                        )
                        coordinator.accept_agent_result(
                            job["job_ref"],
                            job["active_attempt_ref"],
                            synthesis_result(),
                            claim_ref=claimed["claim_ref"],
                            result_ref=claimed["result_ref"],
                        )
                    continue
                coordinator.advance()
        else:
            self.fail(
                "run did not become exportable: "
                f"stage={status['stage']} blocked={status['blocked_reason']} "
                f"next={status['next_actions']}"
            )

        state = coordinator.load_state()
        run_state, review_data = cli_module._retained_inputs(coordinator, state)
        run_state["durable_state"] = coordinator.publication_durable_state()
        bundle = self.root / ".codex-local" / "exports" / name / "retained-v2"
        export_clock = export_now or dt.datetime(2026, 7, 15, tzinfo=dt.UTC)
        export_deadline = export_retention_deadline or "2026-07-15T01:00:00Z"
        receipt = export_retained_bundle(
            bundle,
            run_state,
            review_data,
            now=export_clock,
            retention_deadline=export_deadline,
        )
        if persist_descriptor:
            cli_module._claim_export_destination(
                coordinator.run_dir,
                bundle,
                publication_role="standalone",
            )
            cli_module._persist_export_descriptor(
                coordinator.run_dir,
                bundle,
                receipt,
                publication_role="standalone",
            )
        if bind_export:
            if shadow:
                coordinator.mark_shadow_exported(bundle)
            else:
                coordinator.mark_exported(
                    receipt["bundle_digest"],
                    bundle,
                    retention_deadline=receipt["retention_deadline"],
                )
        return coordinator, bundle

    def finalize_cli(
        self,
        coordinator: RetrospectiveOrchestrator,
    ) -> cli_module.CommandResult:
        args = cli_module.build_parser().parse_args(
            [
                "finalize",
                "--identity-path",
                str(self.identity_path),
                "--require-existing-identity",
                "--run-dir",
                str(coordinator.run_dir),
            ]
        )
        result = self.command_finalize_cli(args)
        self.assertTrue(result.ok, result.to_json())
        return result

    @staticmethod
    def _frozen_cli_orchestrator(*args, **kwargs):
        kwargs.setdefault("clock", lambda: "2026-07-15T00:00:00Z")
        return RetrospectiveOrchestrator(*args, **kwargs)

    def command_finalize_cli(
        self,
        args: argparse.Namespace,
    ) -> cli_module.CommandResult:
        with mock.patch.object(
            cli_module.orchestrator_api,
            "RetrospectiveOrchestrator",
            side_effect=self._frozen_cli_orchestrator,
        ):
            return cli_module.command_finalize(args)

    @staticmethod
    def destination(state: dict[str, object]) -> str:
        run_ref = str(state["run_ref"]).rsplit(":", 1)[1]
        return f"runs/daily/2026-07-06/{run_ref}"

    def transaction(
        self,
        coordinator: RetrospectiveOrchestrator,
        bundle: Path,
        *,
        attempt_ref: str | None = None,
        claim_before_persist: Callable[[str, str], Mapping[str, object]] | None = None,
        journal_name: str = "publication-transaction-v2.json",
        destination: str | None = None,
        expected_head: str | None = None,
        adapter: LocalGitPublicationAdapter | None = None,
        failure_injector=None,
    ) -> PublicationTransaction:
        state = coordinator.load_state()

        def claim_publication(
            attempt_ref: str,
            plan_digest: str,
        ) -> Mapping[str, object]:
            return coordinator.claim_publication(
                attempt_ref,
                plan_digest,
                bundle_dir=bundle,
            )

        transaction = PublicationTransaction.create(
            coordinator.run_dir / journal_name,
            bundle_dir=bundle,
            destination=destination or self.destination(state),
            target_ref=TARGET_REF,
            expected_target_head=(
                state["authority"]["history_snapshot"]["history_commit"]
                if expected_head is None
                else expected_head
            ),
            attempt_ref=attempt_ref,
            run_dir=coordinator.run_dir,
            identity_path=self.identity_path,
            adapter=adapter or self.adapter,
            failure_injector=failure_injector,
            claim_before_persist=claim_before_persist or claim_publication,
        )
        return transaction

    def publication_adapter(
        self,
        *,
        failure_injector=None,
    ) -> LocalGitPublicationAdapter:
        return LocalGitPublicationAdapter(
            self.repo,
            self.provider_state,
            signing_key=self.fingerprint,
            gnupg_home=self.gnupg_home,
            expected_signer_uid=DEFAULT_PUBLISHER_UID,
            signing_program=self.gpg,
            failure_injector=failure_injector,
        )

    @staticmethod
    def publish(transaction: PublicationTransaction) -> None:
        transaction.prepare()
        transaction.stage()
        transaction.seal()
        transaction.close_compliance()
        transaction.promote()
        transaction.commit()

    def test_real_signed_publication_derives_history_cache_then_cleans_raw(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run("signed")
        transaction = self.transaction(coordinator, bundle)
        self.publish(transaction)

        published = self.load_history()
        self.assertEqual(1, published.provider_revision)
        self.assertEqual(self.head(), published.publication_commit)
        prior = authority.load_prior_period_from_history(
            self.repo,
            TARGET_REF,
            identity=self.identity,
            expected_fingerprint=self.fingerprint,
            gnupg_home=self.gnupg_home,
        )
        self.assertEqual(
            self.head(),
            prior["authenticated_history"]["history_commit"],
        )
        self.assertEqual(
            2,
            prior["trend_report"]["schema_version"],
        )
        authority.assert_provider_cache_matches(
            self.provider_state,
            published,
            identity=self.identity,
        )
        verify_env = dict(os.environ)
        verify_env["GNUPGHOME"] = str(self.gnupg_home)
        run_command(
            ["git", "verify-commit", self.head()], cwd=self.repo, env=verify_env
        )
        self.assertEqual("committed", transaction.status()["phase"])
        self.assertEqual(
            "committed",
            PublicationTransaction.open(
                transaction.journal_path, adapter=self.adapter
            ).status()["phase"],
        )

        claim = coordinator.load_state()["publication"]["publication_claim"]
        completed = coordinator.mark_finalized(
            "committed",
            attempt_ref=claim["attempt_ref"],
            claim_revision=claim["checkpoint_revision"],
            plan_digest=claim["plan_digest"],
        )
        self.assertEqual(RunStage.COMPLETE.value, completed["stage"])
        self.assertFalse((coordinator.run_dir / "raw-inputs").exists())
        self.assertIsNotNone(completed["publication"]["cleanup_receipt"])

    def test_gpg_configuration_cannot_redirect_publication_or_verification(
        self,
    ) -> None:
        config = self.gnupg_home / "gpg.conf"
        agent_config = self.gnupg_home / "gpg-agent.conf"
        marker = self.root / "gpg-default-options-marker"
        agent_marker = self.root / "gpg-agent-options-marker"
        config.write_text(f"logger-file {marker}\n", encoding="ascii")
        agent_config.write_text(f"log-file {agent_marker}\n", encoding="ascii")
        try:
            run_command(
                [
                    self.gpgconf,
                    "--homedir",
                    str(self.gnupg_home),
                    "--kill",
                    "gpg-agent",
                ]
            )
            run_command(
                [
                    self.gpg,
                    "--homedir",
                    str(self.gnupg_home),
                    "--batch",
                    "--list-secret-keys",
                ]
            )
            self.assertTrue(marker.exists())
            self.assertTrue(agent_marker.exists())
            marker.unlink()
            agent_marker.unlink()

            publication_support.validate_publisher_keyring(
                gnupg_home=self.gnupg_home,
                fingerprint=self.fingerprint,
                expected_uid=DEFAULT_PUBLISHER_UID,
                gpg_program=self.gpg,
            )
            with mock.patch.object(
                orchestrator_support,
                "PUBLISHER_FINGERPRINT",
                self.fingerprint,
            ):
                self.assertTrue(
                    orchestrator_support.publisher_sign_verify_canary(
                        gnupg_home=self.gnupg_home,
                        fingerprint=self.fingerprint,
                        gpg_program=self.gpg,
                    )
                )
            coordinator, bundle = self.build_exportable_run("gpg-no-options")
            self.publish(self.transaction(coordinator, bundle))
            self.load_history()
            self.assertFalse(marker.exists())
            self.assertFalse(agent_marker.exists())
        finally:
            run_command(
                [
                    self.gpgconf,
                    "--homedir",
                    str(self.gnupg_home),
                    "--kill",
                    "gpg-agent",
                ]
            )
            config.unlink(missing_ok=True)
            agent_config.unlink(missing_ok=True)
            marker.unlink(missing_ok=True)
            agent_marker.unlink(missing_ok=True)

    def test_repository_fsmonitor_cannot_run_during_publication(self) -> None:
        marker = self.root / "fsmonitor-invoked"
        hook = self.root / "fsmonitor-hook"
        hook.write_text(
            "#!/bin/sh\n"
            f"/usr/bin/touch {shlex.quote(str(marker))}\n"
            'printf \'%s\\n\' \'{"version":2,"lastUpdateToken":"0","files":[]}\'\n',
            encoding="ascii",
        )
        hook.chmod(0o700)
        run_command(
            ["git", "config", "--local", "core.fsmonitor", str(hook)],
            cwd=self.repo,
        )
        try:
            adapter = self.publication_adapter()
            coordinator, bundle = self.build_exportable_run("fsmonitor-disabled")
            self.publish(self.transaction(coordinator, bundle, adapter=adapter))
            self.load_history()
            self.assertFalse(marker.exists())
        finally:
            run_command(
                ["git", "config", "--local", "--unset-all", "core.fsmonitor"],
                cwd=self.repo,
            )

    def test_publication_disables_repository_split_index(self) -> None:
        git_directory = Path(
            run_command(
                ["git", "rev-parse", "--absolute-git-dir"],
                cwd=self.repo,
            ).stdout.strip()
        )
        run_command(
            ["git", "config", "--local", "core.splitIndex", "true"],
            cwd=self.repo,
        )
        before = tuple(sorted(git_directory.glob("sharedindex.*")))
        try:
            adapter = self.publication_adapter()
            coordinator, bundle = self.build_exportable_run("split-index-disabled")
            self.publish(self.transaction(coordinator, bundle, adapter=adapter))
            self.load_history()
            self.assertEqual(before, tuple(sorted(git_directory.glob("sharedindex.*"))))
        finally:
            run_command(
                ["git", "config", "--local", "--unset-all", "core.splitIndex"],
                cwd=self.repo,
            )

    def test_history_verification_ignores_repo_configured_gpg_program(self) -> None:
        coordinator, bundle = self.build_exportable_run("untrusted-gpg-config")
        self.publish(self.transaction(coordinator, bundle))

        fake_gpg = self.root / "fake-gpg"
        invocation_marker = self.root / "fake-gpg-invoked"
        fake_gpg.write_text(
            "#!/bin/sh\n"
            f": > {shlex.quote(str(invocation_marker))}\n"
            f'exec {shlex.quote(self.gpg)} "$@"\n',
            encoding="ascii",
        )
        fake_gpg.chmod(0o700)
        run_command(["git", "config", "gpg.program", str(fake_gpg)], cwd=self.repo)
        run_command(
            ["git", "config", "gpg.openpgp.program", str(fake_gpg)],
            cwd=self.repo,
        )
        self.load_history()
        self.assertFalse(invocation_marker.exists())

        self.replace_tip_with_tampered_signature(self.head())

        with self.assertRaisesRegex(
            authority.HistoryValidationError,
            "signature is invalid",
        ):
            authority.load_durable_history(
                self.repo,
                TARGET_REF,
                identity=self.identity,
                expected_fingerprint=self.fingerprint,
                gnupg_home=self.gnupg_home,
                gpg_program=self.gpg,
            )

    def test_adapter_keyring_probe_binds_captured_gpg_authority(self) -> None:
        with mock.patch.object(
            publication_git_storage,
            "validate_publisher_keyring",
            return_value={"fingerprint": self.fingerprint},
        ) as probe:
            self.adapter._validate_signing_identity()

        self.assertEqual(
            executable_authority.authority_digest(
                self.adapter._signing_executable_authority
            ),
            probe.call_args.kwargs["expected_gpg_authority_sha256"],
        )

    def test_formal_request_requires_exact_adapter_gpg_authority(self) -> None:
        coordinator, bundle = self.build_exportable_run("adapter-gpg-authority")
        transaction = self.transaction(coordinator, bundle)
        request = transaction.operation_request("prepare")
        conflicting_authority = executable_authority.resolve_executable(
            "/usr/bin/true",
            label="GPG",
        )
        binding = copy.deepcopy(dict(request.publication_authority))
        binding["publisher_gpg_program"] = conflicting_authority.path
        binding["publisher_gpg_authority_sha256"] = (
            executable_authority.authority_digest(conflicting_authority)
        )
        conflicting_request = replace(request, publication_authority=binding)

        with self.assertRaisesRegex(
            publication_support.LocalGitPublicationError,
            "provider configuration differs",
        ):
            self.adapter.preflight_prepare(conflicting_request)
        self.assertIsNone(self.adapter.inspect_attempt(request.attempt_ref))

    def test_history_rejects_signed_retained_artifact_mutation(self) -> None:
        coordinator, bundle = self.build_exportable_run("artifact-mutation")
        self.publish(self.transaction(coordinator, bundle))
        destination = self.destination(coordinator.load_state())
        run_command(["git", "read-tree", self.head()], cwd=self.repo)
        summary = self.repo / destination / "summary.json"
        summary.parent.mkdir(parents=True, exist_ok=True)
        original = run_command(
            ["git", "show", f"{self.head()}:{destination}/summary.json"],
            cwd=self.repo,
        ).stdout
        summary.write_text(original + " ", encoding="ascii")
        run_command(["git", "add", str(summary)], cwd=self.repo)
        self.commit_signed_fixture("Mutate retained artifact")

        with self.assertRaisesRegex(
            authority.HistoryValidationError,
            "publication commit",
        ):
            self.load_history()

    def test_history_rejects_signed_merge_that_rolls_back_retained_tree(self) -> None:
        coordinator, bundle = self.build_exportable_run("merge-rollback")
        self.publish(self.transaction(coordinator, bundle))
        published = self.head()
        base_tree = run_command(
            ["git", "rev-parse", f"{self.base_head}^{{tree}}"],
            cwd=self.repo,
        ).stdout.strip()
        side = self.commit_signed_tree_fixture(
            base_tree,
            parents=(self.base_head,),
            message="Create signed rollback side parent",
            update_target=False,
        )
        self.commit_signed_tree_fixture(
            base_tree,
            parents=(published, side),
            message="Signed merge restoring the pre-publication tree",
        )

        with self.assertRaisesRegex(
            authority.HistoryValidationError,
            "cannot change across a merge",
        ):
            self.load_history()

    def test_history_accepts_merge_when_every_parent_retains_the_same_tree(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run("merge-unrelated")
        self.publish(self.transaction(coordinator, bundle))
        published = self.head()
        published_tree = run_command(
            ["git", "rev-parse", f"{published}^{{tree}}"],
            cwd=self.repo,
        ).stdout.strip()
        left = self.commit_signed_tree_fixture(
            published_tree,
            parents=(published,),
            message="Create first unrelated side parent",
            update_target=False,
        )
        right = self.commit_signed_tree_fixture(
            published_tree,
            parents=(published,),
            message="Create second unrelated side parent",
            update_target=False,
        )
        merged = self.commit_signed_tree_fixture(
            published_tree,
            parents=(left, right),
            message="Merge unrelated history without changing retained data",
        )

        history = self.load_history()
        self.assertEqual(merged, history.head_commit)
        self.assertEqual(published, history.publication_commit)
        self.assertEqual(1, history.provider_revision)

    def test_gc_recovers_commit_after_response_and_local_finalize_mark_are_lost(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run("lost-commit-response")

        def lose_response(point, _state):
            if point == "commit.after_persist":
                raise RuntimeError("simulated lost commit response")

        transaction = self.transaction(
            coordinator,
            bundle,
            failure_injector=lose_response,
        )
        transaction.prepare()
        transaction.stage()
        transaction.seal()
        transaction.close_compliance()
        transaction.promote()
        with self.assertRaisesRegex(RuntimeError, "lost commit response"):
            transaction.commit()

        self.assertEqual("committed", transaction.status()["phase"])
        self.assertEqual(1, self.load_history().provider_revision)
        self.assertTrue((coordinator.run_dir / "raw-inputs").exists())
        self.assertIn(
            "publication_claim",
            coordinator.load_state()["publication"],
        )

        expired = RetrospectiveOrchestrator(
            coordinator.run_dir,
            identity_path=self.identity_path,
            require_existing_identity=True,
            clock=lambda: "2026-07-24T00:00:00Z",
        )
        recovered = expired.gc_expired_raw()
        state = expired.load_state()

        self.assertTrue(recovered["durable"])
        self.assertTrue(recovered["published"])
        self.assertTrue(recovered["cleaned"])
        self.assertEqual(RunStage.COMPLETE.value, state["stage"])
        self.assertEqual("complete", state["publication"]["phase"])
        self.assertNotIn("publication_claim", state["publication"])
        self.assertFalse((coordinator.run_dir / "raw-inputs").exists())
        authority.assert_provider_cache_matches(
            self.provider_state,
            self.load_history(),
            identity=self.identity,
        )

    def test_gc_rejects_same_root_publication_from_another_attempt(self) -> None:
        original, original_bundle = self.build_exportable_run(
            "same-root-original",
            bind_export=False,
        )
        impostor_run_dir = self.root / "runs" / "same-root-impostor"
        shutil.copytree(original.run_dir, impostor_run_dir)
        impostor = RetrospectiveOrchestrator(
            impostor_run_dir,
            clock=lambda: "2026-07-15T00:00:00Z",
            identity_path=self.identity_path,
            require_existing_identity=True,
        )
        impostor_state = impostor.load_state()
        run_state, review_data = cli_module._retained_inputs(
            impostor,
            impostor_state,
        )
        run_state["durable_state"] = impostor.publication_durable_state()
        impostor_bundle = (
            self.root
            / ".codex-local"
            / "exports"
            / "same-root-impostor"
            / "retained-v2"
        )
        impostor_export = export_retained_bundle(
            impostor_bundle,
            run_state,
            review_data,
            now=dt.datetime(2026, 7, 15, tzinfo=dt.UTC),
            retention_deadline="2026-07-15T01:00:00Z",
        )
        original_export = inspect_staged_export_retention(original_bundle)
        original.mark_exported(
            original_export["bundle_digest"],
            original_bundle,
            original_export["retention_deadline"],
        )
        impostor.mark_exported(
            impostor_export["bundle_digest"],
            impostor_bundle,
            impostor_export["retention_deadline"],
        )
        original_transaction = self.transaction(original, original_bundle)
        impostor_transaction = self.transaction(impostor, impostor_bundle)

        original_durable = original.load_state()["publication"]["durable_state"]
        impostor_durable = impostor.load_state()["publication"]["durable_state"]
        self.assertEqual(
            original_durable["proposed_cursor_root_ref"],
            impostor_durable["proposed_cursor_root_ref"],
        )
        self.assertEqual(
            original_durable["proposed_episode_head_root_ref"],
            impostor_durable["proposed_episode_head_root_ref"],
        )

        self.publish(impostor_transaction)
        published_commitment = authority.load_durable_publication_commitment(
            self.repo,
            self.head(),
            identity=self.identity,
            expected_fingerprint=self.fingerprint,
            gnupg_home=self.gnupg_home,
        )
        self.assertEqual(
            impostor_transaction.attempt_ref,
            published_commitment["attempt_ref"],
        )
        self.assertEqual(
            impostor_transaction.status()["plan_digest"],
            published_commitment["plan_digest"],
        )
        self.assertNotEqual(
            original_transaction.attempt_ref,
            published_commitment["attempt_ref"],
        )

        expired = RetrospectiveOrchestrator(
            original.run_dir,
            identity_path=self.identity_path,
            require_existing_identity=True,
            clock=lambda: "2026-07-24T00:00:00Z",
        )
        rejected = expired.gc_expired_raw()

        self.assertTrue(rejected["publication_claimed"])
        self.assertFalse(rejected["durable"])
        self.assertFalse(rejected["cleaned"])
        self.assertTrue((original.run_dir / "raw-inputs").exists())
        self.assertIn(
            "publication_claim",
            expired.load_state()["publication"],
        )

    def test_core_rejects_shadow_caller_overrides_and_open_jobs(self) -> None:
        shadow, shadow_bundle = self.build_exportable_run("shadow", shadow=True)
        with self.assertRaisesRegex(PublicationRejected, "shadow"):
            self.transaction(shadow, shadow_bundle)

        coordinator, bundle = self.build_exportable_run("overrides")
        with self.assertRaisesRegex(PublicationRejected, "destination"):
            self.transaction(
                coordinator,
                bundle,
                journal_name="wrong-destination.json",
                destination="runs/daily/2026-07-06/" + "f" * 64,
            )
        with self.assertRaisesRegex(PublicationRejected, "expected head"):
            self.transaction(
                coordinator,
                bundle,
                journal_name="wrong-head.json",
                expected_head="f" * 40,
            )

        def add_open_job(state: dict[str, object]):
            state["jobs"]["job_ref_v2:" + "f" * 64] = {
                "attempts": [],
                "status": "runnable",
            }
            return state, None

        coordinator.store.transaction(add_open_job)
        with self.assertRaisesRegex(PublicationRejected, "open"):
            self.transaction(
                coordinator,
                bundle,
                journal_name="open-job.json",
            )

        legacy, legacy_bundle = self.build_exportable_run("legacy-host-matrix")
        legacy_state = legacy.load_state()
        legacy_destination = self.destination(legacy_state)
        legacy_expected_head = legacy_state["authority"]["history_snapshot"][
            "history_commit"
        ]
        legacy_hosts = {"local", "miku-bot-dev", "hoteng-srv-01"}

        def retain_legacy_hosts(state: dict[str, object]):
            for host in set(state["host_refs"]) - legacy_hosts:
                state["host_refs"].pop(host)
                state["source"]["cells"].pop(host)
                state["cursors"].pop(host)
            return state, None

        legacy.store.transaction(retain_legacy_hosts)
        with self.assertRaisesRegex(PublicationRejected, "canonical source matrix"):
            PublicationTransaction.create(
                legacy.run_dir / "legacy-host-matrix.json",
                bundle_dir=legacy_bundle,
                destination=legacy_destination,
                target_ref=TARGET_REF,
                expected_target_head=legacy_expected_head,
                run_dir=legacy.run_dir,
                identity_path=self.identity_path,
                adapter=self.adapter,
            )

    def test_formal_publication_rejects_authenticated_cursor_forgery(self) -> None:
        mutations = {
            "history-start": lambda state, host: state["cursors"][host].update(
                {
                    "before": {
                        "backlog_head": None,
                        "cursor": str(
                            self.identity.derive_ref(
                                RefType.SOURCE,
                                {"parts": ["forged-start-cursor"]},
                            )
                        ),
                        "logical_boundary": WINDOW_START,
                    }
                }
            ),
            "source-proposal": lambda state, host: state["cursors"][host][
                "proposed"
            ].update(
                {
                    "source_snapshot_ref": str(
                        self.identity.derive_ref(
                            RefType.SOURCE,
                            {"parts": ["forged-source-proposal"]},
                        )
                    )
                }
            ),
        }
        for label, mutation in mutations.items():
            with self.subTest(case=label):
                coordinator, bundle = self.build_exportable_run(
                    f"forged-cursor-{label}"
                )
                state = coordinator.load_state()
                host = "codex-hoteng-srv-01"

                def forge(current: dict[str, object]):
                    mutation(current, host)
                    return current, None

                coordinator.store.transaction(forge)
                journal = coordinator.run_dir / f"{label}.json"
                with self.assertRaisesRegex(
                    PublicationRejected,
                    "cursor start|cursor proposal",
                ):
                    PublicationTransaction.create(
                        journal,
                        bundle_dir=bundle,
                        destination=self.destination(state),
                        target_ref=TARGET_REF,
                        expected_target_head=state["authority"]["history_snapshot"][
                            "history_commit"
                        ],
                        run_dir=coordinator.run_dir,
                        identity_path=self.identity_path,
                        adapter=self.adapter,
                    )
                self.assertFalse(journal.exists())

    def test_formal_publication_rejects_ordinary_durable_backlog(self) -> None:
        coordinator, bundle = self.build_exportable_run("ordinary-backlog-splice")
        state = coordinator.load_state()
        host = "miku-bot-dev"
        host_ref = state["host_refs"][host]
        backlog_ref = str(
            self.identity.derive_ref(
                RefType.RUN_INPUT,
                {"parts": ["unrelated-partial", host_ref, "publication_backlog"]},
            )
        )

        def splice_backlog(current: dict[str, object]):
            current["authority"]["history_snapshot"]["cursor_rows"].append(
                {
                    "backlog_ref": backlog_ref,
                    "cursor_ref": None,
                    "host_ref": host_ref,
                    "logical_boundary": None,
                }
            )
            return current, None

        coordinator.store.transaction(splice_backlog)
        journal = coordinator.run_dir / "ordinary-backlog-splice.json"
        with self.assertRaisesRegex(PublicationRejected, "durable backlog"):
            PublicationTransaction.create(
                journal,
                bundle_dir=bundle,
                destination=self.destination(state),
                target_ref=TARGET_REF,
                expected_target_head=state["authority"]["history_snapshot"][
                    "history_commit"
                ],
                run_dir=coordinator.run_dir,
                identity_path=self.identity_path,
                adapter=self.adapter,
                claim_before_persist=lambda attempt_ref, plan_digest: (
                    coordinator.claim_publication(
                        attempt_ref,
                        plan_digest,
                        bundle_dir=bundle,
                    )
                ),
            )
        self.assertFalse(journal.exists())

    def test_formal_gaps_require_exact_daily_holdout_authority(self) -> None:
        coordinator, bundle = self.build_exportable_run(
            "formal-holdout-authority",
            allow_partial=True,
            holdout_host="miku-bot-dev",
        )
        original = coordinator.load_state()
        gap_receipt = copy.deepcopy(original["controlled_holdouts"]["miku-bot-dev"])

        def missing(current: dict[str, object]) -> None:
            current["controlled_holdouts"] = {}

        def cross_host(current: dict[str, object]) -> None:
            current["controlled_holdouts"] = {"local": copy.deepcopy(gap_receipt)}

        def weekly(current: dict[str, object]) -> None:
            current["mode"] = "weekly"

        def complete_receipt(current: dict[str, object]) -> None:
            host = "miku-bot-dev"
            cell = current["source"]["cells"][host][SourceKind.HISTORY.value]
            existing = transport.TransportReceipt.from_dict(cell["transport_receipt"])
            observed = existing.source_snapshot
            snapshot = transport.AuthoritativeSourceSnapshot.create(
                host_ref=observed.host_ref,
                source_kind=observed.source_kind,
                window_start=observed.window_start,
                window_end=observed.window_end,
                session_target=observed.session_target,
                source_content_commitment=observed.source_content_commitment,
                source_byte_count=0,
                terminal_byte_offset=0,
                catalog_record_count=0,
                catalog_byte_count=0,
                catalog_commitment=observed.transcript_commitment,
                transcript_commitment=observed.transcript_commitment,
                terminal_proof_commitment=observed.terminal_proof_commitment,
                terminal_status=SourceCellStatus.NO_ACTIVITY,
                terminal_reason="source_enumeration_complete",
                complete=True,
                resume_position=None,
            )
            unsigned = replace(
                existing,
                receipt_ref=transport.TRANSPORT_RECEIPT_REF_PREFIX + "0" * 64,
                source_snapshot=snapshot,
            )
            forged = replace(
                unsigned,
                receipt_ref=transport.TRANSPORT_RECEIPT_REF_PREFIX
                + self.identity.derive_digest(
                    "source-transport-receipt/v2",
                    unsigned.unsigned_dict(),
                ),
            )
            cell["transport_receipt"] = forged.to_dict()
            cell["transport_receipt_ref"] = forged.receipt_ref
            current["controlled_holdouts"][host] = (
                controlled_gaps.issue_controlled_gap_receipt(
                    self.identity,
                    run_ref=current["run_ref"],
                    host=host,
                    host_ref=current["host_refs"][host],
                    source_kinds=[
                        SourceKind(item) for item in current["source"]["cells"][host]
                    ],
                    window_start=current["window"]["start"],
                    window_end=current["window"]["end"],
                    reason="missing_host_holdout",
                    shadow=False,
                    source_receipt_refs=[
                        item["transport_receipt_ref"]
                        for item in current["source"]["cells"][host].values()
                    ],
                ).to_dict()
            )

        for label, mutation in {
            "complete-receipt": complete_receipt,
            "missing": missing,
            "cross-host": cross_host,
            "weekly": weekly,
        }.items():
            with self.subTest(case=label):

                def tamper(current: dict[str, object]):
                    mutation(current)
                    return current, None

                coordinator.store.transaction(tamper)
                journal = coordinator.run_dir / f"formal-holdout-{label}.json"
                with self.assertRaisesRegex(
                    PublicationRejected,
                    "controlled holdout authority",
                ):
                    PublicationTransaction.create(
                        journal,
                        bundle_dir=bundle,
                        destination=self.destination(original),
                        target_ref=TARGET_REF,
                        expected_target_head=original["authority"]["history_snapshot"][
                            "history_commit"
                        ],
                        run_dir=coordinator.run_dir,
                        identity_path=self.identity_path,
                        adapter=self.adapter,
                    )
                self.assertFalse(journal.exists())

                def restore(current: dict[str, object]):
                    current.clear()
                    current.update(copy.deepcopy(original))
                    return current, None

                coordinator.store.transaction(restore)

    def test_formal_publication_rejects_backfill_lineage_splice(self) -> None:
        host = "miku-bot-dev"
        partial, partial_bundle = self.build_exportable_run(
            "backfill-lineage-partial",
            allow_partial=True,
            holdout_host=host,
        )
        partial_state = partial.load_state()
        self.publish(self.transaction(partial, partial_bundle))
        gap = partial_state["controlled_holdouts"][host]
        coordinator, bundle = self.build_exportable_run(
            "backfill-lineage-splice",
            hosts=(host,),
            backfill_of=partial_state["run_ref"],
            controlled_gap_receipt=gap,
        )
        state = coordinator.load_state()

        def splice(current: dict[str, object]):
            lineage = current["lineage"]
            forged = controlled_gaps.issue_backfill_lineage_receipt(
                self.identity,
                controlled_gap_receipt=lineage["controlled_gap_receipt"],
                expected_episode_head_set_ref=lineage["expected_episode_head_set_ref"],
                proposed_episode_head_set_ref=str(
                    self.identity.derive_ref(
                        RefType.EPISODE_HEAD_SET,
                        {"parts": ["spliced-proposed-head-set"]},
                    )
                ),
                prior_episode_heads=lineage["prior_episode_heads"],
                proposed_episode_heads=lineage["proposed_episode_heads"],
                expected_backlog_ref=lineage["expected_backlog_ref"],
            )
            lineage["backfill_lineage_receipt"] = forged.to_dict()
            return current, None

        coordinator.store.transaction(splice)
        journal = coordinator.run_dir / "backfill-lineage-splice.json"
        history_head = self.head()
        with self.assertRaisesRegex(
            PublicationRejected,
            "formal backfill lineage does not bind durable publication state",
        ):
            PublicationTransaction.create(
                journal,
                bundle_dir=bundle,
                destination=self.destination(state),
                target_ref=TARGET_REF,
                expected_target_head=state["authority"]["history_snapshot"][
                    "history_commit"
                ],
                run_dir=coordinator.run_dir,
                identity_path=self.identity_path,
                adapter=self.adapter,
            )
        self.assertFalse(journal.exists())
        self.assertEqual(history_head, self.head())

    def test_pre_promotion_resume_revalidates_current_run_authority(self) -> None:
        coordinator, bundle = self.build_exportable_run("legacy-resume-matrix")

        def crash(point, _state):
            if point == "promote.after_target_cas":
                raise RuntimeError("simulated target CAS crash")

        transaction = self.transaction(
            coordinator,
            bundle,
            adapter=self.publication_adapter(failure_injector=crash),
        )
        transaction.prepare()
        transaction.stage()
        transaction.seal()
        transaction.close_compliance()
        with self.assertRaisesRegex(RuntimeError, "target CAS crash"):
            transaction.promote()
        published_head = self.head()
        legacy_hosts = {"local", "miku-bot-dev", "hoteng-srv-01"}

        def retain_legacy_hosts(state: dict[str, object]):
            for host in set(state["host_refs"]) - legacy_hosts:
                state["host_refs"].pop(host)
                state["source"]["cells"].pop(host)
                state["cursors"].pop(host)
            return state, None

        coordinator.store.transaction(retain_legacy_hosts)
        with self.assertRaisesRegex(PublicationRejected, "canonical source matrix"):
            PublicationTransaction.open(
                transaction.journal_path,
                adapter=self.adapter,
                expected_attempt_ref=transaction.attempt_ref,
            )
        self.assertEqual("compliance_closed", transaction.status()["phase"])
        self.assertEqual(published_head, self.head())

    def test_existing_journal_is_bound_to_current_run_before_claim(self) -> None:
        original, original_bundle = self.build_exportable_run("journal-original")
        original_state = original.load_state()
        copied_run_dir = self.root / "runs" / "journal-current"
        shutil.copytree(original.run_dir, copied_run_dir)
        PublicationTransaction.create(
            original.run_dir / "publication-transaction-v2.json",
            bundle_dir=original_bundle,
            destination=self.destination(original_state),
            target_ref=TARGET_REF,
            expected_target_head=original_state["authority"]["history_snapshot"][
                "history_commit"
            ],
            run_dir=original.run_dir,
            identity_path=self.identity_path,
            adapter=self.adapter,
            claim_before_persist=lambda attempt_ref, plan_digest: (
                original.claim_publication(
                    attempt_ref,
                    plan_digest,
                    bundle_dir=original_bundle,
                )
            ),
        )
        shutil.copy2(
            original.run_dir / "publication-transaction-v2.json",
            copied_run_dir / "publication-transaction-v2.json",
        )
        current = RetrospectiveOrchestrator(
            copied_run_dir,
            identity_path=self.identity_path,
            require_existing_identity=True,
        )
        copied_journal = copied_run_dir / "publication-transaction-v2.json"
        current_state = current.load_state()

        with self.assertRaisesRegex(
            AttemptMismatchError,
            "current run",
        ):
            PublicationTransaction.inspect_local_for_run(
                copied_journal,
                bundle_dir=original_bundle,
                destination=self.destination(current_state),
                target_ref=TARGET_REF,
                expected_target_head=current_state["authority"]["history_snapshot"][
                    "history_commit"
                ],
                run_dir=current.run_dir,
                identity_path=self.identity_path,
            )

        self.assertNotIn(
            "publication_claim",
            current.load_state()["publication"],
        )

    def test_create_binds_journal_to_safe_authoritative_run_before_claim(self) -> None:
        coordinator, bundle = self.build_exportable_run("journal-source-overlap")
        state = coordinator.load_state()
        codex_root = self.root / "source-account" / ".codex"
        sessions = codex_root / "sessions"
        archived = codex_root / "archived_sessions"
        sessions.mkdir(parents=True, mode=0o700)
        archived.mkdir(mode=0o700)
        claim = mock.Mock()

        with (
            mock.patch.object(
                temporary_paths,
                "local_codex_root",
                return_value=codex_root,
            ),
            self.assertRaisesRegex(
                AttemptMismatchError,
                "outside the authoritative run directory",
            ),
        ):
            PublicationTransaction.create(
                sessions / "foreign-run" / "publication-transaction-v2.json",
                bundle_dir=bundle,
                destination=self.destination(state),
                target_ref=TARGET_REF,
                expected_target_head=state["authority"]["history_snapshot"][
                    "history_commit"
                ],
                run_dir=coordinator.run_dir,
                identity_path=self.identity_path,
                adapter=self.adapter,
                claim_before_persist=claim,
            )

        claim.assert_not_called()
        self.assertFalse((sessions / "foreign-run").exists())

        with (
            mock.patch.object(
                temporary_paths,
                "local_codex_root",
                return_value=codex_root,
            ),
            self.assertRaisesRegex(
                safe_io.UnsafePathError,
                "overlaps a retrospective source root",
            ),
        ):
            PublicationTransaction.create(
                sessions / "source-run" / "publication-transaction-v2.json",
                bundle_dir=bundle,
                destination=self.destination(state),
                target_ref=TARGET_REF,
                expected_target_head=state["authority"]["history_snapshot"][
                    "history_commit"
                ],
                run_dir=sessions / "source-run",
                identity_path=self.identity_path,
                adapter=self.adapter,
                claim_before_persist=claim,
            )

        claim.assert_not_called()
        self.assertFalse((sessions / "source-run").exists())

    def test_open_and_inspect_reject_source_journals_before_lock_creation(
        self,
    ) -> None:
        codex_root = self.root / "source-account" / ".codex"
        sessions = codex_root / "sessions"
        archived = codex_root / "archived_sessions"
        sessions.mkdir(parents=True, mode=0o700)
        archived.mkdir(mode=0o700)

        for source_root in (sessions, archived):
            for operation in (
                PublicationTransaction.open,
                PublicationTransaction.inspect_local,
            ):
                journal = source_root / f"{operation.__name__}.json"
                with (
                    self.subTest(
                        source_root=source_root.name,
                        operation=operation.__name__,
                    ),
                    mock.patch.object(
                        temporary_paths,
                        "local_codex_root",
                        return_value=codex_root,
                    ),
                    self.assertRaisesRegex(
                        safe_io.UnsafePathError,
                        "overlaps a retrospective source root",
                    ),
                ):
                    operation(journal)

                self.assertFalse(journal.exists())
                self.assertFalse((source_root / f".{journal.name}.lock").exists())

    def test_latest_history_rejects_stale_run_and_local_cache_rollback(self) -> None:
        first, first_bundle = self.build_exportable_run("first")
        stale, stale_bundle = self.build_exportable_run("stale")
        old_cache = (self.provider_state / authority.PROVIDER_CACHE_FILE).read_bytes()
        self.publish(self.transaction(first, first_bundle))

        with self.assertRaisesRegex(PublicationRejected, "history"):
            self.transaction(stale, stale_bundle)

        cache_path = self.provider_state / authority.PROVIDER_CACHE_FILE
        safe_io.atomic_write_bytes(cache_path, old_cache)
        rolled_back = RetrospectiveOrchestrator(
            self.root / "runs" / "rolled-back",
            identity_path=self.identity_path,
            require_existing_identity=True,
        )
        with self.assertRaisesRegex(RunConflictError, "durable history"):
            rolled_back.start(
                mode="daily",
                start=WINDOW_START,
                end=WINDOW_END,
                hosts=TEST_HOSTS,
                history_repo=self.repo,
                history_target_ref=TARGET_REF,
                provider_state=self.provider_state,
                production_marker=self.marker_path,
                provenance=self.provenance,
                publisher_fingerprint=self.fingerprint,
                publisher_gpg_program=self.gpg,
                publisher_gnupg_home=self.gnupg_home,
            )

    def test_prepublication_journal_still_rejects_advanced_history(self) -> None:
        first, first_bundle = self.build_exportable_run("preflight-first")
        stale, stale_bundle = self.build_exportable_run("preflight-stale")
        transaction = self.transaction(stale, stale_bundle)
        self.publish(self.transaction(first, first_bundle))

        with self.assertRaisesRegex(PublicationRejected, "history"):
            PublicationTransaction.inspect_local_for_run(
                transaction.journal_path,
                bundle_dir=stale_bundle,
                destination=self.destination(stale.load_state()),
                target_ref=TARGET_REF,
                expected_target_head=transaction.status()["plan"][
                    "expected_target_head"
                ],
                run_dir=stale.run_dir,
                identity_path=self.identity_path,
            )

    def test_marker_is_hmac_cutover_state_not_an_active_lease(self) -> None:
        self.assertFalse(any("lease" in key for key in self.marker))
        self.assertEqual(3, len(self.marker["accepted_shadow_refs"]))
        self.assertEqual(
            self.calibration_receipt.receipt_ref,
            self.marker["calibration_receipt"]["receipt_ref"],
        )
        loaded = authority.load_production_marker(
            self.marker_path,
            identity=self.identity,
            canonical_hosts=TEST_HOSTS,
            history_repo=self.repo,
            target_ref=TARGET_REF,
            configuration_root=self.configuration_root,
            configuration_ref=self.configuration_ref,
            model_era=self.model_era,
            policy_era=self.policy_era,
        )
        self.assertEqual(self.marker, loaded)

        tampered = dict(self.marker)
        tampered["installed_commits"] = ["f" * 40]
        safe_io.atomic_write_json(self.marker_path, tampered)
        with self.assertRaises(authority.ProductionMarkerError):
            authority.load_production_marker(
                self.marker_path,
                identity=self.identity,
                canonical_hosts=TEST_HOSTS,
                history_repo=self.repo,
                target_ref=TARGET_REF,
                configuration_root=self.configuration_root,
                configuration_ref=self.configuration_ref,
                model_era=self.model_era,
                policy_era=self.policy_era,
            )

    def test_marker_requires_calibration_and_exact_shadow_gate_evidence(self) -> None:
        mismatched_bindings = (
            ("f" * 64, self.configuration_ref, self.model_era, self.policy_era),
            (
                self.configuration_root,
                "configuration_ref_v2:" + "f" * 64,
                self.model_era,
                self.policy_era,
            ),
            (
                self.configuration_root,
                self.configuration_ref,
                "gpt_5_7",
                self.policy_era,
            ),
            (
                self.configuration_root,
                self.configuration_ref,
                self.model_era,
                "source_catalog_v3",
            ),
        )
        for index, (
            configuration_root,
            configuration_ref,
            model_era,
            policy_era,
        ) in enumerate(mismatched_bindings):
            with (
                self.subTest(binding_index=index),
                self.assertRaisesRegex(
                    authority.ProductionMarkerError,
                    "not bound by calibration evidence",
                ),
            ):
                authority.issue_production_marker(
                    self.root / f"mismatched-binding-{index}.json",
                    identity=self.identity,
                    canonical_hosts=TEST_HOSTS,
                    history_repo=self.repo,
                    target_ref=TARGET_REF,
                    configuration_root=configuration_root,
                    configuration_ref=configuration_ref,
                    model_era=model_era,
                    policy_era=policy_era,
                    calibration_receipt=self.calibration_receipt,
                    accepted_shadow_evidence=self.shadow_evidence,
                    automation_cutover_record=self.automation_cutover_record,
                    installed_commits=(self.base_head,),
                )

        self.assertFalse(hasattr(authority, "issue_shadow_coverage_receipt"))
        self.assertFalse(hasattr(authority, "issue_shadow_cleanup_receipt"))

        with self.assertRaisesRegex(
            authority.ProductionMarkerError,
            "exactly three shadow gate results",
        ):
            authority.issue_production_marker(
                self.root / "missing-shadows.json",
                identity=self.identity,
                canonical_hosts=TEST_HOSTS,
                history_repo=self.repo,
                target_ref=TARGET_REF,
                configuration_root=self.configuration_root,
                configuration_ref=self.configuration_ref,
                model_era=self.model_era,
                policy_era=self.policy_era,
                calibration_receipt=self.calibration_receipt,
                accepted_shadow_evidence=(),
                automation_cutover_record=self.automation_cutover_record,
                installed_commits=(self.base_head,),
            )

        foreign_evidence = json.loads(json.dumps(self.shadow_evidence))
        foreign_evidence[0]["configuration_root"] = "e" * 64
        with self.assertRaisesRegex(
            authority.ProductionMarkerError,
            "shadow gate receipt is invalid",
        ):
            authority.issue_production_marker(
                self.root / "mixed-configuration-evidence.json",
                identity=self.identity,
                canonical_hosts=TEST_HOSTS,
                history_repo=self.repo,
                target_ref=TARGET_REF,
                configuration_root=self.configuration_root,
                configuration_ref=self.configuration_ref,
                model_era=self.model_era,
                policy_era=self.policy_era,
                calibration_receipt=self.calibration_receipt,
                accepted_shadow_evidence=foreign_evidence,
                automation_cutover_record=self.automation_cutover_record,
                installed_commits=(self.base_head,),
            )

        failed_corpus = passing_corpus()
        failed_corpus["privacy_holdout"]["passed"] = False
        failed_corpus["privacy_holdout"]["raw_prompt_leak_count"] = 1
        failed_receipt = calibration.evaluate_calibration_corpus(
            self.identity,
            failed_corpus,
        )
        with self.assertRaisesRegex(
            authority.ProductionMarkerError,
            "calibration evidence is invalid",
        ):
            authority.issue_production_marker(
                self.root / "failed-calibration.json",
                identity=self.identity,
                canonical_hosts=TEST_HOSTS,
                history_repo=self.repo,
                target_ref=TARGET_REF,
                configuration_root=self.configuration_root,
                configuration_ref=self.configuration_ref,
                model_era=self.model_era,
                policy_era=self.policy_era,
                calibration_receipt=failed_receipt,
                accepted_shadow_evidence=self.shadow_evidence,
                automation_cutover_record=self.automation_cutover_record,
                installed_commits=(self.base_head,),
            )

        invalid_daily = json.loads(json.dumps(self.shadow_evidence))
        daily = next(item for item in invalid_daily if item["mode"] == "daily")
        daily["coverage_receipts"][0]["source_units"]["expected"] += 1
        with self.assertRaisesRegex(
            authority.ProductionMarkerError,
            "shadow gate receipt is invalid",
        ):
            authority.issue_production_marker(
                self.root / "invalid-daily.json",
                identity=self.identity,
                canonical_hosts=TEST_HOSTS,
                history_repo=self.repo,
                target_ref=TARGET_REF,
                configuration_root=self.configuration_root,
                configuration_ref=self.configuration_ref,
                model_era=self.model_era,
                policy_era=self.policy_era,
                calibration_receipt=self.calibration_receipt,
                accepted_shadow_evidence=invalid_daily,
                automation_cutover_record=self.automation_cutover_record,
                installed_commits=(self.base_head,),
            )

        legacy_daily = copy.deepcopy(
            next(item for item in self.shadow_evidence if item["mode"] == "weekly")[
                "coverage_receipts"
            ][0]
        )
        legacy_hosts = ("local", "miku-bot-dev", "hoteng-srv-01")
        legacy_host_refs = sorted(
            str(self.identity.derive_ref(RefType.HOST, {"parts": [host]}))
            for host in legacy_hosts
        )
        legacy_daily.update(
            {
                "configured_host_refs": legacy_host_refs,
                "covered_host_refs": legacy_host_refs,
                "gap_host_refs": [],
                "mode": "daily",
                "source_units": {
                    "consumed_candidate": 12,
                    "expected": 12,
                    "explicit_gap": 0,
                    "structurally_excluded": 0,
                },
            }
        )
        (
            legacy_daily["source_snapshot_refs"],
            legacy_daily["source_receipt_refs"],
            legacy_daily["source_evidence_commitment"],
        ) = authority._shadow_source_evidence(
            self.identity,
            run_ref=legacy_daily["run_ref"],
            window_start=legacy_daily["window_start"],
            window_end=legacy_daily["window_end"],
            configured_host_refs=legacy_daily["configured_host_refs"],
            covered_host_refs=legacy_daily["covered_host_refs"],
            gap_host_refs=legacy_daily["gap_host_refs"],
            source_units=legacy_daily["source_units"],
            source_snapshot_refs=legacy_daily["source_snapshot_refs"],
            source_receipt_refs=legacy_daily["source_receipt_refs"],
        )
        legacy_body = {
            key: value
            for key, value in legacy_daily.items()
            if key not in {"authentication_tag", "receipt_ref"}
        }
        legacy_daily["receipt_ref"] = (
            "shadow_coverage_receipt_v2:"
            + self.identity.derive_digest("shadow_coverage_receipt_v2", legacy_body)
        )
        legacy_daily["authentication_tag"] = (
            "shadow_coverage_auth_v2:"
            + self.identity.derive_digest("shadow_coverage_auth_v2", legacy_body)
        )
        with self.assertRaisesRegex(
            authority.ProductionMarkerError,
            "daily complete shadow coverage is invalid",
        ):
            authority.verify_shadow_coverage_receipt(
                self.identity,
                legacy_daily,
                canonical_hosts=TEST_HOSTS,
            )

        unknown_backfill = copy.deepcopy(
            next(
                item
                for item in next(
                    item for item in self.shadow_evidence if item["mode"] == "daily"
                )["coverage_receipts"]
                if item["backfill_of"] is not None
            )
        )
        unknown_host_ref = str(
            self.identity.derive_ref(
                RefType.HOST,
                {"parts": ["unknown-retrospective-host"]},
            )
        )
        unknown_backfill["configured_host_refs"] = [unknown_host_ref]
        unknown_backfill["covered_host_refs"] = [unknown_host_ref]
        (
            unknown_backfill["source_snapshot_refs"],
            unknown_backfill["source_receipt_refs"],
            unknown_backfill["source_evidence_commitment"],
        ) = authority._shadow_source_evidence(
            self.identity,
            run_ref=unknown_backfill["run_ref"],
            window_start=unknown_backfill["window_start"],
            window_end=unknown_backfill["window_end"],
            configured_host_refs=unknown_backfill["configured_host_refs"],
            covered_host_refs=unknown_backfill["covered_host_refs"],
            gap_host_refs=unknown_backfill["gap_host_refs"],
            source_units=unknown_backfill["source_units"],
            source_snapshot_refs=unknown_backfill["source_snapshot_refs"],
            source_receipt_refs=unknown_backfill["source_receipt_refs"],
        )
        unknown_body = {
            key: value
            for key, value in unknown_backfill.items()
            if key not in {"authentication_tag", "receipt_ref"}
        }
        unknown_backfill["receipt_ref"] = (
            "shadow_coverage_receipt_v2:"
            + self.identity.derive_digest("shadow_coverage_receipt_v2", unknown_body)
        )
        unknown_backfill["authentication_tag"] = (
            "shadow_coverage_auth_v2:"
            + self.identity.derive_digest("shadow_coverage_auth_v2", unknown_body)
        )
        with self.assertRaisesRegex(
            authority.ProductionMarkerError,
            "daily backfill shadow coverage is invalid",
        ):
            authority.verify_shadow_coverage_receipt(
                self.identity,
                unknown_backfill,
                canonical_hosts=TEST_HOSTS,
            )

        forged = json.loads(json.dumps(self.marker))
        daily = next(
            item
            for item in forged["accepted_shadow_evidence"]
            if item["mode"] == "daily"
        )
        daily["cleanup_receipts"][0]["cleanup_complete"] = False
        daily_body = {
            key: value
            for key, value in daily.items()
            if key not in {"authentication_tag", "receipt_ref"}
        }
        daily["authentication_tag"] = (
            "shadow_receipt_auth_v2:"
            + self.identity.derive_digest("shadow_receipt_auth_v2", daily_body)
        )
        daily["receipt_ref"] = "shadow_receipt_v2:" + self.identity.derive_digest(
            "shadow_receipt_v2", daily_body
        )
        forged["accepted_shadow_evidence"].sort(key=lambda item: item["receipt_ref"])
        forged["accepted_shadow_refs"] = [
            item["receipt_ref"] for item in forged["accepted_shadow_evidence"]
        ]
        body = {
            key: value for key, value in forged.items() if key != "authentication_tag"
        }
        forged["authentication_tag"] = (
            "production_marker_auth_v2:"
            + self.identity.derive_digest("production-marker-v2", body)
        )
        safe_io.atomic_write_json(self.marker_path, forged)
        with self.assertRaisesRegex(
            authority.ProductionMarkerError,
            "shadow evidence is invalid",
        ):
            authority.load_production_marker(
                self.marker_path,
                identity=self.identity,
                canonical_hosts=TEST_HOSTS,
                history_repo=self.repo,
                target_ref=TARGET_REF,
                configuration_root=self.configuration_root,
                configuration_ref=self.configuration_ref,
                model_era=self.model_era,
                policy_era=self.policy_era,
            )

    def test_shadow_authority_rejects_synthetic_state_bundle_and_cleanup_claim(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run(
            "shadow-authority-adversarial",
            shadow=True,
            bind_export=False,
        )

        with self.assertRaisesRegex(
            orchestrator_module.InvalidTransitionError,
            "staging locator",
        ):
            coordinator.mark_exported("a" * 64, bundle)

        state = coordinator.load_state()
        first_host = next(iter(state["source"]["cells"]))
        first_kind = next(iter(state["source"]["cells"][first_host]))
        original_receipt_ref = state["source"]["cells"][first_host][first_kind][
            "transport_receipt_ref"
        ]

        def replace_source_receipt(state):
            state["source"]["cells"][first_host][first_kind][
                "transport_receipt_ref"
            ] = "source_transport_receipt_v2:" + "e" * 64
            return state, None

        coordinator.store.transaction(replace_source_receipt)
        with self.assertRaisesRegex(
            orchestrator_module.InvalidTransitionError,
            "differs from its transport evidence",
        ):
            coordinator.mark_shadow_exported(bundle)

        def restore_source_receipt(state):
            state["source"]["cells"][first_host][first_kind][
                "transport_receipt_ref"
            ] = original_receipt_ref
            return state, None

        coordinator.store.transaction(restore_source_receipt)

        manifest_path = bundle / "manifest.json"
        original_manifest = manifest_path.read_bytes()
        manifest_path.write_bytes(b'{"synthetic":true}\n')
        with self.assertRaisesRegex(
            orchestrator_module.InvalidTransitionError,
            "bundle validation failed",
        ):
            coordinator.mark_shadow_exported(bundle)
        manifest_path.write_bytes(original_manifest)

        synthetic_root = self.root / "synthetic-shadow-run"
        shutil.copytree(coordinator.run_dir, synthetic_root)
        checkpoint_path = synthetic_root / "checkpoint.json"
        checkpoint = json.loads(checkpoint_path.read_text(encoding="ascii"))
        checkpoint["state"]["run_ref"] = "run_ref_v2:" + "f" * 64
        safe_io.atomic_write_json(checkpoint_path, checkpoint)
        synthetic = RetrospectiveOrchestrator(
            synthetic_root,
            identity_path=self.identity_path,
            require_existing_identity=True,
        )
        with self.assertRaises(CheckpointIntegrityError):
            synthetic.mark_shadow_exported(bundle)

        marked = coordinator.mark_shadow_exported(bundle)
        coverage = marked["publication"]["coverage_receipt"]
        self.assertEqual(coordinator.load_state()["run_ref"], coverage["run_ref"])
        self.assertEqual(
            export_retained_bundle(
                bundle,
                *cli_module._retained_inputs(
                    coordinator,
                    coordinator.load_state(),
                ),
            )["bundle_digest"],
            coverage["export_bundle_digest"],
        )

        coordinator._prepare_shadow_cleanup_claim()

        def forge_counter(state):
            state["publication"]["cleanup_claim"]["removed_file_count"] += 1
            return state, None

        coordinator.store.transaction(forge_counter)
        with self.assertRaisesRegex(
            orchestrator_module.InvalidTransitionError,
            "cleanup totals",
        ):
            coordinator.complete_shadow_export()
        self.assertIsNone(coordinator.load_state()["publication"]["cleanup_receipt"])

        path_run, path_bundle = self.build_exportable_run(
            "shadow-cleanup-path-replacement",
            shadow=True,
            bind_export=False,
        )
        path_run.mark_shadow_exported(path_bundle)
        path_run._prepare_shadow_cleanup_claim()
        outside = self.root / "outside-shadow-cleanup"
        outside.mkdir(mode=0o700)
        marker = outside / "marker.bin"
        marker.write_bytes(b"must survive")
        os.chmod(marker, 0o600)
        raw_root = path_run.run_dir / "raw-inputs"
        raw_saved = path_run.run_dir / "raw-inputs.saved"
        raw_root.rename(raw_saved)
        raw_root.symlink_to(outside, target_is_directory=True)

        pending = path_run.complete_shadow_export()
        self.assertTrue(pending["cleanup_pending"])
        self.assertEqual(b"must survive", marker.read_bytes())
        self.assertIsNone(path_run.load_state()["publication"]["cleanup_receipt"])

    def test_genuine_shadow_cleanup_is_durable_and_lost_response_idempotent(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run(
            "shadow-cleanup-genuine",
            shadow=True,
            bind_export=False,
        )
        raw_file = coordinator.run_dir / "raw-inputs" / "cleanup-evidence.bin"
        raw_file.write_bytes(b"real shadow cleanup evidence")
        os.chmod(raw_file, 0o600)
        expected = coordinator._raw_cleanup_inventory()

        coordinator.mark_shadow_exported(bundle)
        original_transaction = coordinator.store.transaction

        def lose_response_after_commit(mutator, **kwargs):
            result = original_transaction(mutator, **kwargs)
            if result.snapshot.state["publication"]["phase"] == "shadow_complete":
                raise RuntimeError("simulated lost cleanup response")
            return result

        with (
            mock.patch.object(
                coordinator.store,
                "transaction",
                side_effect=lose_response_after_commit,
            ),
            self.assertRaisesRegex(RuntimeError, "lost cleanup response"),
        ):
            coordinator.complete_shadow_export()
        replay = coordinator.complete_shadow_export()
        cleanup = replay["publication"]["cleanup_receipt"]

        self.assertFalse(replay["cleanup_pending"])
        self.assertTrue(replay["idempotent"])
        self.assertEqual(expected["byte_count"], cleanup["removed_byte_count"])
        self.assertEqual(
            expected["directory_count"], cleanup["removed_directory_count"]
        )
        self.assertEqual(expected["file_count"], cleanup["removed_file_count"])
        self.assertEqual(
            replay["publication"]["coverage_receipt"]["receipt_ref"],
            cleanup["coverage_receipt_ref"],
        )
        for name in orchestrator_module.SHADOW_CLEANUP_ROOTS:
            self.assertFalse((coordinator.run_dir / name).exists())

    def test_provider_initialization_requires_exact_revision_and_request(self) -> None:
        replay = authority.initialize_provider_cache(
            self.provider_state,
            history=self.initial_history,
            expected_revision=0,
            identity=self.identity,
        )
        self.assertTrue(replay["idempotent"])
        with self.assertRaises(authority.ProviderCacheConflict):
            authority.initialize_provider_cache(
                self.provider_state,
                history=self.initial_history,
                expected_revision=1,
                identity=self.identity,
            )
        changed_request = replace(self.initial_history, head_commit="f" * 40)
        with self.assertRaises(authority.ProviderCacheConflict):
            authority.initialize_provider_cache(
                self.provider_state,
                history=changed_request,
                expected_revision=0,
                identity=self.identity,
            )

    def test_provider_cache_rejects_tampered_nonzero_initialization_revision(
        self,
    ) -> None:
        cache_path = self.provider_state / authority.PROVIDER_CACHE_FILE
        tampered = json.loads(cache_path.read_text(encoding="ascii"))
        tampered["initialization_request"]["expected_revision"] = 1
        tampered["initialization_request"]["history_projection"][
            "provider_revision"
        ] = 1
        safe_io.atomic_write_json(cache_path, tampered)

        with self.assertRaisesRegex(
            authority.ProviderCacheError,
            "empty cache",
        ):
            authority.assert_provider_cache_matches(
                self.provider_state,
                self.initial_history,
                identity=self.identity,
            )

    def test_provider_initialization_revision_is_independent_of_history_projection(
        self,
    ) -> None:
        state_dir = self.root / "provider-from-existing-history"
        existing_history = replace(self.initial_history, provider_revision=7)

        initialized = authority.initialize_provider_cache(
            state_dir,
            history=existing_history,
            expected_revision=0,
            identity=self.identity,
        )
        validated = authority.assert_provider_cache_matches(
            state_dir,
            existing_history,
            identity=self.identity,
        )

        self.assertEqual(
            0,
            initialized["state"]["initialization_request"]["expected_revision"],
        )
        self.assertEqual(7, validated["provider_revision"])

    def test_provider_cache_must_be_exact_before_creation_and_promotion(self) -> None:
        coordinator, bundle = self.build_exportable_run("provider-cache-closed")
        cache_path = self.provider_state / authority.PROVIDER_CACHE_FILE
        original_cache = cache_path.read_bytes()
        malformed_cache = b'{"schema":"retrospective_provider_cache_v2"}\n'

        for label, payload in (("missing", None), ("malformed", malformed_cache)):
            with self.subTest(phase="create", case=label):
                if payload is None:
                    cache_path.unlink()
                else:
                    safe_io.atomic_write_bytes(cache_path, payload)
                try:
                    with self.assertRaises(PublicationRejected):
                        self.transaction(
                            coordinator,
                            bundle,
                            journal_name=f"{label}-cache-create.json",
                        )
                    self.assertEqual(self.base_head, self.head())
                    self.assertFalse(
                        (coordinator.run_dir / f"{label}-cache-create.json").exists()
                    )
                finally:
                    safe_io.atomic_write_bytes(cache_path, original_cache)

        transaction = self.transaction(
            coordinator,
            bundle,
            journal_name="provider-cache-promotion.json",
        )
        transaction.prepare()
        transaction.stage()
        transaction.seal()
        transaction.close_compliance()
        for label, payload in (("missing", None), ("malformed", malformed_cache)):
            with self.subTest(phase="promote", case=label):
                if payload is None:
                    cache_path.unlink()
                else:
                    safe_io.atomic_write_bytes(cache_path, payload)
                try:
                    with self.assertRaises(authority.ProviderCacheError):
                        transaction.promote()
                    self.assertEqual("compliance_closed", transaction.status()["phase"])
                    self.assertEqual(self.base_head, self.head())
                    with self.assertRaises(authority.ProviderCacheError):
                        PublicationTransaction.open(
                            transaction.journal_path,
                            adapter=self.adapter,
                            expected_attempt_ref=transaction.attempt_ref,
                        )
                    journal = safe_io.read_bounded_json(
                        transaction.journal_path,
                        max_bytes=2 * 1024 * 1024,
                        require_owner_only=True,
                    )
                    self.assertEqual("compliance_closed", journal["phase"])
                finally:
                    safe_io.atomic_write_bytes(cache_path, original_cache)

    def test_state_paths_reject_symlink_ancestors_and_lock_symlinks(self) -> None:
        real_parent = self.root / "path-target"
        real_parent.mkdir(mode=0o700)
        alias = self.root / "path-alias"
        alias.symlink_to(real_parent, target_is_directory=True)

        with self.assertRaises(safe_io.UnsafePathError):
            authority.initialize_provider_cache(
                alias / "provider",
                history=self.initial_history,
                expected_revision=0,
                identity=self.identity,
            )
        self.assertFalse((real_parent / "provider").exists())

        with self.assertRaises(StateCorruptionError):
            LocalGitPublicationAdapter(
                self.repo,
                alias / "adapter-state",
                signing_key=self.fingerprint,
                gnupg_home=self.gnupg_home,
                expected_signer_uid=DEFAULT_PUBLISHER_UID,
                signing_program=self.gpg,
            )
        self.assertFalse((real_parent / "adapter-state").exists())

        coordinator, bundle = self.build_exportable_run("symlink-journal")
        state = coordinator.load_state()
        with self.assertRaisesRegex(
            AttemptMismatchError,
            "outside the authoritative run directory",
        ):
            PublicationTransaction.create(
                alias / "journal-state" / "publication.json",
                bundle_dir=bundle,
                destination=self.destination(state),
                target_ref=TARGET_REF,
                expected_target_head=state["authority"]["history_snapshot"][
                    "history_commit"
                ],
                run_dir=coordinator.run_dir,
                identity_path=self.identity_path,
                adapter=self.adapter,
                claim_before_persist=lambda attempt_ref, plan_digest: (
                    coordinator.claim_publication(
                        attempt_ref,
                        plan_digest,
                        bundle_dir=bundle,
                    )
                ),
            )
        self.assertFalse((real_parent / "journal-state").exists())

        lock_state = self.root / "lock-state"
        lock_state.mkdir(mode=0o700)
        lock_target = self.root / "lock-target"
        safe_io.atomic_write_bytes(lock_target, b"")
        (lock_state / "publication.lock").symlink_to(lock_target)
        with self.assertRaises((OSError, StateCorruptionError)):
            LocalGitPublicationAdapter(
                self.repo,
                lock_state,
                signing_key=self.fingerprint,
                gnupg_home=self.gnupg_home,
                expected_signer_uid=DEFAULT_PUBLISHER_UID,
                signing_program=self.gpg,
            )

    def test_public_write_owners_reject_source_roots_before_creation(self) -> None:
        codex_root = self.root / "source-account" / ".codex"
        sessions = codex_root / "sessions"
        archived = codex_root / "archived_sessions"
        sessions.mkdir(parents=True, mode=0o700)
        archived.mkdir(mode=0o700)
        alias = self.root / "source-alias"
        alias.symlink_to(sessions, target_is_directory=True)

        with mock.patch.object(
            temporary_paths,
            "local_codex_root",
            return_value=codex_root,
        ):
            for source_parent in (sessions, archived, alias):
                state_dir = source_parent / "publication-state"
                marker_path = source_parent / "production-marker.json"
                with (
                    self.subTest(owner="publication-adapter", path=state_dir),
                    self.assertRaisesRegex(
                        safe_io.UnsafePathError,
                        "overlaps a retrospective source root",
                    ),
                ):
                    LocalGitPublicationAdapter(
                        self.repo,
                        state_dir,
                        signing_key=self.fingerprint,
                        gnupg_home=self.gnupg_home,
                        expected_signer_uid=DEFAULT_PUBLISHER_UID,
                        signing_program=self.gpg,
                    )
                with (
                    self.subTest(owner="production-marker", path=marker_path),
                    self.assertRaisesRegex(
                        safe_io.UnsafePathError,
                        "overlaps a retrospective source root",
                    ),
                ):
                    authority.issue_production_marker(
                        marker_path,
                        identity=self.identity,
                        canonical_hosts=TEST_HOSTS,
                        history_repo=self.repo,
                        target_ref=TARGET_REF,
                        configuration_root=self.configuration_root,
                        configuration_ref=self.configuration_ref,
                        model_era=self.model_era,
                        policy_era=self.policy_era,
                        calibration_receipt=self.calibration_receipt,
                        accepted_shadow_evidence=self.shadow_evidence,
                        automation_cutover_record=self.automation_cutover_record,
                        installed_commits=(self.base_head,),
                    )
                self.assertFalse(state_dir.exists())
                self.assertFalse(marker_path.exists())

    def test_git_metadata_requires_real_current_user_controlled_directories(
        self,
    ) -> None:
        git_dir = Path(
            run_command(
                ["git", "rev-parse", "--path-format=absolute", "--git-dir"],
                cwd=self.repo,
            ).stdout.strip()
        )
        original_mode = git_dir.stat().st_mode & 0o777
        os.chmod(git_dir, original_mode | 0o020)
        try:
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "current-user controlled|current-user-controlled",
            ):
                self.publication_adapter()
        finally:
            os.chmod(git_dir, original_mode)

        objects = git_dir / "objects"
        real_objects = git_dir / "objects-real"
        objects.rename(real_objects)
        objects.symlink_to(real_objects, target_is_directory=True)
        try:
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "Git object store",
            ):
                self.publication_adapter()
        finally:
            objects.unlink()
            real_objects.rename(objects)

    def test_linked_worktree_uses_validated_real_git_metadata(self) -> None:
        linked = self.root / "linked-history"
        run_command(
            ["git", "worktree", "add", "--detach", str(linked), self.base_head],
            cwd=self.repo,
        )
        common_dir = Path(
            run_command(
                [
                    "git",
                    "rev-parse",
                    "--path-format=absolute",
                    "--git-common-dir",
                ],
                cwd=linked,
            ).stdout.strip()
        )
        common_mode = common_dir.stat().st_mode & 0o777
        os.chmod(common_dir, common_mode | 0o020)
        try:
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "current-user-controlled real directory",
            ):
                LocalGitPublicationAdapter(
                    linked,
                    self.root / "invalid-linked-provider-state",
                    signing_key=self.fingerprint,
                    gnupg_home=self.gnupg_home,
                    expected_signer_uid=DEFAULT_PUBLISHER_UID,
                    signing_program=self.gpg,
                )
        finally:
            os.chmod(common_dir, common_mode)

        adapter = LocalGitPublicationAdapter(
            linked,
            self.root / "linked-provider-state",
            signing_key=self.fingerprint,
            gnupg_home=self.gnupg_home,
            expected_signer_uid=DEFAULT_PUBLISHER_UID,
            signing_program=self.gpg,
        )

        self.assertEqual(linked, adapter.repo_path)
        self.assertEqual(
            self.base_head,
            adapter._git(("rev-parse", "HEAD")).stdout.decode("ascii").strip(),
        )

    def test_linked_worktree_rejects_discovery_file_replacement(self) -> None:
        linked = self.root / "linked-discovery-binding"
        run_command(
            ["git", "worktree", "add", "--detach", str(linked), self.base_head],
            cwd=self.repo,
        )
        git_dir = Path(
            run_command(
                ["git", "rev-parse", "--path-format=absolute", "--git-dir"],
                cwd=linked,
            ).stdout.strip()
        )
        adapter = LocalGitPublicationAdapter(
            linked,
            self.root / "linked-discovery-provider-state",
            signing_key=self.fingerprint,
            gnupg_home=self.gnupg_home,
            expected_signer_uid=DEFAULT_PUBLISHER_UID,
            signing_program=self.gpg,
        )

        for index, path in enumerate(
            (linked / ".git", git_dir / "commondir", git_dir / "gitdir")
        ):
            with self.subTest(path=path.name):
                displaced = path.with_name(f"{path.name}.original-{index}")
                original_mode = stat.S_IMODE(path.stat().st_mode)
                original = path.read_bytes()
                path.rename(displaced)
                path.write_bytes(original)
                path.chmod(original_mode)
                try:
                    with self.assertRaisesRegex(
                        publication_support.LocalGitPublicationError,
                        "discovery file changed|safety binding",
                    ):
                        adapter._git(("rev-parse", "HEAD"))
                finally:
                    path.unlink()
                    displaced.rename(path)

        commondir = git_dir / "commondir"
        original = commondir.read_bytes()
        commondir.write_bytes(original + b"\n")
        try:
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "discovery file changed|safety binding",
            ):
                adapter._git(("rev-parse", "HEAD"))
        finally:
            commondir.write_bytes(original)

    def test_linked_worktree_commands_ignore_discovery_file_aba(self) -> None:
        linked = self.root / "linked-discovery-aba"
        replacement = self.root / "replacement-discovery-aba"
        run_command(
            ["git", "worktree", "add", "--detach", str(linked), self.base_head],
            cwd=self.repo,
        )
        run_command(["git", "init", "-q", str(replacement)])
        git_dir = Path(
            run_command(
                ["git", "rev-parse", "--path-format=absolute", "--git-dir"],
                cwd=linked,
            ).stdout.strip()
        )
        repository = authority._GitRepository(
            linked,
            gnupg_home=self.gnupg_home,
            git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
            gpg_program=self.gpg,
        )
        malicious_git_dir = replacement / ".git"

        for index, (path, payload) in enumerate(
            (
                (linked / ".git", f"gitdir: {malicious_git_dir}\n".encode()),
                (git_dir / "commondir", f"{malicious_git_dir}\n".encode()),
                (git_dir / "gitdir", f"{malicious_git_dir}\n".encode()),
            )
        ):
            with self.subTest(path=path.name):
                real_run = authority._run_bounded
                displaced = path.with_name(f"{path.name}.aba-{index}")
                observed = False

                def swap_after_binding(argv, **kwargs):
                    nonlocal observed
                    if not observed:
                        observed = True
                        path.rename(displaced)
                        path.write_bytes(payload)
                        try:
                            return real_run(argv, **kwargs)
                        finally:
                            path.unlink()
                            displaced.rename(path)
                    return real_run(argv, **kwargs)

                with mock.patch.object(
                    authority, "_run_bounded", side_effect=swap_after_binding
                ):
                    subject = repository.text(
                        "show", "-s", "--format=%s", self.base_head
                    )

                self.assertTrue(observed)
                self.assertEqual("Initialize history", subject)

    def test_history_reader_and_publisher_reject_shallow_drift(self) -> None:
        repository = authority._GitRepository(
            self.repo,
            gnupg_home=self.gnupg_home,
            git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
            gpg_program=self.gpg,
        )
        common_dir = repository._repository_admission.common_dir
        shallow = common_dir / "shallow"
        shallow.write_text(f"{self.base_head}\n", encoding="ascii")
        try:
            with self.assertRaisesRegex(
                authority.HistoryValidationError, "safety binding changed"
            ):
                repository.text("merge-base", "--is-ancestor", self.base_head, "HEAD")
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "Git shallow boundaries are not allowed",
            ):
                self.adapter._git(
                    ("merge-base", "--is-ancestor", self.base_head, "HEAD")
                )
        finally:
            shallow.unlink()

    def test_history_reader_and_publisher_share_repository_admission(self) -> None:
        alias = self.root / "history-repository-alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaisesRegex(
            authority.HistoryValidationError, "local safety admission"
        ):
            authority._GitRepository(
                alias,
                gnupg_home=self.gnupg_home,
                git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
                gpg_program=self.gpg,
            )

        mode = self.repo.stat().st_mode & 0o777
        os.chmod(self.repo, mode | 0o020)
        try:
            with self.assertRaisesRegex(
                authority.HistoryValidationError, "local safety admission"
            ):
                authority._GitRepository(
                    self.repo,
                    gnupg_home=self.gnupg_home,
                    git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
                    gpg_program=self.gpg,
                )
        finally:
            os.chmod(self.repo, mode)

        alternates = self.repo / ".git" / "objects" / "info" / "alternates"
        alternates.write_text(str(self.root / "alternate-objects") + "\n")
        try:
            with self.assertRaisesRegex(
                authority.HistoryValidationError, "local safety admission"
            ):
                authority._GitRepository(
                    self.repo,
                    gnupg_home=self.gnupg_home,
                    git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
                    gpg_program=self.gpg,
                )
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "Git object alternates are not allowed",
            ):
                self.publication_adapter()
        finally:
            alternates.unlink()

    def test_history_reader_and_publisher_reject_promisor_pack_markers(self) -> None:
        repository = authority._GitRepository(
            self.repo,
            gnupg_home=self.gnupg_home,
            git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
            gpg_program=self.gpg,
        )
        pack_dir = self.repo / ".git" / "objects" / "pack"
        pack_dir.mkdir(exist_ok=True)
        marker = pack_dir / ("0" * 40 + ".promisor")
        marker.write_bytes(b"")
        try:
            with self.assertRaisesRegex(
                authority.HistoryValidationError, "safety binding changed"
            ):
                repository.text("rev-parse", "HEAD")
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "promisor pack metadata",
            ):
                self.adapter._git(("rev-parse", "HEAD"))
            with self.assertRaisesRegex(
                authority.HistoryValidationError, "complete and non-promisor"
            ):
                authority._GitRepository(
                    self.repo,
                    gnupg_home=self.gnupg_home,
                    git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
                    gpg_program=self.gpg,
                )
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "complete and non-promisor",
            ):
                self.publication_adapter()
        finally:
            marker.unlink()

        real_revalidate = git_safety.revalidate_local_repository
        injected = False

        def inject_after_path_revalidation(*args, **kwargs) -> None:
            nonlocal injected
            real_revalidate(*args, **kwargs)
            if not injected:
                marker.write_bytes(b"")
                injected = True

        try:
            with mock.patch.object(
                git_safety,
                "revalidate_local_repository",
                side_effect=inject_after_path_revalidation,
            ):
                with self.assertRaisesRegex(
                    git_safety.LocalRepositorySafetyError,
                    "promisor pack metadata",
                ):
                    with git_safety.bind_local_repository_command(
                        self.adapter._git_repository_admission,
                        self.adapter._git_directory_identity,
                    ):
                        self.fail("promisor marker reached a bound Git command")
        finally:
            marker.unlink(missing_ok=True)

        alias_marker = pack_dir / ("1" * 40 + ".PROMISOR")
        alias_marker.write_bytes(b"")
        try:
            with self.assertRaisesRegex(
                authority.HistoryValidationError, "complete and non-promisor"
            ):
                authority._GitRepository(
                    self.repo,
                    gnupg_home=self.gnupg_home,
                    git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
                    gpg_program=self.gpg,
                )
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "promisor pack metadata",
            ):
                self.adapter._git(("rev-parse", "HEAD"))
        finally:
            alias_marker.unlink()

        ignorable_marker = pack_dir / ("2" * 40 + ".promi\u200dsor")
        ignorable_marker.write_bytes(b"")
        try:
            with self.assertRaisesRegex(
                authority.HistoryValidationError, "safety binding changed"
            ):
                repository.text("rev-parse", "HEAD")
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError, "portable ASCII"
            ):
                self.adapter._git(("rev-parse", "HEAD"))
            with self.assertRaisesRegex(
                authority.HistoryValidationError, "complete and non-promisor"
            ):
                authority._GitRepository(
                    self.repo,
                    gnupg_home=self.gnupg_home,
                    git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
                    gpg_program=self.gpg,
                )
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "complete and non-promisor",
            ):
                self.publication_adapter()
        finally:
            ignorable_marker.unlink()

    def test_history_reader_revalidates_shared_repository_admission(self) -> None:
        repository = authority._GitRepository(
            self.repo,
            gnupg_home=self.gnupg_home,
            git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
            gpg_program=self.gpg,
        )
        grafts = self.repo / ".git" / "info" / "grafts"
        grafts.write_text(f"{self.base_head}\n", encoding="ascii")
        try:
            with self.assertRaisesRegex(
                authority.HistoryValidationError, "safety binding changed"
            ):
                repository.text("rev-parse", "HEAD")
        finally:
            grafts.unlink()

    def test_history_reader_and_publisher_reject_unclosed_config_sources(self) -> None:
        included = self.root / "included-history-config"
        included.write_text('[remote "origin"]\n\tpromisor = true\n', encoding="ascii")
        run_command(
            ["git", "config", "--local", "include.path", str(included)],
            cwd=self.repo,
        )
        try:
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "complete and non-promisor",
            ):
                self.publication_adapter()
            with self.assertRaisesRegex(
                authority.HistoryValidationError,
                "complete and non-promisor",
            ):
                authority._GitRepository(
                    self.repo,
                    gnupg_home=self.gnupg_home,
                    git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
                    gpg_program=self.gpg,
                )
        finally:
            run_command(
                ["git", "config", "--local", "--unset-all", "include.path"],
                cwd=self.repo,
            )

        worktree_config = self.repo / ".git" / "config.worktree"
        worktree_config.write_text(
            '[remote "origin"]\n\tpromisor = true\n', encoding="ascii"
        )
        try:
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "Git worktree configurations are not allowed",
            ):
                self.publication_adapter()
            with self.assertRaisesRegex(
                authority.HistoryValidationError, "local safety admission"
            ):
                authority._GitRepository(
                    self.repo,
                    gnupg_home=self.gnupg_home,
                    git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
                    gpg_program=self.gpg,
                )
        finally:
            worktree_config.unlink()

        run_command(
            ["git", "config", "--local", "extensions.worktreeConfig", "true"],
            cwd=self.repo,
        )
        try:
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "complete and non-promisor",
            ):
                self.publication_adapter()
            with self.assertRaisesRegex(
                authority.HistoryValidationError,
                "complete and non-promisor",
            ):
                authority._GitRepository(
                    self.repo,
                    gnupg_home=self.gnupg_home,
                    git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
                    gpg_program=self.gpg,
                )
        finally:
            run_command(
                [
                    "git",
                    "config",
                    "--local",
                    "--unset-all",
                    "extensions.worktreeConfig",
                ],
                cwd=self.repo,
            )

    def test_history_reader_and_publisher_reject_config_drift(self) -> None:
        repository = authority._GitRepository(
            self.repo,
            gnupg_home=self.gnupg_home,
            git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
            gpg_program=self.gpg,
        )
        config_path = self.repo / ".git" / "config"
        original = config_path.read_bytes()
        config_path.write_bytes(original + b"\n")
        try:
            with self.assertRaisesRegex(
                authority.HistoryValidationError, "safety binding changed"
            ):
                repository.text("rev-parse", "HEAD")
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "local Git configuration changed after validation",
            ):
                self.adapter._git(("rev-parse", "HEAD"))
        finally:
            config_path.write_bytes(original)

    @darwin_security_test
    def test_history_reader_and_publisher_reject_config_extended_acl(self) -> None:
        config_path = self.repo / ".git" / "config"
        self._add_darwin_acl(config_path)
        try:
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "owner-controlled",
            ):
                self.publication_adapter()
            with self.assertRaisesRegex(
                authority.HistoryValidationError,
                "local safety admission",
            ):
                authority._GitRepository(
                    self.repo,
                    gnupg_home=self.gnupg_home,
                    git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
                    gpg_program=self.gpg,
                )
        finally:
            self._remove_darwin_acl(config_path)

    @darwin_security_test
    def test_history_reader_and_publisher_reject_late_config_acl(self) -> None:
        repository = authority._GitRepository(
            self.repo,
            gnupg_home=self.gnupg_home,
            git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
            gpg_program=self.gpg,
        )
        config_path = self.repo / ".git" / "config"
        self._add_darwin_acl(config_path)
        try:
            with self.assertRaisesRegex(
                authority.HistoryValidationError,
                "safety binding changed",
            ):
                repository.text("rev-parse", "HEAD")
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "owner-controlled",
            ):
                self.adapter._git(("rev-parse", "HEAD"))
        finally:
            self._remove_darwin_acl(config_path)

    def test_history_git_uses_admitted_directories_after_path_replacement(self) -> None:
        repository = authority._GitRepository(
            self.repo,
            gnupg_home=self.gnupg_home,
            git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
            gpg_program=self.gpg,
        )
        replacement = self.root / "replacement-history"
        displaced = self.root / "admitted-history"
        run_command(["git", "init", "-q", str(replacement)])
        real_run = authority._run_bounded
        observed = False

        def swap_after_binding(argv, **kwargs):
            nonlocal observed
            if not observed:
                observed = True
                self.assertIn(("-C", "."), tuple(zip(argv, argv[1:])))
                self.assertNotIn(str(self.repo), argv)
                descriptors = kwargs["pass_fds"]
                self.assertEqual(4, len(descriptors))
                environment = kwargs["env"]
                self.assertTrue(
                    git_safety._BOUND_GIT_ENVIRONMENT_KEYS.isdisjoint(environment)
                )
                self.assertEqual(str(descriptors[2]), argv[6])
                self.assertEqual(str(descriptors[1]), argv[7])
                self.assertEqual(str(descriptors[3]), argv[8])
                self.assertEqual(".", argv[9])
                self.repo.rename(displaced)
                replacement.rename(self.repo)
                try:
                    return real_run(argv, **kwargs)
                finally:
                    self.repo.rename(replacement)
                    displaced.rename(self.repo)
            return real_run(argv, **kwargs)

        with mock.patch.object(
            authority, "_run_bounded", side_effect=swap_after_binding
        ):
            subject = repository.text("show", "-s", "--format=%s", self.base_head)

        self.assertTrue(observed)
        self.assertEqual("Initialize history", subject)

    def test_publication_git_writes_admitted_object_store_after_path_replacement(
        self,
    ) -> None:
        replacement = self.root / "replacement-publication"
        displaced = self.root / "admitted-publication"
        run_command(["git", "init", "-q", str(replacement)])
        real_run = publication_git_commits._run_bounded_subprocess
        observed = False

        def swap_after_binding(argv, **kwargs):
            nonlocal observed
            if not observed:
                observed = True
                self.assertIn(("-C", "."), tuple(zip(argv, argv[1:])))
                self.assertNotIn(str(self.repo), argv)
                descriptors = kwargs["inherited_descriptors"]
                self.assertEqual(4, len(descriptors))
                environment = kwargs["environment"]
                self.assertTrue(
                    git_safety._BOUND_GIT_ENVIRONMENT_KEYS.isdisjoint(environment)
                )
                self.assertEqual(str(descriptors[2]), argv[6])
                self.assertEqual(str(descriptors[1]), argv[7])
                self.assertEqual(str(descriptors[3]), argv[8])
                self.assertEqual(".", argv[9])
                self.repo.rename(displaced)
                replacement.rename(self.repo)
                try:
                    return real_run(argv, **kwargs)
                finally:
                    self.repo.rename(replacement)
                    displaced.rename(self.repo)
            return real_run(argv, **kwargs)

        payload = b"descriptor-bound publication object\n"
        with mock.patch.object(
            publication_git_commits,
            "_run_bounded_subprocess",
            side_effect=swap_after_binding,
        ):
            object_id = (
                self.adapter._git(("hash-object", "-w", "--stdin"), input_bytes=payload)
                .stdout.decode("ascii")
                .strip()
            )

        self.assertTrue(observed)
        run_command(["git", "cat-file", "-e", object_id], cwd=self.repo)
        replacement_result = subprocess.run(
            ["git", "cat-file", "-e", object_id],
            cwd=replacement,
            check=False,
            capture_output=True,
            timeout=30,
        )
        self.assertNotEqual(0, replacement_result.returncode)

    def test_history_git_commands_ignore_replace_refs(self) -> None:
        tree = run_command(
            ["git", "rev-parse", f"{self.base_head}^{{tree}}"], cwd=self.repo
        ).stdout.strip()
        replacement = run_command(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit-tree",
                tree,
                "-m",
                "Replacement history",
            ],
            cwd=self.repo,
        ).stdout.strip()
        run_command(["git", "replace", self.base_head, replacement], cwd=self.repo)
        ordinary = run_command(
            ["git", "show", "-s", "--format=%s", self.base_head], cwd=self.repo
        ).stdout.strip()
        repository = authority._GitRepository(
            self.repo,
            gnupg_home=self.gnupg_home,
            git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
            gpg_program=self.gpg,
        )

        publication_subject = (
            self.adapter._git(("show", "-s", "--format=%s", self.base_head))
            .stdout.decode("utf-8")
            .strip()
        )
        authority_subject = repository.text("show", "-s", "--format=%s", self.base_head)

        self.assertEqual("Replacement history", ordinary)
        self.assertEqual("Initialize history", publication_subject)
        self.assertEqual("Initialize history", authority_subject)

    def test_history_git_commands_reject_grafts_that_forge_reachability(self) -> None:
        tree = run_command(
            ["git", "rev-parse", f"{self.base_head}^{{tree}}"], cwd=self.repo
        ).stdout.strip()
        unreachable = run_command(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit-tree",
                tree,
                "-m",
                "Unreachable history",
            ],
            cwd=self.repo,
        ).stdout.strip()
        grafts = self.repo / ".git" / "info" / "grafts"
        grafts.write_text(f"{self.base_head} {unreachable}\n", encoding="ascii")

        forged = subprocess.run(
            ["git", "merge-base", "--is-ancestor", unreachable, self.base_head],
            cwd=self.repo,
            check=False,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(0, forged.returncode)
        with self.assertRaisesRegex(
            publication_support.LocalGitPublicationError,
            "Git grafts are not allowed",
        ):
            self.adapter._is_ancestor(unreachable, self.base_head)
        with self.assertRaisesRegex(
            publication_support.LocalGitPublicationError,
            "Git grafts are not allowed",
        ):
            self.publication_adapter()

    def test_history_git_rejects_promisor_configuration_without_credentials(
        self,
    ) -> None:
        marker = self.root / "credential-helper-ran"
        helper = self.root / "credential-helper"
        helper.write_text(
            f"#!/bin/sh\n/usr/bin/touch {shlex.quote(str(marker))}\nexit 1\n",
            encoding="ascii",
        )
        helper.chmod(0o700)
        run_command(
            [
                "git",
                "config",
                "--local",
                "credential.helper",
                f"!{shlex.quote(str(helper))}",
            ],
            cwd=self.repo,
        )
        run_command(
            ["git", "config", "--local", "remote.origin.promisor", "true"],
            cwd=self.repo,
        )
        try:
            with self.assertRaisesRegex(
                publication_support.LocalGitPublicationError,
                "complete and non-promisor",
            ):
                self.publication_adapter()
            with self.assertRaisesRegex(
                authority.HistoryValidationError,
                "complete and non-promisor",
            ):
                authority._GitRepository(
                    self.repo,
                    gnupg_home=self.gnupg_home,
                    git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
                    gpg_program=self.gpg,
                )
            self.assertFalse(marker.exists())
        finally:
            run_command(
                ["git", "config", "--local", "--unset-all", "credential.helper"],
                cwd=self.repo,
            )
            run_command(
                ["git", "config", "--local", "--unset-all", "remote.origin.promisor"],
                cwd=self.repo,
            )

    def test_history_git_commands_disable_lazy_fetch_and_credentials(self) -> None:
        publication_calls: list[tuple[tuple[str, ...], dict[str, str]]] = []
        authority_calls: list[tuple[tuple[str, ...], dict[str, str]]] = []
        real_publication_run = publication_git_commits._run_bounded_subprocess
        real_authority_run = authority._run_bounded

        def record_publication(argv, **kwargs):
            publication_calls.append((tuple(argv), dict(kwargs["environment"])))
            return real_publication_run(argv, **kwargs)

        def record_authority(argv, **kwargs):
            authority_calls.append((tuple(argv), dict(kwargs["env"])))
            return real_authority_run(argv, **kwargs)

        with mock.patch.object(
            publication_git_commits,
            "_run_bounded_subprocess",
            side_effect=record_publication,
        ):
            adapter = self.publication_adapter()
            adapter._git(("rev-parse", "HEAD"))
        with mock.patch.object(
            authority,
            "_run_bounded",
            side_effect=record_authority,
        ):
            repository = authority._GitRepository(
                self.repo,
                gnupg_home=self.gnupg_home,
                git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
                gpg_program=self.gpg,
            )
            repository.text("rev-parse", "HEAD")

        for calls in (publication_calls, authority_calls):
            self.assertTrue(calls)
            for argv, environment in calls:
                self.assertIn("core.commitGraph=false", argv)
                self.assertIn("core.fsmonitor=false", argv)
                self.assertIn("core.multiPackIndex=false", argv)
                self.assertIn("core.askPass=/usr/bin/false", argv)
                self.assertIn("credential.helper=", argv)
                self.assertEqual("/usr/bin/false", environment["GIT_ASKPASS"])
                self.assertEqual("/usr/bin/false", environment["SSH_ASKPASS"])
                self.assertEqual("1", environment["GIT_NO_LAZY_FETCH"])
                self.assertEqual("0", environment["GIT_OPTIONAL_LOCKS"])
                self.assertEqual("0", environment["GIT_TERMINAL_PROMPT"])

    def test_history_git_commands_override_repository_topology_caches(self) -> None:
        for key in ("core.commitGraph", "core.fsmonitor", "core.multiPackIndex"):
            run_command(["git", "config", "--local", key, "true"], cwd=self.repo)
        try:
            repository = authority._GitRepository(
                self.repo,
                gnupg_home=self.gnupg_home,
                git_binary=executable_authority.DEFAULT_GIT_EXECUTABLE,
                gpg_program=self.gpg,
            )
            publisher = self.publication_adapter()
            for key in ("core.commitGraph", "core.fsmonitor", "core.multiPackIndex"):
                with self.subTest(reader="authority", key=key):
                    self.assertEqual("false", repository.text("config", "--bool", key))
                with self.subTest(reader="publisher", key=key):
                    value = publisher._git(("config", "--bool", key)).stdout
                    self.assertEqual(b"false", value.strip())
        finally:
            for key in ("core.commitGraph", "core.fsmonitor", "core.multiPackIndex"):
                run_command(
                    ["git", "config", "--local", "--unset-all", key], cwd=self.repo
                )

    def test_privacy_reread_rejects_replacement_symlink_and_oversize_races(
        self,
    ) -> None:
        _, bundle = self.build_exportable_run("privacy-races")
        target_name = "manifest.json"
        target = bundle / target_name
        original = target.read_bytes()
        real_open = os.open

        for scenario in ("replacement", "symlink", "oversize"):
            with self.subTest(scenario=scenario):
                safe_io.atomic_write_bytes(target, original)
                inventory = build_artifact_inventory(bundle)
                replacement = self.root / f"{scenario}-replacement"
                if scenario == "replacement":
                    changed = bytearray(original)
                    changed[0] ^= 1
                    safe_io.atomic_write_bytes(replacement, bytes(changed))
                elif scenario == "symlink":
                    symlink_source = self.root / "symlink-source"
                    safe_io.atomic_write_bytes(symlink_source, original)
                    replacement.symlink_to(symlink_source)

                triggered = False

                def racing_open(
                    path,
                    flags,
                    mode=0o777,
                    *,
                    dir_fd=None,
                ):
                    nonlocal triggered
                    if path == target_name and dir_fd is not None and not triggered:
                        triggered = True
                        if scenario in {"replacement", "symlink"}:
                            os.replace(replacement, target)
                        else:
                            descriptor = real_open(
                                target,
                                os.O_WRONLY | os.O_APPEND,
                            )
                            try:
                                os.write(descriptor, b"oversize")
                            finally:
                                os.close(descriptor)
                    return real_open(path, flags, mode, dir_fd=dir_fd)

                try:
                    with mock.patch.object(
                        finalize_module.os,
                        "open",
                        side_effect=racing_open,
                    ):
                        with self.assertRaises(finalize_module.ArtifactValidationError):
                            finalize_module._privacy_validate_bundle(
                                bundle,
                                expected_inventory=inventory,
                            )
                    self.assertTrue(triggered)
                finally:
                    target.unlink(missing_ok=True)
                    safe_io.atomic_write_bytes(target, original)
                    replacement.unlink(missing_ok=True)

    def test_privacy_reread_accepts_benign_timestamp_change(self) -> None:
        _, bundle = self.build_exportable_run("privacy-benign-timestamp")
        target_name = "manifest.json"
        target = bundle / target_name
        inventory = build_artifact_inventory(bundle)
        real_open = os.open
        triggered = False

        def touching_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal triggered
            if path == target_name and dir_fd is not None and not triggered:
                triggered = True
                metadata = target.stat()
                os.utime(
                    target,
                    ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000),
                )
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch.object(
            finalize_module.os,
            "open",
            side_effect=touching_open,
        ):
            artifacts, _parsed = finalize_module._privacy_validate_bundle(
                bundle,
                expected_inventory=inventory,
            )

        self.assertTrue(triggered)
        self.assertEqual(target.read_bytes(), artifacts[target_name])

    def test_privacy_reread_rejects_late_acl_policy_drift(self) -> None:
        _, bundle = self.build_exportable_run("privacy-late-acl")
        inventory = build_artifact_inventory(bundle)
        real_validate = safe_io.validate_owner_only_file_descriptor
        target_validations = 0

        def drift_after_read(descriptor, display_path, **kwargs):
            nonlocal target_validations
            real_validate(descriptor, display_path, **kwargs)
            if display_path.name == "manifest.json":
                target_validations += 1
                if target_validations == 2:
                    raise safe_io.UnsafePathError("simulated late Darwin ACL drift")

        with (
            mock.patch.object(
                publication_support.safe_io,
                "validate_owner_only_file_descriptor",
                side_effect=drift_after_read,
            ),
            self.assertRaisesRegex(
                finalize_module.ArtifactValidationError,
                "access policy changed while reading",
            ),
        ):
            finalize_module._privacy_validate_bundle(
                bundle,
                expected_inventory=inventory,
            )

        self.assertEqual(2, target_validations)

    def test_recovery_repairs_outer_promoted_after_exact_target_cas_crash(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run("crash-after-target-cas")

        def crash(point, _state):
            if point == "promote.after_target_cas":
                raise RuntimeError("simulated target CAS crash")

        crashing = self.publication_adapter(failure_injector=crash)
        transaction = self.transaction(coordinator, bundle, adapter=crashing)
        transaction.prepare()
        transaction.stage()
        transaction.seal()
        transaction.close_compliance()
        with self.assertRaisesRegex(RuntimeError, "target CAS crash"):
            transaction.promote()
        self.assertEqual("compliance_closed", transaction.status()["phase"])
        self.assertNotEqual(self.base_head, self.head())

        recovered_adapter = self.publication_adapter()
        recovered = PublicationTransaction.open(
            transaction.journal_path,
            adapter=recovered_adapter,
            expected_attempt_ref=transaction.attempt_ref,
        )
        self.assertEqual("promoted", recovered.status()["phase"])
        self.assertEqual(
            self.head(), recovered.status()["receipts"]["promotion"]["target_head"]
        )
        self.assertEqual(
            "promoted",
            safe_io.read_bounded_json(
                transaction.journal_path,
                max_bytes=2 * 1024 * 1024,
                require_owner_only=True,
            )["phase"],
        )

    def test_missing_retention_sidecar_fails_before_binding_state_persists(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run("missing-retention-sidecar")
        sidecar = bundle.with_name(f".{bundle.name}.retention-v2.json")
        sidecar.unlink()
        with self.assertRaisesRegex(RetainedExportError, "sidecar is missing"):
            self.transaction(coordinator, bundle)

        self.assertFalse(
            (coordinator.run_dir / "publication-transaction-v2.json").exists()
        )
        self.assertNotIn(
            "publication_claim",
            coordinator.load_state()["publication"],
        )

    def test_retention_binding_and_abort_serialize_on_the_attempt_lock(self) -> None:
        for cleanup_first in (False, True):
            with self.subTest(cleanup_first=cleanup_first):
                coordinator, bundle = self.build_exportable_run(
                    f"retention-race-{cleanup_first}"
                )
                adapter = self.publication_adapter()
                abort_adapter = self.publication_adapter()
                transaction = self.transaction(
                    coordinator,
                    bundle,
                    adapter=adapter,
                )
                request = transaction.operation_request("prepare")
                lock_receipt = adapter.acquire_publication_lock(request)
                adapter.reserve(request)

                entered = threading.Event()
                proceed = threading.Event()
                bind_called = threading.Event()
                failures: list[BaseException] = []
                real_bind = adapter._bind_export_retention_sidecars
                real_claim = abort_adapter._local_cleanup_claim

                def blocking_bind(*args, **kwargs):
                    bind_called.set()
                    entered.set()
                    if not proceed.wait(5):
                        raise AssertionError("retention race did not resume")
                    return real_bind(*args, **kwargs)

                def blocking_claim(*args, **kwargs):
                    entered.set()
                    if not proceed.wait(5):
                        raise AssertionError("cleanup race did not resume")
                    return real_claim(*args, **kwargs)

                def release() -> None:
                    try:
                        adapter.release_publication_lock(request, lock_receipt)
                    except BaseException as error:
                        failures.append(error)

                def abort() -> None:
                    try:
                        abort_adapter.abort(request)
                    except BaseException as error:
                        failures.append(error)

                release_thread = threading.Thread(target=release)
                abort_thread = threading.Thread(target=abort)
                if cleanup_first:
                    with (
                        mock.patch.object(
                            abort_adapter,
                            "_local_cleanup_claim",
                            side_effect=blocking_claim,
                        ),
                        mock.patch.object(
                            adapter,
                            "_bind_export_retention_sidecars",
                            wraps=real_bind,
                        ) as bind_mock,
                    ):
                        abort_thread.start()
                        self.assertTrue(entered.wait(5))
                        release_thread.start()
                        proceed.set()
                        abort_thread.join(5)
                        release_thread.join(5)
                        self.assertEqual(0, bind_mock.call_count)
                else:
                    with mock.patch.object(
                        adapter,
                        "_bind_export_retention_sidecars",
                        side_effect=blocking_bind,
                    ):
                        release_thread.start()
                        self.assertTrue(entered.wait(5))
                        abort_thread.start()
                        self.assertTrue(abort_thread.is_alive())
                        proceed.set()
                        release_thread.join(5)
                        abort_thread.join(5)

                self.assertFalse(release_thread.is_alive())
                self.assertFalse(abort_thread.is_alive())
                self.assertEqual([], failures)
                attempt = adapter.inspect_attempt(transaction.attempt_ref)
                self.assertIsNotNone(attempt)
                assert attempt is not None
                self.assertTrue(attempt["aborted"])
                self.assertIn("cleanup", attempt["receipts"])
                self.assertIn("reservation_release", attempt["receipts"])
                self.assertFalse(attempt["capacity_held"])
                self.assertEqual(
                    not cleanup_first,
                    attempt["retention_bound"],
                )
                self.assertEqual(
                    attempt["retention_bound"],
                    attempt["cleanup_claim"]["retention_bound"],
                )

    def test_cleanup_presence_mismatch_does_not_persist_abort(self) -> None:
        for missing in ("bundle", "sidecar"):
            with self.subTest(missing=missing):
                coordinator, bundle = self.build_exportable_run(
                    f"cleanup-presence-mismatch-{missing}"
                )
                adapter = self.publication_adapter()
                transaction = self.transaction(
                    coordinator,
                    bundle,
                    adapter=adapter,
                )
                transaction.prepare()
                sidecar = bundle.with_name(f".{bundle.name}.retention-v2.json")
                if missing == "bundle":
                    shutil.rmtree(bundle)
                else:
                    sidecar.unlink()

                with self.assertRaisesRegex(
                    ExportConflictError,
                    "bundle and retention state presence differ",
                ):
                    transaction.abort("cleanup_presence_mismatch")

                attempt = adapter.inspect_attempt(transaction.attempt_ref)
                self.assertIsNotNone(attempt)
                assert attempt is not None
                self.assertFalse(attempt["aborted"])
                self.assertNotIn("cleanup", attempt["receipts"])
                self.assertTrue(attempt["capacity_held"])
                self.assertIsNotNone(attempt["cleanup_claim"])
                self.assertEqual("abort_pending", transaction.status()["phase"])
                capacity = safe_io.read_bounded_json(
                    self.provider_state / "capacity.json",
                    max_bytes=1024 * 1024,
                    require_owner_only=True,
                )
                self.assertIn(transaction.attempt_ref, capacity["reservations"])

    def test_cleanup_recovers_after_retention_release_precedes_journal(self) -> None:
        coordinator, bundle = self.build_exportable_run(
            "cleanup-retention-release-before-journal"
        )
        transaction = self.transaction(coordinator, bundle)
        transaction.prepare()

        def crash(point, _state):
            if point == "cleanup.after_retention_release":
                raise RuntimeError("simulated post-retention-release crash")

        crashing = self.publication_adapter(failure_injector=crash)
        with self.assertRaisesRegex(RuntimeError, "post-retention-release crash"):
            crashing.cleanup(transaction.operation_request("cleanup"))

        sidecar = bundle.with_name(f".{bundle.name}.retention-v2.json")
        terminal = safe_io.read_bounded_json(
            sidecar,
            max_bytes=1024 * 1024,
            require_owner_only=True,
        )
        self.assertEqual("publication_terminal", terminal["status"])
        self.assertEqual("aborted", terminal["terminal_disposition"])
        interrupted = crashing.inspect_attempt(transaction.attempt_ref)
        self.assertIsNotNone(interrupted)
        assert interrupted is not None
        self.assertFalse(interrupted["aborted"])
        self.assertNotIn("cleanup", interrupted["receipts"])
        self.assertTrue(interrupted["capacity_held"])

        collected = garbage_collect_expired_exports(
            bundle.parent,
            now=dt.datetime(2100, 1, 1, tzinfo=dt.UTC),
        )
        self.assertIn(str(bundle.resolve()), collected["deleted"])
        self.assertFalse(bundle.exists())
        self.assertFalse(sidecar.exists())

        recovered = self.adapter.cleanup(transaction.operation_request("cleanup"))

        self.assertEqual("remote_object_cleanup_complete", recovered["status"])
        attempt = self.adapter.inspect_attempt(transaction.attempt_ref)
        self.assertIsNotNone(attempt)
        assert attempt is not None
        self.assertTrue(attempt["aborted"])
        self.assertIn("cleanup", attempt["receipts"])
        self.assertTrue(attempt["capacity_held"])

    def test_abort_reconciles_retention_bound_before_attempt_flag_persists(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run(
            "retention-bind-before-attempt-flag"
        )

        def crash(point, _state):
            if point == "release_publication_lock.after_retention_bind":
                raise RuntimeError("simulated retention binding journal crash")

        adapter = self.publication_adapter(failure_injector=crash)
        transaction = self.transaction(coordinator, bundle, adapter=adapter)
        with self.assertRaisesRegex(RuntimeError, "binding journal crash"):
            transaction.prepare()

        attempt = adapter.inspect_attempt(transaction.attempt_ref)
        self.assertIsNotNone(attempt)
        assert attempt is not None
        self.assertFalse(attempt["retention_bound"])
        sidecar = bundle.with_name(f".{bundle.name}.retention-v2.json")
        bound = safe_io.read_bounded_json(
            sidecar,
            max_bytes=1024 * 1024,
            require_owner_only=True,
        )
        self.assertEqual("publication_bound", bound["status"])
        self.assertEqual(
            transaction.attempt_ref,
            bound["publication_attempt_ref"],
        )

        transaction.abort("retention_binding_interrupted")

        terminal = safe_io.read_bounded_json(
            sidecar,
            max_bytes=1024 * 1024,
            require_owner_only=True,
        )
        self.assertEqual("publication_terminal", terminal["status"])
        self.assertEqual("aborted", terminal["terminal_disposition"])

    def test_cleanup_claim_blocks_every_stale_forward_transition(self) -> None:
        coordinator, bundle = self.build_exportable_run("cleanup-monotonicity")
        adapter = self.publication_adapter()
        transaction = self.transaction(coordinator, bundle, adapter=adapter)
        transaction.prepare()
        transaction.stage()
        transaction.seal()
        transaction.close_compliance()

        def crash(point, _state):
            if point == "cleanup.after_claim_persist":
                raise RuntimeError("simulated cleanup claim crash")

        crashing = self.publication_adapter(failure_injector=crash)
        with self.assertRaisesRegex(RuntimeError, "cleanup claim crash"):
            crashing.cleanup(transaction.operation_request("cleanup"))

        for method_name, phase in (
            ("stage", "stage"),
            ("seal", "seal"),
            ("close_compliance", "close_compliance"),
            ("promote", "promote"),
        ):
            with (
                self.subTest(method=method_name),
                self.assertRaisesRegex(
                    publication_support.InvalidTransitionError,
                    "cleanup-owned",
                ),
            ):
                getattr(adapter, method_name)(transaction.operation_request(phase))

    def test_legacy_capacity_requires_matching_durable_attempt(self) -> None:
        coordinator, bundle = self.build_exportable_run("legacy-capacity-binding")
        adapter = self.publication_adapter()
        transaction = self.transaction(coordinator, bundle, adapter=adapter)
        transaction.prepare()
        request = transaction.operation_request("stage")
        attempt = adapter.inspect_attempt(transaction.attempt_ref)
        self.assertIsNotNone(attempt)
        assert attempt is not None
        capacity = attempt["capacity_bytes"]
        capacity_path = self.provider_state / "capacity.json"
        ledger = safe_io.read_bounded_json(
            capacity_path,
            max_bytes=1024 * 1024,
            require_owner_only=True,
        )
        ledger["reservations"][transaction.attempt_ref] = capacity
        safe_io.atomic_write_json(capacity_path, ledger)

        self.assertEqual(capacity, adapter._capacity_reservation(request))
        migrated = safe_io.read_bounded_json(
            capacity_path,
            max_bytes=1024 * 1024,
            require_owner_only=True,
        )["reservations"][transaction.attempt_ref]
        self.assertEqual("local_git_capacity_reservation_v2", migrated["schema"])

        orphan_ref = "attempt_ref_v2:" + "f" * 64
        orphan_request = replace(request, attempt_ref=orphan_ref)
        ledger = safe_io.read_bounded_json(
            capacity_path,
            max_bytes=1024 * 1024,
            require_owner_only=True,
        )
        ledger["reservations"][orphan_ref] = capacity
        safe_io.atomic_write_json(capacity_path, ledger)
        with self.assertRaisesRegex(
            StateCorruptionError,
            "lacks a durable attempt",
        ):
            adapter._capacity_reservation(orphan_request)

    def test_capacity_release_requires_exact_request_and_amount(self) -> None:
        coordinator, bundle = self.build_exportable_run("capacity-release-binding")
        adapter = self.publication_adapter()
        transaction = self.transaction(coordinator, bundle, adapter=adapter)
        transaction.prepare()
        request = transaction.operation_request("stage")
        attempt = adapter.inspect_attempt(transaction.attempt_ref)
        self.assertIsNotNone(attempt)
        assert attempt is not None
        amount = attempt["capacity_bytes"]
        wrong_request = replace(request, destination=f"{request.destination}.other")

        with self.assertRaisesRegex(StateCorruptionError, "binding changed"):
            adapter._release_capacity(wrong_request, amount)
        with self.assertRaisesRegex(StateCorruptionError, "release binding changed"):
            adapter._release_capacity(request, amount + 1)

        ledger = safe_io.read_bounded_json(
            self.provider_state / "capacity.json",
            max_bytes=1024 * 1024,
            require_owner_only=True,
        )
        self.assertIn(transaction.attempt_ref, ledger["reservations"])
        adapter._release_capacity(request, amount)
        released = safe_io.read_bounded_json(
            self.provider_state / "capacity.json",
            max_bytes=1024 * 1024,
            require_owner_only=True,
        )
        self.assertNotIn(transaction.attempt_ref, released["reservations"])

    def test_legacy_capacity_migration_rejects_each_attempt_authority_drift(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run("legacy-capacity-authority")
        adapter = self.publication_adapter()
        transaction = self.transaction(coordinator, bundle, adapter=adapter)
        transaction.prepare()
        request = transaction.operation_request("stage")
        original = adapter._read_attempt(transaction.attempt_ref)
        self.assertIsNotNone(original)
        assert original is not None
        amount = original["capacity_bytes"]
        capacity_path = self.provider_state / "capacity.json"
        attempt_path = adapter._attempt_state_path(transaction.attempt_ref)

        def reservation_receipt_drift(state):
            state["receipts"]["reservation"]["capacity_bytes"] += 1

        def observation_drift(state):
            state["receipts"]["target_observation"]["destination_exists"] = True

        def unit_plan_drift(state):
            state["unit_plan"] = []

        def inventory_drift(state):
            state["unit_plan"][0]["inventory"]["total_bytes"] += 1

        def status_drift(state):
            state["capacity_held"] = False

        for label, mutate in {
            "inventory": inventory_drift,
            "observation": observation_drift,
            "receipt": reservation_receipt_drift,
            "status": status_drift,
            "unit-plan": unit_plan_drift,
        }.items():
            with self.subTest(authority=label):
                tampered = copy.deepcopy(original)
                mutate(tampered)
                safe_io.atomic_write_json(attempt_path, tampered)
                ledger = safe_io.read_bounded_json(
                    capacity_path,
                    max_bytes=1024 * 1024,
                    require_owner_only=True,
                )
                ledger["reservations"][transaction.attempt_ref] = amount
                safe_io.atomic_write_json(capacity_path, ledger)
                with self.assertRaises(StateCorruptionError):
                    adapter._capacity_reservation(request)

        safe_io.atomic_write_json(attempt_path, original)

    def test_abort_recovers_capacity_persisted_before_attempt_state(self) -> None:
        coordinator, bundle = self.build_exportable_run("capacity-before-attempt-state")

        def crash(point, _state):
            if point == "reserve.after_capacity_persist":
                raise RuntimeError("simulated reservation journal crash")

        adapter = self.publication_adapter(failure_injector=crash)
        transaction = self.transaction(coordinator, bundle, adapter=adapter)
        with self.assertRaisesRegex(RuntimeError, "reservation journal crash"):
            transaction.prepare()
        self.assertEqual("created", transaction.status()["phase"])
        self.assertIsNone(adapter.inspect_attempt(transaction.attempt_ref))

        transaction.abort("reservation_interrupted")
        self.assertEqual("aborted", transaction.status()["phase"])
        attempt = adapter.inspect_attempt(transaction.attempt_ref)
        self.assertIsNotNone(attempt)
        assert attempt is not None
        self.assertGreater(attempt["capacity_bytes"], 0)
        self.assertFalse(attempt["capacity_held"])
        self.assertTrue(attempt["cleanup_claim"]["provider_attempt_reserved"])
        self.assertEqual(
            attempt["capacity_bytes"],
            attempt["cleanup_claim"]["capacity_reservation_observed"],
        )
        ledger = safe_io.read_bounded_json(
            self.provider_state / "capacity.json",
            max_bytes=1024 * 1024,
            require_owner_only=True,
        )
        self.assertNotIn(transaction.attempt_ref, ledger["reservations"])
        self.assertEqual(
            transaction.status(),
            PublicationTransaction.open(
                transaction.journal_path,
                adapter=self.publication_adapter(),
                expected_attempt_ref=transaction.attempt_ref,
            ).status(),
        )

    def test_target_cas_recovery_does_not_require_lost_local_bundle(self) -> None:
        coordinator, bundle = self.build_exportable_run("target-cas-bundle-lost")

        def crash(point, _state):
            if point == "promote.after_target_cas":
                raise RuntimeError("simulated target CAS crash")

        transaction = self.transaction(
            coordinator,
            bundle,
            adapter=self.publication_adapter(failure_injector=crash),
        )
        transaction.prepare()
        transaction.stage()
        transaction.seal()
        transaction.close_compliance()
        with self.assertRaisesRegex(RuntimeError, "target CAS crash"):
            transaction.promote()
        publication_tip = self.head()
        shutil.rmtree(bundle)

        recovered = PublicationTransaction.open(
            transaction.journal_path,
            adapter=self.publication_adapter(),
            expected_attempt_ref=transaction.attempt_ref,
        )
        self.assertEqual("promoted", recovered.status()["phase"])
        self.assertEqual(
            publication_tip,
            recovered.status()["receipts"]["promotion"]["target_head"],
        )
        recovered.commit()

        self.assertEqual("committed", recovered.status()["phase"])
        self.assertEqual(1, self.load_history().provider_revision)

    def test_target_cas_recovery_rejects_present_bundle_drift_before_adapter(
        self,
    ) -> None:
        for label, preinspect in (("direct", False), ("after-preinspect", True)):
            with self.subTest(case=label):
                coordinator, bundle = self.build_exportable_run(
                    f"target-cas-present-drift-{label}"
                )

                def crash(point, _state):
                    if point == "promote.after_target_cas":
                        raise RuntimeError("simulated target CAS crash")

                transaction = self.transaction(
                    coordinator,
                    bundle,
                    adapter=self.publication_adapter(failure_injector=crash),
                )
                transaction.prepare()
                transaction.stage()
                transaction.seal()
                transaction.close_compliance()
                with self.assertRaisesRegex(RuntimeError, "target CAS crash"):
                    transaction.promote()
                if preinspect:
                    PublicationTransaction.inspect_local_for_run(
                        transaction.journal_path,
                        bundle_dir=bundle,
                        destination=self.destination(coordinator.load_state()),
                        target_ref=TARGET_REF,
                        expected_target_head=transaction.status()["plan"][
                            "expected_target_head"
                        ],
                        run_dir=coordinator.run_dir,
                        identity_path=self.identity_path,
                    )
                replacement = bundle.with_name(f"{bundle.name}-replacement")
                shutil.copytree(bundle, replacement)
                shutil.rmtree(bundle)
                bundle.symlink_to(replacement, target_is_directory=True)
                adapter = self.publication_adapter()
                with (
                    mock.patch.object(
                        adapter,
                        "promote",
                        wraps=adapter.promote,
                    ) as promote,
                    self.assertRaises(finalize_module.ArtifactValidationError),
                ):
                    PublicationTransaction.open(
                        transaction.journal_path,
                        adapter=adapter,
                        expected_attempt_ref=transaction.attempt_ref,
                    )
                promote.assert_not_called()
                bundle.unlink()
                os.replace(replacement, bundle)
                recovered = PublicationTransaction.open(
                    transaction.journal_path,
                    adapter=adapter,
                    expected_attempt_ref=transaction.attempt_ref,
                )
                recovered.commit()

    def test_finalize_cli_recovers_target_cas_after_local_export_collection(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run(
            "target-cas-cli-bundle-collected",
            persist_descriptor=True,
        )

        def crash(point, _state):
            if point == "promote.after_target_cas":
                raise RuntimeError("simulated target CAS crash")

        transaction = self.transaction(
            coordinator,
            bundle,
            adapter=self.publication_adapter(failure_injector=crash),
        )
        transaction.prepare()
        transaction.stage()
        transaction.seal()
        transaction.close_compliance()
        with self.assertRaisesRegex(RuntimeError, "target CAS crash"):
            transaction.promote()
        publication_tip = self.head()
        sidecar = bundle.with_name(f".{bundle.name}.retention-v2.json")
        shutil.rmtree(bundle)
        sidecar.unlink()

        finalized = self.finalize_cli(coordinator)

        self.assertEqual("committed", finalized.result["transaction_phase"])
        self.assertEqual(RunStage.COMPLETE.value, finalized.result["stage"])
        self.assertEqual(publication_tip, self.load_history().publication_commit)
        self.assertFalse(bundle.exists())
        self.assertFalse(sidecar.exists())

    def test_target_cas_recovery_advances_cache_below_unrelated_successor(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run(
            "target-cas-unrelated-successor",
            persist_descriptor=True,
        )

        def crash(point, _state):
            if point == "promote.after_target_cas":
                raise RuntimeError("simulated target CAS crash")

        crashing = self.publication_adapter(failure_injector=crash)
        transaction = self.transaction(coordinator, bundle, adapter=crashing)
        transaction.prepare()
        transaction.stage()
        transaction.seal()
        transaction.close_compliance()
        with self.assertRaisesRegex(RuntimeError, "target CAS crash"):
            transaction.promote()
        publication_tip = self.head()

        run_command(["git", "read-tree", publication_tip], cwd=self.repo)
        (self.repo / "unrelated.txt").write_text("successor\n", encoding="ascii")
        run_command(["git", "add", "unrelated.txt"], cwd=self.repo)
        run_command(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-q",
                "-m",
                "Add unrelated successor",
            ],
            cwd=self.repo,
        )
        successor = self.head()
        self.assertNotEqual(publication_tip, successor)

        recovered = PublicationTransaction.open(
            transaction.journal_path,
            adapter=self.publication_adapter(),
            expected_attempt_ref=transaction.attempt_ref,
        )
        self.assertEqual("promoted", recovered.status()["phase"])
        self.assertEqual(
            publication_tip,
            recovered.status()["receipts"]["promotion"]["target_head"],
        )
        recovered.commit()

        published = self.load_history()
        self.assertEqual(successor, published.head_commit)
        self.assertEqual(publication_tip, published.publication_commit)
        authority.assert_provider_cache_matches(
            self.provider_state,
            published,
            identity=self.identity,
        )
        self.assertEqual("committed", recovered.status()["phase"])

        finalized = self.finalize_cli(coordinator)

        self.assertEqual(RunStage.COMPLETE.value, finalized.result["stage"])
        self.assertEqual(
            "complete",
            coordinator.load_state()["publication"]["phase"],
        )
        self.assertEqual(successor, self.head())
        self.assertEqual(
            publication_tip,
            coordinator.load_state()["publication"]["cleanup_receipt"][
                "durable_commit"
            ],
        )

    def test_provider_cas_crash_keeps_export_recoverable_across_gc(self) -> None:
        coordinator, bundle = self.build_exportable_run(
            "provider-cas-gc-recovery",
            persist_descriptor=True,
        )

        def crash(point, _state):
            if point == "advance_state.after_callback":
                raise RuntimeError("simulated outer commit journal crash")

        transaction = self.transaction(
            coordinator,
            bundle,
            failure_injector=crash,
        )
        transaction.prepare()
        transaction.stage()
        transaction.seal()
        transaction.close_compliance()
        transaction.promote()
        with self.assertRaisesRegex(RuntimeError, "outer commit journal crash"):
            transaction.commit()

        sidecar = bundle.with_name(f".{bundle.name}.retention-v2.json")
        retained_state = json.loads(sidecar.read_text(encoding="ascii"))
        self.assertEqual("publication_bound", retained_state["status"])
        self.assertEqual(
            transaction.attempt_ref,
            retained_state["publication_attempt_ref"],
        )
        collected = garbage_collect_expired_exports(
            self.root / ".codex-local" / "exports",
            now=dt.datetime(2100, 1, 1, tzinfo=dt.UTC),
        )
        self.assertIn(str(bundle.resolve()), collected["retained"])
        self.assertTrue(bundle.is_dir())

        finalized = self.finalize_cli(coordinator)

        self.assertEqual("complete", finalized.result["publication_phase"])
        terminal_state = json.loads(sidecar.read_text(encoding="ascii"))
        self.assertEqual("publication_terminal", terminal_state["status"])
        self.assertEqual("committed", terminal_state["terminal_disposition"])
        reaped = garbage_collect_expired_exports(
            self.root / ".codex-local" / "exports",
            now=dt.datetime(2100, 1, 1, tzinfo=dt.UTC),
        )
        self.assertIn(str(bundle.resolve()), reaped["deleted"])
        self.assertFalse(bundle.exists())
        self.assertFalse(sidecar.exists())

        retry = self.finalize_cli(coordinator)
        self.assertTrue(retry.result["idempotent"])
        self.assertEqual(RunStage.COMPLETE.value, retry.result["stage"])

    def test_finalize_recovers_preclaim_crashes_across_expiry_and_gc(self) -> None:
        started = dt.datetime(2026, 7, 15, 0, 0, tzinfo=dt.UTC)
        deadline = "2026-07-15T01:00:00Z"
        resumed_at = started + dt.timedelta(days=8)
        for crash_point in ("after_binding", "after_checkpoint_claim"):
            with self.subTest(crash_point=crash_point):
                coordinator, bundle = self.build_exportable_run(
                    f"preclaim-crash-{crash_point}",
                    persist_descriptor=True,
                    export_now=started,
                    export_retention_deadline=deadline,
                )
                state = coordinator.load_state()
                journal = coordinator.run_dir / "publication-transaction-v2.json"
                attempt_ref = finalize_module.new_attempt_ref()

                def claim_before_persist(
                    claimed_attempt_ref: str,
                    plan_digest: str,
                ) -> Mapping[str, object]:
                    return coordinator.claim_publication(
                        claimed_attempt_ref,
                        plan_digest,
                        bundle_dir=bundle,
                    )

                def crash(point, _state):
                    if (
                        crash_point == "after_checkpoint_claim"
                        and point == "create.after_claim_before_persist"
                    ):
                        raise RuntimeError("simulated crash after checkpoint claim")

                claim_crash = (
                    mock.patch.object(
                        coordinator.store,
                        "transaction",
                        side_effect=RuntimeError(
                            "simulated crash after retention binding"
                        ),
                    )
                    if crash_point == "after_binding"
                    else nullcontext()
                )
                with (
                    mock.patch.object(
                        cli_module.export_api,
                        "_utc_now",
                        return_value=started,
                    ),
                    claim_crash,
                    self.assertRaisesRegex(RuntimeError, "simulated crash"),
                ):
                    PublicationTransaction.create(
                        journal,
                        bundle_dir=bundle,
                        destination=self.destination(state),
                        target_ref=TARGET_REF,
                        expected_target_head=state["authority"]["history_snapshot"][
                            "history_commit"
                        ],
                        run_dir=coordinator.run_dir,
                        identity_path=self.identity_path,
                        attempt_ref=attempt_ref,
                        adapter=self.adapter,
                        claim_before_persist=claim_before_persist,
                        failure_injector=crash,
                    )

                self.assertFalse(journal.exists())
                retention = inspect_staged_export_retention(bundle)
                self.assertEqual("publication_bound", retention["status"])
                self.assertEqual(attempt_ref, retention["publication_attempt_ref"])
                claim = coordinator.load_state()["publication"].get("publication_claim")
                self.assertEqual(
                    crash_point == "after_checkpoint_claim",
                    claim is not None,
                )
                collected = garbage_collect_expired_exports(
                    self.root / ".codex-local" / "exports",
                    now=dt.datetime(2100, 1, 1, tzinfo=dt.UTC),
                )
                self.assertIn(str(bundle.resolve()), collected["retained"])

                resumed = RetrospectiveOrchestrator(
                    coordinator.run_dir,
                    clock=lambda: resumed_at,
                    identity_path=self.identity_path,
                    require_existing_identity=True,
                )
                raw_marker = coordinator.run_dir / "raw-inputs" / "preclaim.bin"
                raw_marker.write_bytes(b"must survive preclaim expiry")
                os.chmod(raw_marker, 0o600)
                protected = resumed.status()
                self.assertEqual(RunStage.EXPORT.value, protected["stage"])
                self.assertNotIn(
                    "expired_cleanup_claim",
                    resumed.load_state()["publication"],
                )
                self.assertEqual(
                    b"must survive preclaim expiry",
                    raw_marker.read_bytes(),
                )
                with (
                    mock.patch.object(
                        cli_module.orchestrator_api,
                        "RetrospectiveOrchestrator",
                        return_value=resumed,
                    ),
                    mock.patch.object(
                        cli_module.export_api,
                        "_utc_now",
                        return_value=resumed_at,
                    ),
                ):
                    recovered = self.finalize_cli(resumed)

                self.assertEqual("prepared", recovered.result["transaction_phase"])
                self.assertTrue(journal.is_file())
                recovered_claim = resumed.load_state()["publication"][
                    "publication_claim"
                ]
                self.assertEqual(attempt_ref, recovered_claim["attempt_ref"])

    def test_expired_gc_claim_prevents_waiting_predeadline_bind(self) -> None:
        coordinator, bundle = self.build_exportable_run(
            "gc-wins-before-preclaim-bind",
            persist_descriptor=True,
        )
        started = dt.datetime(2026, 7, 15, 0, 0, tzinfo=dt.UTC)
        deadline = dt.datetime(2026, 7, 15, 1, 0, tzinfo=dt.UTC)
        gc_coordinator = RetrospectiveOrchestrator(
            coordinator.run_dir,
            clock=lambda: started + dt.timedelta(days=8),
            identity_path=self.identity_path,
            require_existing_identity=True,
        )
        bind_coordinator = RetrospectiveOrchestrator(
            coordinator.run_dir,
            clock=lambda: deadline - dt.timedelta(seconds=1),
            identity_path=self.identity_path,
            require_existing_identity=True,
        )
        gc_holds_bundle_lock = threading.Event()
        allow_gc_claim = threading.Event()
        real_transaction = gc_coordinator.store.transaction
        errors: list[BaseException] = []
        gc_results: list[dict[str, object]] = []

        def delayed_gc_transaction(*args, **kwargs):
            gc_holds_bundle_lock.set()
            if not allow_gc_claim.wait(timeout=5):
                raise RuntimeError("timed out waiting for raw GC claim")
            return real_transaction(*args, **kwargs)

        def run_gc() -> None:
            try:
                gc_results.append(gc_coordinator.gc_expired_raw())
            except BaseException as error:  # pragma: no cover - assertion payload
                errors.append(error)

        def run_bind() -> None:
            try:
                bind_coordinator.claim_publication(
                    "attempt_ref_v2:" + "9" * 64,
                    "8" * 64,
                    bundle_dir=bundle,
                )
            except BaseException as error:  # pragma: no cover - assertion payload
                errors.append(error)

        with mock.patch.object(
            gc_coordinator.store,
            "transaction",
            side_effect=delayed_gc_transaction,
        ):
            gc_thread = threading.Thread(target=run_gc)
            gc_thread.start()
            self.assertTrue(gc_holds_bundle_lock.wait(timeout=5))
            bind_thread = threading.Thread(target=run_bind)
            bind_thread.start()
            time.sleep(0.05)
            self.assertTrue(bind_thread.is_alive())
            allow_gc_claim.set()
            gc_thread.join(timeout=10)
            bind_thread.join(timeout=10)

        self.assertFalse(gc_thread.is_alive())
        self.assertFalse(bind_thread.is_alive())
        self.assertTrue(gc_results[0]["cleaned"])
        self.assertEqual(1, len(errors))
        self.assertIsInstance(errors[0], orchestrator_module.InvalidTransitionError)
        retention = inspect_staged_export_retention(bundle)
        self.assertEqual("exported", retention["status"])
        self.assertIsNone(retention["publication_attempt_ref"])

    def test_finalize_journal_is_gc_protected_before_prepare(self) -> None:
        started = dt.datetime(2026, 7, 15, 0, 0, tzinfo=dt.UTC)
        coordinator, bundle = self.build_exportable_run(
            "pre-prepare-crash",
            persist_descriptor=True,
            export_now=started,
            export_retention_deadline="2026-07-15T01:00:00Z",
        )
        state = coordinator.load_state()
        journal = coordinator.run_dir / "publication-transaction-v2.json"
        with self.assertRaisesRegex(
            PublicationRejected,
            "persistent claim callback",
        ):
            PublicationTransaction.create(
                journal,
                bundle_dir=bundle,
                destination=self.destination(state),
                target_ref=TARGET_REF,
                expected_target_head=state["authority"]["history_snapshot"][
                    "history_commit"
                ],
                run_dir=coordinator.run_dir,
                identity_path=self.identity_path,
                adapter=self.adapter,
            )
        self.assertFalse(journal.exists())
        with self.assertRaisesRegex(
            PublicationRejected,
            "persistent publication claim",
        ):
            PublicationTransaction.create(
                journal,
                bundle_dir=bundle,
                destination=self.destination(state),
                target_ref=TARGET_REF,
                expected_target_head=state["authority"]["history_snapshot"][
                    "history_commit"
                ],
                run_dir=coordinator.run_dir,
                identity_path=self.identity_path,
                adapter=self.adapter,
                claim_before_persist=lambda _attempt, _digest: {"claimed": True},
            )
        self.assertFalse(journal.exists())
        self.assertNotIn(
            "publication_claim",
            coordinator.load_state()["publication"],
        )
        args = cli_module.build_parser().parse_args(
            [
                "finalize",
                "--identity-path",
                str(self.identity_path),
                "--require-existing-identity",
                "--run-dir",
                str(coordinator.run_dir),
            ]
        )
        with (
            mock.patch.object(
                cli_module.orchestrator_api,
                "RetrospectiveOrchestrator",
                return_value=coordinator,
            ),
            mock.patch.object(
                cli_module.export_api,
                "_utc_now",
                return_value=started,
            ),
            mock.patch.object(
                finalize_module.PublicationTransaction,
                "prepare",
                side_effect=RuntimeError("simulated pre-prepare crash"),
            ),
            self.assertRaisesRegex(RuntimeError, "pre-prepare crash"),
        ):
            cli_module.command_finalize(args)

        self.assertTrue(journal.is_file())
        claim = coordinator.load_state()["publication"]["publication_claim"]
        retention = inspect_staged_export_retention(bundle)
        self.assertEqual("publication_bound", retention["status"])
        self.assertEqual(claim["attempt_ref"], retention["publication_attempt_ref"])
        collected = garbage_collect_expired_exports(
            self.root / ".codex-local" / "exports",
            now=dt.datetime(2100, 1, 1, tzinfo=dt.UTC),
        )
        self.assertIn(str(bundle.resolve()), collected["retained"])

    def test_finalize_cli_releases_export_only_after_committed_checkpoint(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run(
            "cli-phased-finalize",
            persist_descriptor=True,
        )
        sidecar = bundle.with_name(f".{bundle.name}.retention-v2.json")
        orchestrator_class = cli_module.orchestrator_api.RetrospectiveOrchestrator

        def frozen_orchestrator(*args, **kwargs):
            return orchestrator_class(
                *args,
                clock=lambda: "2026-07-15T00:00:00Z",
                **kwargs,
            )

        with mock.patch.object(
            cli_module.orchestrator_api,
            "RetrospectiveOrchestrator",
            side_effect=frozen_orchestrator,
        ):
            for expected_phase in (
                "prepared",
                "staged",
                "sealed",
                "compliance_closed",
                "promoted",
            ):
                result = self.finalize_cli(coordinator)
                self.assertEqual(expected_phase, result.result["transaction_phase"])
                self.assertEqual(expected_phase, result.result["publication_phase"])
                retained_state = json.loads(sidecar.read_text(encoding="ascii"))
                self.assertEqual("publication_bound", retained_state["status"])
                collected = garbage_collect_expired_exports(
                    self.root / ".codex-local" / "exports",
                    now=dt.datetime(2100, 1, 1, tzinfo=dt.UTC),
                )
                self.assertEqual("complete", collected["status"])
                self.assertIn(str(bundle.resolve()), collected["retained"])
                self.assertTrue(bundle.is_dir())

            committed = self.finalize_cli(coordinator)

        self.assertEqual("committed", committed.result["transaction_phase"])
        self.assertEqual("complete", committed.result["publication_phase"])
        terminal_state = json.loads(sidecar.read_text(encoding="ascii"))
        self.assertEqual("publication_terminal", terminal_state["status"])
        self.assertEqual("committed", terminal_state["terminal_disposition"])
        collected = garbage_collect_expired_exports(
            self.root / ".codex-local" / "exports",
            now=dt.datetime(2100, 1, 1, tzinfo=dt.UTC),
        )
        self.assertIn(str(bundle.resolve()), collected["deleted"])
        self.assertFalse(bundle.exists())

    def test_finalize_cli_uses_only_the_persisted_gpg_authority(self) -> None:
        coordinator, _bundle = self.build_exportable_run(
            "cli-persisted-gpg-authority",
            persist_descriptor=True,
        )
        orchestrator_class = cli_module.orchestrator_api.RetrospectiveOrchestrator

        with (
            mock.patch.object(
                cli_module.orchestrator_api,
                "RetrospectiveOrchestrator",
                side_effect=lambda *args, **kwargs: orchestrator_class(
                    *args,
                    clock=lambda: "2026-07-15T00:00:00Z",
                    **kwargs,
                ),
            ),
            mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}),
        ):
            finalized = self.finalize_cli(coordinator)

        self.assertEqual("prepared", finalized.result["transaction_phase"])

    def test_finalize_cli_rejects_changed_persisted_gpg_authority(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as trusted_directory:
            gpg_copy = Path(trusted_directory) / "publisher-gpg-copy"
            shutil.copyfile(self.gpg, gpg_copy)
            gpg_copy.chmod(0o700)
            coordinator, _bundle = self.build_exportable_run(
                "cli-changed-gpg-authority",
                persist_descriptor=True,
                publisher_gpg_program=str(gpg_copy),
            )
            gpg_copy.write_bytes(b"#!/bin/sh\nexit 1\n")
            gpg_copy.chmod(0o700)
            args = cli_module.build_parser().parse_args(
                [
                    "finalize",
                    "--identity-path",
                    str(self.identity_path),
                    "--require-existing-identity",
                    "--run-dir",
                    str(coordinator.run_dir),
                ]
            )

            with self.assertRaises(cli_module.CliContractError) as raised:
                self.command_finalize_cli(args)
            self.assertEqual("publication_authority_invalid", raised.exception.code)
            self.assertIn(
                "persisted publisher GPG authority", raised.exception.safe_message
            )

    def test_finalize_cli_preserves_aborted_export_disposition(self) -> None:
        coordinator, bundle = self.build_exportable_run(
            "cli-aborted-finalize",
            persist_descriptor=True,
        )
        transaction = self.transaction(coordinator, bundle)
        transaction.prepare()
        transaction.abort("test_requested_abort")

        result = self.finalize_cli(coordinator)

        self.assertEqual("aborted", result.result["transaction_phase"])
        self.assertEqual("aborted", result.result["publication_phase"])
        sidecar = bundle.with_name(f".{bundle.name}.retention-v2.json")
        terminal_state = json.loads(sidecar.read_text(encoding="ascii"))
        self.assertEqual("publication_terminal", terminal_state["status"])
        self.assertEqual("aborted", terminal_state["terminal_disposition"])

    def test_aborted_checkpoint_cannot_recreate_a_publication_journal(self) -> None:
        coordinator, bundle = self.build_exportable_run(
            "aborted-journal-recreation",
            persist_descriptor=True,
        )
        transaction = self.transaction(coordinator, bundle)
        transaction.prepare()
        transaction.abort("test_requested_abort")
        result = self.finalize_cli(coordinator)
        self.assertEqual("aborted", result.result["publication_phase"])
        claim = coordinator.load_state()["publication"]["publication_claim"]

        with self.assertRaisesRegex(
            orchestrator_module.InvalidTransitionError,
            "aborted publication cannot be claimed",
        ):
            coordinator.claim_publication(
                claim["attempt_ref"],
                claim["plan_digest"],
            )

        recovered = PublicationTransaction.open(
            transaction.journal_path,
            adapter=self.publication_adapter(),
            expected_attempt_ref=transaction.attempt_ref,
        )
        self.assertEqual("aborted", recovered.status()["phase"])
        transaction.journal_path.unlink()
        with self.assertRaisesRegex(
            PublicationRejected,
            "terminal checkpoint cannot authorize an active publication transaction",
        ):
            self.transaction(
                coordinator,
                bundle,
                attempt_ref=transaction.attempt_ref,
                claim_before_persist=lambda *_args: {},
            )
        self.assertFalse(transaction.journal_path.exists())

    def test_aborted_finalize_response_loss_retries_and_expired_raw_gc_closes(
        self,
    ) -> None:
        for collect_export in (False, True):
            with self.subTest(collect_export=collect_export):
                suffix = "collected" if collect_export else "retained"
                coordinator, bundle = self.build_exportable_run(
                    f"aborted-response-loss-{suffix}",
                    persist_descriptor=True,
                )
                raw_marker = coordinator.run_dir / "raw-inputs" / "aborted.bin"
                raw_marker.write_bytes(
                    b"raw input must expire after authenticated abort"
                )
                os.chmod(raw_marker, 0o600)
                transaction = self.transaction(coordinator, bundle)
                transaction.prepare()
                transaction.abort("test_requested_abort")
                args = cli_module.build_parser().parse_args(
                    [
                        "finalize",
                        "--identity-path",
                        str(self.identity_path),
                        "--require-existing-identity",
                        "--run-dir",
                        str(coordinator.run_dir),
                    ]
                )
                real_mark_finalized = RetrospectiveOrchestrator.mark_finalized
                response_lost = False

                def lose_aborted_checkpoint_response(instance, *call_args, **kwargs):
                    nonlocal response_lost
                    result = real_mark_finalized(instance, *call_args, **kwargs)
                    if (
                        not response_lost
                        and result["publication"]["phase"] == "aborted"
                    ):
                        response_lost = True
                        raise RuntimeError("lost aborted checkpoint response")
                    return result

                with (
                    mock.patch.object(
                        RetrospectiveOrchestrator,
                        "mark_finalized",
                        new=lose_aborted_checkpoint_response,
                    ),
                    self.assertRaisesRegex(
                        RuntimeError,
                        "lost aborted checkpoint response",
                    ),
                ):
                    self.command_finalize_cli(args)

                checkpoint = coordinator.load_state()
                publication_claim = checkpoint["publication"]["publication_claim"]
                self.assertEqual("aborted", checkpoint["publication"]["phase"])
                self.assertEqual(
                    transaction.attempt_ref,
                    publication_claim["attempt_ref"],
                )

                if collect_export:
                    collected = garbage_collect_expired_exports(
                        self.root / ".codex-local" / "exports",
                        now=dt.datetime(2100, 1, 1, tzinfo=dt.UTC),
                    )
                    self.assertIn(str(bundle.resolve()), collected["deleted"])
                    self.assertFalse(bundle.exists())
                    self.assertFalse(
                        bundle.with_name(f".{bundle.name}.retention-v2.json").exists()
                    )

                retry = self.finalize_cli(coordinator)
                self.assertTrue(retry.result["idempotent"])
                self.assertEqual("aborted", retry.result["transaction_phase"])
                self.assertEqual("aborted", retry.result["publication_phase"])
                self.assertEqual(
                    publication_claim,
                    coordinator.load_state()["publication"]["publication_claim"],
                )

                expired = RetrospectiveOrchestrator(
                    coordinator.run_dir,
                    clock=lambda: "2026-07-23T00:00:00Z",
                    identity_path=self.identity_path,
                    require_existing_identity=True,
                )
                cleaned = expired.gc_expired_raw()
                self.assertTrue(cleaned["cleaned"])
                self.assertFalse(raw_marker.exists())
                terminal = expired.load_state()
                cleanup_claim = terminal["publication"]["expired_cleanup_claim"]
                self.assertEqual("expired_aborted", cleanup_claim["disposition"])
                self.assertEqual("aborted", cleanup_claim["phase_before"])
                self.assertEqual(
                    publication_claim["receipt_ref"],
                    cleanup_claim["publication_claim_ref"],
                )
                self.assertNotIn(
                    "publication_claim",
                    terminal["publication"],
                )
                self.assertEqual(
                    "expired_cleanup_complete",
                    terminal["publication"]["phase"],
                )
                self.assertTrue(expired.gc_expired_raw()["idempotent"])

    def test_legacy_aborted_checkpoint_recovers_claim_authority_after_expiry(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run(
            "legacy-aborted-claim-recovery",
            persist_descriptor=True,
        )
        raw_marker = coordinator.run_dir / "raw-inputs" / "legacy-aborted.bin"
        raw_marker.write_bytes(b"legacy aborted raw input")
        os.chmod(raw_marker, 0o600)
        transaction = self.transaction(coordinator, bundle)
        transaction.prepare()
        transaction.abort("test_requested_abort")
        self.finalize_cli(coordinator)
        publication_claim = copy.deepcopy(
            coordinator.load_state()["publication"]["publication_claim"]
        )

        def remove_legacy_claim(current: dict[str, object]):
            current["publication"].pop("publication_claim")
            return current, None

        coordinator.store.transaction(remove_legacy_claim)
        replayed = self.finalize_cli(coordinator)
        self.assertTrue(replayed.result["idempotent"])
        self.assertEqual("aborted", replayed.result["transaction_phase"])
        self.assertEqual("aborted", replayed.result["publication_phase"])
        with self.assertRaisesRegex(
            orchestrator_module.InvalidTransitionError,
            "cannot rewrite aborted publication",
        ):
            coordinator.mark_finalized("prepared")
        self.assertEqual("aborted", coordinator.load_state()["publication"]["phase"])

        collected = garbage_collect_expired_exports(
            self.root / ".codex-local" / "exports",
            now=dt.datetime(2100, 1, 1, tzinfo=dt.UTC),
        )
        self.assertIn(str(bundle.resolve()), collected["deleted"])
        expired = RetrospectiveOrchestrator(
            coordinator.run_dir,
            clock=lambda: "2026-07-23T00:00:00Z",
            identity_path=self.identity_path,
            require_existing_identity=True,
        )
        cleaned = expired.gc_expired_raw()
        self.assertTrue(cleaned["cleaned"])
        self.assertFalse(raw_marker.exists())
        terminal = expired.load_state()
        cleanup_claim = terminal["publication"]["expired_cleanup_claim"]
        self.assertEqual("expired_aborted", cleanup_claim["disposition"])
        self.assertEqual(
            publication_claim["receipt_ref"],
            cleanup_claim["publication_claim_ref"],
        )
        completed_replay = self.finalize_cli(expired)
        self.assertTrue(completed_replay.result["idempotent"])
        self.assertEqual("aborted", completed_replay.result["transaction_phase"])
        self.assertEqual(
            "expired_cleanup_complete",
            completed_replay.result["publication_phase"],
        )

    def test_delayed_abort_ack_cannot_replace_expired_cleanup_claim(self) -> None:
        coordinator, bundle = self.build_exportable_run(
            "aborted-cleanup-ack-race",
            persist_descriptor=True,
        )
        raw_marker = coordinator.run_dir / "raw-inputs" / "ack-race.bin"
        raw_marker.write_bytes(b"abort acknowledgement race")
        os.chmod(raw_marker, 0o600)
        transaction = self.transaction(coordinator, bundle)
        transaction.prepare()
        transaction.abort("test_requested_abort")
        self.finalize_cli(coordinator)
        publication_claim = copy.deepcopy(
            coordinator.load_state()["publication"]["publication_claim"]
        )
        expired = RetrospectiveOrchestrator(
            coordinator.run_dir,
            clock=lambda: "2026-07-23T00:00:00Z",
            identity_path=self.identity_path,
            require_existing_identity=True,
        )
        delete_claimed = expired._delete_claimed_raw_paths

        def delete_then_replay(cleanup_claim):
            delete_claimed(cleanup_claim)
            claimed_state = expired.load_state()
            claimed_value = copy.deepcopy(
                claimed_state["publication"]["expired_cleanup_claim"]
            )
            replayed = self.finalize_cli(expired)
            self.assertTrue(replayed.result["idempotent"])
            self.assertEqual("aborted", replayed.result["transaction_phase"])
            after_replay = expired.load_state()
            self.assertEqual(
                "expired_cleanup_claimed",
                after_replay["publication"]["phase"],
            )
            self.assertEqual(
                claimed_value,
                after_replay["publication"]["expired_cleanup_claim"],
            )

        with mock.patch.object(
            expired,
            "_delete_claimed_raw_paths",
            side_effect=delete_then_replay,
        ):
            cleaned = expired.gc_expired_raw()
        self.assertTrue(cleaned["cleaned"])
        self.assertFalse(raw_marker.exists())
        self.assertEqual(
            "expired_cleanup_complete",
            expired.load_state()["publication"]["phase"],
        )
        completed_state = copy.deepcopy(expired.load_state()["publication"])
        replayed = expired.mark_finalized(
            "aborted",
            attempt_ref=publication_claim["attempt_ref"],
            claim_revision=publication_claim["checkpoint_revision"],
            plan_digest=publication_claim["plan_digest"],
        )
        self.assertTrue(replayed["idempotent"])
        self.assertEqual(completed_state, expired.load_state()["publication"])
        with self.assertRaisesRegex(
            orchestrator_module.RunConflictError,
            "does not match recovered abort authority",
        ):
            expired.mark_finalized(
                "aborted",
                attempt_ref=publication_claim["attempt_ref"],
                claim_revision=publication_claim["checkpoint_revision"] + 1,
                plan_digest=publication_claim["plan_digest"],
            )
        self.assertEqual(completed_state, expired.load_state()["publication"])

    def test_finalize_cli_reclassifies_claim_race_as_terminal_abort(self) -> None:
        coordinator, bundle = self.build_exportable_run(
            "aborted-claim-race-reclassification",
            persist_descriptor=True,
        )
        raw_marker = coordinator.run_dir / "raw-inputs" / "claim-race.bin"
        raw_marker.write_bytes(b"claim race raw input")
        os.chmod(raw_marker, 0o600)
        transaction = self.transaction(coordinator, bundle)
        transaction.prepare()
        transaction.abort("test_requested_abort")
        publication_claim = copy.deepcopy(
            coordinator.load_state()["publication"]["publication_claim"]
        )
        real_claim_publication = RetrospectiveOrchestrator.claim_publication
        raced = False

        def expire_before_claim(instance, *args, **kwargs):
            nonlocal raced
            if not raced and instance.run_dir == coordinator.run_dir:
                raced = True
                instance.mark_finalized(
                    "aborted",
                    attempt_ref=publication_claim["attempt_ref"],
                    claim_revision=publication_claim["checkpoint_revision"],
                    plan_digest=publication_claim["plan_digest"],
                )
                expired = RetrospectiveOrchestrator(
                    coordinator.run_dir,
                    clock=lambda: "2026-07-23T00:00:00Z",
                    identity_path=self.identity_path,
                    require_existing_identity=True,
                )
                self.assertTrue(expired.gc_expired_raw()["cleaned"])
            return real_claim_publication(instance, *args, **kwargs)

        with mock.patch.object(
            RetrospectiveOrchestrator,
            "claim_publication",
            new=expire_before_claim,
        ):
            replayed = self.finalize_cli(coordinator)

        self.assertTrue(raced)
        self.assertTrue(replayed.result["idempotent"])
        self.assertEqual("aborted", replayed.result["transaction_phase"])
        self.assertEqual(
            "expired_cleanup_complete",
            replayed.result["publication_phase"],
        )
        self.assertFalse(raw_marker.exists())

    def test_finalize_cli_reclassifies_inspection_race_as_terminal_abort(self) -> None:
        coordinator, bundle = self.build_exportable_run(
            "aborted-inspection-race-reclassification",
            persist_descriptor=True,
        )
        raw_marker = coordinator.run_dir / "raw-inputs" / "inspection-race.bin"
        raw_marker.write_bytes(b"inspection race raw input")
        os.chmod(raw_marker, 0o600)
        transaction = self.transaction(coordinator, bundle)
        transaction.prepare()
        transaction.abort("test_requested_abort")
        publication_claim = copy.deepcopy(
            coordinator.load_state()["publication"]["publication_claim"]
        )
        real_inspect = PublicationTransaction.inspect_local_for_run
        raced = False
        inspection_failed = False

        def expire_before_inspection(*args, **kwargs):
            nonlocal raced, inspection_failed
            if not raced:
                raced = True
                coordinator.mark_finalized(
                    "aborted",
                    attempt_ref=publication_claim["attempt_ref"],
                    claim_revision=publication_claim["checkpoint_revision"],
                    plan_digest=publication_claim["plan_digest"],
                )
                expired = RetrospectiveOrchestrator(
                    coordinator.run_dir,
                    clock=lambda: "2026-07-23T00:00:00Z",
                    identity_path=self.identity_path,
                    require_existing_identity=True,
                )
                self.assertTrue(expired.gc_expired_raw()["cleaned"])
            try:
                return real_inspect(*args, **kwargs)
            except (OSError, finalize_module.PublicationError):
                inspection_failed = True
                raise

        with mock.patch.object(
            PublicationTransaction,
            "inspect_local_for_run",
            side_effect=expire_before_inspection,
        ):
            replayed = self.finalize_cli(coordinator)

        self.assertTrue(raced)
        self.assertTrue(inspection_failed)
        self.assertTrue(replayed.result["idempotent"])
        self.assertEqual("aborted", replayed.result["transaction_phase"])
        self.assertEqual(
            "expired_cleanup_complete",
            replayed.result["publication_phase"],
        )
        self.assertFalse(raw_marker.exists())

    def test_finalize_cli_reclassifies_open_race_as_terminal_abort(self) -> None:
        coordinator, bundle = self.build_exportable_run(
            "aborted-open-race-reclassification",
            persist_descriptor=True,
        )
        raw_marker = coordinator.run_dir / "raw-inputs" / "open-race.bin"
        raw_marker.write_bytes(b"open race raw input")
        os.chmod(raw_marker, 0o600)
        transaction = self.transaction(coordinator, bundle)
        transaction.prepare()
        transaction.abort("test_requested_abort")
        publication_claim = copy.deepcopy(
            coordinator.load_state()["publication"]["publication_claim"]
        )
        real_open = PublicationTransaction.open
        raced = False
        open_failed = False

        def expire_before_open(*args, **kwargs):
            nonlocal raced, open_failed
            if not raced:
                raced = True
                coordinator.mark_finalized(
                    "aborted",
                    attempt_ref=publication_claim["attempt_ref"],
                    claim_revision=publication_claim["checkpoint_revision"],
                    plan_digest=publication_claim["plan_digest"],
                )
                expired = RetrospectiveOrchestrator(
                    coordinator.run_dir,
                    clock=lambda: "2026-07-23T00:00:00Z",
                    identity_path=self.identity_path,
                    require_existing_identity=True,
                )
                self.assertTrue(expired.gc_expired_raw()["cleaned"])
            try:
                return real_open(*args, **kwargs)
            except (OSError, finalize_module.PublicationError):
                open_failed = True
                raise

        with mock.patch.object(
            PublicationTransaction,
            "open",
            side_effect=expire_before_open,
        ):
            replayed = self.finalize_cli(coordinator)

        self.assertTrue(raced)
        self.assertTrue(open_failed)
        self.assertTrue(replayed.result["idempotent"])
        self.assertEqual("aborted", replayed.result["transaction_phase"])
        self.assertEqual(
            "expired_cleanup_complete",
            replayed.result["publication_phase"],
        )
        self.assertFalse(raw_marker.exists())

    def test_finalize_cli_reclassifies_absent_journal_race_as_terminal_abort(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run(
            "aborted-absent-journal-race",
            persist_descriptor=True,
        )
        raw_marker = coordinator.run_dir / "raw-inputs" / "absent-journal-race.bin"
        raw_marker.write_bytes(b"absent journal race raw input")
        os.chmod(raw_marker, 0o600)
        real_attempt_ref = export_cli_api.publication_attempt_ref
        raced = False
        attempt_ref_failed = False

        def abort_before_attempt_ref(*args, **kwargs):
            nonlocal raced, attempt_ref_failed
            if not raced:
                raced = True
                transaction = self.transaction(coordinator, bundle)
                transaction.prepare()
                transaction.abort("test_requested_abort")
                publication_claim = coordinator.load_state()["publication"][
                    "publication_claim"
                ]
                coordinator.mark_finalized(
                    "aborted",
                    attempt_ref=publication_claim["attempt_ref"],
                    claim_revision=publication_claim["checkpoint_revision"],
                    plan_digest=publication_claim["plan_digest"],
                )
                expired = RetrospectiveOrchestrator(
                    coordinator.run_dir,
                    clock=lambda: "2026-07-23T00:00:00Z",
                    identity_path=self.identity_path,
                    require_existing_identity=True,
                )
                self.assertTrue(expired.gc_expired_raw()["cleaned"])
            try:
                return real_attempt_ref(*args, **kwargs)
            except export_cli_api.ExportCliContractError:
                attempt_ref_failed = True
                raise

        with mock.patch.object(
            export_cli_api,
            "publication_attempt_ref",
            side_effect=abort_before_attempt_ref,
        ):
            replayed = self.finalize_cli(coordinator)

        self.assertTrue(raced)
        self.assertTrue(attempt_ref_failed)
        self.assertTrue(replayed.result["idempotent"])
        self.assertEqual("aborted", replayed.result["transaction_phase"])
        self.assertEqual(
            "expired_cleanup_complete",
            replayed.result["publication_phase"],
        )
        self.assertFalse(raw_marker.exists())

    def test_ordinary_export_stage_cleanup_rejects_abort_ack(self) -> None:
        coordinator, _bundle = self.build_exportable_run(
            "ordinary-expired-cleanup-ack",
            bind_export=False,
        )
        raw_marker = coordinator.run_dir / "raw-inputs" / "ordinary-expired.bin"
        raw_marker.write_bytes(b"ordinary expired raw input")
        os.chmod(raw_marker, 0o600)
        expired = RetrospectiveOrchestrator(
            coordinator.run_dir,
            clock=lambda: "2026-07-23T00:00:00Z",
            identity_path=self.identity_path,
            require_existing_identity=True,
        )
        delete_claimed = expired._delete_claimed_raw_paths

        def reject_abort_then_delete(cleanup_claim):
            with self.assertRaisesRegex(
                orchestrator_module.InvalidTransitionError,
                "cannot rewrite expired cleanup",
            ):
                expired.mark_finalized("aborted")
            claimed = expired.load_state()["publication"]
            self.assertEqual("expired_cleanup_claimed", claimed["phase"])
            self.assertEqual(
                "expired_unpublished",
                claimed["expired_cleanup_claim"]["disposition"],
            )
            self.assertEqual(
                cleanup_claim,
                claimed["expired_cleanup_claim"],
            )
            delete_claimed(cleanup_claim)

        with mock.patch.object(
            expired,
            "_delete_claimed_raw_paths",
            side_effect=reject_abort_then_delete,
        ):
            cleaned = expired.gc_expired_raw()
        self.assertTrue(cleaned["cleaned"])
        self.assertFalse(raw_marker.exists())
        self.assertEqual(
            "expired_cleanup_complete",
            expired.load_state()["publication"]["phase"],
        )

    def test_pending_checkpoint_recovers_after_terminal_export_gc(self) -> None:
        coordinator, bundle = self.build_exportable_run(
            "pending-checkpoint-collected-export",
            persist_descriptor=True,
        )
        transaction = self.transaction(coordinator, bundle)
        self.publish(transaction)
        claim = coordinator.claim_publication(
            transaction.attempt_ref,
            transaction.status()["plan_digest"],
        )
        pending = coordinator.mark_finalized(
            "committed",
            attempt_ref=transaction.attempt_ref,
            claim_revision=claim["checkpoint_revision"],
            defer_cleanup=True,
            plan_digest=transaction.status()["plan_digest"],
        )
        self.assertEqual(
            "published_cleanup_pending",
            pending["publication"]["phase"],
        )
        release_committed_staged_export(bundle, transaction.attempt_ref)
        reaped = garbage_collect_expired_exports(
            self.root / ".codex-local" / "exports",
            now=dt.datetime(2100, 1, 1, tzinfo=dt.UTC),
        )
        self.assertIn(str(bundle.resolve()), reaped["deleted"])

        finalized = self.finalize_cli(coordinator)

        self.assertEqual(RunStage.COMPLETE.value, finalized.result["stage"])
        self.assertEqual(
            "complete",
            coordinator.load_state()["publication"]["phase"],
        )

    def test_recovery_repairs_outer_committed_after_exact_provider_cas_crash(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run("crash-after-provider-cas")

        def crash(point, _state):
            if point == "advance_state.after_provider_cas":
                raise RuntimeError("simulated provider CAS crash")

        crashing = self.publication_adapter(failure_injector=crash)
        transaction = self.transaction(coordinator, bundle, adapter=crashing)
        transaction.prepare()
        transaction.stage()
        transaction.seal()
        transaction.close_compliance()
        transaction.promote()
        with self.assertRaisesRegex(RuntimeError, "provider CAS crash"):
            transaction.commit()
        self.assertEqual("promoted", transaction.status()["phase"])
        authority.assert_provider_cache_matches(
            self.provider_state,
            self.load_history(),
            identity=self.identity,
        )

        recovered_adapter = self.publication_adapter()
        recovered = PublicationTransaction.open(
            transaction.journal_path,
            adapter=recovered_adapter,
            expected_attempt_ref=transaction.attempt_ref,
        )
        self.assertEqual("committed", recovered.status()["phase"])
        self.assertTrue(recovered.status()["state_advanced"])
        self.assertFalse(recovered.status()["reservations_held"])
        reopened = PublicationTransaction.open(
            transaction.journal_path,
            adapter=recovered_adapter,
            expected_attempt_ref=transaction.attempt_ref,
        )
        self.assertEqual("committed", reopened.status()["phase"])

    def test_abort_recovery_validates_checkpoint_and_claim_before_adapter(self) -> None:
        coordinator, bundle = self.build_exportable_run("abort-claim-authority")
        transaction = self.transaction(coordinator, bundle)
        transaction.prepare()
        transaction.abort("test_requested_abort")
        original = coordinator.load_state()

        def remove_host(current: dict[str, object]) -> None:
            host = "codex-hoteng-srv-01"
            current["host_refs"].pop(host)
            current["source"]["cells"].pop(host)
            current["cursors"].pop(host)

        def tamper_claim(current: dict[str, object]) -> None:
            current["publication"]["publication_claim"]["plan_digest"] = "0" * 64

        for label, mutation in {
            "checkpoint": remove_host,
            "claim": tamper_claim,
        }.items():
            with self.subTest(case=label):

                def tamper(current: dict[str, object]):
                    mutation(current)
                    return current, None

                coordinator.store.transaction(tamper)
                adapter = mock.Mock()
                transaction._adapter = adapter
                with self.assertRaises(PublicationRejected):
                    transaction.recover_abort()
                self.assertEqual([], adapter.mock_calls)
                with self.assertRaises(PublicationRejected):
                    PublicationTransaction.open(
                        transaction.journal_path,
                        adapter=adapter,
                        expected_attempt_ref=transaction.attempt_ref,
                    )
                self.assertEqual([], adapter.mock_calls)

                def restore(current: dict[str, object]):
                    current.clear()
                    current.update(copy.deepcopy(original))
                    return current, None

                coordinator.store.transaction(restore)

    def test_pending_abort_direct_recovery_validates_claim_before_adapter(self) -> None:
        coordinator, bundle = self.build_exportable_run("abort-pending-claim-authority")
        transaction = self.transaction(coordinator, bundle)
        transaction.prepare()
        transaction._mark_abort_pending(
            "test_requested_abort",
            details={},
            receipts={},
            action="abort_pending",
        )

        def tamper(current: dict[str, object]):
            current["publication"]["publication_claim"]["plan_digest"] = "0" * 64
            return current, None

        coordinator.store.transaction(tamper)
        adapter = mock.Mock()
        transaction._adapter = adapter
        with self.assertRaises(PublicationRejected):
            transaction.recover_abort()
        self.assertEqual([], adapter.mock_calls)

    def test_pre_reservation_abort_recovers_lost_cleanup_responses_exactly_once(
        self,
    ) -> None:
        coordinator, bundle = self.build_exportable_run("abort-before-reservation")
        advanced = False

        def advance_target(point, _state):
            nonlocal advanced
            if point != "prepare.after_inventory" or advanced:
                return
            advanced = True
            (self.repo / "conflict.txt").write_text("conflict\n", encoding="ascii")
            run_command(["git", "add", "conflict.txt"], cwd=self.repo)
            run_command(
                [
                    "git",
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "-q",
                    "-m",
                    "Advance target before reservation",
                ],
                cwd=self.repo,
            )

        transaction = self.transaction(
            coordinator,
            bundle,
            failure_injector=advance_target,
        )
        with self.assertRaises(finalize_module.TargetHeadConflict):
            transaction.prepare()
        self.assertEqual("abort_pending", transaction.status()["phase"])
        self.assertIsNone(self.adapter.inspect_attempt(transaction.attempt_ref))
        with self.assertRaises(finalize_module.ReceiptValidationError):
            transaction.recover_abort(cleanup_receipt={"synthetic": True})

        claim = coordinator.load_state()["publication"]["publication_claim"]
        inspected = PublicationTransaction.inspect_local_for_run(
            transaction.journal_path,
            bundle_dir=bundle,
            destination=self.destination(coordinator.load_state()),
            target_ref=TARGET_REF,
            expected_target_head=transaction.status()["plan"]["expected_target_head"],
            run_dir=coordinator.run_dir,
            identity_path=self.identity_path,
        )
        self.assertEqual("abort_pending", inspected["phase"])
        coordinator.claim_publication(
            claim["attempt_ref"],
            claim["plan_digest"],
        )
        with self.assertRaises(RunConflictError):
            coordinator.mark_finalized(
                "aborted",
                attempt_ref=claim["attempt_ref"],
                claim_revision=claim["checkpoint_revision"],
                plan_digest=claim["plan_digest"],
            )

        lost = set()

        def lose_response(point, _state):
            if (
                point
                in {
                    "cleanup.after_persist",
                    "release_reservations.after_persist",
                }
                and point not in lost
            ):
                lost.add(point)
                raise RuntimeError(f"lost {point}")

        crashing_adapter = self.publication_adapter(failure_injector=lose_response)
        with self.assertRaisesRegex(RuntimeError, "cleanup.after_persist"):
            PublicationTransaction.open(
                transaction.journal_path,
                adapter=crashing_adapter,
                expected_attempt_ref=transaction.attempt_ref,
            )
        with self.assertRaisesRegex(RuntimeError, "release_reservations.after_persist"):
            PublicationTransaction.open(
                transaction.journal_path,
                adapter=crashing_adapter,
                expected_attempt_ref=transaction.attempt_ref,
            )

        recovered = PublicationTransaction.open(
            transaction.journal_path,
            adapter=self.publication_adapter(),
            expected_attempt_ref=transaction.attempt_ref,
        )
        self.assertEqual("aborted", recovered.status()["phase"])
        self.assertEqual(
            recovered.status(),
            PublicationTransaction.open(
                transaction.journal_path,
                adapter=self.publication_adapter(),
                expected_attempt_ref=transaction.attempt_ref,
            ).status(),
        )
        provider_attempt = self.adapter.inspect_attempt(transaction.attempt_ref)
        self.assertIsNotNone(provider_attempt)
        assert provider_attempt is not None
        self.assertEqual(0, provider_attempt["capacity_bytes"])
        self.assertFalse(provider_attempt["capacity_held"])
        self.assertFalse(provider_attempt["cleanup_claim"]["provider_attempt_reserved"])
        self.assertIsNone(provider_attempt["cleanup_claim"]["staging_tip"])
        ledger = safe_io.read_bounded_json(
            self.provider_state / "capacity.json",
            max_bytes=1024 * 1024,
            require_owner_only=True,
        )
        self.assertNotIn(transaction.attempt_ref, ledger["reservations"])

        completed = coordinator.mark_finalized(
            "aborted",
            attempt_ref=claim["attempt_ref"],
            claim_revision=claim["checkpoint_revision"],
            plan_digest=claim["plan_digest"],
        )
        self.assertEqual("aborted", completed["publication"]["phase"])
        self.assertEqual(
            claim,
            completed["publication"]["publication_claim"],
        )
        replayed = coordinator.mark_finalized(
            "aborted",
            attempt_ref=claim["attempt_ref"],
            claim_revision=claim["checkpoint_revision"],
            plan_digest=claim["plan_digest"],
        )
        self.assertTrue(replayed["idempotent"])
        self.assertEqual(claim, replayed["publication"]["publication_claim"])


if __name__ == "__main__":
    unittest.main()
