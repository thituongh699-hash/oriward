"""Next actions and an *explainable* ranking.

The score is a documented, additive heuristic — never a probability of success.
Every ranked action carries the factors that produced its position, so the model
can say why it suggests it and the user can disagree with one factor instead of
the whole list.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..db import audit, connect, deserialize, now, serialize
from .errors import NotFoundError

SOURCE_TYPES = ("goal", "job", "application", "learning", "interview", "reflection", "core")
ACTION_TYPES = ("apply", "research", "prepare", "follow_up", "practice", "learn",
                "decide", "confirm", "log_result", "other")
STATUSES = ("todo", "doing", "blocked", "done", "cancelled")
OPEN = ("todo", "doing", "blocked")

#: Points contributed by the kind of object the action belongs to.
SOURCE_WEIGHT = {"interview": 25, "application": 20, "goal": 15, "job": 12,
                 "learning": 8, "reflection": 5, "core": 3}
#: Points contributed by proximity of the deadline.
URGENCY_STEPS = ((0, 50), (1, 40), (3, 30), (7, 20), (14, 10), (30, 4))


def _parse(value: str):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _urgency(due_at: str, reference: datetime) -> tuple[int, int | None]:
    due = _parse(due_at)
    if due is None:
        return 0, None
    days = (due - reference).total_seconds() / 86400
    if days < 0:
        return 60, int(days)
    for limit, points in URGENCY_STEPS:
        if days <= limit:
            return points, int(days)
    return 2, int(days)


def propose(*, title: str, source_type: str, source_id: int | None = None,
            action_type: str = "other", due_at: str = "", priority: int = 3,
            depends_on=None, suggestion_reason: str = "",
            requires_approval: bool = False) -> dict:
    title = (title or "").strip()
    if not title:
        raise ValueError("title is required")
    if source_type not in SOURCE_TYPES:
        raise ValueError("source_type must be one of " + ", ".join(SOURCE_TYPES))
    if action_type not in ACTION_TYPES:
        raise ValueError("action_type must be one of " + ", ".join(ACTION_TYPES))
    priority = int(priority)
    if not 1 <= priority <= 5:
        raise ValueError("priority must be between 1 (highest) and 5")
    if not suggestion_reason.strip():
        raise ValueError("suggestion_reason is required: an action must explain why it exists")
    depends = depends_on or []
    if not isinstance(depends, list):
        raise ValueError("depends_on must be an array of action ids")
    with connect() as conn:
        for dep in depends:
            if conn.execute("SELECT 1 FROM next_actions WHERE id=?", (int(dep),)).fetchone() is None:
                raise ValueError(f"depends_on references unknown action #{dep}")
        cursor = conn.execute(
            "INSERT INTO next_actions(title,source_type,source_id,action_type,status,due_at,priority,"
            "depends_on_json,suggestion_reason,requires_approval,created_at) VALUES (?,?,?,?,'todo',?,?,?,?,?,?)",
            (title, source_type, source_id, action_type, due_at, priority,
             serialize([int(x) for x in depends]), suggestion_reason.strip(),
             1 if requires_approval else 0, now()),
        )
        action_id = cursor.lastrowid
        audit(conn, "action.proposed", "next_actions", action_id, title[:80])
        return {"id": action_id, "status": "todo", "requires_approval": bool(requires_approval)}


def rank(rows: list[dict], reference: datetime | None = None) -> dict:
    reference = reference or datetime.now(timezone.utc)
    ranked, waiting, blocked = [], [], []
    done_ids = set()
    open_ids = {}
    for row in rows:
        open_ids[row["id"]] = row
    for row in rows:
        if row["status"] == "blocked":
            blocked.append({**row, "why": f"阻塞：{row['blocked_reason'] or '未说明原因'}"})
            continue
        depends = deserialize(row["depends_on_json"] or "[]")
        missing = [d for d in depends if d in open_ids and open_ids[d]["status"] != "done"]
        if missing:
            waiting.append({**row, "why": f"等待前置行动 {missing} 完成"})
            continue
        urgency, days = _urgency(row["due_at"], reference)
        source_points = SOURCE_WEIGHT.get(row["source_type"], 3)
        priority_points = (6 - int(row["priority"])) * 5
        score = urgency + source_points + priority_points
        factors = {
            "urgency": urgency,
            "source_weight": source_points,
            "priority": priority_points,
            "days_left": days,
            "requires_approval": bool(row["requires_approval"]),
        }
        reasons = []
        if days is not None and days < 0:
            reasons.append(f"已逾期 {abs(days)} 天")
        elif days is not None:
            reasons.append(f"{days} 天内到期")
        reasons.append(f"{row['source_type']} 来源权重 {source_points}")
        reasons.append(f"优先级 {row['priority']}")
        if row["requires_approval"]:
            reasons.append("需要用户授权后才能执行")
        ranked.append({**row, "score": score, "factors": factors, "why": "；".join(reasons)})
    ranked.sort(key=lambda item: (-item["score"], item["due_at"] or "9999", item["id"]))
    return {"ranked": ranked, "waiting": waiting, "blocked": blocked, "done_ids": sorted(done_ids)}


def list_actions(*, status: str | None = None, sort: str = "rank", limit: int = 20) -> dict:
    clauses, params = [], []
    if status:
        if status not in STATUSES:
            raise ValueError("status must be one of " + ", ".join(STATUSES))
        clauses.append("status=?")
        params.append(status)
    if not status:
        clauses.append("status IN ('todo','doing','blocked')")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as conn:
        rows = [dict(row) for row in conn.execute(
            f"SELECT * FROM next_actions {where} ORDER BY id DESC", params)]
    if sort == "due":
        rows.sort(key=lambda item: (item["due_at"] or "9999", item["priority"], item["id"]))
        return {"items": rows[:limit], "sort": "due"}
    result = rank(rows)
    result["ranked"] = result["ranked"][:limit]
    result["sort"] = "rank"
    return result


def get(action_id: int) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM next_actions WHERE id=?", (action_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"action #{action_id} not found")
        return dict(row)


def complete(action_id: int, *, human_confirmed: bool = False, evidence: str = "") -> dict:
    """Only a verifiable artifact or a direct user statement may close an action."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM next_actions WHERE id=?", (action_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"action #{action_id} not found")
        if row["status"] == "done":
            raise ValueError(f"action #{action_id} is already done")
        if row["status"] == "cancelled":
            raise ValueError(f"action #{action_id} is cancelled")
        if not evidence.strip() and not human_confirmed:
            raise ValueError(
                "Completion needs evidence (--evidence) or explicit user confirmation (--human-confirmed); "
                "a natural-language claim alone does not close an action"
            )
        if row["requires_approval"] and not human_confirmed:
            raise ValueError(f"action #{action_id} requires explicit user approval before completion")
        conn.execute(
            "UPDATE next_actions SET status='done', completed_at=?, completion_evidence=? WHERE id=?",
            (now(), (evidence.strip() or "user_confirmed"), action_id))
        audit(conn, "action.completed", "next_actions", action_id, evidence[:120])
        return {"id": action_id, "status": "done", "evidence": evidence.strip() or "user_confirmed"}


def block(action_id: int, reason: str) -> dict:
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("reason is required")
    with connect() as conn:
        row = conn.execute("SELECT status FROM next_actions WHERE id=?", (action_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"action #{action_id} not found")
        conn.execute("UPDATE next_actions SET status='blocked', blocked_reason=? WHERE id=?",
                     (reason, action_id))
        audit(conn, "action.blocked", "next_actions", action_id, reason[:120])
        return {"id": action_id, "status": "blocked", "reason": reason}


def unblock(action_id: int) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT status FROM next_actions WHERE id=?", (action_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"action #{action_id} not found")
        if row["status"] != "blocked":
            raise ValueError(f"action #{action_id} is not blocked")
        conn.execute("UPDATE next_actions SET status='todo', blocked_reason='' WHERE id=?", (action_id,))
        return {"id": action_id, "status": "todo"}
