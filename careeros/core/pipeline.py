"""Opportunity pipeline — what the user intends to do with each discovered job.

This is deliberately separate from ``applications``: a job can be researched and
shortlisted long before any resume exists, and "prepared" is never "submitted".
"""
from __future__ import annotations

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


def ensure(job_id: int, *, status: str = "discovered", priority: int | None = None,
           reason: str = "") -> dict:
    """Create a pipeline row without changing an existing one."""
    if status not in STATES:
        raise ValueError("status must be one of " + ", ".join(STATES))
    with connect() as conn:
        job = conn.execute("SELECT id FROM jobs WHERE id=?", (int(job_id),)).fetchone()
        if job is None:
            raise NotFoundError(f"job #{job_id} not found")
        existing = conn.execute("SELECT * FROM job_pipeline WHERE job_id=?", (int(job_id),)).fetchone()
        if existing is not None:
            return {"job_id": int(job_id), "created": False, "discovery_status": existing["discovery_status"]}
        conn.execute(
            "INSERT INTO job_pipeline(job_id,discovery_status,decision_reason,priority,last_checked_at,"
            "next_review_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (int(job_id), status, reason, priority, now(), "", now(), now()),
        )
        audit(conn, "pipeline.created", "job_pipeline", int(job_id), f"{status} {reason}"[:120])
        return {"job_id": int(job_id), "created": True, "discovery_status": status}


def update(job_id: int, *, status: str, reason: str = "", priority: int | None = None,
           next_review_at: str | None = None, last_checked_at: str | None = None) -> dict:
    status = status.strip().lower()
    if status not in STATES:
        raise ValueError("status must be one of " + ", ".join(STATES))
    with connect() as conn:
        row = conn.execute("SELECT * FROM job_pipeline WHERE job_id=?", (int(job_id),)).fetchone()
        if row is None:
            job = conn.execute("SELECT id FROM jobs WHERE id=?", (int(job_id),)).fetchone()
            if job is None:
                raise NotFoundError(f"job #{job_id} not found")
            conn.execute(
                "INSERT INTO job_pipeline(job_id,discovery_status,decision_reason,priority,last_checked_at,"
                "next_review_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (int(job_id), status, reason, priority, now(),
                 next_review_at or "", now(), now()),
            )
            audit(conn, "pipeline.created", "job_pipeline", int(job_id), f"{status} {reason}"[:120])
            return {"job_id": int(job_id), "from": None, "to": status, "created": True}
        if status != row["discovery_status"] and status not in TRANSITIONS[row["discovery_status"]]:
            raise ValueError(
                f"pipeline transition {row['discovery_status']} -> {status} not allowed; "
                f"allowed: {sorted(TRANSITIONS[row['discovery_status']]) or 'none'}"
            )
        conn.execute(
            "UPDATE job_pipeline SET discovery_status=?, decision_reason=?, priority=?, "
            "next_review_at=?, last_checked_at=?, updated_at=? WHERE job_id=?",
            (status, reason or row["decision_reason"],
             priority if priority is not None else row["priority"],
             next_review_at if next_review_at is not None else row["next_review_at"],
             last_checked_at or now(), now(), int(job_id)),
        )
        audit(conn, "pipeline.updated", "job_pipeline", int(job_id),
              f"{row['discovery_status']}->{status} {reason}"[:160])
        return {"job_id": int(job_id), "from": row["discovery_status"], "to": status,
                "reason": reason}


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
            "SELECT p.*, j.title, j.company, j.url FROM job_pipeline p JOIN jobs j ON j.id=p.job_id "
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
    return conn.execute(
        "SELECT kind,label,COALESCE(NULLIF(occurred_at,''),created_at) AS at,from_status,to_status,"
        "human_confirmed FROM application_events WHERE application_id=? ORDER BY id DESC LIMIT 1",
        (application_id,)).fetchone()


def _next_deadline(conn, application_ids: list[int]) -> dict | None:
    if not application_ids:
        return None
    placeholders = ",".join("?" * len(application_ids))
    row = conn.execute(
        f"SELECT application_id,kind,label,scheduled_at FROM application_events "
        f"WHERE application_id IN ({placeholders}) AND scheduled_at!='' "
        "AND scheduled_at >= ? ORDER BY scheduled_at LIMIT 1",
        (*application_ids, now())).fetchone()
    return dict(row) if row else None


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

    blocker = None
    for action in actions:
        if action["status"] == "blocked":
            blocker = {"action_id": action["id"], "reason": action["blocked_reason"] or "未说明"}
            break
    if blocker is None:
        pending = [a for a in actions if a["requires_approval"]]
        if pending:
            blocker = {"action_id": pending[0]["id"], "reason": "需要用户确认后才能继续"}
    stage = None
    if applications:
        stage = applications[0]["status"]
    return {
        "job": {"id": job["id"], "title": job["title"], "company": job["company"],
                "url": job["url"], "location": job_data.get("location", ""),
                "availability": job_data.get("availability", "unknown")},
        "pipeline": dict(pipeline) if pipeline else {"discovery_status": "unclassified"},
        "current_stage": stage,
        "last_verified_event": events[0] if events else None,
        "next_action": actions[0] if actions else None,
        "deadline": deadline,
        "blocking_issue": blocker,
        "applications": applications,
        "feedback": feedback,
    }
