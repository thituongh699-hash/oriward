"""Agent-authored decisions, frozen evidence and append-only outcomes.

The Core checks references and changes in state; it does not infer semantic fit
from prose. Unknown or conflicting constraints stay visible until assessed.
"""
from __future__ import annotations

import math

from ..db import audit, connect, deserialize, now, serialize
from . import assertions, relations
from .errors import NotFoundError

FACTOR_NAMES = ("goal", "preference", "job", "deadline", "capability", "cost")
FACTOR_STATUSES = ("supports", "conflicts", "unknown", "not_applicable")
CHECK_STATUSES = ("satisfied", "conflict", "unknown")
EVENT_KINDS = ("accepted", "rejected", "result", "completed")


def _action(conn, action_id):
    row = conn.execute("SELECT * FROM next_actions WHERE id=?", (action_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"action #{action_id} not found")
    return dict(row)


def _settled(row):
    return (not row["valid_to"] and row["epistemic_status"] in assertions.USER_BACKED
            and not (row["epistemic_status"] == "user_stated" and row["confidence"] == "low")
            and not (row["source_type"] in assertions.NON_USER_SOURCES
                     and row["epistemic_status"] != "user_confirmed"))


def _context(conn, action):
    related = relations.source_context(conn, action["source_type"], action["source_id"])
    claims = [dict(row) for row in conn.execute(
        "SELECT * FROM user_assertions WHERE valid_to='' AND epistemic_status!='retracted' ORDER BY id")]
    for claim in claims:
        claim["links"] = [dict(link) for link in conn.execute(
            "SELECT * FROM assertion_links WHERE assertion_id=? ORDER BY id", (claim["id"],))]
    goals = [dict(conn.execute("SELECT * FROM career_goals WHERE id=?", (gid,)).fetchone())
             for gid in related["goal_ids"]]
    jobs = []
    for jid in related["job_ids"]:
        row = dict(conn.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone())
        snapshots = []
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='job_source_snapshots'").fetchone():
            snapshots = [dict(s) for s in conn.execute(
                "SELECT * FROM job_source_snapshots WHERE job_id=? ORDER BY id", (jid,))]
        state = conn.execute("SELECT * FROM job_pipeline WHERE job_id=?", (jid,)).fetchone()
        jobs.append({"record": row, "snapshots": snapshots,
                     "pipeline": dict(state) if state else None})
    return {"action": {key: action[key] for key in (
                "id", "title", "source_type", "source_id", "action_type", "due_at", "priority",
                "depends_on_json", "suggestion_reason", "effort_hours", "requires_approval")},
            "assertions": claims, "goals": goals, "jobs": jobs,
            "related": related}


def _validate_factors(conn, factors):
    if not isinstance(factors, dict) or set(factors) != set(FACTOR_NAMES):
        raise ValueError("factors must contain exactly: " + ", ".join(FACTOR_NAMES))
    evidence = {}
    for name, factor in factors.items():
        if not isinstance(factor, dict) or factor.get("status") not in FACTOR_STATUSES:
            raise ValueError(f"factor {name} needs status in {FACTOR_STATUSES}")
        if not isinstance(factor.get("reason"), str) or not factor["reason"].strip():
            raise ValueError(f"factor {name} needs a reason (including unknown/not_applicable)")
        if set(factor) - {"status", "reason", "assertion_ids", "experience_ids", "planned_weekly_hours"}:
            raise ValueError(f"factor {name} contains unknown fields")
        evidence[name] = []
        for field in ("assertion_ids", "experience_ids"):
            ids = factor.get(field, [])
            if not isinstance(ids, list):
                raise ValueError(f"factor {name}.{field} must be an array")
            table = "user_assertions" if field == "assertion_ids" else "experiences"
            for rid in ids:
                row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (int(rid),)).fetchone()
                if row is None:
                    raise NotFoundError(f"{table} #{rid} not found")
                if factor["status"] == "supports":
                    if field == "assertion_ids" and not _settled(row):
                        raise ValueError(f"factor {name} cannot use unconfirmed/retired assertion #{rid} as support")
                    if field == "assertion_ids" and name == "capability":
                        value = deserialize(row["value_json"])
                        skill_value = (isinstance(value, dict) and any(
                            isinstance(value.get(key), str) and value[key].strip() for key in ("skill", "name", "text")))
                        if (row["assertion_type"] != "skill_hypothesis" or row["predicate"] != "has_skill"
                                or not (row["subject"] == "user" or row["subject"].startswith("skill:"))
                                or not skill_value):
                            raise ValueError("capability evidence needs a skill_hypothesis with skill subject, has_skill and skill value")
                    if field == "experience_ids":
                        data = deserialize(row["data"])
                        if (not data.get("approved_for_resume") or not data.get("evidence")
                                or any(e.get("status") not in ("user_confirmed", "document_verified")
                                       for e in data["evidence"])):
                            raise ValueError(f"experience #{rid} has no approved verified evidence")
                evidence[name].append({"kind": field, "record": dict(row)})
        if name == "capability" and factor["status"] == "supports" and not evidence[name]:
            raise ValueError("supporting capability requires assertion_ids or experience_ids")
        weekly = factor.get("planned_weekly_hours")
        if weekly is not None and (isinstance(weekly, bool) or not isinstance(weekly, (int, float))
                                   or not math.isfinite(weekly) or not 0 <= weekly <= 168):
            raise ValueError("planned_weekly_hours must be finite and between 0 and 168")
    return evidence


