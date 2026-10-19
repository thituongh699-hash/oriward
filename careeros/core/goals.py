"""Career goals — what the user is actually trying to achieve, and how sure we are.

``owner`` keeps an explicit goal separate from a direction the model merely
suggested: only ``owner='user'`` goals may drive ``priority`` ordering.
Priority 1 is the highest.
"""
from __future__ import annotations

from datetime import datetime

from ..db import audit, connect, now, serialize, deserialize
from .errors import NotFoundError

STATUSES = ("exploring", "active", "paused", "achieved", "discarded")
OPEN_STATUSES = ("exploring", "active", "paused")
OWNERS = ("user", "agent")
_UNSET = object()


def _budget(value):
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                              or not 0 <= value <= 168):
        raise ValueError("time_budget_hours must be between 0 and 168 hours per week, or null")
    return value


def _date(value):
    if not isinstance(value, str):
        raise ValueError("target_date must be an ISO date or datetime")
    if value:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError) as error:
            raise ValueError("target_date must be an ISO date or datetime") from error
    return value


def _save_revision(conn, goal_id: int, reason: str) -> int:
    snapshot = _row(conn.execute("SELECT * FROM career_goals WHERE id=?", (goal_id,)).fetchone())
    revision = conn.execute("SELECT COALESCE(MAX(revision),0)+1 FROM goal_revisions WHERE goal_id=?",
                            (goal_id,)).fetchone()[0]
    conn.execute("INSERT INTO goal_revisions(goal_id,revision,snapshot_json,reason,created_at) VALUES (?,?,?,?,?)",
                 (goal_id, revision, serialize(snapshot), reason, now()))
    return revision


def history(goal_id: int) -> dict:
    with connect() as conn:
        if conn.execute("SELECT 1 FROM career_goals WHERE id=?", (goal_id,)).fetchone() is None:
            raise NotFoundError(f"goal #{goal_id} not found")
        rows = conn.execute("SELECT * FROM goal_revisions WHERE goal_id=? ORDER BY revision", (goal_id,))
        return {"goal_id": goal_id, "versions": [
            {"revision": row["revision"], "snapshot": deserialize(row["snapshot_json"]),
             "reason": row["reason"], "at": row["created_at"]} for row in rows]}


def _check_priority(priority: int) -> int:
    priority = int(priority)
    if not 1 <= priority <= 5:
        raise ValueError("priority must be between 1 (highest) and 5")
    return priority


def add(*, title: str, direction_id: int | None = None, priority: int = 3,
        status: str = "exploring", target_date: str = "", success_criteria=None,
        time_budget_hours: int | None = None, owner: str = "user",
        rationale: str = "") -> dict:
    title = (title or "").strip()
    if not title:
        raise ValueError("title is required")
    if status not in STATUSES:
        raise ValueError("status must be one of " + ", ".join(STATUSES))
    if owner not in OWNERS:
        raise ValueError("owner must be one of " + ", ".join(OWNERS))
    _check_priority(priority)
    if success_criteria is not None and not isinstance(success_criteria, list):
        raise ValueError("success_criteria must be an array")
    _budget(time_budget_hours)
    _date(target_date)
    with connect() as conn:
        if direction_id is not None and conn.execute(
                "SELECT 1 FROM career_directions WHERE id=?", (direction_id,)).fetchone() is None:
            raise NotFoundError(f"career direction #{direction_id} not found")
        cursor = conn.execute(
            "INSERT INTO career_goals(direction_id,title,priority,status,target_date,success_criteria_json,"
            "time_budget_hours,owner,rationale,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (direction_id, title, priority, status, target_date,
             serialize(success_criteria or []), time_budget_hours, owner, rationale, now(), now()),
        )
        goal_id = cursor.lastrowid
        _save_revision(conn, goal_id, rationale or "目标建立")
        audit(conn, "goal.added", "career_goals", goal_id, title[:60])
        return {"id": goal_id, "status": status, "owner": owner}


def list_goals(*, status: str | None = None, limit: int = 50) -> list[dict]:
    clauses, params = [], []
    if status:
        if status not in STATUSES:
            raise ValueError("status must be one of " + ", ".join(STATUSES))
        clauses.append("status=?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM career_goals {where} ORDER BY priority, created_at DESC LIMIT ?",
            params).fetchall()
        return [_row(row) for row in rows]


def _row(row) -> dict:
    data = dict(row)
    data["success_criteria"] = deserialize(data.pop("success_criteria_json", "[]"))
    return data


def get(goal_id: int) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM career_goals WHERE id=?", (goal_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"goal #{goal_id} not found")
        return _row(row)


def update(goal_id: int, *, status: str | None = None, priority: int | None = None,
           target_date: str | None = None, note: str = "", title: str | None = None,
           rationale: str | None = None, success_criteria=None, time_budget_hours=_UNSET,
           direction_id=_UNSET) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM career_goals WHERE id=?", (goal_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"goal #{goal_id} not found")
        if status is not None and status not in STATUSES:
            raise ValueError("status must be one of " + ", ".join(STATUSES))
        new_status = status or row["status"]
        new_priority = _check_priority(priority) if priority is not None else row["priority"]
        new_target = row["target_date"] if target_date is None else _date(target_date)
        new_title = row["title"] if title is None else title.strip()
        if not new_title:
            raise ValueError("title is required")
        new_rationale = row["rationale"] if rationale is None else rationale
        if success_criteria is not None and not isinstance(success_criteria, list):
            raise ValueError("success_criteria must be an array")
        criteria = row["success_criteria_json"] if success_criteria is None else serialize(success_criteria)
        budget = row["time_budget_hours"] if time_budget_hours is _UNSET else _budget(time_budget_hours)
        direction = row["direction_id"] if direction_id is _UNSET else direction_id
        if direction is not None and conn.execute(
                "SELECT 1 FROM career_directions WHERE id=?", (direction,)).fetchone() is None:
            raise NotFoundError(f"career direction #{direction} not found")
        if not note.strip():
            raise ValueError("note is required to explain a goal change")
        if not conn.execute("SELECT 1 FROM goal_revisions WHERE goal_id=?", (goal_id,)).fetchone():
            _save_revision(conn, goal_id, "升级前的目标基线；更早的版本未知")
        conn.execute(
            "UPDATE career_goals SET status=?, priority=?, target_date=?, updated_at=?, "
            "last_reviewed_at=?, title=?, rationale=?, success_criteria_json=?, time_budget_hours=?, "
            "direction_id=? WHERE id=?",
            (new_status, new_priority, new_target, now(), now(), new_title, new_rationale,
             criteria, budget, direction, goal_id),
        )
        revision = _save_revision(conn, goal_id, note.strip())
        audit(conn, "goal.updated", "career_goals", goal_id,
              f"{row['status']}->{new_status} p{row['priority']}->p{new_priority} {note}"[:200])
        return {"id": goal_id, "status": new_status, "priority": new_priority,
                "target_date": new_target, "revision": revision}
