"""Versioned schema migrations for the Career Twin Core.

The v0.1 database was created by a single ``CREATE TABLE IF NOT EXISTS`` script
plus ad-hoc ``ALTER TABLE`` calls, so nothing recorded *which* structural change
had already been applied. This module introduces ``schema_migrations`` and makes
every further change an explicit, ordered, checksummed step.

Guarantees:

* each migration runs once and is recorded in ``schema_migrations``;
* a consistent SQLite backup is written before the first upgrade of a non-empty
  database, so a failed upgrade can be restored by copying the file back;
* column additions are idempotent, so a partially applied migration can be
  re-run without raising "duplicate column name";
* ``apply`` never deletes or rewrites user rows. Destructive changes are the
  caller's decision, not a side effect of starting the CLI.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

BASELINE = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS career_directions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    experience_ids TEXT NOT NULL,
    output_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    resume_id INTEGER NOT NULL REFERENCES resumes(id),
    status TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    external_reference TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vacancy_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_key TEXT NOT NULL UNIQUE,
    company_norm TEXT NOT NULL,
    title_norm TEXT NOT NULL,
    location_norm TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_group_members (
    job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    group_id INTEGER NOT NULL REFERENCES vacancy_groups(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS application_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    scheduled_at TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_application_events_app ON application_events(application_id, id);
CREATE INDEX IF NOT EXISTS idx_job_group_members_group ON job_group_members(group_id);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    resource TEXT NOT NULL,
    resource_id INTEGER,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""

# --------------------------------------------------------------------------
# v2 · Career Twin Core
# --------------------------------------------------------------------------

CORE_SQL = """
CREATE TABLE IF NOT EXISTS user_assertions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value_json TEXT NOT NULL,
    assertion_type TEXT NOT NULL CHECK (assertion_type IN
        ('fact','preference','value','constraint','skill_hypothesis','career_hypothesis')),
    epistemic_status TEXT NOT NULL CHECK (epistemic_status IN
        ('user_stated','user_confirmed','document_verified','inferred','disputed','retracted')),
    confidence TEXT NOT NULL CHECK (confidence IN ('low','medium','high')),
    source_type TEXT NOT NULL CHECK (source_type IN
        ('user_message','interview','document','experience','feedback','external_source','model_inference','reflection','legacy_profile')),
    source_ref TEXT NOT NULL DEFAULT '',
    explanation TEXT NOT NULL DEFAULT '',
    recorded_at TEXT NOT NULL,
    last_confirmed_at TEXT NOT NULL DEFAULT '',
    valid_from TEXT NOT NULL DEFAULT '',
    valid_to TEXT NOT NULL DEFAULT '',
    supersedes_id INTEGER REFERENCES user_assertions(id),
    superseded_by_id INTEGER REFERENCES user_assertions(id),
    retracted_at TEXT NOT NULL DEFAULT '',
    retract_reason TEXT NOT NULL DEFAULT '',
    dedupe_key TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_assertion_subject ON user_assertions(subject, predicate);
CREATE INDEX IF NOT EXISTS idx_assertion_live ON user_assertions(epistemic_status, valid_to);
CREATE INDEX IF NOT EXISTS idx_assertion_dedupe ON user_assertions(dedupe_key);

CREATE TABLE IF NOT EXISTS assertion_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assertion_id INTEGER NOT NULL REFERENCES user_assertions(id) ON DELETE CASCADE,
    ref_type TEXT NOT NULL CHECK (ref_type IN
        ('assertion','experience','feedback','job','application','goal','action','document','message')),
    ref_id TEXT NOT NULL,
    relation TEXT NOT NULL CHECK (relation IN ('supports','contradicts','derived_from','about')),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assertion_links_owner ON assertion_links(assertion_id, relation);

CREATE TABLE IF NOT EXISTS user_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL CHECK (target_type IN
        ('career_direction','job','goal','action','plan','brief','resume','system')),
    target_id INTEGER NOT NULL,
    feedback_type TEXT NOT NULL CHECK (feedback_type IN
        ('interested','not_interested','applied','declined','corrected','useful','not_useful','accepted','rejected','other')),
    reason TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'user_message',
    scope TEXT NOT NULL DEFAULT 'this_case' CHECK (scope IN ('this_case','general')),
    recorded_at TEXT NOT NULL,
    promoted_assertion_id INTEGER REFERENCES user_assertions(id)
);
CREATE INDEX IF NOT EXISTS idx_user_feedback_target ON user_feedback(target_type, target_id);

