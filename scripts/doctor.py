"""Run with `python scripts/doctor.py` from project root."""
from __future__ import annotations

import sys
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    print("CareerOS environment check")
    print("Python:", sys.version.split()[0], "(requires >=3.10)")
    print("Interpreter:", sys.executable)
    print("SQLite:", sqlite3.sqlite_version)
    print("Agent: use your chosen LLM-backed tool; no vendor-specific CLI is required")
    print("Agent capabilities: local file access and command execution, or user-assisted execution (not verified)")
    print("Project AGENTS.md:", (ROOT / "AGENTS.md").is_file())
    skills = list((ROOT / ".agents" / "skills").glob("*/SKILL.md"))
    print("Skills count:", len(skills), "(expected 9: eight career workflows plus document export)")
    print("Data path (default):", ROOT / "data" / "private" / "careeros.sqlite3")
    if sys.version_info < (3, 10) or len(skills) != 9:
        raise SystemExit("Environment not ready")
    print("Ready for `python -m careeros init` (Agent access and model connection not verified)")


if __name__ == "__main__":
    main()
