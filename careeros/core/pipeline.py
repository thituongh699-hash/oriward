"""Opportunity pipeline — what the user intends to do with each discovered job.

This is deliberately separate from ``applications``: a job can be researched and
shortlisted long before any resume exists, and "prepared" is never "submitted".
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..db import audit, connect, deserialize, now
from .errors import NotFoundError

STATES = ("discovered", "evaluating", "shortlisted", "parked", "discarded")
TRANSITIONS = {
    "discovered": {"evaluating", "shortlisted", "parked", "discarded"},
    "evaluating": {"shortlisted", "parked", "discarded"},
    "shortlisted": {"evaluating", "parked", "discarded"},
    "parked": {"evaluating", "discarded"},
    "discarded": {"evaluating"},
}
OPEN_STATES = ("discovered", "evaluating", "shortlisted")
#: Application stages are ordered by progress, so the newest row cannot hide a
#: further-along application for the same vacancy.
_STAGE_RANK = {"READY_FOR_USER": 0, "SUBMITTED": 1, "INTERVIEW": 2, "OFFER": 3,
               "ACCEPTED": 4, "REJECTED": 4, "WITHDRAWN": 4, "DECLINED": 4}


def _check_goal(conn, goal_id: int | None) -> None:
    if goal_id is None:
        return
    if conn.execute("SELECT 1 FROM career_goals WHERE id=?", (int(goal_id),)).fetchone() is None:
        raise NotFoundError(f"goal #{goal_id} not found")


def ensure(job_id: int, *, status: str = "discovered", priority: int | None = None,
           reason: str = "", goal_id: int | None = None) -> dict:
    """Create a pipeline row without changing an existing one."""
    if status not in STATES:
        raise ValueError("status must be one of " + ", ".join(STATES))
    with connect() as conn:
        job = conn.execute("SELECT id FROM jobs WHERE id=?", (int(job_id),)).fetchone()
        if job is None:
            raise NotFoundError(f"job #{job_id} not found")
        _check_goal(conn, goal_id)
        existing = conn.execute("SELECT * FROM job_pipeline WHERE job_id=?", (int(job_id),)).fetchone()
        if existing is not None:
            return {"job_id": int(job_id), "created": False, "discovery_status": existing["discovery_status"]}
        conn.execute(
            "INSERT INTO job_pipeline(job_id,discovery_status,decision_reason,priority,last_checked_at,"
            "next_review_at,created_at,updated_at,goal_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (int(job_id), status, reason, priority, now(), "", now(), now(), goal_id),
        )
        audit(conn, "pipeline.created", "job_pipeline", int(job_id), f"{status} {reason}"[:120])
        return {"job_id": int(job_id), "created": True, "discovery_status": status, "goal_id": goal_id}


def update(job_id: int, *, status: str, reason: str = "", priority: int | None = None,
           next_review_at: str | None = None, last_checked_at: str | None = None,
           goal_id: int | None = None) -> dict:
    status = status.strip().lower()
    if status not in STATES:
        raise ValueError("status must be one of " + ", ".join(STATES))
    with connect() as conn:
        _check_goal(conn, goal_id)
        row = conn.execute("SELECT * FROM job_pipeline WHERE job_id=?", (int(job_id),)).fetchone()
        if row is None:
            job = conn.execute("SELECT id FROM jobs WHERE id=?", (int(job_id),)).fetchone()
            if job is None:
                raise NotFoundError(f"job #{job_id} not found")
            conn.execute(
                "INSERT INTO job_pipeline(job_id,discovery_status,decision_reason,priority,last_checked_at,"
                "next_review_at,created_at,updated_at,goal_id) VALUES (?,?,?,?,?,?,?,?,?)",
                (int(job_id), status, reason, priority, now(),
                 next_review_at or "", now(), now(), goal_id),
            )
            audit(conn, "pipeline.created", "job_pipeline", int(job_id), f"{status} {reason}"[:120])
            return {"job_id": int(job_id), "from": None, "to": status, "created": True, "goal_id": goal_id}
        if status != row["discovery_status"] and status not in TRANSITIONS[row["discovery_status"]]:
            raise ValueError(
                f"pipeline transition {row['discovery_status']} -> {status} not allowed; "
                f"allowed: {sorted(TRANSITIONS[row['discovery_status']]) or 'none'}"
            )
        conn.execute(
            "UPDATE job_pipeline SET discovery_status=?, decision_reason=?, priority=?, "
            "next_review_at=?, last_checked_at=?, updated_at=?, goal_id=? WHERE job_id=?",
            (status, reason or row["decision_reason"],
             priority if priority is not None else row["priority"],
             next_review_at if next_review_at is not None else row["next_review_at"],
             last_checked_at or now(), now(),
             goal_id if goal_id is not None else row["goal_id"], int(job_id)),
        )
        audit(conn, "pipeline.updated", "job_pipeline", int(job_id),
              f"{row['discovery_status']}->{status} {reason}"[:160])
        return {"job_id": int(job_id), "from": row["discovery_status"], "to": status,
                "reason": reason, "goal_id": goal_id if goal_id is not None else row["goal_id"]}


def list_pipeline(*, status: str | None = None, include_discarded: bool = False,
                  limit: int = 100) -> list[dict]:
    """Active opportunities by default; discarded rows need an explicit opt-in."""
    clauses, params = [], []
    if status:
        if status not in STATES:
            raise ValueError("status must be one of " + ", ".join(STATES))
        clauses.append("p.discovery_status=?")
        params.append(status)
    elif not include_discarded:
        clauses.append("p.discovery_status!='discarded'")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(
            "SELECT p.*, j.title, j.company, j.url, g.title AS goal_title FROM job_pipeline p "
            "JOIN jobs j ON j.id=p.job_id LEFT JOIN career_goals g ON g.id=p.goal_id "
            f"{where} ORDER BY COALESCE(p.priority,9), p.updated_at DESC LIMIT ?", params).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["applications"] = _applications(conn, row["job_id"])
            result.append(item)
        return result


def counts() -> dict:
    with connect() as conn:
        return {row["discovery_status"]: row["n"] for row in conn.execute(
            "SELECT discovery_status, COUNT(*) AS n FROM job_pipeline GROUP BY discovery_status")}


def _applications(conn, job_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id,status,channel,applied_at,updated_at FROM applications WHERE job_id=? ORDER BY id DESC",
        (job_id,)).fetchall()
    return [dict(row) for row in rows]


def _latest_event(conn, application_id: int):
    """Prefer an event the user confirmed; never label an unverified one as verified."""
    row = conn.execute(
        "SELECT kind,label,COALESCE(NULLIF(occurred_at,''),created_at) AS at,from_status,to_status,"
        "human_confirmed FROM application_events WHERE application_id=? ORDER BY id DESC LIMIT 1",
        (application_id,)).fetchone()
    if row is None or row["human_confirmed"]:
        return row
    verified = conn.execute(
        "SELECT kind,label,COALESCE(NULLIF(occurred_at,''),created_at) AS at,from_status,to_status,"
        "human_confirmed FROM application_events WHERE application_id=? AND human_confirmed=1 "
        "ORDER BY id DESC LIMIT 1", (application_id,)).fetchone()
    return verified or row


def _parse_when(value: str):
    try:
        parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _next_deadline(conn, application_ids: list[int]) -> dict | None:
    if not application_ids:
        return None
    placeholders = ",".join("?" * len(application_ids))
    rows = conn.execute(
        f"SELECT application_id,kind,label,scheduled_at FROM application_events "
        f"WHERE application_id IN ({placeholders}) AND scheduled_at!='' ORDER BY scheduled_at",
        tuple(application_ids)).fetchall()
    reference = _parse_when(now())
    upcoming = []
    for row in rows:
        when = _parse_when(row["scheduled_at"])
        if when is not None and reference is not None and when >= reference:
            upcoming.append((when, dict(row)))
    if not upcoming:
        return None
    upcoming.sort(key=lambda item: item[0])
    return upcoming[0][1]


def show(job_id: int) -> dict:
    """Single-job record: stage, last verified event, next action, deadline, blocker."""
    with connect() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id=?", (int(job_id),)).fetchone()
        if job is None:
            raise NotFoundError(f"job #{job_id} not found")
        job_data = deserialize(job["data"])
        pipeline = conn.execute("SELECT * FROM job_pipeline WHERE job_id=?", (int(job_id),)).fetchone()
        applications = _applications(conn, int(job_id))
        events = []
        for application in applications:
            latest = _latest_event(conn, application["id"])
            if latest:
                events.append({"application_id": application["id"], **dict(latest)})
        actions = [dict(row) for row in conn.execute(
            "SELECT id,title,action_type,status,due_at,priority,requires_approval,blocked_reason "
            "FROM next_actions WHERE source_type='job' AND source_id=? AND status IN ('todo','doing','blocked') "
            "ORDER BY COALESCE(NULLIF(due_at,''),'9999') LIMIT 5", (int(job_id),))]
        deadline = _next_deadline(conn, [a["id"] for a in applications])
        from . import signals
        feedback = signals.open_for(conn, "job", job_id)
        goal_row = None
        if pipeline is not None and pipeline["goal_id"]:
            goal_row = conn.execute(
                "SELECT id,title,priority,owner FROM career_goals WHERE id=?",
                (pipeline["goal_id"],)).fetchone()

    blocker = None
    for action in actions:
        if action["status"] == "blocked":
            blocker = {"action_id": action["id"], "reason": action["blocked_reason"] or "未说明"}
            break
    if blocker is None:
        pending = [a for a in actions if a["requires_approval"]]
        if pending:
            blocker = {"action_id": pending[0]["id"], "reason": "需要用户确认后才能继续"}
    if applications:
        # "Where am I" means the furthest stage reached, not the newest row.
        stage = max(applications, key=lambda item: (_STAGE_RANK.get(item["status"], 0), item["id"]))["status"]
    else:
        discovery_status = pipeline["discovery_status"] if pipeline else "unclassified"
        stage = f"discovery:{discovery_status}"
    return {
        "job": {"id": job["id"], "title": job["title"], "company": job["company"],
                "url": job["url"], "location": job_data.get("location", ""),
                "availability": job_data.get("availability", "unknown")},
        "source": {"job_id": job["id"], "url": job["url"],
                   "availability": job_data.get("availability", "unknown")},
        "pipeline": dict(pipeline) if pipeline else {"discovery_status": "unclassified"},
        "goal": dict(goal_row) if goal_row else None,
        "current_stage": stage,
        "last_verified_event": ({**dict(events[0]), "verified": bool(events[0]["human_confirmed"])}
                                if events else None),
        "next_action": actions[0] if actions else None,
        "deadline": deadline,
        "blocking_issue": blocker,
        "applications": applications,
        "feedback": feedback,
    }
