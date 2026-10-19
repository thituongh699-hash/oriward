"""Keep the documents the Agent actually reads from growing back.

These are budgets, not style rules: they fail only when guidance that is
supposed to stay short becomes long, duplicated or factually stale again.
"""
import json
import re
import unittest
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
SKILLS = sorted((ROOT / ".agents" / "skills").glob("*/SKILL.md"))
REFERENCES = sorted((ROOT / ".agents" / "skills").glob("*/references/*.md"))
EXCLUDED_PARTS = {".git", ".workbuddy", "outputs", "data"}


def _markdown_files():
    return [path for path in ROOT.rglob("*.md")
            if not any(part in EXCLUDED_PARTS for part in path.parts)]


def _heading_anchors(text):
    """GitHub-style anchors for the plain ATX headings used in this repo."""
    anchors = set()
    counts = defaultdict(int)
    for heading in re.findall(r"(?m)^#{1,6}\s+(.+?)\s*#*\s*$", text):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        number = counts[slug]
        counts[slug] += 1
        anchors.add(f"{slug}-{number}" if number else slug)
    return anchors


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
            for command in re.findall(r"python -m oriward [a-z-]+(?: [a-z-]+)?", text):
                owners[command].add(str(path))
        crowded = {command: sorted(paths) for command, paths in owners.items() if len(paths) > 3}
        self.assertEqual(crowded, {}, f"commands documented in more than three agent-facing files: {crowded}")

    def test_relative_links_exist(self):
        broken = []
        for path in _markdown_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", text):
                target = match.group(1).strip()
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc:
                    continue
                destination = path.parent / unquote(parsed.path) if parsed.path else path
                if not destination.is_file():
                    broken.append(f"{path.relative_to(ROOT)} -> {target}")
                elif parsed.fragment and destination.suffix == ".md":
                    anchors = _heading_anchors(destination.read_text(encoding="utf-8"))
                    if unquote(parsed.fragment) not in anchors:
                        broken.append(f"{path.relative_to(ROOT)} -> missing heading {target}")
        self.assertEqual(broken, [])

    def test_json_examples_are_parseable(self):
        """Copied input examples must use the same strict JSON syntax as CLI files."""
        for path in _markdown_files():
            for number, block in enumerate(re.findall(
                    r"(?ms)^```json\s*\n(.*?)^```", path.read_text(encoding="utf-8")), 1):
                with self.subTest(path=str(path.relative_to(ROOT)), example=number):
                    json.loads(block)

    def test_documented_script_paths_exist(self):
        """Entrypoints documented as repository-root commands must be executable files."""
        for path in _markdown_files():
            for script in re.findall(
                    r"\b(?:python|node)\s+([^\s`]+\.(?:py|mjs))(?=\s|`|$)",
                    path.read_text(encoding="utf-8")):
                with self.subTest(document=str(path.relative_to(ROOT)), script=script):
                    self.assertTrue((ROOT / script).is_file(), script)


if __name__ == "__main__":
    unittest.main()
