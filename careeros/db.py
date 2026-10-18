"""SQLite repository; personal data is stored outside version control.

Structural changes live in :mod:`careeros.migrations`. This module only opens
connections and exposes tiny shared helpers, so a skill never has to know which
schema version the local database is at.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import migrations

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Baseline DDL, kept as an alias for callers that create a schema by hand.
SCHEMA = migrations.BASELINE
#: Backwards-compatible alias: column additions are now a v2 migration step.
ADDED_COLUMNS = migrations.ADDED_COLUMNS


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def database_path() -> Path:
    value = os.environ.get("CAREEROS_DB")
    return Path(value).expanduser().resolve() if value else PROJECT_ROOT / "data" / "private" / "careeros.sqlite3"


def migrate(connection) -> None:
    """Idempotent schema upgrade; returns nothing for legacy callers."""
    migrations.apply(connection, database_path())


@contextmanager
def connect():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    try:
        connection.executescript(SCHEMA)
        migrations.apply(connection, path)
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def serialize(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def deserialize(value: str):
    return json.loads(value)


def audit(conn, kind: str, resource: str, resource_id: int | None = None, detail: str = ""):
    conn.execute(
        "INSERT INTO audit_events(kind,resource,resource_id,detail,created_at) VALUES (?,?,?,?,?)",
        (kind, resource, resource_id, detail[:200], now()),
    )


_ALLOWED_TABLES = {
    "experiences", "career_directions", "jobs", "job_analyses", "resumes", "applications",
    "learning_plans", "interviews",
    "user_assertions", "assertion_links", "user_feedback", "career_goals",
    "job_pipeline", "next_actions", "reflection_runs", "application_events",
}


def one(conn, table: str, row_id: int):
    if table not in _ALLOWED_TABLES:
        raise ValueError("Unknown table")
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
    if row is None:
        raise ValueError(f"{table} ID={row_id} not found")
    return row
