from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SCRIPTS = ROOT / "scripts"


class RetrospectiveV2BootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temporary.name)
        self.scripts = self.root / "scripts"
        self.scripts.mkdir(mode=0o700)
        shutil.copytree(
            SOURCE_SCRIPTS / "retrospective_v2",
            self.scripts / "retrospective_v2",
        )
        for source in SOURCE_SCRIPTS.glob("session_retrospective_v2*.py"):
            shutil.copy2(source, self.scripts / source.name)
        self.entrypoint = self.scripts / "session_retrospective_v2.py"
        self.runtime = self.scripts / "session_retrospective_v2_runtime.py"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_entrypoint(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-S",
                os.fspath(self.entrypoint),
                *arguments,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def assert_authority_rejected(
        self, completed: subprocess.CompletedProcess[str]
    ) -> None:
        self.assertEqual(9, completed.returncode, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual("startup", result["command"])
        self.assertEqual(
            "implementation_authority_invalid",
            result["error"]["code"],
        )

    def add_package_import_marker(self, marker: Path) -> None:
        package_init = self.scripts / "retrospective_v2" / "__init__.py"
        package_init.write_text(
            package_init.read_text(encoding="utf-8")
            + "\nfrom pathlib import Path\n"
            + f"Path({os.fspath(marker)!r}).touch()\n",
            encoding="utf-8",
        )

    def instrument_readiness_receipt(self, marker: Path) -> None:
        authority = self.scripts / "retrospective_v2" / "implementation_authority.py"
        authority.write_text(
            authority.read_text(encoding="utf-8")
            + "\n_original_readiness = coordinator_implementation_readiness\n"
            + "def coordinator_implementation_readiness():\n"
            + "    value = _original_readiness()\n"
            + "    Path("
            + repr(os.fspath(marker))
            + ").write_text(\n"
            + "        json.dumps(value, sort_keys=True), encoding='ascii'\n"
            + "    )\n"
            + "    return value\n",
            encoding="utf-8",
        )

    def test_stray_scripts_selectors_is_not_executed(self) -> None:
        marker = self.root / "selectors-executed"
        self.scripts.joinpath("selectors.py").write_text(
            "from pathlib import Path\n" + f"Path({os.fspath(marker)!r}).touch()\n",
            encoding="utf-8",
        )

        completed = self.run_entrypoint("--help")

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["ok"])
        self.assertFalse(marker.exists())

    def test_entrypoint_requires_all_isolation_flags(self) -> None:
        for arguments in (("-B", "-S"), ("-I", "-S"), ("-I", "-B")):
            with self.subTest(arguments=arguments):
                completed = subprocess.run(
                    [
                        sys.executable,
                        *arguments,
                        os.fspath(self.entrypoint),
                        "--help",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(9, completed.returncode, completed.stderr)
                result = json.loads(completed.stdout)
                self.assertEqual("unsafe_python_runtime", result["error"]["code"])

    def test_runtime_rejects_direct_execution_without_descriptor_launcher(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-S",
                os.fspath(self.runtime),
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assert_authority_rejected(completed)

    def test_writable_fixture_root_is_rejected(self) -> None:
        self.root.chmod(0o777)

        completed = self.run_entrypoint("--help")

        self.assert_authority_rejected(completed)

    def test_import_substitutes_reject_before_package_import(self) -> None:
        cases = (
            "cache",
            "bytecode",
            "native",
            "package",
            "symlink",
            "unlisted-source",
            "missing-source",
        )
        for case in cases:
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory(dir=self.root) as case_directory:
                    case_root = Path(case_directory)
                    case_scripts = case_root / "scripts"
                    shutil.copytree(self.scripts, case_scripts)
                    case_package = case_scripts / "retrospective_v2"
                    entrypoint = case_scripts / "session_retrospective_v2.py"
                    marker = case_root / "package-imported"
                    package_init = case_package / "__init__.py"
                    package_init.write_text(
                        package_init.read_text(encoding="utf-8")
                        + "\nfrom pathlib import Path\n"
                        + f"Path({os.fspath(marker)!r}).touch()\n",
                        encoding="utf-8",
                    )
                    if case == "cache":
                        case_package.joinpath("__pycache__").mkdir()
                    elif case == "bytecode":
                        case_package.joinpath("authority.pyc").write_bytes(b"bytecode")
                    elif case == "native":
                        case_package.joinpath("authority.so").write_bytes(b"native")
                    elif case == "package":
                        case_package.joinpath("authority").mkdir()
                    elif case == "symlink":
                        authority = case_package / "authority.py"
                        target = case_root / "authority.py"
                        target.write_bytes(authority.read_bytes())
                        authority.unlink()
                        authority.symlink_to(target)
                    elif case == "unlisted-source":
                        case_package.joinpath("unlisted.py").write_text(
                            "VALUE = 1\n", encoding="ascii"
                        )
                    else:
                        case_package.joinpath("catalog.py").unlink()
                    completed = subprocess.run(
                        [
                            sys.executable,
                            "-I",
                            "-B",
                            "-S",
                            os.fspath(entrypoint),
                            "--help",
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    self.assert_authority_rejected(completed)
                    self.assertFalse(marker.exists())

    def test_unknown_owned_module_does_not_fall_through(self) -> None:
        marker = self.root / "fallback-loader-executed"
        cli_path = self.scripts / "retrospective_v2" / "cli.py"
        cli_source = cli_path.read_text(encoding="utf-8")
        future = "from __future__ import annotations\n"
        cli_path.write_text(
            cli_source.replace(
                future,
                future + "\nimport retrospective_v2.unlisted\n",
                1,
            ),
            encoding="utf-8",
        )
        wrapper = self.root / "fallback_wrapper.py"
        wrapper.write_text(
            "import importlib.abc,importlib.util,pathlib,runpy,sys\n"
            "class Loader(importlib.abc.Loader):\n"
            " def create_module(self,spec): return None\n"
            f" def exec_module(self,module): pathlib.Path({os.fspath(marker)!r}).touch()\n"
            "class Finder(importlib.abc.MetaPathFinder):\n"
            " def find_spec(self,fullname,path=None,target=None):\n"
            "  if fullname == 'retrospective_v2.unlisted':\n"
            "   return importlib.util.spec_from_loader(fullname,Loader())\n"
            "  return None\n"
            "sys.meta_path.append(Finder())\n"
            f"sys.argv=[{os.fspath(self.entrypoint)!r},'--help']\n"
            f"runpy.run_path({os.fspath(self.entrypoint)!r},run_name='__main__')\n",
            encoding="utf-8",
        )

        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-S", os.fspath(wrapper)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assert_authority_rejected(completed)
        self.assertFalse(marker.exists())

    def test_help_validates_schema_v2_startup_receipt(self) -> None:
        marker = self.root / "startup-receipt.json"
        self.instrument_readiness_receipt(marker)

        completed = self.run_entrypoint("--help")

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["ok"])
        receipt = json.loads(marker.read_text(encoding="ascii"))
        self.assertEqual("coordinator_implementation_readiness_v2", receipt["schema"])

    def test_startup_receipt_rejects_launcher_relabel_for_executed_runtime(
        self,
    ) -> None:
        source = self.runtime.read_text(encoding="utf-8")
        binding = (
            '                "session_retrospective_v2_runtime",\n'
            "                entry_name,\n"
        )
        self.assertIn(binding, source)
        self.runtime.write_text(
            source.replace(
                binding,
                '                "session_retrospective_v2",\n'
                "                _BOOTSTRAP_LAUNCHER_NAME,\n",
                1,
            ),
            encoding="utf-8",
        )

        completed = self.run_entrypoint("--help")

        self.assert_authority_rejected(completed)

    def test_successful_runtime_exit_rejects_descriptor_close_failure(self) -> None:
        source = self.runtime.read_text(encoding="utf-8")
        launch = "    try:\n        _cli = _authenticated_cli()\n"
        self.assertIn(launch, source)
        instrumented = source.replace(
            launch,
            "    _test_runtime_descriptor = globals()[\n"
            "        _PRELOADED_ENTRY_ATTRIBUTE\n"
            '    ]["descriptor"]\n'
            "    _test_original_close = os.close\n"
            "    def _test_close(descriptor):\n"
            "        if descriptor == _test_runtime_descriptor:\n"
            '            raise OSError("synthetic runtime descriptor close failure")\n'
            "        return _test_original_close(descriptor)\n"
            "    os.close = _test_close\n" + launch,
            1,
        )
        self.runtime.write_text(instrumented, encoding="utf-8")

        completed = self.run_entrypoint("--help")

        self.assert_authority_rejected(completed)

    def test_startup_receipt_binds_entrypoint_content_and_access_policy(self) -> None:
        marker = self.root / "startup-entry-receipt.json"
        self.instrument_readiness_receipt(marker)
        original = self.runtime.read_bytes()
        original_mode = self.runtime.stat().st_mode & 0o777

        initial = self.run_entrypoint("--help")
        self.assertEqual(0, initial.returncode, initial.stderr)
        initial_receipt = json.loads(marker.read_text(encoding="ascii"))

        self.runtime.write_bytes(original + b"\n# runtime receipt mutation\n")
        changed = self.run_entrypoint("--help")
        self.assertEqual(0, changed.returncode, changed.stderr)
        changed_receipt = json.loads(marker.read_text(encoding="ascii"))
        self.assertNotEqual(
            initial_receipt["source_sha256"], changed_receipt["source_sha256"]
        )
        self.assertNotEqual(
            initial_receipt["authority_sha256"], changed_receipt["authority_sha256"]
        )
        self.assertEqual(
            initial_receipt["access_policy_sha256"],
            changed_receipt["access_policy_sha256"],
        )

        self.runtime.write_bytes(original)
        self.runtime.chmod(0o700 if original_mode != 0o700 else 0o500)
        policy_changed = self.run_entrypoint("--help")
        self.assertEqual(0, policy_changed.returncode, policy_changed.stderr)
        policy_receipt = json.loads(marker.read_text(encoding="ascii"))
        self.assertEqual(
            initial_receipt["source_sha256"], policy_receipt["source_sha256"]
        )
        self.assertNotEqual(
            initial_receipt["access_policy_sha256"],
            policy_receipt["access_policy_sha256"],
        )
        self.assertNotEqual(
            initial_receipt["authority_sha256"],
            policy_receipt["authority_sha256"],
        )

    def test_runtime_replacement_after_capture_fails_closed(self) -> None:
        barrier = self.root / "runtime-captured"
        release = self.root / "runtime-release"
        package_marker = self.root / "package-imported-after-replacement"
        self.add_package_import_marker(package_marker)
        source = self.runtime.read_text(encoding="utf-8")
        needle = "    try:\n        _cli = _authenticated_cli()\n"
        self.assertIn(needle, source)
        instrumented = source.replace(
            needle,
            "    import time as _bootstrap_test_time\n"
            f"    open({os.fspath(barrier)!r}, 'wb').close()\n"
            f"    while not os.path.exists({os.fspath(release)!r}):\n"
            "        _bootstrap_test_time.sleep(0.01)\n" + needle,
            1,
        )
        self.runtime.write_text(instrumented, encoding="utf-8")

        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-B",
                "-S",
                os.fspath(self.entrypoint),
                "--help",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 10
        while not barrier.exists() and process.poll() is None:
            if time.monotonic() >= deadline:
                process.kill()
                process.communicate(timeout=10)
                self.fail("descriptor launcher did not reach the runtime barrier")
            time.sleep(0.01)
        if not barrier.exists():
            stdout, stderr = process.communicate(timeout=10)
            self.fail(
                "descriptor launcher exited before the runtime barrier: "
                + stdout
                + stderr
            )

        retained = self.scripts / "captured-runtime.py"
        replacement = self.scripts / "replacement-runtime.py"
        os.replace(self.runtime, retained)
        replacement.write_text(
            instrumented + "\n# replacement object\n",
            encoding="utf-8",
        )
        os.replace(replacement, self.runtime)
        release.touch()
        stdout, stderr = process.communicate(timeout=30)

        completed = subprocess.CompletedProcess(
            process.args,
            process.returncode,
            stdout,
            stderr,
        )
        self.assert_authority_rejected(completed)
        self.assertFalse(package_marker.exists())

    def test_generated_manifest_is_current(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-S",
                os.fspath(
                    SOURCE_SCRIPTS / "generate_retrospective_v2_bootstrap_manifest.py"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
