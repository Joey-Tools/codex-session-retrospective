from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_test_shard  # noqa: E402


class CiContractTests(unittest.TestCase):
    def test_ci_uses_the_authorized_python_minor(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )

        self.assertEqual(2, workflow.count('python-version: "3.13"'))
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
        self.assertEqual(3, workflow.count("timeout-minutes:"))
        self.assertIn("timeout-minutes: 40", workflow)
        self.assertIn("needs: [contract, test-shard]", workflow)
        self.assertIn('test "${{ needs.test-shard.result }}" = success', workflow)

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