def record(*, action_id: int, reason: str, factors: dict, constraint_checks=None,
           alternatives=None) -> dict:
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason is required")
    if alternatives is not None and not isinstance(alternatives, list):
        raise ValueError("alternatives must be an array")
    if any(not isinstance(option, dict) or not str(option.get("title", "")).strip()
           or not str(option.get("reason", "")).strip() for option in alternatives or []):
        raise ValueError("every alternative needs a title and reason")
    checks = constraint_checks if constraint_checks is not None else []
    if not isinstance(checks, list):
        raise ValueError("constraint_checks must be an array")
    with connect() as conn:
        action = _action(conn, action_id)
        if action["status"] not in ("todo", "doing", "blocked"):
            raise ValueError("only an open action can receive a new decision")
        snapshot = _context(conn, action)
        snapshot["evidence"] = _validate_factors(conn, factors)
        if action["action_type"] == "apply" and factors["capability"]["status"] == "not_applicable":
            raise ValueError("an application decision must assess capability, including unknown")
        constraints = {row["id"]: row for row in snapshot["assertions"]
                       if row["assertion_type"] == "constraint" and _settled(row)}
        seen = set()
        for check in checks:
            if not isinstance(check, dict):
                raise ValueError("each constraint check must be an object")
            rid = check.get("assertion_id")
            if rid not in constraints or rid in seen:
                raise ValueError(f"constraint #{rid} is not a distinct current settled constraint")
            if check.get("status") not in CHECK_STATUSES or not str(check.get("reason", "")).strip():
                raise ValueError("constraint check needs satisfied/conflict/unknown and a reason")
            seen.add(rid)
        if set(constraints) != seen:
            raise ValueError("assess every current settled constraint; missing: " + str(sorted(set(constraints) - seen)))
        previous = conn.execute("SELECT id FROM decision_records WHERE action_id=? ORDER BY id DESC LIMIT 1",
                                (action_id,)).fetchone()
        cursor = conn.execute(
            "INSERT INTO decision_records(action_id,previous_id,reason,alternatives_json,factors_json,"
            "constraint_checks_json,context_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (action_id, previous[0] if previous else None, reason.strip(), serialize(alternatives or []),
             serialize(factors), serialize(checks), serialize(snapshot), now()))
        decision_id = cursor.lastrowid
        audit(conn, "decision.recorded", "decision_records", decision_id, f"action:{action_id}")
        return {"id": decision_id, "action_id": action_id, "previous_id": previous[0] if previous else None,
                "assessment": assess_action(conn, action)}


def _decode(row):
    result = dict(row)
    for field in ("alternatives", "factors", "constraint_checks", "context"):
        result[field] = deserialize(result.pop(field + "_json"))
    return result


def get(decision_id: int) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM decision_records WHERE id=?", (decision_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"decision #{decision_id} not found")
        result = _decode(row)
        result["events"] = [dict(e) for e in conn.execute(
            "SELECT * FROM decision_events WHERE decision_id=? ORDER BY id", (decision_id,))]
        result["current_assessment"] = assess_action(conn, _action(conn, result["action_id"]))
        return result


def history(action_id: int) -> dict:
    with connect() as conn:
        _action(conn, action_id)
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM decision_records WHERE action_id=? ORDER BY id", (action_id,))]
    return {"action_id": action_id, "versions": [get(rid) for rid in ids]}


def _event(conn, decision_id, kind, note, evidence, human_confirmed):
    if kind not in EVENT_KINDS:
        raise ValueError("invalid decision event kind")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("note is required")
    if kind in ("accepted", "rejected") and not human_confirmed:
        raise ValueError("recording the user's choice requires --human-confirmed")
    if kind in ("result", "completed") and not human_confirmed and not evidence.strip():
        raise ValueError("a real result needs evidence or user confirmation")
    cursor = conn.execute(
        "INSERT INTO decision_events(decision_id,kind,note,evidence,human_confirmed,created_at) VALUES (?,?,?,?,?,?)",
        (decision_id, kind, note.strip(), evidence.strip(), int(human_confirmed), now()))
    audit(conn, "decision." + kind, "decision_records", decision_id, note)
    return {"id": cursor.lastrowid, "decision_id": decision_id, "kind": kind}


