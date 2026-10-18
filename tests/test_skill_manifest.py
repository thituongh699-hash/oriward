from pathlib import Path
import contextlib
import io
import re
import unittest

from careeros import cli

ROOT = Path(__file__).resolve().parents[1]
SKILLS = {
    "career-discovery", "career-mapping", "job-search", "job-analysis",
    "resume-builder", "application-assistant", "learning-planner", "interview-coach", "document-export"
}


class SkillManifestTests(unittest.TestCase):
    def test_discoverable_career_and_document_skills(self):
        folder = ROOT / ".agents" / "skills"
        found = {p.parent.name for p in folder.glob("*/SKILL.md")}
        self.assertEqual(found, SKILLS)
        for skill in found:
            content = (folder / skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(content.startswith("---\n"), skill)
            self.assertRegex(content, r"(?m)^name: " + re.escape(skill) + r"$")
            match = re.search(r"(?m)^description: (.+)$", content)
            self.assertIsNotNone(match, skill)
            self.assertGreater(len(match.group(1)), 40)

    def test_privacy_paths_ignored(self):
        content = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/data/private/", content)
        self.assertIn("/outputs/", content)

    def test_global_rules_cover_submission(self):
        content = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("--human-confirmed", content)
        self.assertIn("untrusted data", content)

    def test_global_rules_route_through_career_twin_core(self):
        content = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("context brief", content)
        self.assertIn("belief confirm", content)
        self.assertIn("signal promote", content)

    def test_every_career_skill_declares_core_contract(self):
        folder = ROOT / ".agents" / "skills"
        for skill in SKILLS - {"document-export"}:
            content = (folder / skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("Career Twin Core contract", content, skill)

    def test_documented_commands_exist(self):
        """Every `python -m careeros ...` in a skill must at least parse."""
        pattern = re.compile(r"python -m careeros ([a-z][a-z-]*)(?: ([a-z][a-z-]*))?")
        folder = ROOT / ".agents" / "skills"
        commands = set()
        for skill in SKILLS:
            content = (folder / skill / "SKILL.md").read_text(encoding="utf-8")
            commands.update(tuple(match.groups()) for match in pattern.finditer(content))
        self.assertTrue(commands)
        for domain, action in sorted(commands):
            argv = [domain] + ([action] if action else []) + ["--help"]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exit_code:
                    cli.run(argv)
            self.assertEqual(exit_code.exception.code, 0,
                             f"{domain} {action or ''} is documented but not a valid command")

    def test_document_export_is_conversion_only(self):
        content = (ROOT / ".agents" / "skills" / "document-export" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("Career Twin Core contract", content)
        self.assertIn("does not create or change any CareerOS record", content)
        self.assertNotIn("hash", content.lower())


if __name__ == "__main__":
    unittest.main()
