from __future__ import annotations

import ast
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ci_runtime  # noqa: E402
import run_test_shard  # noqa: E402
import run_darwin_security_tests  # noqa: E402


class CiContractTests(unittest.TestCase):
    def test_review_gate_pins_the_audited_action_commit(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "codex-review-gate.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "uses: JoeyTeng/codex-review-gate-action@"
            "2a7f9d8cd98f90cb56dc1540bf54d9dc7484afc6",
            workflow,
        )
        self.assertNotIn("codex-review-gate-action@v1", workflow)

    def test_ci_uses_the_authorized_python_minor(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )

        self.assertEqual(3, workflow.count('python-version: "3.13"'))
        self.assertNotIn('python-version: "3.x"', workflow)
        self.assertIn(
            'python3 -I -B -S -m venv --copies "$RUNNER_TEMP/codex-python"',
            workflow,
        )
        self.assertIn('chmod 0755 "$RUNNER_TEMP/codex-python/bin/python3"', workflow)
        self.assertIn(
            '"$RUNNER_TEMP/codex-python/bin/python3" -I -B -S -m unittest discover \\\n'
            "            -s tests -p test_ci_contract.py",
            workflow,
        )
        self.assertIn("shard: [0, 1, 2, 3]", workflow)
        self.assertIn("fail-fast: false", workflow)
        self.assertIn(
            '"$RUNNER_TEMP/codex-python/bin/python3" -I -B -S '
            "scripts/run_test_shard.py \\",
            workflow,
        )
        self.assertIn('--shard-index "${{ matrix.shard }}" --shard-count 4', workflow)
        self.assertNotIn("\n          python3 -m unittest discover -s tests", workflow)

    def test_ci_has_bounded_parallel_lifecycle(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "group: ${{ github.workflow }}-"
            "${{ github.event.pull_request.number || github.ref }}",
            workflow,
        )
        self.assertIn("cancel-in-progress: true", workflow)
        self.assertEqual(4, workflow.count("timeout-minutes:"))
        self.assertIn("timeout-minutes: 40", workflow)
        self.assertIn("needs: [contract, test-shard, darwin-security]", workflow)
        self.assertIn('test "${{ needs.test-shard.result }}" = success', workflow)
        self.assertIn('test "${{ needs.darwin-security.result }}" = success', workflow)

    def test_ci_runs_the_closed_darwin_security_inventory(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        selected = run_darwin_security_tests.discover_darwin_security_tests()
        observed = tuple(
            test.id() if test.id().startswith("tests.") else f"tests.{test.id()}"
            for test in selected
        )
        self.assertEqual(
            run_darwin_security_tests.EXPECTED_DARWIN_SECURITY_TEST_IDS,
            observed,
        )
        self.assertEqual(10, len(selected))
        with (
            mock.patch.object(
                run_darwin_security_tests,
                "EXPECTED_DARWIN_SECURITY_TEST_IDS",
                observed[:-1],
            ),
            self.assertRaisesRegex(RuntimeError, "does not match policy"),
        ):
            run_darwin_security_tests.discover_darwin_security_tests()
        self.assertIn("darwin-security:", workflow)
        self.assertIn("runs-on: macos-15", workflow)
        self.assertIn("timeout-minutes: 15", workflow)
        self.assertIn("scripts/run_darwin_security_tests.py", workflow)

    def test_darwin_security_inventory_cannot_bypass_the_shared_marker(self) -> None:
        direct_platform_skips: list[str] = []
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in node.decorator_list:
                    if (
                        isinstance(decorator, ast.Call)
                        and isinstance(decorator.func, ast.Attribute)
                        and isinstance(decorator.func.value, ast.Name)
                        and decorator.func.value.id == "unittest"
                        and decorator.func.attr in {"skipIf", "skipUnless"}
                        and any(
                            isinstance(part, ast.Constant) and part.value == "darwin"
                            for part in ast.walk(decorator)
                        )
                    ):
                        direct_platform_skips.append(f"{path.name}:{node.lineno}")

        self.assertEqual([], direct_platform_skips)

    def test_darwin_security_result_rejects_skips_and_partial_execution(self) -> None:
        result = unittest.TestResult()
        result.testsRun = 10
        self.assertTrue(
            run_darwin_security_tests.result_is_complete(result, expected_count=10)
        )

        result.skipped.append((self, "missing dependency"))
        self.assertFalse(
            run_darwin_security_tests.result_is_complete(result, expected_count=10)
        )
        result.skipped.clear()
        self.assertFalse(
            run_darwin_security_tests.result_is_complete(result, expected_count=11)
        )

    def test_ci_runtime_admission_rejects_writable_or_linked_python(self) -> None:
        ci_runtime.require_owner_controlled_python()
        with tempfile.TemporaryDirectory(dir=ROOT) as raw:
            executable = Path(raw) / "python3"
            executable.write_bytes(b"synthetic executable")
            executable.chmod(0o755)
            ci_runtime.require_owner_controlled_python(executable)

            executable.chmod(0o775)
            with self.assertRaisesRegex(ci_runtime.CiRuntimeError, "group/world"):
                ci_runtime.require_owner_controlled_python(executable)
            executable.chmod(0o755)
            os.link(executable, Path(raw) / "second-link")
            with self.assertRaisesRegex(ci_runtime.CiRuntimeError, "one link"):
                ci_runtime.require_owner_controlled_python(executable)

    def test_test_ids_partition_exactly_once(self) -> None:
        ids = [f"tests.example.Case.test_{index:04d}" for index in range(256)]
        partitions = [
            {
                test_id
                for test_id in ids
                if run_test_shard.shard_for_test_id(test_id, 4) == shard
            }
            for shard in range(4)
        ]

        self.assertTrue(all(partitions))
        self.assertEqual(set(ids), set().union(*partitions))
        self.assertEqual(len(ids), sum(len(partition) for partition in partitions))
        self.assertEqual(2, run_test_shard.shard_for_test_id(ids[0], 4))

    def test_test_shard_rejects_invalid_dimensions(self) -> None:
        for test_id, shard_count in (("", 4), ("test", 1), ("test", 17)):
            with self.subTest(test_id=test_id, shard_count=shard_count):
                with self.assertRaises(ValueError):
                    run_test_shard.shard_for_test_id(test_id, shard_count)

    def test_isolated_shard_discovery_is_importable(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-S",
                str(ROOT / "scripts" / "run_test_shard.py"),
                "--shard-index",
                "0",
                "--shard-count",
                "4",
                "--list-only",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertRegex(
            completed.stdout,
            r"\ASelected [1-9][0-9]* of [1-9][0-9]* tests for shard 0/4\n\Z",
        )
        self.assertEqual("", completed.stderr)

    def test_ci_runtime_is_owner_controlled(self) -> None:
        executable = Path(sys.executable)
        metadata = executable.lstat()

        self.assertEqual((3, 13), sys.version_info[:2])
        self.assertEqual(1, sys.flags.no_site)
        self.assertEqual(1, sys.flags.dont_write_bytecode)
        self.assertTrue(executable.is_absolute())
        self.assertEqual(executable, Path(os.path.realpath(executable)))
        self.assertTrue(stat.S_ISREG(metadata.st_mode))
        self.assertEqual(os.geteuid(), metadata.st_uid)
        self.assertFalse(stat.S_IMODE(metadata.st_mode) & 0o022)
        self.assertEqual(1, metadata.st_nlink)


if __name__ == "__main__":
    unittest.main()
