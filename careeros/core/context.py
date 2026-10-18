"""Context builder — the bounded "remember the user" payload for every session.

The brief answers the five product questions in one payload and stays small as
the database grows. Nothing here is a source of truth: every item carries an ID
so the model can drill down (``context inspect``) instead of loading the whole
database into the context window.
"""
from __future__ import annotations

import json

from ..db import connect, deserialize, now
from . import actions as actions_mod
from . import assertions, pipeline
from .errors import NotFoundError

DEFAULT_MAX_CHARS = 3200


def _text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "claim", "rule", "title", "summary", "direction", "name", "skill"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
        return json.dumps(value, ensure_ascii=False)[:120]
    if isinstance(value, list):
        return "、".join(_text(item) for item in value)[:120]
    return str(value)


def _source(row) -> str:
    """`source_ref` already names the concrete record; fall back to its class."""
    return row["source_ref"] or row["source_type"]


def _profile(conn) -> dict:
    row = conn.execute("SELECT data,updated_at FROM profile WHERE id=1").fetchone()
    return deserialize(row["data"]) if row else {}


def _claim(conn, row, *, with_basis: bool = True) -> dict:
    item = {
        "assertion_id": row["id"],
        "claim": _text(deserialize(row["value_json"])),
        "type": row["assertion_type"],
        "status": row["epistemic_status"],
        "confidence": row["confidence"],
        "since": row["recorded_at"],
        "source": _source(row),
    }
    if with_basis:
        links = assertions.links_of(conn, row["id"])
        item["basis"] = [{key: link[key] for key in ("relation", "label")} for link in links][:4]
    return item


def _live_rows(conn, assertion_type=None, statuses=None, limit=20) -> list:
    clauses = ["valid_to=''", "epistemic_status!='retracted'"]
    params: list = []
    if assertion_type:
        clauses.append("assertion_type=?")
        params.append(assertion_type)
    if statuses:
        clauses.append("epistemic_status IN (%s)" % ",".join("?" * len(statuses)))
        params.extend(statuses)
    params.append(limit)
    return conn.execute(
        f"SELECT * FROM user_assertions WHERE {' AND '.join(clauses)} "
        "ORDER BY CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, "
        "recorded_at DESC LIMIT ?", params).fetchall()


def _experience_base(conn) -> dict:
    rows = conn.execute("SELECT id,data FROM experiences ORDER BY id DESC").fetchall()
    approved = 0
    recent = []
    for row in rows:
        data = deserialize(row["data"])
        if data.get("approved_for_resume"):
            approved += 1
        if len(recent) < 3:
            recent.append({"id": row["id"], "event": str(data.get("event", ""))[:40],
                           "approved": bool(data.get("approved_for_resume"))})
    return {"total": len(rows), "approved_for_resume": approved, "recent": recent}


def _directions(conn) -> list[dict]:
    items = []
    for row in _live_rows(conn, "career_hypothesis", limit=6):
        value = deserialize(row["value_json"])
        links = assertions.links_of(conn, row["id"])
        items.append({
            "hypothesis_id": row["id"],
            "direction": _text(value),
            "status": row["epistemic_status"],
            "confidence": row["confidence"],
            "support": [link["label"] for link in links if link["relation"] == "supports"][:3],
            "contradict": [link["label"] for link in links if link["relation"] == "contradicts"][:3],
            "explanation": row["explanation"] or None,
        })
    if not items:
        legacy = conn.execute("SELECT id,data FROM career_directions ORDER BY id DESC LIMIT 3").fetchall()
        for row in legacy:
            data = deserialize(row["data"])
            items.append({
                "hypothesis_id": None,
                "legacy_direction_id": row["id"],
                "direction": str(data.get("title", ""))[:60],
                "status": "unmapped",
                "confidence": "unknown",
                "support": [f"经历 {i}" for i in data.get("supporting_experience_ids", [])][:3],
                "contradict": [],
                "explanation": "v0.1 方向记录，尚未转为假设，需运行 twin sync-legacy",
            })
    return items


def _active_pipeline(conn, limit: int = 3) -> list[dict]:
    rows = conn.execute(
        "SELECT job_id, discovery_status, priority, decision_reason, last_checked_at FROM job_pipeline "
        "WHERE discovery_status IN ('shortlisted','evaluating') "
        "ORDER BY CASE discovery_status WHEN 'shortlisted' THEN 0 ELSE 1 END, COALESCE(priority,9), updated_at DESC "
        "LIMIT ?", (limit,)).fetchall()
    result = []
    for row in rows:
        card = pipeline.show(row["job_id"])
        result.append({
            "job_id": row["job_id"],
            "job": f"{card['job']['company']} / {card['job']['title']}"[:60],
            "discovery_status": row["discovery_status"],
            "application_stage": card["current_stage"],
            "last_verified_event": card["last_verified_event"],
            "next_action": (card["next_action"] or {}).get("title"),
            "deadline": card["deadline"],
            "blocker": card["blocking_issue"],
            "source": f"job:{row['job_id']}",
        })
    return result


