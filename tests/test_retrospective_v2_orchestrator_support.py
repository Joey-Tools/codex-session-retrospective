from __future__ import annotations

import contextlib
import errno
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from unittest import mock
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from retrospective_v2 import orchestrator_support  # noqa: E402


class PublisherCanaryPathContractTests(unittest.TestCase):
    def test_production_canary_root_is_fixed_outside_environment_selection(
        self,
    ) -> None:
        self.assertEqual(
            Path("/tmp")
            / f"codex-session-retrospective-{os.getuid()}"
            / "publisher-canary",
            orchestrator_support.temporary_paths.PUBLISHER_CANARY_TEMP_ROOT,
        )
        self.assertEqual(
            Path("/tmp")
            / f"codex-session-retrospective-{os.getuid()}"
            / "remote-helper",
            orchestrator_support.temporary_paths.REMOTE_HELPER_TEMP_ROOT,
        )
        self.assertEqual(
            Path("/tmp")
            / f"codex-session-retrospective-{os.getuid()}"
            / "publication-index",
            orchestrator_support.temporary_paths.PUBLICATION_INDEX_TEMP_ROOT,
        )

    def test_lexical_source_overlap_is_rejected_independently_of_resolution(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source_root = root / "source-root"
            source_root.mkdir(mode=0o700)
            outside = root / "outside"
            outside.mkdir(mode=0o700)
            (source_root / "escape").symlink_to(outside, target_is_directory=True)
            canary_root = source_root / "escape" / "publisher-canary"

            self.assertFalse(
                canary_root.resolve(strict=False).is_relative_to(
                    source_root.resolve(strict=False)
                )
            )
            with self.assertRaises(orchestrator_support.safe_io.UnsafePathError):
                orchestrator_support.temporary_paths._require_root_outside_source(
                    canary_root,
                    source_root,
                )

    def test_bound_creation_rejects_parent_replacement_before_yield(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source_root = root / "source-root"
            source_root.mkdir(mode=0o700)
            source_sentinel = source_root / "source-sentinel"
            source_sentinel.write_text("unchanged", encoding="ascii")
            temporary_root = root / "temporary-root"
            displaced_root = root / "displaced-root"
            real_mkdir = os.mkdir
            swapped = False

            def replace_after_child_creation(path, mode=0o777, *, dir_fd=None):
                nonlocal swapped
                result = real_mkdir(path, mode, dir_fd=dir_fd)
                if (
                    dir_fd is not None
                    and str(path).startswith("replacement-test-")
                    and not swapped
                ):
                    swapped = True
                    temporary_root.rename(displaced_root)
                    temporary_root.symlink_to(source_root, target_is_directory=True)
                return result

            try:
                with (
                    mock.patch.object(
                        orchestrator_support.temporary_paths.transport_source,
                        "_local_codex_root",
                        return_value=source_root,
                    ),
                    mock.patch.object(
                        orchestrator_support.temporary_paths.os,
                        "mkdir",
                        side_effect=replace_after_child_creation,
                    ),
                    self.assertRaisesRegex(
                        orchestrator_support.safe_io.UnsafePathError,
                        "temporary root changed",
                    ),
                ):
                    with orchestrator_support.temporary_paths.owner_only_temporary_directory(
                        root=temporary_root,
                        prefix="replacement-test-",
                    ):
                        self.fail("a replaced temporary root must not be published")
            finally:
                if temporary_root.is_symlink():
                    temporary_root.unlink()
                if displaced_root.exists():
                    shutil.rmtree(displaced_root)

            self.assertTrue(swapped)
            self.assertEqual("unchanged", source_sentinel.read_text(encoding="ascii"))
            self.assertEqual([source_sentinel], list(source_root.iterdir()))


class PublisherCanaryProcessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temporary_directory.name)
        self.source_root = self.root / "source-root"
        self.source_root.mkdir(mode=0o700)
        self.canary_root = self.root / "canary-root"
        self.canary_root_patch = mock.patch.object(
            orchestrator_support.temporary_paths,
            "PUBLISHER_CANARY_TEMP_ROOT",
            self.canary_root,
        )
        self.source_root_patch = mock.patch.object(
            orchestrator_support.temporary_paths.transport_source,
            "_local_codex_root",
            return_value=self.source_root,
        )
        self.canary_root_patch.start()
        self.source_root_patch.start()
        self.gnupg_home = self.root / "gnupg"
        self.gnupg_home.mkdir(mode=0o700)
        self.gpg_program = self.root / "fake-gpg"
        self.gpg_mode = self.root / "fake-gpg-mode"
        self.gpg_environment = self.root / "fake-gpg-environments"
        self.gpg_child_pids = self.root / "fake-gpg-child-pids"
        self.gpg_sentinel = self.root / "fake-gpg-sentinel"
        self.gpg_mode.write_text("success", encoding="ascii")
        self.gpg_program.write_text(
            textwrap.dedent(
                f"""\
                #!{sys.executable}
                import json
                import os
                from pathlib import Path
                import subprocess
                import sys
                import time

                arguments = sys.argv[1:]
                if arguments[:1] != ["--no-options"]:
                    Path({str(self.gpg_sentinel)!r}).write_text(
                        "default options were not suppressed", encoding="utf-8"
                    )
                    raise SystemExit(96)
                arguments = arguments[1:]
                phase = "sign" if "--detach-sign" in arguments else "verify"
                mode = Path({str(self.gpg_mode)!r}).read_text(encoding="ascii").strip()
                if mode == "record_environment":
                    recorded_value_keys = (
                        "GNUPGHOME",
                        "HOME",
                        "LANG",
                        "LC_ALL",
                        "PATH",
                        "TEMP",
                        "TMP",
                        "TMPDIR",
                        "TZ",
                    )
                    environment_record = {{
                        "keys": sorted(os.environ),
                        "values": {{
                            key: os.environ[key]
                            for key in recorded_value_keys
                            if key in os.environ
                        }},
                        "runtime_text_encoding_is_poisoned": (
                            os.environ.get("__CF_USER_TEXT_ENCODING") == "poisoned"
                        ),
                    }}
                    with Path({str(self.gpg_environment)!r}).open(
                        "a", encoding="utf-8"
                    ) as environment_stream:
                        environment_stream.write(
                            json.dumps(environment_record, sort_keys=True) + chr(10)
                        )
                limit = {orchestrator_support._PUBLISHER_CANARY_STREAM_LIMIT_BYTES}
                if mode == f"{{phase}}_stdout":
                    stream = sys.stdout.buffer
                elif mode == f"{{phase}}_stderr":
                    stream = sys.stderr.buffer
                else:
                    stream = None
                if mode in {{"spawn_closed_child", "spawn_inherited_child"}}:
                    closed_stream = (
                        subprocess.DEVNULL
                        if mode == "spawn_closed_child"
                        else None
                    )
                    child = subprocess.Popen(
                        [sys.executable, "-c", "import time;time.sleep(60)"],
                        stdin=subprocess.DEVNULL,
                        stdout=closed_stream,
                        stderr=closed_stream,
                        close_fds=True,
                    )
                    with Path({str(self.gpg_child_pids)!r}).open(
                        "a", encoding="ascii"
                    ) as child_stream:
                        child_stream.write(str(child.pid) + chr(10))
                        child_stream.flush()
                if stream is not None:
                    stream.write(b"x" * (limit + 1))
                    stream.flush()
                    time.sleep(2)
                    Path({str(self.gpg_sentinel)!r}).write_text(
                        "completed", encoding="utf-8"
                    )
                    raise SystemExit(0)
                if phase == "sign":
                    output = Path(arguments[arguments.index("--output") + 1])
                    output.write_bytes(b"signature")
                    raise SystemExit(0)
                primary_fingerprint = {orchestrator_support.PUBLISHER_FINGERPRINT!r}
                signing_fingerprint = primary_fingerprint
                if mode == "subkey_validsig":
                    signing_fingerprint = "0123456789ABCDEF0123456789ABCDEF01234567"
                fields = [
                    signing_fingerprint,
                    "20260818",
                    "1787010000",
                    "0",
                    "4",
                    "0",
                    "22",
                    "10",
                    "00",
                ]
                if mode == "subkey_validsig":
                    fields.append(primary_fingerprint)
                print("[GNUPG:] VALIDSIG " + " ".join(fields))
                """
            ),
            encoding="utf-8",
        )
        self.gpg_program.chmod(0o700)

    def tearDown(self) -> None:
        if self.gpg_child_pids.exists():
            for value in self.gpg_child_pids.read_text(encoding="ascii").splitlines():
                try:
                    os.kill(int(value), signal.SIGKILL)
                except (ProcessLookupError, ValueError):
                    pass
        self.source_root_patch.stop()
        self.canary_root_patch.stop()
        self.temporary_directory.cleanup()

    def _spawned_child_pids(self) -> list[int]:
        return [
            int(value)
            for value in self.gpg_child_pids.read_text(encoding="ascii").splitlines()
        ]

    def _assert_spawned_children_absent(self, expected_count: int) -> None:
        pids = self._spawned_child_pids()
        self.assertEqual(expected_count, len(pids))
        deadline = time.monotonic() + 3.0
        for pid in pids:
            while True:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                if time.monotonic() >= deadline:
                    self.fail(f"publisher canary child {pid} survived cleanup")
                time.sleep(0.01)

    @staticmethod
    def _mark_cleanup_incomplete(error: RuntimeError) -> RuntimeError:
        def cleanup_failure(_process) -> int:
            raise RuntimeError("simulated persistent process cleanup failure")

        orchestrator_support.process_lifecycle.finish_cleanup(
            mock.Mock(spec=subprocess.Popen),
            signal_retirement=(
                orchestrator_support.process_lifecycle.GroupSignalRetirement()
            ),
            terminate_and_reap=cleanup_failure,
            reap_only=cleanup_failure,
            active_error=error,
        )
        return error

    def test_bounded_canary_accepts_valid_sign_and_verify_output(self) -> None:
        self.assertTrue(
            orchestrator_support.publisher_sign_verify_canary(
                gnupg_home=self.gnupg_home,
                gpg_program=self.gpg_program,
            )
        )
        self.assertFalse(self.gpg_sentinel.exists())
        self.assertEqual(0o700, self.canary_root.stat().st_mode & 0o777)

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_canary_selector_setup_failure_reaps_started_process(self) -> None:
        real_popen = subprocess.Popen
        spawned: list[subprocess.Popen[bytes]] = []

        def capture_popen(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            spawned.append(process)
            return process

        with (
            mock.patch.object(
                orchestrator_support.subprocess,
                "Popen",
                side_effect=capture_popen,
            ),
            mock.patch.object(
                orchestrator_support.selectors,
                "DefaultSelector",
                side_effect=OSError(errno.EMFILE, "selector unavailable"),
            ),
            self.assertRaises(OSError),
        ):
            orchestrator_support._run_bounded_publisher_canary_process(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-S",
                    "-c",
                    "import time; time.sleep(60)",
                ],
                environment=dict(os.environ),
                timeout_seconds=2,
            )

        self.assertEqual(1, len(spawned))
        self.assertIsNotNone(spawned[0].poll())

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_canary_selector_close_failure_still_finishes_process_cleanup(self) -> None:
        real_selector = orchestrator_support.selectors.DefaultSelector

        class CloseFailingSelector:
            def __init__(self) -> None:
                self._inner = real_selector()

            def __getattr__(self, name: str):
                return getattr(self._inner, name)

            def close(self) -> None:
                self._inner.close()
                raise OSError(errno.EIO, "selector close failure")

        with (
            mock.patch.object(
                orchestrator_support.selectors,
                "DefaultSelector",
                CloseFailingSelector,
            ),
            self.assertRaisesRegex(OSError, "selector close failure"),
        ):
            orchestrator_support._run_bounded_publisher_canary_process(
                [sys.executable, "-I", "-B", "-S", "-c", "pass"],
                environment=dict(os.environ),
                timeout_seconds=2,
            )

    def test_readiness_does_not_downgrade_incomplete_process_cleanup(self) -> None:
        error = self._mark_cleanup_incomplete(
            orchestrator_support.finalize.LocalGitPublicationError(
                "simulated readiness failure"
            )
        )
        with (
            mock.patch.object(
                orchestrator_support.finalize,
                "validate_publisher_keyring",
                side_effect=error,
            ),
            self.assertRaises(
                orchestrator_support.process_lifecycle.ProcessGroupCleanupIncompleteError
            ),
        ):
            orchestrator_support.publisher_readiness(
                gnupg_home=self.gnupg_home,
                gpg_program=self.gpg_program,
            )

    def test_canary_does_not_downgrade_incomplete_process_cleanup(self) -> None:
        error = self._mark_cleanup_incomplete(
            orchestrator_support._PublisherCanaryProcessError(
                "simulated canary failure"
            )
        )
        with (
            mock.patch.object(
                orchestrator_support,
                "_run_bounded_publisher_canary_process",
                side_effect=error,
            ),
            self.assertRaises(
                orchestrator_support.process_lifecycle.ProcessGroupCleanupIncompleteError
            ),
        ):
            orchestrator_support.publisher_sign_verify_canary(
                gnupg_home=self.gnupg_home,
                gpg_program=self.gpg_program,
            )

    def test_canary_does_not_downgrade_cleanup_only_failure(self) -> None:
        error = orchestrator_support._PublisherCanaryProcessError(
            "simulated direct process cleanup failure"
        )

        def cleanup_failure(_process) -> int:
            raise error

        with self.assertRaises(
            orchestrator_support._PublisherCanaryProcessError
        ) as caught:
            orchestrator_support.process_lifecycle.finish_cleanup(
                mock.Mock(spec=subprocess.Popen),
                signal_retirement=(
                    orchestrator_support.process_lifecycle.GroupSignalRetirement()
                ),
                terminate_and_reap=cleanup_failure,
                reap_only=cleanup_failure,
                active_error=None,
            )

        with (
            mock.patch.object(
                orchestrator_support,
                "_run_bounded_publisher_canary_process",
                side_effect=caught.exception,
            ),
            self.assertRaises(
                orchestrator_support.process_lifecycle.ProcessGroupCleanupIncompleteError
            ),
        ):
            orchestrator_support.publisher_sign_verify_canary(
                gnupg_home=self.gnupg_home,
                gpg_program=self.gpg_program,
            )

    def test_canary_accepts_signing_subkey_bound_to_primary(self) -> None:
        self.gpg_mode.write_text("subkey_validsig", encoding="ascii")

        self.assertTrue(
            orchestrator_support.publisher_sign_verify_canary(
                gnupg_home=self.gnupg_home,
                gpg_program=self.gpg_program,
            )
        )

    def test_canary_uses_closed_subprocess_environment(self) -> None:
        captured_environments: list[dict[str, str]] = []
        run_canary = orchestrator_support._run_bounded_publisher_canary_process
        self.gpg_mode.write_text("record_environment", encoding="ascii")

        def capture_environment(command, *, environment):
            captured_environments.append(dict(environment))
            return run_canary(command, environment=environment)

        poisoned = {
            "BASH_ENV": str(self.root / "bash-env"),
            "DYLD_INSERT_LIBRARIES": str(self.root / "inject.dylib"),
            "ENV": str(self.root / "shell-env"),
            "GIT_CONFIG_GLOBAL": str(self.root / "gitconfig"),
            "GPG_AGENT_INFO": str(self.root / "agent-info"),
            "LD_PRELOAD": str(self.root / "inject.so"),
            "PATH": str(self.root / "bin"),
            "PYTHONHOME": str(self.root / "python-home"),
            "PYTHONPATH": str(self.root / "python-path"),
            "SSH_AUTH_SOCK": str(self.root / "ssh-agent"),
            "TEMP": str(self.source_root),
            "TMP": str(self.source_root),
            "TMPDIR": str(self.source_root),
            "__CF_USER_TEXT_ENCODING": "poisoned",
        }
        source_sentinel = self.source_root / "source-sentinel"
        source_sentinel.write_text("unchanged", encoding="ascii")
        with (
            mock.patch.dict(os.environ, poisoned),
            mock.patch.object(
                orchestrator_support,
                "_run_bounded_publisher_canary_process",
                side_effect=capture_environment,
            ),
        ):
            self.assertTrue(
                orchestrator_support.publisher_sign_verify_canary(
                    gnupg_home=self.gnupg_home,
                    gpg_program=self.gpg_program,
                )
            )

        child_environment_records = tuple(
            json.loads(line)
            for line in self.gpg_environment.read_text(encoding="utf-8").splitlines()
        )
        self.assertEqual(2, len(captured_environments))
        allowed = {
            "GNUPGHOME",
            "HOME",
            "LANG",
            "LC_ALL",
            "PATH",
            "TEMP",
            "TMP",
            "TMPDIR",
            "TZ",
        }
        for captured, record in zip(
            captured_environments, child_environment_records, strict=True
        ):
            child_keys = set(record["keys"])
            runtime_added = child_keys.difference(captured)
            self.assertLessEqual(runtime_added, {"__CF_USER_TEXT_ENCODING"})
            self.assertEqual(
                set(captured),
                child_keys.difference({"__CF_USER_TEXT_ENCODING"}),
            )
            self.assertEqual(captured, record["values"])
            self.assertFalse(record["runtime_text_encoding_is_poisoned"])
            self.assertLessEqual(set(captured), allowed)
            self.assertEqual(captured["GNUPGHOME"], str(self.gnupg_home))
            self.assertEqual(captured["HOME"], str(self.gnupg_home))
            self.assertEqual(captured["PATH"], os.defpath)
            self.assertEqual(captured["LANG"], "C")
            self.assertEqual(captured["LC_ALL"], "C")
            self.assertEqual(captured["TZ"], "UTC")
            selected_temp = captured["TMPDIR"]
            self.assertEqual(selected_temp, captured["TEMP"])
            self.assertEqual(selected_temp, captured["TMP"])
            self.assertEqual(self.canary_root, Path(selected_temp).parent)
            self.assertNotEqual(str(self.source_root), selected_temp)
        self.assertEqual("unchanged", source_sentinel.read_text(encoding="ascii"))
        self.assertEqual([source_sentinel], list(self.source_root.iterdir()))

    def test_canary_cold_start_uses_fixed_safe_io_probe_parent(self) -> None:
        source_sentinel = self.source_root / "source-sentinel"
        source_sentinel.write_text("unchanged", encoding="ascii")
        temporary_directory_calls: list[dict[str, object]] = []
        real_temporary_directory = tempfile.TemporaryDirectory

        def capture_temporary_directory(*args, **kwargs):
            temporary_directory_calls.append(dict(kwargs))
            return real_temporary_directory(*args, **kwargs)

        safe_io = orchestrator_support.safe_io
        safe_io._cached_dir_fd_capability_issues.cache_clear()
        try:
            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "TEMP": str(self.source_root),
                        "TMP": str(self.source_root),
                        "TMPDIR": str(self.source_root),
                    },
                ),
                mock.patch.object(tempfile, "tempdir", str(self.source_root)),
                mock.patch.object(
                    tempfile,
                    "TemporaryDirectory",
                    side_effect=capture_temporary_directory,
                ),
            ):
                self.assertTrue(
                    orchestrator_support.publisher_sign_verify_canary(
                        gnupg_home=self.gnupg_home,
                        gpg_program=self.gpg_program,
                    )
                )
        finally:
            safe_io._cached_dir_fd_capability_issues.cache_clear()

        probe_calls = tuple(
            call
            for call in temporary_directory_calls
            if call.get("prefix") == "retrospective-safe-io-probe-"
        )
        self.assertEqual(1, len(probe_calls))
        self.assertEqual(Path("/tmp"), probe_calls[0].get("dir"))
        self.assertEqual("unchanged", source_sentinel.read_text(encoding="ascii"))
        self.assertEqual([source_sentinel], list(self.source_root.iterdir()))

    def test_canary_rejects_a_fixed_root_inside_a_source_root(self) -> None:
        source_sentinel = self.source_root / "source-sentinel"
        source_sentinel.write_text("unchanged", encoding="ascii")

        with mock.patch.object(
            orchestrator_support.temporary_paths,
            "PUBLISHER_CANARY_TEMP_ROOT",
            self.source_root / "publisher-canary",
        ):
            self.assertFalse(
                orchestrator_support.publisher_sign_verify_canary(
                    gnupg_home=self.gnupg_home,
                    gpg_program=self.gpg_program,
                )
            )

        self.assertEqual("unchanged", source_sentinel.read_text(encoding="ascii"))
        self.assertEqual([source_sentinel], list(self.source_root.iterdir()))

    def test_canary_rejects_a_fixed_root_resolving_into_a_source_root(self) -> None:
        actual_source_root = self.root / "actual-source-root"
        actual_source_root.mkdir(mode=0o700)
        source_alias = self.root / "source-alias"
        source_alias.symlink_to(actual_source_root, target_is_directory=True)
        source_sentinel = actual_source_root / "source-sentinel"
        source_sentinel.write_text("unchanged", encoding="ascii")
        canary_root = actual_source_root / "publisher-canary"

        with (
            mock.patch.object(
                orchestrator_support.temporary_paths,
                "PUBLISHER_CANARY_TEMP_ROOT",
                canary_root,
            ),
            mock.patch.object(
                orchestrator_support.temporary_paths.transport_source,
                "_local_codex_root",
                return_value=source_alias,
            ),
        ):
            self.assertFalse(
                orchestrator_support.publisher_sign_verify_canary(
                    gnupg_home=self.gnupg_home,
                    gpg_program=self.gpg_program,
                )
            )

        self.assertEqual("unchanged", source_sentinel.read_text(encoding="ascii"))
        self.assertEqual([source_sentinel], list(actual_source_root.iterdir()))

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_canary_closes_spawned_process_groups_after_success(self) -> None:
        self.gpg_mode.write_text("spawn_closed_child", encoding="ascii")

        self.assertTrue(
            orchestrator_support.publisher_sign_verify_canary(
                gnupg_home=self.gnupg_home,
                gpg_program=self.gpg_program,
            )
        )

        self._assert_spawned_children_absent(2)

    def test_canary_waits_for_leader_after_output_eof(self) -> None:
        helper = self.root / "close-canary-output-before-side-effect.py"
        ready = self.root / "canary-ready"
        release = self.root / "canary-release"
        marker = self.root / "canary-complete"
        helper.write_text(
            "import os, pathlib, sys, time\n"
            "pathlib.Path(sys.argv[1]).write_text('ready', encoding='ascii')\n"
            "os.close(1)\n"
            "os.close(2)\n"
            "while not pathlib.Path(sys.argv[2]).exists(): time.sleep(0.01)\n"
            "pathlib.Path(sys.argv[3]).write_text('complete', encoding='ascii')\n",
            encoding="ascii",
        )
        wait_for_exit = orchestrator_support.process_lifecycle.wait_for_unreaped_exit

        def release_after_wait_entry(*args, **kwargs) -> None:
            self.assertEqual("ready", ready.read_text(encoding="ascii"))
            release.write_text("release", encoding="ascii")
            wait_for_exit(*args, **kwargs)

        with mock.patch.object(
            orchestrator_support.process_lifecycle,
            "wait_for_unreaped_exit",
            side_effect=release_after_wait_entry,
        ):
            result = orchestrator_support._run_bounded_publisher_canary_process(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-S",
                    str(helper),
                    str(ready),
                    str(release),
                    str(marker),
                ],
                environment=dict(os.environ),
                timeout_seconds=2,
            )

        self.assertEqual(0, result.returncode)
        self.assertEqual("complete", marker.read_text(encoding="ascii"))

    def test_canary_post_eof_wait_obeys_deadline(self) -> None:
        helper = self.root / "close-canary-output-and-stall.py"
        pid_path = self.root / "canary-stall.pid"
        helper.write_text(
            "import os, pathlib, sys, time\n"
            "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()), encoding='ascii')\n"
            "os.close(1)\n"
            "os.close(2)\n"
            "time.sleep(60)\n",
            encoding="ascii",
        )
        wait_entries = 0
        wait_for_exit = orchestrator_support.process_lifecycle.wait_for_unreaped_exit

        def expire_inside_wait(*args, **kwargs) -> None:
            nonlocal wait_entries
            wait_entries += 1
            kwargs["deadline"] = time.monotonic() - 1
            wait_for_exit(*args, **kwargs)

        with (
            mock.patch.object(
                orchestrator_support.process_lifecycle,
                "wait_for_unreaped_exit",
                side_effect=expire_inside_wait,
            ),
            self.assertRaisesRegex(
                orchestrator_support._PublisherCanaryProcessError,
                "deadline",
            ),
        ):
            orchestrator_support._run_bounded_publisher_canary_process(
                [sys.executable, "-I", "-B", "-S", str(helper), str(pid_path)],
                environment=dict(os.environ),
                timeout_seconds=2,
            )

        self.assertEqual(1, wait_entries)
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pid_path.read_text(encoding="ascii")), 0)

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_canary_does_not_resignal_group_after_leader_reap(self) -> None:
        kill_signals: list[int] = []
        wait_calls = 0
        process_wait = subprocess.Popen.wait

        def observe_group_signal(_process_group_id: int, selected_signal: int) -> None:
            kill_signals.append(selected_signal)
            if selected_signal == 0:
                raise ProcessLookupError

        def reap_then_interrupt(process, *args, **kwargs):
            nonlocal wait_calls
            result = process_wait(process, *args, **kwargs)
            wait_calls += 1
            if wait_calls == 1:
                raise KeyboardInterrupt
            return result

        with (
            mock.patch.object(os, "killpg", side_effect=observe_group_signal),
            mock.patch.object(
                subprocess.Popen,
                "wait",
                autospec=True,
                side_effect=reap_then_interrupt,
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            orchestrator_support._run_bounded_publisher_canary_process(
                [sys.executable, "-I", "-B", "-S", "-c", "pass"],
                environment=dict(os.environ),
                timeout_seconds=2,
            )

        self.assertEqual(1, kill_signals.count(signal.SIGKILL))
        self.assertEqual(2, wait_calls)

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_canary_eperm_requires_group_absence_after_reap(self) -> None:
        for group_present in (False, True):
            with self.subTest(group_present=group_present):
                attempted_signals: list[int] = []

                def deny_signal_then_probe(
                    _process_group_id: int,
                    selected_signal: int,
                ) -> None:
                    attempted_signals.append(selected_signal)
                    if selected_signal == signal.SIGKILL:
                        raise PermissionError(errno.EPERM, "simulated denial")
                    self.assertEqual(0, selected_signal)
                    if not group_present:
                        raise ProcessLookupError(errno.ESRCH, "simulated absence")

                context = (
                    self.assertRaisesRegex(
                        orchestrator_support._PublisherCanaryProcessError,
                        "closure is unproven",
                    )
                    if group_present
                    else contextlib.nullcontext()
                )
                with (
                    mock.patch.object(
                        orchestrator_support.process_lifecycle.os,
                        "killpg",
                        side_effect=deny_signal_then_probe,
                    ),
                    context,
                ):
                    result = orchestrator_support._run_bounded_publisher_canary_process(
                        [sys.executable, "-I", "-B", "-S", "-c", "pass"],
                        environment=dict(os.environ),
                        timeout_seconds=0.25,
                    )
                    self.assertEqual(0, result.returncode)

                self.assertEqual(signal.SIGKILL, attempted_signals[0])
                self.assertTrue(
                    all(selected == 0 for selected in attempted_signals[1:])
                )
                if group_present:
                    self.assertGreater(len(attempted_signals), 2)
                else:
                    self.assertEqual([signal.SIGKILL, 0], attempted_signals)

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_canary_timeout_closes_group_after_leader_exit(self) -> None:
        self.gpg_mode.write_text("spawn_inherited_child", encoding="ascii")
        payload = self.root / "timeout-payload"
        signature = self.root / "timeout-payload.sig"
        payload.write_bytes(b"payload\n")
        environment = (
            orchestrator_support.publication_support._strict_subprocess_environment(
                home=self.gnupg_home
            )
        )
        environment["GNUPGHOME"] = str(self.gnupg_home)

        with self.assertRaisesRegex(
            orchestrator_support._PublisherCanaryProcessError,
            "deadline",
        ):
            orchestrator_support._run_bounded_publisher_canary_process(
                [
                    str(self.gpg_program),
                    "--no-options",
                    "--detach-sign",
                    "--output",
                    str(signature),
                    str(payload),
                ],
                environment=environment,
                # Exercise inherited-pipe cleanup, not interpreter startup latency.
                timeout_seconds=5.0,
            )

        self._assert_spawned_children_absent(1)

    def test_canary_rejects_gpg_content_change_after_sign(self) -> None:
        def mutate_after_sign(command, *, environment):
            del environment
            signature = Path(command[command.index("--output") + 1])
            signature.write_bytes(b"signature")
            self.gpg_program.write_text("#!/bin/sh\nexit 1\n", encoding="ascii")
            self.gpg_program.chmod(0o700)
            return subprocess.CompletedProcess(command, 0, b"", b"")

        with mock.patch.object(
            orchestrator_support,
            "_run_bounded_publisher_canary_process",
            side_effect=mutate_after_sign,
        ):
            self.assertFalse(
                orchestrator_support.publisher_sign_verify_canary(
                    gnupg_home=self.gnupg_home,
                    gpg_program=self.gpg_program,
                )
            )

    def test_bounded_canary_terminates_oversized_stdout_during_execution(
        self,
    ) -> None:
        self._assert_oversized_stream_is_terminated("stdout")

    def test_bounded_canary_terminates_oversized_stderr_during_execution(
        self,
    ) -> None:
        self._assert_oversized_stream_is_terminated("stderr")

    def _assert_oversized_stream_is_terminated(self, stream: str) -> None:
        for phase in ("sign", "verify"):
            with self.subTest(phase=phase, stream=stream):
                self.gpg_mode.write_text(f"{phase}_{stream}", encoding="ascii")
                self.assertFalse(
                    orchestrator_support.publisher_sign_verify_canary(
                        gnupg_home=self.gnupg_home,
                        gpg_program=self.gpg_program,
                    )
                )
                self.assertFalse(
                    self.gpg_sentinel.exists(),
                    "the process reached post-output work before being terminated",
                )


if __name__ == "__main__":
    unittest.main()