CREATE TABLE IF NOT EXISTS career_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction_id INTEGER,
    title TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3,
    status TEXT NOT NULL CHECK (status IN ('exploring','active','paused','achieved','discarded')),
    target_date TEXT NOT NULL DEFAULT '',
    success_criteria_json TEXT NOT NULL DEFAULT '[]',
    time_budget_hours INTEGER,
    owner TEXT NOT NULL DEFAULT 'user' CHECK (owner IN ('user','agent')),
    rationale TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_reviewed_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS job_pipeline (
    job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    discovery_status TEXT NOT NULL CHECK (discovery_status IN
        ('discovered','evaluating','shortlisted','parked','discarded')),
    decision_reason TEXT NOT NULL DEFAULT '',
    priority INTEGER,
    last_checked_at TEXT NOT NULL DEFAULT '',
    next_review_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS next_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN
        ('goal','job','application','learning','interview','reflection','core')),
    source_id INTEGER,
    action_type TEXT NOT NULL CHECK (action_type IN
        ('apply','research','prepare','follow_up','practice','learn','decide','confirm','log_result','other')),
    status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','doing','blocked','done','cancelled')),
    due_at TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 3,
    depends_on_json TEXT NOT NULL DEFAULT '[]',
    suggestion_reason TEXT NOT NULL DEFAULT '',
    requires_approval INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT '',
    completion_evidence TEXT NOT NULL DEFAULT '',
    blocked_reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_next_actions_status ON next_actions(status, due_at);

CREATE TABLE IF NOT EXISTS reflection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    input_event_ids_json TEXT NOT NULL DEFAULT '[]',
    proposed_updates_json TEXT NOT NULL DEFAULT '[]',
    approved_updates_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN
        ('proposed','approved','partially_approved','rejected')),
    created_at TEXT NOT NULL,
    decided_at TEXT NOT NULL DEFAULT ''
);
"""

DECISION_SQL = """
CREATE TABLE IF NOT EXISTS goal_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL REFERENCES career_goals(id),
    revision INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(goal_id, revision)
);
CREATE TABLE IF NOT EXISTS decision_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id INTEGER NOT NULL REFERENCES next_actions(id),
    previous_id INTEGER REFERENCES decision_records(id),
    reason TEXT NOT NULL,
    alternatives_json TEXT NOT NULL,
    factors_json TEXT NOT NULL,
    constraint_checks_json TEXT NOT NULL,
    context_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decision_action ON decision_records(action_id, id);
CREATE TABLE IF NOT EXISTS decision_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER NOT NULL REFERENCES decision_records(id),
    kind TEXT NOT NULL CHECK(kind IN ('accepted','rejected','result','completed')),
    note TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '',
    human_confirmed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decision_events ON decision_events(decision_id, id);
