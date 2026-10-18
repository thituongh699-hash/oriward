"""Next actions and an *explainable* ranking.

The score is a documented, additive heuristic — never a probability of success.
Every ranked action carries the factors that produced its position, so the model
can say why it suggests it and the user can disagree with one factor instead of
the whole list.
"""
from __future__ import annotations

import math
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
#: Points contributed by proximity of the deadline (documented in
#: docs/CAREER_TWIN_CORE_ARCHITECTURE.md §7.4; keep the two in step).
URGENCY_STEPS = ((0, 50), (3, 40), (7, 30), (14, 20), (30, 10))


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
        return 60, math.floor(days)
    for limit, points in URGENCY_STEPS:
        if days <= limit:
            return points, math.floor(days)
    return 4, math.floor(days)


def _effort_points(hours) -> int:
    """Cheap next steps should not lose to expensive ones with equal urgency."""
    if hours is None:
        return 0
    try:
        value = float(hours)
    except (TypeError, ValueError):
        return 0
    if value <= 1:
        return 8
    if value <= 3:
        return 5
    if value <= 8:
        return 2
    return 0


def propose(*, title: str, source_type: str, source_id: int | None = None,
            action_type: str = "other", due_at: str = "", priority: int = 3,
            depends_on=None, suggestion_reason: str = "",
            requires_approval: bool = False, effort_hours: int | None = None) -> dict:
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
    if effort_hours is not None:
        effort_hours = int(effort_hours)
        if not 0 <= effort_hours <= 200:
            raise ValueError("effort_hours must be between 0 and 200")
    with connect() as conn:
        for dep in depends:
            if conn.execute("SELECT 1 FROM next_actions WHERE id=?", (int(dep),)).fetchone() is None:
                raise ValueError(f"depends_on references unknown action #{dep}")
        cursor = conn.execute(
            "INSERT INTO next_actions(title,source_type,source_id,action_type,status,due_at,priority,"
            "depends_on_json,suggestion_reason,requires_approval,created_at,effort_hours) "
            "VALUES (?,?,?,?,'todo',?,?,?,?,?,?,?)",
            (title, source_type, source_id, action_type, due_at, priority,
             serialize([int(x) for x in depends]), suggestion_reason.strip(),
             1 if requires_approval else 0, now(), effort_hours),
        )
        action_id = cursor.lastrowid
        audit(conn, "action.proposed", "next_actions", action_id, title[:80])
        return {"id": action_id, "status": "todo", "requires_approval": bool(requires_approval)}


def _goal_context(rows: list[dict]):
    """Resolve the goal behind each action: direct goal, or the job's goal.

    Without this, "what should I do next" cannot say which objective an action
    serves, and a priority-1 goal ranks exactly like a priority-5 one.
    """
    goal_ids, job_ids = set(), set()
    for row in rows:
        source_id = row.get("source_id")
        if not source_id:
            continue
        if row["source_type"] == "goal":
            goal_ids.add(int(source_id))
        elif row["source_type"] == "job":
            job_ids.add(int(source_id))
    job_goal: dict[int, int] = {}
    goals: dict[int, dict] = {}
    with connect() as conn:
        if job_ids:
            marks = ",".join("?" * len(job_ids))
            for item in conn.execute(
                    f"SELECT job_id,goal_id FROM job_pipeline WHERE job_id IN ({marks})",
                    tuple(job_ids)):
                if item["goal_id"]:
                    job_goal[item["job_id"]] = item["goal_id"]
                    goal_ids.add(item["goal_id"])
        if goal_ids:
            marks = ",".join("?" * len(goal_ids))
            for item in conn.execute(
                    f"SELECT id,title,priority,owner,status FROM career_goals WHERE id IN ({marks})",
                    tuple(goal_ids)):
                goals[item["id"]] = dict(item)
    return job_goal, goals


