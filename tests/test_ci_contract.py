from __future__ import annotations

import ast
import hashlib
import json
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
import test_inventory  # noqa: E402


SYNTHETIC_SOURCE_SHA256 = "0" * 64


class CiContractTests(unittest.TestCase):
    @staticmethod
    def _write_raw_test_manifest(root: Path, payload: object) -> tuple[Path, Path]:
        encoded = (
            json.dumps(
                payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("ascii")
        manifest = root / "test-manifest.json"
        digest = root / "test-manifest.sha256"
        manifest.write_bytes(encoded)
        digest.write_bytes(hashlib.sha256(encoded).hexdigest().encode("ascii") + b"\n")
        return manifest, digest

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
            '"$RUNNER_TEMP/codex-python/bin/python3" -I -B -S '
            "tests/test_ci_contract.py",
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
        self.assertIn(
            '--manifest "$RUNNER_TEMP/test-inventory/test-manifest.json"', workflow
        )
        self.assertIn(
            '--digest "$RUNNER_TEMP/test-inventory/test-manifest.sha256"', workflow
        )
        self.assertNotIn("\n          python3 -m unittest discover -s tests", workflow)

    def test_ci_shares_one_canonical_inventory_across_every_shard(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        contract_job, remainder = workflow.split("  test-shard:", 1)
        shard_job, _ = remainder.split("\n  darwin-security:", 1)

        self.assertEqual(1, contract_job.count("scripts/test_inventory.py"))
        self.assertNotIn("unittest discover", contract_job)
        self.assertIn("actions/upload-artifact@v4", contract_job)
        self.assertIn("test-manifest.json", contract_job)
        self.assertIn("test-manifest.sha256", contract_job)
        self.assertIn("retention-days: 1", contract_job)
        self.assertIn("needs: contract", shard_job)
        self.assertEqual(1, shard_job.count("actions/download-artifact@v4"))
        self.assertEqual(0, shard_job.count("scripts/test_inventory.py"))
        self.assertIn("scripts/run_test_shard.py", shard_job)
        self.assertEqual(
            2,
            workflow.count("name: canonical-test-inventory-${{ github.sha }}"),
        )
        self.assertLess(
            shard_job.index("actions/download-artifact@v4"),
            shard_job.index("scripts/run_test_shard.py"),
        )

    def test_readme_aggregates_every_shard_exit_status(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertLess(readme.index("set -e"), readme.index("test_ci_contract.py"))
        self.assertLess(
            readme.index("rm -f .codex-tmp/test-inventory/test-manifest.json"),
            readme.index("scripts/test_inventory.py"),
        )
        self.assertIn("shard_failed=0", readme)
        self.assertIn("|| shard_failed=1", readme)
        self.assertIn('test "$shard_failed" -eq 0', readme)

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
            run_darwin_security_tests.DARWIN_SECURITY_ATTRIBUTE,
            test_inventory.DARWIN_SECURITY_ATTRIBUTE,
        )
        self.assertEqual(
            run_darwin_security_tests.EXPECTED_DARWIN_SECURITY_TEST_IDS,
            observed,
        )
        self.assertEqual(15, len(selected))
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
                carries_darwin_marker = any(
                    isinstance(decorator, ast.Name)
                    and decorator.id == "darwin_security_test"
                    for decorator in node.decorator_list
                )
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
                for call in filter(
                    lambda part: isinstance(part, ast.Call), ast.walk(node)
                ):
                    if (
                        isinstance(call.func, ast.Attribute)
                        and isinstance(call.func.value, ast.Name)
                        and call.func.value.id == "self"
                        and call.func.attr == "skipTest"
                        and not carries_darwin_marker
                    ):
                        direct_platform_skips.append(f"{path.name}:{call.lineno}")

        self.assertEqual([], direct_platform_skips)

    def test_darwin_security_result_rejects_skips_and_partial_execution(self) -> None:
        result = unittest.TestResult()
        result.testsRun = 11
        self.assertTrue(
            run_darwin_security_tests.result_is_complete(result, expected_count=11)
        )

        result.skipped.append((self, "missing dependency"))
        self.assertFalse(
            run_darwin_security_tests.result_is_complete(result, expected_count=11)
        )
        result.skipped.clear()
        self.assertFalse(
            run_darwin_security_tests.result_is_complete(result, expected_count=12)
        )

    def test_darwin_security_runner_rejects_hidden_generator_results(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            module_name = "test_darwin_hidden_generator_fixture"
            root.joinpath(f"{module_name}.py").write_text(
                "import unittest\n"
                "def mark(function):\n"
                "    function._codex_darwin_security_contract = True\n"
                "    return function\n"
                "def wrapper(function):\n"
                "    def wrapped(self): return function(self)\n"
                "    return wrapped\n"
                "class HiddenTests(unittest.TestCase):\n"
                "    @mark\n"
                "    @wrapper\n"
                "    def test_hidden(self): yield 'not executed'\n",
                encoding="ascii",
            )
            expected = (f"tests.{module_name}.HiddenTests.test_hidden",)
            try:
                with (
                    mock.patch.object(run_darwin_security_tests, "TEST_ROOT", root),
                    mock.patch.object(
                        run_darwin_security_tests,
                        "EXPECTED_DARWIN_SECURITY_TEST_IDS",
                        expected,
                    ),
                ):
                    selected = (
                        run_darwin_security_tests.discover_darwin_security_tests()
                    )
                result = unittest.TestResult()
                unittest.TestSuite(selected).run(result)
                self.assertEqual(1, len(result.errors))
                self.assertIn("test methods must return None", result.errors[0][1])
                self.assertFalse(
                    run_darwin_security_tests.result_is_complete(
                        result, expected_count=1
                    )
                )
            finally:
                sys.modules.pop(module_name, None)
                while str(root) in sys.path:
                    sys.path.remove(str(root))

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
                if test_inventory.shard_for_test_id(test_id, 4) == shard
            }
            for shard in range(4)
        ]

        self.assertTrue(all(partitions))
        self.assertEqual(set(ids), set().union(*partitions))
        self.assertEqual(len(ids), sum(len(partition) for partition in partitions))
        self.assertEqual(2, test_inventory.shard_for_test_id(ids[0], 4))

    def test_shard_selection_uses_the_captured_test_id_once(self) -> None:
        class StatefulIdCase(unittest.TestCase):
            calls = 0

            def test_value(self) -> None:
                pass

            def id(self) -> str:
                self.calls += 1
                return (
                    "tests.example.Case.test_first"
                    if self.calls == 1
                    else "tests.example.Case.test_changed"
                )

        test = StatefulIdCase("test_value")
        ordered, captured_ids = test_inventory.inventory_from_tests((test,))
        selections = tuple(
            test_inventory.select_test_shard(
                ordered,
                captured_ids,
                shard_index=shard,
                shard_count=4,
            )
            for shard in range(4)
        )

        self.assertEqual(1, test.calls)
        self.assertEqual(1, sum(map(len, selections)))
        self.assertIn(test, tuple(item for shard in selections for item in shard))

    def test_test_shard_rejects_invalid_dimensions(self) -> None:
        for test_id, shard_count in (("", 4), ("test", 1), ("test", 17)):
            with self.subTest(test_id=test_id, shard_count=shard_count):
                with self.assertRaises(ValueError):
                    test_inventory.shard_for_test_id(test_id, shard_count)

    def test_full_inventory_excludes_only_marked_darwin_skips(self) -> None:
        class SyntheticCase(unittest.TestCase):
            def test_regular(self) -> None:
                pass

            @unittest.skip("Darwin security contract")
            def test_darwin(self) -> None:
                pass

            @unittest.skip("ordinary unavailable dependency")
            def test_ordinary_skip(self) -> None:
                pass

        setattr(
            SyntheticCase.test_darwin,
            test_inventory.DARWIN_SECURITY_ATTRIBUTE,
            True,
        )
        selected, _ = test_inventory.inventory_from_tests(
            (
                SyntheticCase("test_regular"),
                SyntheticCase("test_darwin"),
            ),
            platform="linux",
        )
        self.assertEqual(["test_regular"], [test._testMethodName for test in selected])

        with self.assertRaisesRegex(
            test_inventory.TestInventoryError, "skipped test placeholder"
        ):
            test_inventory.inventory_from_tests(
                (SyntheticCase("test_ordinary_skip"),), platform="linux"
            )

    def test_full_shard_result_rejects_skips_and_partial_execution(self) -> None:
        result = unittest.TestResult()
        result.testsRun = 2
        self.assertTrue(run_test_shard.result_is_complete(result, expected_count=2))

        result.skipped.append((self, "synthetic skip"))
        self.assertFalse(run_test_shard.result_is_complete(result, expected_count=2))
        result.skipped.clear()
        self.assertFalse(run_test_shard.result_is_complete(result, expected_count=3))

    def test_source_anchor_rejects_invalid_and_unpackageable_paths(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.joinpath("test_bad-name.py").write_text("", encoding="ascii")
            with self.assertRaisesRegex(
                test_inventory.TestInventoryError, "valid module path"
            ):
                test_inventory.discover_test_sources(root)

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            nested = root / "nested"
            nested.mkdir()
            nested.joinpath("test_nested.py").write_text("", encoding="ascii")
            with self.assertRaisesRegex(
                test_inventory.TestInventoryError, "is not a package"
            ):
                test_inventory.discover_test_sources(root)

    def test_source_anchor_rejects_module_discovery_hooks(self) -> None:
        fixtures = {
            "load_tests": (
                "import unittest\n"
                "class PresentTests(unittest.TestCase):\n"
                "    def test_first(self):\n"
                "        pass\n"
                "    def test_second(self):\n"
                "        pass\n"
                "def load_tests(loader, tests, pattern):\n"
                "    return loader.loadTestsFromName(\n"
                "        'PresentTests.test_first', module=globals()\n"
                "    )\n"
            ),
            "dynamic_getattr": (
                "import unittest\n"
                "class PresentTests(unittest.TestCase):\n"
                "    def test_first(self): pass\n"
                "    def test_second(self): pass\n"
                "def __getattr__(name):\n"
                "    if name == 'load_tests':\n"
                "        return lambda loader, tests, pattern: (\n"
                "            unittest.TestSuite([PresentTests('test_first')])\n"
                "        )\n"
                "    raise AttributeError(name)\n"
            ),
            "dynamic_dir": (
                "import unittest\n"
                "class VisibleTests(unittest.TestCase):\n"
                "    def test_visible(self): pass\n"
                "class HiddenTests(unittest.TestCase):\n"
                "    def test_hidden(self): pass\n"
                "def __dir__():\n"
                "    return ['VisibleTests']\n"
            ),
            "custom_metaclass": (
                "import unittest\n"
                "class HiddenMeta(type):\n"
                "    def __dir__(cls): return []\n"
                "class HiddenTests(unittest.TestCase, metaclass=HiddenMeta):\n"
                "    def test_hidden(self): pass\n"
            ),
            "disabled_method": (
                "import unittest\n"
                "class HiddenTests(unittest.TestCase):\n"
                "    test_hidden = None\n"
            ),
            "callable_descriptor": (
                "import unittest\n"
                "class CallableDescriptor:\n"
                "    def __call__(self): return None\n"
                "    def __get__(self, instance, owner): return self\n"
                "class HiddenTests(unittest.TestCase):\n"
                "    test_hidden = CallableDescriptor()\n"
            ),
            "inherited_generator": (
                "import unittest\n"
                "class GeneratorMixin:\n"
                "    def test_hidden(self):\n"
                "        yield 'not executed'\n"
                "class HiddenTests(GeneratorMixin, unittest.TestCase):\n"
                "    pass\n"
            ),
            "inherited_async": (
                "import unittest\n"
                "class AsyncMixin:\n"
                "    async def test_hidden(self):\n"
                "        return None\n"
                "class HiddenTests(AsyncMixin, unittest.TestCase):\n"
                "    pass\n"
            ),
            "inherited_async_generator": (
                "import unittest\n"
                "class AsyncGeneratorMixin:\n"
                "    async def test_hidden(self):\n"
                "        yield 'not executed'\n"
                "class HiddenTests(AsyncGeneratorMixin, unittest.TestCase):\n"
                "    pass\n"
            ),
            "wrapped_async": (
                "import functools\n"
                "import unittest\n"
                "def sync_wrapper(function):\n"
                "    @functools.wraps(function)\n"
                "    def wrapped(self): return function(self)\n"
                "    return wrapped\n"
                "class HiddenTests(unittest.IsolatedAsyncioTestCase):\n"
                "    @sync_wrapper\n"
                "    async def test_hidden(self): return None\n"
            ),
            "wrapped_generator": (
                "import functools\n"
                "import unittest\n"
                "def sync_wrapper(function):\n"
                "    @functools.wraps(function)\n"
                "    def wrapped(self): return function(self)\n"
                "    return wrapped\n"
                "class HiddenTests(unittest.TestCase):\n"
                "    @sync_wrapper\n"
                "    def test_hidden(self): yield 'not executed'\n"
            ),
            "local_run_test": (
                "import unittest\n"
                "class HiddenTests(unittest.TestCase):\n"
                "    def runTest(self): pass\n"
            ),
        }
        for label, source in fixtures.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                module_name = f"test_anchor_{label}_fixture"
                root.joinpath(f"{module_name}.py").write_text(
                    source,
                    encoding="ascii",
                )
                try:
                    with self.assertRaises(test_inventory.TestInventoryError):
                        test_inventory.discover_test_inventory(root, platform="linux")
                finally:
                    sys.modules.pop(module_name, None)
                    while str(root) in sys.path:
                        sys.path.remove(str(root))

    def test_source_anchor_accepts_isolated_asyncio_test_cases(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            module_name = "test_supported_isolated_asyncio_fixture"
            root.joinpath(f"{module_name}.py").write_text(
                "import unittest\n"
                "class SupportedTests(unittest.IsolatedAsyncioTestCase):\n"
                "    async def test_supported(self):\n"
                "        return None\n",
                encoding="ascii",
            )
            try:
                tests, test_ids, _sources = test_inventory.discover_test_inventory(
                    root, platform="linux"
                )
                self.assertEqual(
                    (f"{module_name}.SupportedTests.test_supported",), test_ids
                )
                result = unittest.TestResult()
                unittest.TestSuite(tests).run(result)
                self.assertTrue(result.wasSuccessful(), result.errors)
            finally:
                sys.modules.pop(module_name, None)
                while str(root) in sys.path:
                    sys.path.remove(str(root))

    def test_source_anchor_rejects_imported_test_cases(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            helper_name = "external_case_fixture"
            module_name = "test_external_case_anchor_fixture"
            root.joinpath(f"{helper_name}.py").write_text(
                "import unittest\n"
                "class ImportedCase(unittest.TestCase):\n"
                "    def test_imported(self): pass\n",
                encoding="ascii",
            )
            root.joinpath(f"{module_name}.py").write_text(
                f"from {helper_name} import ImportedCase\n"
                "import unittest\n"
                "class LocalCase(unittest.TestCase):\n"
                "    def test_local(self): pass\n",
                encoding="ascii",
            )
            try:
                with self.assertRaisesRegex(
                    test_inventory.TestInventoryError, "external TestCase"
                ):
                    test_inventory.discover_test_inventory(root, platform="linux")
            finally:
                sys.modules.pop(module_name, None)
                sys.modules.pop(helper_name, None)
                while str(root) in sys.path:
                    sys.path.remove(str(root))

    def test_source_anchor_rejects_import_time_source_changes(self) -> None:
        fixtures = {
            "created_source": (
                "from pathlib import Path\n"
                "import unittest\n"
                "Path(__file__).with_name('test_created_source_fixture.py').write_text(\n"
                "    'import unittest\\nclass Created(unittest.TestCase):\\n'\n"
                "    '    def test_created(self): pass\\n', encoding='ascii'\n"
                ")\n"
                "class Present(unittest.TestCase):\n"
                "    def test_present(self): pass\n"
            ),
            "changed_content": (
                "from pathlib import Path\n"
                "import unittest\n"
                "source = Path(__file__)\n"
                "source.write_text(source.read_text(encoding='ascii') + '# changed\\n', "
                "encoding='ascii')\n"
                "class Present(unittest.TestCase):\n"
                "    def test_present(self): pass\n"
            ),
        }
        for label, source in fixtures.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                module_name = f"test_{label}_anchor_fixture"
                root.joinpath(f"{module_name}.py").write_text(source, encoding="ascii")
                try:
                    with self.assertRaisesRegex(
                        test_inventory.TestInventoryError,
                        "source inventory changed during discovery",
                    ):
                        test_inventory.discover_test_inventory(root, platform="linux")
                finally:
                    sys.modules.pop(module_name, None)
                    sys.modules.pop("test_created_source_fixture", None)
                    while str(root) in sys.path:
                        sys.path.remove(str(root))

    def test_source_anchor_rejects_imported_run_test_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            helper_name = "external_run_test_fixture"
            module_name = "test_external_run_test_anchor_fixture"
            root.joinpath(f"{helper_name}.py").write_text(
                "import unittest\n"
                "class ImportedRunCase(unittest.TestCase):\n"
                "    def runTest(self): pass\n",
                encoding="ascii",
            )
            root.joinpath(f"{module_name}.py").write_text(
                f"from {helper_name} import ImportedRunCase\n"
                "import unittest\n"
                "class LocalCase(unittest.TestCase):\n"
                "    def test_local(self): pass\n",
                encoding="ascii",
            )
            try:
                with self.assertRaisesRegex(
                    test_inventory.TestInventoryError, "runTest fallback"
                ):
                    test_inventory.discover_test_inventory(root, platform="linux")
            finally:
                sys.modules.pop(module_name, None)
                sys.modules.pop(helper_name, None)
                while str(root) in sys.path:
                    sys.path.remove(str(root))

    def test_source_anchor_fails_runtime_non_none_test_results(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            module_name = "test_non_none_result_anchor_fixture"
            root.joinpath(f"{module_name}.py").write_text(
                "import unittest\n"
                "class HiddenTests(unittest.TestCase):\n"
                "    def test_hidden(self): return 'not executed'\n",
                encoding="ascii",
            )
            try:
                tests, _test_ids, _sources = test_inventory.discover_test_inventory(
                    root, platform="linux"
                )
                result = unittest.TestResult()
                unittest.TestSuite(tests).run(result)
                self.assertEqual(1, len(result.errors))
                self.assertIn("test methods must return None", result.errors[0][1])
            finally:
                sys.modules.pop(module_name, None)
                while str(root) in sys.path:
                    sys.path.remove(str(root))

    def test_source_anchor_is_bounded(self) -> None:
        sources = tuple(
            test_inventory.TestSource(
                f"test_fixture_{index:04d}.py",
                f"test_fixture_{index:04d}",
                SYNTHETIC_SOURCE_SHA256,
            )
            for index in range(test_inventory.MAX_TEST_SOURCE_COUNT + 1)
        )
        with self.assertRaisesRegex(
            test_inventory.TestInventoryError, "count is outside"
        ):
            test_inventory.validate_test_sources(sources)

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.joinpath("fixture-a").write_text("", encoding="ascii")
            root.joinpath("fixture-b").write_text("", encoding="ascii")
            with (
                mock.patch.object(test_inventory, "MAX_SOURCE_TREE_ENTRIES", 1),
                self.assertRaisesRegex(
                    test_inventory.TestInventoryError, "entry limit"
                ),
            ):
                test_inventory.discover_test_sources(root)

    def test_test_manifest_round_trip_is_canonical_and_closed(self) -> None:
        test_ids = (
            "tests.example.Case.test_alpha",
            "tests.example.Case.test_beta",
        )
        test_sources = (
            test_inventory.TestSource(
                "test_example.py", "test_example", SYNTHETIC_SOURCE_SHA256
            ),
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest = root / "test-manifest.json"
            digest = root / "test-manifest.sha256"

            observed_digest = test_inventory.write_test_manifest(
                test_ids, test_sources, manifest, digest
            )

            self.assertEqual(
                (test_ids, test_sources),
                test_inventory.load_test_manifest(manifest, digest),
            )
            self.assertLessEqual(
                len(manifest.read_bytes()), test_inventory.MAX_MANIFEST_BYTES
            )
            self.assertEqual(
                observed_digest.encode("ascii") + b"\n", digest.read_bytes()
            )
            payload = json.loads(manifest.read_text(encoding="ascii"))
            self.assertEqual(
                {"schema", "test_ids", "test_sources"},
                set(payload),
            )
            self.assertEqual(
                {"module", "path", "sha256"}, set(payload["test_sources"][0])
            )

    def test_test_manifest_rejects_wrong_digest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest = root / "test-manifest.json"
            digest = root / "test-manifest.sha256"
            test_inventory.write_test_manifest(
                ("tests.example.Case.test_one",),
                (
                    test_inventory.TestSource(
                        "test_example.py",
                        "test_example",
                        SYNTHETIC_SOURCE_SHA256,
                    ),
                ),
                manifest,
                digest,
            )
            digest.write_bytes(b"0" * 64 + b"\n")

            with self.assertRaisesRegex(
                test_inventory.TestInventoryError, "digest does not match"
            ):
                test_inventory.load_test_manifest(manifest, digest)

    def test_test_manifest_rejects_duplicate_or_unsorted_ids(self) -> None:
        cases = (
            (["tests.Case.test_a", "tests.Case.test_a"], "duplicates"),
            (["tests.Case.test_b", "tests.Case.test_a"], "must be sorted"),
        )
        for test_ids, expected_error in cases:
            with self.subTest(test_ids=test_ids):
                with tempfile.TemporaryDirectory() as raw:
                    manifest, digest = self._write_raw_test_manifest(
                        Path(raw),
                        {
                            "schema": test_inventory.MANIFEST_SCHEMA,
                            "test_ids": test_ids,
                            "test_sources": [
                                {
                                    "module": "test_case",
                                    "path": "test_case.py",
                                    "sha256": SYNTHETIC_SOURCE_SHA256,
                                }
                            ],
                        },
                    )
                    with self.assertRaisesRegex(
                        test_inventory.TestInventoryError, expected_error
                    ):
                        test_inventory.load_test_manifest(manifest, digest)

    def test_test_manifest_rejects_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest, digest = self._write_raw_test_manifest(
                Path(raw),
                {
                    "schema": test_inventory.MANIFEST_SCHEMA,
                    "test_ids": ["tests.Case.test_a"],
                    "test_sources": [
                        {
                            "module": "test_case",
                            "path": "test_case.py",
                            "sha256": SYNTHETIC_SOURCE_SHA256,
                        }
                    ],
                    "unexpected": True,
                },
            )
            with self.assertRaisesRegex(
                test_inventory.TestInventoryError, "closed schema"
            ):
                test_inventory.load_test_manifest(manifest, digest)

    def test_test_inventory_rejects_unittest_failed_test(self) -> None:
        failed = unittest.loader._FailedTest("broken", ImportError("synthetic"))

        with self.assertRaisesRegex(
            test_inventory.TestInventoryError, "unittest _FailedTest"
        ):
            test_inventory.inventory_from_suite(unittest.TestSuite([failed]))

    def test_test_shard_rejects_inventory_divergence_before_selection(self) -> None:
        observed_ids = (
            "tests.example.Case.test_alpha",
            "tests.example.Case.test_beta",
        )
        expected_ids = (
            "tests.example.Case.test_alpha",
            "tests.example.Case.test_gamma",
        )
        sources = (
            test_inventory.TestSource(
                "test_example.py", "test_example", SYNTHETIC_SOURCE_SHA256
            ),
        )
        with (
            mock.patch.object(
                run_test_shard,
                "load_test_manifest",
                return_value=(expected_ids, sources),
            ),
            mock.patch.object(
                run_test_shard,
                "discover_test_inventory",
                return_value=((mock.Mock(), mock.Mock()), observed_ids, sources),
            ),
            mock.patch.object(run_test_shard, "select_test_shard") as select,
            self.assertRaisesRegex(
                SystemExit,
                r"discovery diverges from manifest \(missing=1, unexpected=1\)",
            ),
        ):
            run_test_shard.main(
                [
                    "--shard-index",
                    "0",
                    "--shard-count",
                    "4",
                    "--manifest",
                    "unused.json",
                    "--digest",
                    "unused.sha256",
                    "--list-only",
                ]
            )

        select.assert_not_called()

    def test_test_shard_rejects_source_divergence_before_selection(self) -> None:
        test_ids = (
            "tests.example.Case.test_alpha",
            "tests.example.Case.test_beta",
        )
        observed_sources = (
            test_inventory.TestSource(
                "test_alpha.py", "test_alpha", SYNTHETIC_SOURCE_SHA256
            ),
            test_inventory.TestSource(
                "test_beta.py", "test_beta", SYNTHETIC_SOURCE_SHA256
            ),
        )
        expected_sources = (
            test_inventory.TestSource(
                "test_alpha.py", "test_alpha", SYNTHETIC_SOURCE_SHA256
            ),
            test_inventory.TestSource(
                "test_gamma.py", "test_gamma", SYNTHETIC_SOURCE_SHA256
            ),
        )
        with (
            mock.patch.object(
                run_test_shard,
                "load_test_manifest",
                return_value=(test_ids, expected_sources),
            ),
            mock.patch.object(
                run_test_shard,
                "discover_test_inventory",
                return_value=(
                    (mock.Mock(), mock.Mock()),
                    test_ids,
                    observed_sources,
                ),
            ),
            mock.patch.object(run_test_shard, "select_test_shard") as select,
            self.assertRaisesRegex(
                SystemExit,
                r"source inventory diverges from manifest "
                r"\(missing=1, unexpected=1\)",
            ),
        ):
            run_test_shard.main(
                [
                    "--shard-index",
                    "0",
                    "--shard-count",
                    "4",
                    "--manifest",
                    "unused.json",
                    "--digest",
                    "unused.sha256",
                    "--list-only",
                ]
            )

        select.assert_not_called()

    def test_test_shard_propagates_no_bytecode_to_child_processes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.joinpath("imported.py").write_text("VALUE = 1\n", encoding="ascii")
            child = root / "child.py"
            child.write_text("import imported\n", encoding="ascii")
            with mock.patch.dict(os.environ, {}, clear=True):
                run_test_shard.harden_child_python_environment()
                completed = subprocess.run(
                    [sys.executable, str(child)],
                    cwd=root,
                    env=dict(os.environ),
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertFalse(root.joinpath("__pycache__").exists())

    def test_isolated_shard_cli_is_importable(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-S",
                str(ROOT / "scripts" / "run_test_shard.py"),
                "--help",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("usage:", completed.stdout)
        self.assertIn("--manifest MANIFEST", completed.stdout)
        self.assertIn("--digest DIGEST", completed.stdout)
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