CREATE TRIGGER IF NOT EXISTS decision_records_no_update
BEFORE UPDATE ON decision_records BEGIN SELECT RAISE(ABORT, 'decisions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS decision_events_no_update
BEFORE UPDATE ON decision_events BEGIN SELECT RAISE(ABORT, 'decision events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS goal_revisions_no_update
BEFORE UPDATE ON goal_revisions BEGIN SELECT RAISE(ABORT, 'goal revisions are immutable'); END;
"""

LIBRARY_SQL = """
CREATE TABLE IF NOT EXISTS experience_versions (
    experience_id INTEGER NOT NULL REFERENCES experiences(id),
    version INTEGER NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(experience_id, version)
);
CREATE TABLE IF NOT EXISTS career_settings (
    key TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS search_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    report_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""

# Columns that later migrations added to existing tables. Kept as data so a
# rerun is idempotent even if a previous attempt died between DDL statements.
ADDED_COLUMNS = {
    "applications": {
        "channel": "TEXT NOT NULL DEFAULT ''",
        "apply_url": "TEXT NOT NULL DEFAULT ''",
        "applied_at": "TEXT NOT NULL DEFAULT ''",
    },
    "application_events": {
        "from_status": "TEXT NOT NULL DEFAULT ''",
        "to_status": "TEXT NOT NULL DEFAULT ''",
        "human_confirmed": "INTEGER NOT NULL DEFAULT 0",
        "evidence_ref": "TEXT NOT NULL DEFAULT ''",
    },
    "job_pipeline": {
        "goal_id": "INTEGER REFERENCES career_goals(id)",
    },
    "next_actions": {
        "effort_hours": "INTEGER",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def add_missing_columns(conn) -> list[str]:
    added = []
    for table, columns in ADDED_COLUMNS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if not existing:
            continue
        for name, declaration in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
                added.append(f"{table}.{name}")
    return added


def _seed_goal_history(conn):
    cursor = conn.execute("SELECT * FROM career_goals ORDER BY id")
    names = [description[0] for description in cursor.description]
    for row in cursor.fetchall():
        snapshot = dict(zip(names, row))
        snapshot["success_criteria"] = json.loads(snapshot.pop("success_criteria_json"))
        conn.execute(
            "INSERT OR IGNORE INTO goal_revisions(goal_id,revision,snapshot_json,reason,created_at) "
            "VALUES (?,1,?,?,?)", (snapshot["id"], json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
                                  "schema v4 升级时的目标基线；更早版本未知", _now()))


MIGRATIONS = [
    {"version": 1, "name": "baseline_v0_1", "sql": BASELINE, "post": None},
    {"version": 2, "name": "career_twin_core", "sql": CORE_SQL, "post": add_missing_columns},
    # v3 links the three time scales: a goal owns a job, a job carries effort.
    {"version": 3, "name": "goal_job_action_link", "sql": "SELECT 1;", "post": add_missing_columns},
    {"version": 4, "name": "decision_and_goal_history", "sql": DECISION_SQL, "post": _seed_goal_history},
    {"version": 5, "name": "experience_library_and_search_runs", "sql": LIBRARY_SQL, "post": None},
]


def ensure_table(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "applied_at TEXT NOT NULL, checksum TEXT NOT NULL DEFAULT '')"
    )


def applied_versions(conn) -> list[int]:
    ensure_table(conn)
    return sorted(row[0] for row in conn.execute("SELECT version FROM schema_migrations"))


def current_version(conn) -> int:
    versions = applied_versions(conn)
    return max(versions) if versions else 0


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()[:16]


def _has_user_data(conn) -> bool:
    """A backup of an empty file is noise; a backup of real data is insurance."""
    for table in ("profile", "experiences", "career_directions", "jobs",
                  "applications", "user_assertions", "career_goals", "next_actions", "decision_records",
                  "experience_versions", "career_settings", "search_runs"):
        try:
            if conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                return True
        except sqlite3.OperationalError:
            continue
    return False


def _backup(conn, path: Path, from_version: int) -> str:
    conn.commit()
    target = path.with_name(f"{path.name}.bak-v{from_version}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    # The backup API includes committed WAL pages, unlike copying the main file.
    # Open exclusively so an upgrade never overwrites an earlier restore point.
    with target.open('xb'):
        pass
    try:
        with closing(sqlite3.connect(target)) as backup:
            conn.backup(backup)
            backup.commit()
            if backup.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise OSError('SQLite backup integrity check failed')
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return str(target)


def apply(conn, path: Path | None = None) -> dict:
    """Apply every pending migration. Safe to call on each connection."""
    ensure_table(conn)
    done = applied_versions(conn)
    if not done and conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='experiences'"
    ).fetchone():
        # An existing v0.1 database was created by the baseline script, not by
        # this runner. Record it instead of replaying DDL that already exists.
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version,name,applied_at,checksum) VALUES (?,?,?,?)",
            (1, "baseline_v0_1", _now(), _checksum(BASELINE)),
        )
        conn.commit()
        done = [1]

    pending = [m for m in MIGRATIONS if m["version"] not in done]
    if not pending:
        return {"from": current_version(conn), "to": current_version(conn), "applied": [], "backup": None}

    backup_path = None
    if path is not None and path.exists() and _has_user_data(conn):
        try:
            backup_path = _backup(conn, path, current_version(conn))
        except (OSError, sqlite3.Error) as error:
            raise OSError("Cannot back up existing Oriward data; migration was not started") from error

    applied = []
    for migration in pending:
        try:
            conn.executescript("BEGIN IMMEDIATE;\n" + migration["sql"])
            if migration["post"]:
                migration["post"](conn)
            conn.execute(
                "INSERT INTO schema_migrations(version,name,applied_at,checksum) VALUES (?,?,?,?)",
                (migration["version"], migration["name"], _now(), _checksum(migration["sql"])),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied.append(migration["name"])
    return {"from": min(done) - 1 if done else 0, "to": current_version(conn),
            "applied": applied, "backup": backup_path}
