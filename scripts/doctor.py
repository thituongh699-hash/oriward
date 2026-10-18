"""Run with `python scripts/doctor.py` from project root."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    print("CareerOS environment check")
    print("Python:", sys.version.split()[0], "(requires >=3.10)")
    print("Codex CLI:", shutil.which("codex") or "NOT FOUND (install/login separately, or use Codex IDE)")
    print("Project AGENTS.md:", (ROOT / "AGENTS.md").is_file())
    skills = list((ROOT / ".agents" / "skills").glob("*/SKILL.md"))
    print("Skills count:", len(skills), "(expected 8)")
    print("Data path (default):", ROOT / "data" / "private" / "careeros.sqlite3")
    if sys.version_info < (3, 10) or len(skills) != 8:
        raise SystemExit("Environment not ready")
    print("Ready for `python -m careeros init` (Codex authentication not verified)")


if __name__ == "__main__":
    main()
