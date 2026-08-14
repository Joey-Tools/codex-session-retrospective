from __future__ import annotations

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
                fingerprint = {orchestrator_support.PUBLISHER_FINGERPRINT!r}
                print(f"[GNUPG:] VALIDSIG {{fingerprint}} 0")
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

    def test_bounded_canary_accepts_valid_sign_and_verify_output(self) -> None:
        self.assertTrue(
            orchestrator_support.publisher_sign_verify_canary(
                gnupg_home=self.gnupg_home,
                gpg_program=self.gpg_program,
            )
        )
        self.assertFalse(self.gpg_sentinel.exists())

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
                    "--detach-sign",
                    "--output",
                    str(signature),
                    str(payload),
                ],
                environment=environment,
                timeout_seconds=0.5,
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
