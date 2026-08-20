from __future__ import annotations

import contextlib
import errno
import os
from pathlib import Path
import signal
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


class PublisherCanaryProcessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temporary_directory.name)
        self.gnupg_home = self.root / "gnupg"
        self.gnupg_home.mkdir(mode=0o700)
        self.gpg_program = self.root / "fake-gpg"
        self.gpg_mode = self.root / "fake-gpg-mode"
        self.gpg_child_pids = self.root / "fake-gpg-child-pids"
        self.gpg_sentinel = self.root / "fake-gpg-sentinel"
        self.gpg_mode.write_text("success", encoding="ascii")
        self.gpg_program.write_text(
            textwrap.dedent(
                f"""\
                #!{sys.executable}
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
        }
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

        self.assertEqual(len(captured_environments), 2)
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
        for environment in captured_environments:
            self.assertLessEqual(set(environment), allowed)
            self.assertEqual(environment["GNUPGHOME"], str(self.gnupg_home))
            self.assertEqual(environment["HOME"], str(self.gnupg_home))
            self.assertEqual(environment["PATH"], os.defpath)
            self.assertEqual(environment["LANG"], "C")
            self.assertEqual(environment["LC_ALL"], "C")
            self.assertEqual(environment["TZ"], "UTC")

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