def _dependency_status(open_ids: dict, dep_ids: set[int]) -> dict[int, str]:
    external = [dep for dep in dep_ids if dep not in open_ids]
    statuses: dict[int, str] = {}
    if external:
        with connect() as conn:
            marks = ",".join("?" * len(external))
            for item in conn.execute(
                    f"SELECT id,status FROM next_actions WHERE id IN ({marks})", tuple(external)):
                statuses[item["id"]] = item["status"]
    return statuses


def rank(rows: list[dict], reference: datetime | None = None) -> dict:
    reference = reference or datetime.now(timezone.utc)
    ranked, waiting, blocked = [], [], []
    open_ids = {row["id"]: row for row in rows}
    dep_ids = {int(dep) for row in rows for dep in deserialize(row["depends_on_json"] or "[]")}
    external = _dependency_status(open_ids, dep_ids)
    job_goal, goals = _goal_context(rows)
    for row in rows:
        if row["status"] == "blocked":
            blocked.append({**row, "why": f"阻塞：{row['blocked_reason'] or '未说明原因'}"})
            continue
        depends = deserialize(row["depends_on_json"] or "[]")
        missing, cancelled = [], []
        for dep in depends:
            status = open_ids[dep]["status"] if dep in open_ids else external.get(dep)
            if status == "done":
                continue
            if status in (None, "cancelled"):
                # A cancelled prerequisite must not silently unlock its successor.
                cancelled.append(dep)
            else:
                missing.append(dep)
        if cancelled:
            waiting.append({**row, "why": f"前置行动 {cancelled} 已取消或不存在，需要重新规划"})
            continue
        if missing:
            waiting.append({**row, "why": f"等待前置行动 {missing} 完成"})
            continue
        urgency, days = _urgency(row["due_at"], reference)
        source_points = SOURCE_WEIGHT.get(row["source_type"], 3)
        priority_points = (6 - int(row["priority"])) * 5
        goal = goals.get(_goal_id_for(row, job_goal))
        goal_points = 0
        if goal and goal["status"] in ("active", "exploring") and goal["owner"] == "user":
            goal_points = (6 - int(goal["priority"])) * 3
        effort_points = _effort_points(row.get("effort_hours"))
        score = urgency + source_points + priority_points + goal_points + effort_points
        factors = {
            "urgency": urgency,
            "source_weight": source_points,
            "priority": priority_points,
            "goal_priority": goal_points,
            "effort": effort_points,
            "days_left": days,
            "effort_hours": row.get("effort_hours"),
            "requires_approval": bool(row["requires_approval"]),
        }
        reasons = []
        if days is not None and days < 0:
            reasons.append(f"已逾期 {abs(days)} 天")
        elif days is not None:
            reasons.append(f"{days} 天内到期")
        reasons.append(f"{row['source_type']} 来源权重 {source_points}")
        reasons.append(f"优先级 {row['priority']}")
        if goal_points:
            reasons.append(f"服务目标「{goal['title']}」（优先级 {goal['priority']}）")
        if effort_points:
            reasons.append(f"预计投入 {row.get('effort_hours')} 小时")
        if row["requires_approval"]:
            reasons.append("需要用户授权后才能执行")
        ranked.append({**row, "score": score, "factors": factors, "why": "；".join(reasons)})
    ranked.sort(key=lambda item: (-item["score"], item["due_at"] or "9999", item["id"]))
    return {"ranked": ranked, "waiting": waiting, "blocked": blocked}


def _goal_id_for(row: dict, job_goal: dict[int, int]) -> int | None:
    source_id = row.get("source_id")
    if not source_id:
        return None
    if row["source_type"] == "goal":
        return int(source_id)
    if row["source_type"] == "job":
        return job_goal.get(int(source_id))
    return None


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
        if row["status"] == "blocked":
            raise ValueError(
                f"action #{action_id} is blocked ({row['blocked_reason'] or '未说明原因'}); "
                "run action unblock --id first"
            )
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
        row = conn.execute("SELECT status,blocked_reason FROM next_actions WHERE id=?", (action_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"action #{action_id} not found")
        if row["status"] not in ("todo", "doing"):
            raise ValueError(f"only a todo/doing action can be blocked; #{action_id} is {row['status']}")
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
