"""User feedback signals — the mechanism that makes the Twin learn.

A reaction is recorded *where it happened* (``scope='this_case'``) before it is
allowed to say anything about the person. Rejecting one job because it requires
constant travel is evidence about that job, not a permanent personality trait;
it becomes a standing constraint only through an explicit ``promote`` call.
"""
from __future__ import annotations

from ..db import audit, connect, now
from . import assertions
from .errors import NotFoundError

TARGET_TYPES = (
    "career_direction", "job", "goal", "action", "plan", "brief", "resume", "system",
)
FEEDBACK_TYPES = (
    "interested", "not_interested", "applied", "declined", "corrected",
    "useful", "not_useful", "accepted", "rejected", "other",
)
SCOPES = ("this_case", "general")

#: Target types that must point at a stored row. A reaction to a job that does
#: not exist is not evidence, and would later support a fabricated constraint.
_TARGET_TABLES = {
    "career_direction": "career_directions", "job": "jobs", "goal": "career_goals",
    "action": "next_actions", "plan": "learning_plans", "resume": "resumes",
}

_COLUMNS = ("id", "target_type", "target_id", "feedback_type", "reason", "source",
            "scope", "recorded_at", "promoted_assertion_id")


def add(*, target_type: str, target_id: int, feedback_type: str, reason: str = "",
        source: str = "user_message", scope: str = "this_case", at: str | None = None) -> dict:
    if target_type not in TARGET_TYPES:
        raise ValueError("target_type must be one of " + ", ".join(TARGET_TYPES))
    if feedback_type not in FEEDBACK_TYPES:
        raise ValueError("feedback_type must be one of " + ", ".join(FEEDBACK_TYPES))
    if scope not in SCOPES:
        raise ValueError("scope must be one of " + ", ".join(SCOPES))
    with connect() as conn:
        table = _TARGET_TABLES.get(target_type)
        if table and conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (int(target_id),)).fetchone() is None:
            raise NotFoundError(
                f"{target_type} #{target_id} does not exist; record the reaction against a stored object"
            )
        cursor = conn.execute(
            "INSERT INTO user_feedback(target_type,target_id,feedback_type,reason,source,scope,recorded_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (target_type, int(target_id), feedback_type, reason.strip(), source, scope, at or now()),
        )
        feedback_id = cursor.lastrowid
        audit(conn, "feedback.added", "user_feedback", feedback_id,
              f"{target_type}:{target_id} {feedback_type}")
    result = {"id": feedback_id, "scope": scope, "promoted": False}
    if scope == "this_case" and feedback_type in ("not_interested", "declined", "rejected"):
        result["hint"] = ("这是针对该对象的一次观察，尚未成为长期偏好；"
                          "如果它适用于所有同类机会，运行 signal promote --id "
                          f"{feedback_id}")
    return result


def list_feedback(*, target_type: str | None = None, target_id: int | None = None,
                  limit: int = 50) -> list[dict]:
    clauses, params = [], []
    if target_type:
        clauses.append("target_type=?")
        params.append(target_type)
    if target_id is not None:
        clauses.append("target_id=?")
        params.append(int(target_id))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {','.join(_COLUMNS)} FROM user_feedback {where} ORDER BY id DESC LIMIT ?",
            params).fetchall()
        return [dict(row) for row in rows]


def promote(feedback_id: int, *, subject: str = "work_conditions", predicate: str = "hard_constraint",
            assertion_type: str = "constraint", confidence: str = "medium",
            value: str | None = None, explanation: str = "",
            human_confirmed: bool = False) -> dict:
    """Turn one situational observation into a standing rule, on request only.

    A single reaction must never become a permanent trait on the Agent's say-so,
    so promoting requires an explicit user confirmation, just like recording a
    submission or completing an approval-gated action.
    """
    if not human_confirmed:
        raise ValueError(
            "promoting one reaction into a standing constraint requires the user's explicit "
            "confirmation (--human-confirmed); keep it case-scoped for now"
        )
    with connect() as conn:
        row = conn.execute("SELECT * FROM user_feedback WHERE id=?", (feedback_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"feedback #{feedback_id} not found")
        if row["promoted_assertion_id"]:
            raise ValueError(f"feedback #{feedback_id} already promoted to assertion #{row['promoted_assertion_id']}")
        reason = row["reason"] or row["feedback_type"]
        text = (value or reason).strip()
        case = {"target_type": row["target_type"], "target_id": row["target_id"]}

    assertion_type = assertion_type if assertion_type in ("constraint", "preference", "value") else "constraint"
    payload = {"text": text, "from_feedback": int(feedback_id), "case": case}
    created = assertions.propose(
        subject=subject, predicate=predicate, value=payload, assertion_type=assertion_type,
        source_type="feedback", confidence=confidence,
        source_ref=f"user_feedback:{feedback_id}",
        explanation=explanation or "由一次具体反馈推广而来，需用户确认后生效",
        links=[{"ref_type": "feedback", "ref_id": feedback_id, "relation": "supports"}],
    )
    with connect() as conn:
        conn.execute("UPDATE user_feedback SET promoted_assertion_id=?, scope='general' WHERE id=?",
                     (created["id"], feedback_id))
        audit(conn, "feedback.promoted", "user_feedback", feedback_id, f"-> assertion {created['id']}")
    return {"feedback_id": feedback_id, "assertion_id": created["id"], "created": created["created"],
            "epistemic_status": created["epistemic_status"], "confirmed": True,
            "hint": "该偏好已按用户确认写入长期约束；如需改口，使用 belief revise 或 belief retract"}


def open_for(conn, target_type: str, target_id: int, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        f"SELECT {','.join(_COLUMNS)} FROM user_feedback WHERE target_type=? AND target_id=? "
        "ORDER BY id DESC LIMIT ?",
        (target_type, int(target_id), limit)).fetchall()
    return [dict(row) for row in rows]