def _active_goals(conn, limit: int = 3) -> list[dict]:
    rows = conn.execute(
        "SELECT id,title,priority,status,target_date,owner FROM career_goals "
        "WHERE status IN ('active','exploring') ORDER BY priority, updated_at DESC LIMIT ?",
        (limit,)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["open_actions"] = conn.execute(
            "SELECT COUNT(*) FROM next_actions WHERE source_type='goal' AND source_id=? "
            "AND status IN ('todo','doing','blocked')", (row["id"],)).fetchone()[0]
        result.append(item)
    return result


def _uncertainties(conn, limit: int = 3) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM user_assertions WHERE valid_to='' AND (epistemic_status='disputed' OR "
        "(epistemic_status='inferred' AND confidence IN ('low','medium'))) "
        "ORDER BY CASE epistemic_status WHEN 'disputed' THEN 0 ELSE 1 END, recorded_at DESC LIMIT ?",
        (limit,)).fetchall()
    items = []
    for row in rows:
        items.append({
            "assertion_id": row["id"],
            "claim": _text(deserialize(row["value_json"])),
            "status": row["epistemic_status"],
            "confidence": row["confidence"],
            "question": ("这条推断与用户说法冲突，需要用户裁决" if row["epistemic_status"] == "disputed"
                         else "这是推断，尚未获得用户确认"),
        })
    return items


def _fit(data: dict, max_chars: int) -> dict:
    """Shrink the brief by dropping the least critical tail items first."""
    plan = [
        ("who_could_i_become", "directions"),
        ("where_i_am_now", "active"),
        ("what_next", "actions"),
        ("who_am_i", "strengths"),
        ("who_am_i", "values"),
        ("who_am_i", "preferences"),
        (None, "uncertainties"),
    ]
    dropped: dict[str, int] = {}

    def size() -> int:
        return len(json.dumps(data, ensure_ascii=False, separators=(",", ":")))

    guard = 0
    while size() > max_chars and guard < 200:
        guard += 1
        progressed = False
        for parent, key in plan:
            bucket = data[key] if parent is None else data[parent][key]
            floor = 1 if key in ("directions", "active", "actions", "strengths") else 0
            if isinstance(bucket, list) and len(bucket) > floor:
                bucket.pop()
                label = f"{parent}.{key}" if parent else key
                dropped[label] = dropped.get(label, 0) + 1
                progressed = True
                break
        if not progressed:
            break
    if size() > max_chars:
        # Last resort: the fixed scaffolding may itself exceed a very small
        # budget. Drop the human notes and drill-down hints, and report it.
        data.pop("drill_down", None)
        for parent, key in (("who_could_i_become", "note"), ("what_next", "rule")):
            bucket = data.get(parent)
            if isinstance(bucket, dict):
                bucket.pop(key, None)
    budget = {"max_chars": max_chars, "chars": 0, "truncated": dropped,
              "complete": not dropped, "over_budget": False}
    data["context_budget"] = budget
    for _ in range(3):
        budget["chars"] = size()
    if budget["chars"] > max_chars:
        budget["over_budget"] = True
        budget["complete"] = False
    return data


def brief(max_chars: int = DEFAULT_MAX_CHARS) -> dict:
    with connect() as conn:
        profile = _profile(conn)
        identity = {
            "display_name": profile.get("display_name"),
            "location": profile.get("location"),
            "target_roles": profile.get("target_roles") or profile.get("target_role"),
        }
        identity = {key: value for key, value in identity.items() if value}

        strengths = [_claim(conn, row) for row in _live_rows(
            conn, "skill_hypothesis", statuses=assertions.USER_BACKED, limit=4)]
        values = [_claim(conn, row) for row in _live_rows(
            conn, "value", statuses=assertions.USER_BACKED, limit=3)]
        preferences = [_claim(conn, row) for row in _live_rows(
            conn, "preference", statuses=assertions.USER_BACKED, limit=3)]
        constraints = [_claim(conn, row, with_basis=False) for row in _live_rows(
            conn, "constraint", statuses=assertions.USER_BACKED, limit=3)]
        facts = [_claim(conn, row, with_basis=False) for row in _live_rows(
            conn, "fact", statuses=assertions.USER_BACKED, limit=3)]

        directions = _directions(conn)
        goals = _active_goals(conn)
        active = _active_pipeline(conn)
        pipeline_counts = pipeline.counts()
        evidence_base = _experience_base(conn)
        open_actions = actions_mod.list_actions(limit=6)
        uncertainties = _uncertainties(conn)
        signal_count = conn.execute("SELECT COUNT(*) FROM user_feedback").fetchone()[0]
        application_counts = {row["status"]: row["n"] for row in conn.execute(
            "SELECT status,COUNT(*) AS n FROM applications GROUP BY status")}

    ranked = open_actions.get("ranked", [])
    next_actions = [{
        "action_id": row["id"],
        "title": row["title"],
        "source": f"{row['source_type']}:{row['source_id']}",
        "due_at": row["due_at"] or None,
        "requires_approval": bool(row["requires_approval"]),
        "why": row["why"],
    } for row in ranked[:3]]

    referenced = {item["assertion_id"] for item in strengths + values + preferences + constraints + facts}
    why = {}
    with connect() as conn:
        for assertion_id in referenced:
            try:
                record = assertions.get(assertion_id, with_audit=False)
            except NotFoundError:
                continue
            why[str(assertion_id)] = {
                "claim": _text(record["value"]),
                "status": record["epistemic_status"],
                "source": _source(record),
                "recorded_at": record["recorded_at"],
                "last_confirmed_at": record["last_confirmed_at"] or None,
                "basis": [{"relation": link["relation"], "label": link["label"]} for link in record["links"]][:4],
                "versions": len(record["chain"]),
            }

    data = {
        "generated_at": now(),
        "who_am_i": {
            "identity": identity,
            "facts": facts,
            "strengths": strengths,
            "values": values,
            "preferences": preferences,
            "constraints": constraints,
            "evidence_base": evidence_base,
        },
        "who_could_i_become": {
            "directions": directions,
            "note": "每个方向都是假设；support/contradict 只能来自带来源的记录",
        },
        "where_i_am_now": {
            "goals": goals,
            "pipeline": pipeline_counts,
            "applications": application_counts,
            "active": active,
            "open_actions": len(ranked) + len(open_actions.get("waiting", [])) + len(open_actions.get("blocked", [])),
            "blocked": [{"action_id": row["id"], "title": row["title"], "why": row["why"]}
                        for row in open_actions.get("blocked", [])][:2],
            "waiting": [{"action_id": row["id"], "title": row["title"], "why": row["why"]}
                        for row in open_actions.get("waiting", [])][:2],
            "user_signals": signal_count,
        },
        "what_next": {"actions": next_actions, "rule": "紧急度+来源权重+优先级；不是成功概率"},
        "why": why,
        "uncertainties": uncertainties,
        "drill_down": {
            "assertion": "python -m careeros context inspect --assertion-id <id>",
            "belief_history": "python -m careeros belief history --id <id>",
            "job": "python -m careeros pipeline show --job-id <id>",
        },
    }
    return _fit(data, max_chars)


def inspect(assertion_id: int) -> dict:
    record = assertions.get(assertion_id)
    with connect() as conn:
        dependents = conn.execute(
            "SELECT a.id,a.subject,a.predicate,a.epistemic_status,b.relation FROM assertion_links b "
            "JOIN user_assertions a ON a.id=b.assertion_id "
            "WHERE b.ref_type='assertion' AND b.ref_id=? AND a.valid_to=''",
            (str(assertion_id),)).fetchall()
    record["used_by"] = [dict(row) for row in dependents]
    record["versions"] = record["chain"]
    return record


def why(assertion_id: int) -> dict:
    record = assertions.get(assertion_id)
    trajectory = assertions.history(assertion_id=assertion_id)
    return {
        "claim": _text(record["value"]),
        "subject": record["subject"],
        "predicate": record["predicate"],
        "status": record["epistemic_status"],
        "confidence": record["confidence"],
        "source": _source(record),
        "explanation": record["explanation"] or None,
        "recorded_at": record["recorded_at"],
        "last_confirmed_at": record["last_confirmed_at"] or None,
        "basis": [{"relation": link["relation"], "label": link["label"], "ref": link["ref"]}
                  for link in record["links"]],
        "changed": len(trajectory["versions"]) > 1,
        "trajectory": trajectory["versions"],
        "audit": record.get("audit", []),
    }
