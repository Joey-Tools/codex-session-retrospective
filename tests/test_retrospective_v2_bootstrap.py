from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
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

        completed = self.run_entrypoint("--help")

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["ok"])
        receipt = json.loads(marker.read_text(encoding="ascii"))
        self.assertEqual("coordinator_implementation_readiness_v2", receipt["schema"])

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
