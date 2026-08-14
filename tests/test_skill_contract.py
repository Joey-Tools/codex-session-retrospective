from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    def test_repository_root_is_the_skill_root(self) -> None:
        self.assertTrue((ROOT / "SKILL.md").is_file())
        self.assertTrue((ROOT / "agents" / "openai.yaml").is_file())
        self.assertTrue((ROOT / "scripts" / "session_retrospective_v2.py").is_file())
        self.assertFalse((ROOT / "skills" / "codex-session-retrospective").exists())

    def test_skill_requires_explicit_invocation(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        interface = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        frontmatter = skill.split("---", 2)[1]

        self.assertIn(
            "Use only when the user explicitly invokes $codex-session-retrospective.",
            frontmatter,
        )
        self.assertIn(
            "Use this skill only when the user explicitly invokes "
            "`$codex-session-retrospective`",
            skill,
        )
        self.assertIn("policy:\n  allow_implicit_invocation: false\n", interface)
        self.assertNotIn("allow_implicit_invocation: true", interface)

    def test_operator_output_is_bounded(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("task-scoped ignored log", skill)
        self.assertIn("progress markers", skill)
        self.assertIn("do not poll with 30k+ visible output caps", skill)
        self.assertIn("`pgrep -af`", skill)
        self.assertIn("`ps -p`", skill)
        self.assertIn("`ps -eo` / `ps -axo`", skill)
        self.assertIn("full `sample` output", skill)

    def test_public_coordinator_requires_isolated_python(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cli_reference = (ROOT / "references" / "v2-cli.md").read_text(encoding="utf-8")

        self.assertIn("`python3 -I -B -S`", skill)
        self.assertIn("python3 -I -B -S", readme)
        self.assertNotIn('python3 "$V2_CLI"', cli_reference)
        self.assertEqual(11, cli_reference.count('python3 -I -B -S "$V2_CLI"'))

    def test_references_and_entry_points_exist(self) -> None:
        for name in (
            "v2-agent-prompts.md",
            "v2-cli.md",
            "v2-data-contract.md",
            "v2-engine-architecture.md",
            "v2-recovery.md",
            "v2-shadow-cutover.md",
        ):
            with self.subTest(name=name):
                self.assertTrue((ROOT / "references" / name).is_file())

        for name in (
            "session_retrospective.py",
            "session_retrospective_v2.py",
            "session_retrospective_v2_export.py",
            "session_retrospective_v2_export_records.py",
            "session_retrospective_v2_transcript.py",
        ):
            with self.subTest(name=name):
                self.assertTrue((ROOT / "scripts" / name).is_file())


if __name__ == "__main__":
    unittest.main()
