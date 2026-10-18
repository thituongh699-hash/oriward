from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = {
    "career-discovery", "career-mapping", "job-search", "job-analysis",
    "resume-builder", "application-assistant", "learning-planner", "interview-coach"
}


class SkillManifestTests(unittest.TestCase):
    def test_exactly_eight_discoverable_skills(self):
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

    def test_every_skill_declares_core_contract(self):
        folder = ROOT / ".agents" / "skills"
        for skill in SKILLS:
            content = (folder / skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("Career Twin Core contract", content, skill)


if __name__ == "__main__":
    unittest.main()
