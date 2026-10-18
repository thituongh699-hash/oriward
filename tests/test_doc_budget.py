"""Keep the documents the Agent actually reads from growing back.

These are budgets, not style rules: they fail only when guidance that is
supposed to stay short becomes long, duplicated or factually stale again.
"""
import re
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
SKILLS = sorted((ROOT / ".agents" / "skills").glob("*/SKILL.md"))
REFERENCES = sorted((ROOT / ".agents" / "skills").glob("*/references/*.md"))
EXCLUDED_PARTS = {".git", ".workbuddy", "outputs", "data"}


def _markdown_files():
    return [path for path in ROOT.rglob("*.md")
            if not any(part in EXCLUDED_PARTS for part in path.parts)]


class DocumentBudgetTests(unittest.TestCase):
    def test_agents_stays_short(self):
        self.assertLessEqual(len(AGENTS.read_text(encoding="utf-8")), 7200)

    def test_each_skill_stays_short(self):
        for path in SKILLS:
            self.assertLessEqual(len(path.read_text(encoding="utf-8")), 4400, str(path))

    def test_skill_bodies_do_not_grow_back(self):
        total = sum(len(path.read_text(encoding="utf-8")) for path in SKILLS)
        self.assertLessEqual(total, 28000, f"nine SKILL.md files total {total} chars")

    def test_no_stale_schema_version(self):
        for path in [AGENTS, *SKILLS, *REFERENCES]:
            self.assertNotIn("schema v2", path.read_text(encoding="utf-8"), str(path))

    def test_commands_are_not_copied_everywhere(self):
        owners = defaultdict(set)
        for path in [AGENTS, *SKILLS, *REFERENCES]:
            text = path.read_text(encoding="utf-8")
            for command in re.findall(r"python -m careeros [a-z-]+(?: [a-z-]+)?", text):
                owners[command].add(str(path))
        crowded = {command: sorted(paths) for command, paths in owners.items() if len(paths) > 3}
        self.assertEqual(crowded, {}, f"commands documented in more than three agent-facing files: {crowded}")

    def test_relative_links_exist(self):
        broken = []
        for path in _markdown_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r"\[[^\]]*\]\(([^)#]+)(?:#[^)]*)?\)", text):
                target = match.group(1).strip()
                if target.startswith(("http", "mailto:", "#")):
                    continue
                if not (path.parent / target).exists():
                    broken.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual(broken, [])


if __name__ == "__main__":
    unittest.main()