def outcome(decision_id: int, *, kind: str, note: str, evidence: str = "",
            human_confirmed: bool = False) -> dict:
    with connect() as conn:
        if conn.execute("SELECT 1 FROM decision_records WHERE id=?", (decision_id,)).fetchone() is None:
            raise NotFoundError(f"decision #{decision_id} not found")
        return _event(conn, decision_id, kind, note, evidence, human_confirmed)


def record_completion(conn, action_id, evidence, human_confirmed):
    row = conn.execute("SELECT id FROM decision_records WHERE action_id=? ORDER BY id DESC LIMIT 1",
                       (action_id,)).fetchone()
    if row:
        _event(conn, row[0], "completed", "行动完成", evidence, human_confirmed)


def assess_action(conn, action) -> dict:
    """Deterministic admission, separate from the scheduling score."""
    try:
        current = _context(conn, action)
    except NotFoundError as error:
        return {"status": "review", "reasons": [str(error)], "decision_id": None}
    row = conn.execute("SELECT * FROM decision_records WHERE action_id=? ORDER BY id DESC LIMIT 1",
                       (action["id"],)).fetchone()
    reasons, excluded = [], []
    constraints = [r for r in current["assertions"] if r["assertion_type"] == "constraint" and _settled(r)]
    for job in current["jobs"]:
        # Goal-level preparation can continue after an individual opportunity
        # closes; only work targeting concrete jobs is excluded by their state.
        if (action["source_type"] != "goal" and
                deserialize(job["record"]["data"]).get("availability") in ("closed", "expired", "removed")):
            excluded.append(f"岗位 #{job['record']['id']} 已关闭或失效")
    if row:
        decision = _decode(row)
        stored = dict(decision["context"])
        evidence = stored.pop("evidence", {})
        if serialize(stored) != serialize(current):
            reasons.append("目标、用户认识、岗位或行动已变化，需要重新评估；旧依据仍保留")
        for items in evidence.values():
            for item in items:
                table = "user_assertions" if item["kind"] == "assertion_ids" else "experiences"
                live = conn.execute(f"SELECT * FROM {table} WHERE id=?", (item["record"]["id"],)).fetchone()
                if live is None or serialize(dict(live)) != serialize(item["record"]):
                    reasons.append("决策引用的能力或经历证据已变化，需要重新核实")
        for check in decision["constraint_checks"]:
            if check["status"] == "conflict":
                excluded.append(f"违反约束 #{check['assertion_id']}：{check['reason']}")
            elif check["status"] == "unknown":
                reasons.append(f"约束 #{check['assertion_id']} 尚未核实：{check['reason']}")
        for name, factor in decision["factors"].items():
            if factor["status"] == "conflicts":
                excluded.append(f"{name} 不匹配：{factor['reason']}")
            elif factor["status"] == "unknown":
                reasons.append(f"{name} 待验证：{factor['reason']}")
        latest_choice = conn.execute(
            "SELECT kind FROM decision_events WHERE decision_id=? AND kind IN ('accepted','rejected') "
            "ORDER BY id DESC LIMIT 1", (row["id"],)).fetchone()
        if latest_choice and latest_choice[0] == "rejected":
            excluded.append("用户已否决这次建议；新建议须另存决定")
        planned = decision["factors"]["cost"].get("planned_weekly_hours", action["effort_hours"])
    else:
        if current["jobs"] and constraints:
            reasons.append("尚未逐项核实用户硬约束，不能作为适配建议")
        planned = action["effort_hours"]
    for goal in current["goals"]:
        budget = goal["time_budget_hours"]
        if goal["owner"] == "user" and goal["status"] in ("active", "exploring") and budget is not None:
            if planned is None:
                reasons.append(f"目标 #{goal['id']} 有每周时间预算，尚未估算行动投入")
            elif planned > budget:
                reasons.append(f"预计每周投入 {planned} 小时超过目标 #{goal['id']} 的 {budget} 小时预算；需拆分规划")
    validation = (action["action_type"] in ("research", "confirm", "decide", "log_result")
                  and reasons and all("待验证" in r or "尚未核实" in r or "尚未逐项核实" in r for r in reasons))
    return {"status": "excluded" if excluded else "validation" if validation else "review" if reasons
                      else "eligible" if row else "unassessed",
            "reasons": excluded + reasons, "decision_id": row["id"] if row else None}
