"""Context builder — the bounded "remember the user" payload for every session.

The brief answers the five product questions in one payload and stays small as
the database grows. Nothing here is a source of truth: every item carries an ID
so the model can drill down (``context inspect``) instead of loading the whole
database into the context window.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ..db import connect, deserialize, now
from . import actions as actions_mod
from . import assertions, pipeline
from .errors import NotFoundError
from .profile import read_profile

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
    return read_profile(conn) or {}


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


def _live_rows(conn, assertion_type=None, statuses=None, limit=20, settled=False) -> list:
    clauses = ["valid_to=''", "epistemic_status!='retracted'"]
    params: list = []
    if assertion_type:
        clauses.append("assertion_type=?")
        params.append(assertion_type)
    if statuses:
        clauses.append("epistemic_status IN (%s)" % ",".join("?" * len(statuses)))
        params.extend(statuses)
    clauses.append("NOT (source_type IN ('model_inference','reflection','external_source') "
                   "AND epistemic_status IN ('user_stated','document_verified'))")
    if settled:
        # A single hedged sentence ("I guess I value autonomy?") is a starting
        # point, not an identity trait. It stays in `uncertainties` until the
        # user confirms it or a second source supports it.
        clauses.append("NOT (epistemic_status='user_stated' AND confidence='low')")
    params.append(limit if limit is not None else -1)
    return conn.execute(
        f"SELECT * FROM user_assertions WHERE {' AND '.join(clauses)} "
        "ORDER BY CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, "
        "recorded_at DESC LIMIT ?", params).fetchall()


def _experience_base(conn) -> dict:
    from .. import experience_library
    rows = experience_library.list_current(conn=conn)
    approved = 0
    recent = []
    for row in rows:
        data = row["data"] if isinstance(row["data"], dict) else deserialize(row["data"])
        if data.get("approved_for_resume") and not data.get("needs_review"):
            approved += 1
        if len(recent) < 3:
            recent.append({"id": row["id"], "event": str(data.get("event", ""))[:40],
                           "approved": bool(data.get("approved_for_resume")) and not data.get("needs_review"),
                           "version": data.get("version", 1), "needs_review": bool(data.get("needs_review"))})
    return {"total": len(rows), "approved_for_resume": approved, "recent": recent}


def _directions(conn) -> list[dict]:
    items = []
    for row in _live_rows(conn, "career_hypothesis", limit=None):
        value = deserialize(row["value_json"])
        links = assertions.links_of(conn, row["id"])
        items.append({
            "hypothesis_id": row["id"],
            "direction": _text(value),
            "status": row["epistemic_status"],
            "confidence": row["confidence"],
            "support": [link["label"] for link in links
                        if link["relation"] in ("supports", "derived_from")][:3],
            "contradict": [link["label"] for link in links if link["relation"] == "contradicts"][:3],
            "explanation": row["explanation"] or None,
        })
    if not items:
        legacy = conn.execute(
            "SELECT d.id,d.data FROM career_directions d WHERE NOT EXISTS "
            "(SELECT 1 FROM user_assertions a WHERE a.source_ref='career_directions:' || d.id "
            "OR (json_valid(a.value_json) AND json_extract(a.value_json,'$.legacy_direction_id')=d.id)) "
            "ORDER BY d.id DESC").fetchall()
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
            "goal": (card.get("goal") or {}).get("title"),
            "source": f"job:{row['job_id']}",
        })
    return result


def _active_goals(conn, limit: int = 3) -> list[dict]:
    rows = conn.execute(
        "SELECT id,title,priority,status,target_date,owner,direction_id FROM career_goals "
        "WHERE status IN ('active','exploring') ORDER BY priority, updated_at DESC LIMIT ?",
        (limit,)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        if row["direction_id"]:
            direction = conn.execute("SELECT data FROM career_directions WHERE id=?",
                                     (row["direction_id"],)).fetchone()
            item["direction"] = (deserialize(direction["data"]).get("title", "")
                                 if direction else f"direction:{row['direction_id']}")
        from . import relations
        item["open_actions"] = 0
        for action in conn.execute("SELECT source_type,source_id FROM next_actions WHERE status IN ('todo','doing','blocked')"):
            try:
                item["open_actions"] += row["id"] in relations.source_context(
                    conn, action["source_type"], action["source_id"])["goal_ids"]
            except ValueError:
                continue
        result.append(item)
    return result


def _uncertainties(conn, limit: int = 3) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM user_assertions WHERE valid_to='' AND (epistemic_status='disputed' OR "
        "(epistemic_status='inferred' AND confidence IN ('low','medium')) OR "
        "(epistemic_status='user_stated' AND confidence='low' AND "
        "assertion_type IN ('value','preference','skill_hypothesis'))) "
        "ORDER BY CASE epistemic_status WHEN 'disputed' THEN 0 ELSE 1 END, recorded_at DESC LIMIT ?",
        (limit,)).fetchall()
    items = []
    for row in rows:
        if row["epistemic_status"] == "disputed":
            question = "这条推断与用户说法冲突，需要用户裁决"
        elif row["epistemic_status"] == "user_stated":
            question = "这条自述措辞含糊；请确认它是否真的要写进长期画像"
        else:
            question = "这是推断，尚未获得用户确认"
        items.append({
            "assertion_id": row["id"],
            "claim": _text(deserialize(row["value_json"])),
            "status": row["epistemic_status"],
            "confidence": row["confidence"],
            "question": question,
        })
    return items


def _recent_changes(conn, days: int = 7, limit: int = 4) -> list[dict]:
    """What the system *changed its mind about* recently, not just how often.

    The fifth question ("why do you think so") is mostly about movement: a
    version count tells the user nothing, a one-line diff does.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT a.kind, a.resource_id, a.detail, a.created_at, u.value_json, u.epistemic_status "
        "FROM audit_events a LEFT JOIN user_assertions u ON u.id=a.resource_id "
        "WHERE a.resource='user_assertions' AND a.kind IN "
        "('assertion.revised','assertion.retracted','assertion.disputed') "
        "AND a.created_at >= ? ORDER BY a.id DESC LIMIT ?", (cutoff, limit)).fetchall()
    labels = {"assertion.revised": "修订", "assertion.retracted": "撤回", "assertion.disputed": "存疑"}
    return [{
        "assertion_id": row["resource_id"],
        "change": labels.get(row["kind"], row["kind"]),
        "now": _text(deserialize(row["value_json"])) if row["value_json"] else "",
        "status": row["epistemic_status"],
        "at": row["created_at"],
        "detail": (row["detail"] or "")[:80],
    } for row in rows]


def _recent_signals(conn, limit: int = 3) -> list[dict]:
    """Why recently-considered options were accepted or rejected, in the user's words."""
    rows = conn.execute(
        "SELECT id,target_type,target_id,feedback_type,reason,scope,recorded_at,"
        "promoted_assertion_id FROM user_feedback ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{
        "feedback_id": row["id"],
        "target": f"{row['target_type']}:{row['target_id']}",
        "reaction": row["feedback_type"],
        "reason": (row["reason"] or "")[:60],
        "scope": row["scope"],
        "promoted": bool(row["promoted_assertion_id"]),
        "at": row["recorded_at"],
    } for row in rows]


def _focus_score(text, focus):
    if not focus or focus == "inferred/default":
        return 0
    tokens = [token.casefold() for token in focus.split() if len(token) > 1]
    value = str(text or "").casefold()
    return sum(token in value for token in tokens)


def _recovery_claim(item):
    return {key: item.get(source) for key, source in (("id", "assertion_id"), ("claim", "claim"),
            ("status", "status"), ("at", "since")) if item.get(source) is not None}


def _recovery_action(item):
    if not item:
        return None
    return {key: item.get(key) for key in ("action_id", "id", "title", "status", "due_at")
            if item.get(key) is not None}


def _fit(data: dict, max_chars: int) -> dict:
    """Fit the *printed JSON* budget; omissions always remain visible.

    Keep constraints and continuation until less critical history is removed.
    Small impossible budgets preserve the section skeleton and report overflow.
    """
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 1:
        raise ValueError("max_chars must be a positive integer")
    dropped = data.pop("_omitted", {})
    budget = {"max_chars": max_chars, "chars": 0, "truncated": {},
              "complete": not dropped, "over_budget": False}
    data["context_budget"] = budget

    # Even the protected capsule can contain growing arrays (for example many
    # paused branches). Keep the count and a few restore IDs, not every branch.
    recovery = data.get("recovery", {})
    for key in ("paused_restore", "important_corrections", "conflicts", "job_ids", "resume_ids"):
        values = recovery.get(key)
        if isinstance(values, list) and len(values) > 3:
            recovery[key] = values[:3]
            dropped["recovery." + key] = len(values) - 3
            budget["complete"] = False

    def size():
        summary = {}
        for path, count in dropped.items():
            section = path.split(".", 1)[0]
            summary[section] = summary.get(section, 0) + count
        budget["truncated"] = ";".join(f"{section}:{count}" for section, count in sorted(summary.items()))
        for _ in range(4):
            budget["chars"] = len(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return budget["chars"]

    def note(path, count=1):
        dropped[path] = dropped.get(path, 0) + count
        budget["complete"] = False

    # `why` used to duplicate claims even after their primary card was dropped.
    if size() > max_chars and data.get("why"):
        note("why", len(data["why"]))
        data["why"] = {}
    paths = [
        (None, "recent_changes"), ("where_i_am_now", "recent_signals"),
        ("who_could_i_become", "directions"), ("where_i_am_now", "active"),
        ("where_i_am_now", "needs_review"), ("where_i_am_now", "excluded"),
        ("where_i_am_now", "waiting"), ("where_i_am_now", "blocked"),
        ("continuation", "paused_branches"),
        ("who_am_i", "strengths"), ("who_am_i", "values"),
        ("who_am_i", "preferences"), (None, "uncertainties"),
        ("who_am_i", "facts"), ("who_am_i", "evidence_base.recent"),
        ("where_i_am_now", "goals"), ("what_next", "actions"),
        ("who_am_i", "constraints"),
    ]
    if size() > max_chars:
        for parent, key in ((None, "drill_down"), ("who_could_i_become", "note"), ("what_next", "rule")):
            bucket = data if parent is None else data.get(parent, {})
            if key in bucket:
                bucket.pop(key)
                note(key if parent is None else parent + "." + key)
            if size() <= max_chars:
                break
    for parent, key in paths:
        # The recovery capsule is deliberately outside the optional detail list.
        if parent is None and key == "recovery":
            continue
        bucket = data if parent is None else data.get(parent, {})
        parts = key.split(".")
        for part in parts[:-1]:
            bucket = bucket.get(part, {})
        values = bucket.get(parts[-1], [])
        while isinstance(values, list) and values and size() > max_chars:
            values.pop()
            note(key if parent is None else parent + "." + key)
    # A user can enter an arbitrarily long current topic or identity. Shorten
    # only text leaves, preserving their IDs, state and honest omission marker.
    def shorten(value, path=""):
        changed = False
        if isinstance(value, dict):
            for key, item in list(value.items()):
                if key == "context_budget":
                    continue
                label = path + "." + key if path else key
                if isinstance(item, str) and len(item) > 60:
                    value[key] = item[:60] + "…"
                    changed = True
                elif isinstance(item, (dict, list)):
                    changed = shorten(item, label) or changed
        elif isinstance(value, list):
            for item in value:
                changed = shorten(item, path) or changed
        return changed
    if size() > max_chars and shorten(data):
        note("text_shortened")
    if size() > max_chars:
        for key in ("conflicts", "important_corrections", "paused_restore", "job_ids", "resume_ids"):
            values = recovery.get(key)
            while isinstance(values, list) and len(values) > 1 and size() > max_chars:
                values.pop()
                note("recovery." + key)
    budget["over_budget"] = size() > max_chars
    if budget["over_budget"]:
        budget["complete"] = False
    size()
    return data


def brief(max_chars: int = DEFAULT_MAX_CHARS, focus: str | None = None, *, _section=None) -> dict:
    with connect() as conn:
        profile = _profile(conn)
        identity = {
            "display_name": profile.get("display_name"),
            "location": profile.get("location"),
            "target_roles": profile.get("target_roles") or profile.get("target_role"),
        }
        for key in ("education", "graduation_date", "availability", "target_locations"):
            if profile.get(key):
                identity[key] = profile[key]
        identity = {key: value for key, value in identity.items() if value}

        strengths = [_claim(conn, row) for row in _live_rows(
            conn, "skill_hypothesis", statuses=assertions.USER_BACKED, limit=None, settled=True)]
        values = [_claim(conn, row) for row in _live_rows(
            conn, "value", statuses=assertions.USER_BACKED, limit=None, settled=True)]
        preferences = [_claim(conn, row) for row in _live_rows(
            conn, "preference", statuses=assertions.USER_BACKED, limit=None, settled=True)]
        constraints = [_claim(conn, row, with_basis=False) for row in _live_rows(
            conn, "constraint", statuses=assertions.USER_BACKED, limit=None, settled=True)]
        facts = [_claim(conn, row, with_basis=False) for row in _live_rows(
            conn, "fact", statuses=assertions.USER_BACKED, limit=None, settled=True)]

        directions = _directions(conn)
        goals = _active_goals(conn)
        active = _active_pipeline(conn)
        pipeline_counts = pipeline.counts()
        evidence_base = _experience_base(conn)
        open_actions = actions_mod.list_actions(limit=6)
        uncertainties = _uncertainties(conn)
        recent_changes = _recent_changes(conn)
        recent_signals = _recent_signals(conn)
        signal_count = conn.execute("SELECT COUNT(*) FROM user_feedback").fetchone()[0]
        application_counts = {row["status"]: row["n"] for row in conn.execute(
            "SELECT status,COUNT(*) AS n FROM applications GROUP BY status")}
        current_jobs = [item["job_id"] for item in active]
        if current_jobs:
            resume_ids = [row[0] for row in conn.execute(
                "SELECT id FROM resumes WHERE job_id IN (%s) ORDER BY created_at DESC LIMIT 3" %
                ",".join("?" * len(current_jobs)), current_jobs)]
        else:
            resume_ids = [row[0] for row in conn.execute("SELECT id FROM resumes ORDER BY created_at DESC LIMIT 3")]

    ranked = open_actions.get("ranked", [])
    next_actions = [{
        "action_id": row["id"],
        "title": row["title"],
        "source": f"{row['source_type']}:{row['source_id']}",
        "due_at": row["due_at"] or None,
        "requires_approval": bool(row["requires_approval"]),
        "why": row["why"],
        "suggestion_reason": row["suggestion_reason"],
        "decision_id": row.get("assessment", {}).get("decision_id"),
        "assessment": row.get("assessment", {}).get("status", "unassessed"),
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

    from .. import onboarding
    session = onboarding.continuation()
    resolved_focus = (focus or (session.get("current_topic") or {}).get("title") or "inferred/default")
    if resolved_focus != "inferred/default":
        focus = resolved_focus
        goals.sort(key=lambda item: (-_focus_score(f"{item.get('title', '')} {item.get('direction', '')}", focus), item.get("priority", 9)))
        next_actions.sort(key=lambda item: -_focus_score(item.get("title", ""), focus))
        active.sort(key=lambda item: -_focus_score(item.get("job", ""), focus))
        matching_jobs = [item["job_id"] for item in active if _focus_score(item.get("job", ""), focus)]
        if matching_jobs:
            current_jobs = matching_jobs[:3]
            with connect() as conn:
                resume_ids = [row[0] for row in conn.execute(
                    "SELECT id FROM resumes WHERE job_id IN (%s) ORDER BY created_at DESC LIMIT 3" %
                    ",".join("?" * len(current_jobs)), current_jobs)]
    continuation = {key: session[key] for key in ("intent", "current_topic", "paused_branches")}
    profile = identity.copy()
    recovery = {
        "focus": resolved_focus,
        "current_topic": ({key: session["current_topic"].get(key) for key in
                           ("id", "title", "status", "next_action", "updated_at", "created_at")
                           if session["current_topic"].get(key) is not None} if session.get("current_topic") else None),
        "identity": profile,
        "education_facts": [_recovery_claim(item) for item in sorted(facts, key=lambda item: item["since"], reverse=True)
                            if any(word in item["claim"].lower() for word in ("教育", "学校", "毕业", "学历", "education", "graduat"))][:1],
        "availability": [_recovery_claim(item) for item in sorted(constraints, key=lambda item: item["since"], reverse=True)
                         if any(word in item["claim"].lower() for word in ("地点", "城市", "可到岗", "实习", "全职", "availability", "location"))][:1],
        "active_goal": ({key: goals[0].get(key) for key in ("id", "title", "status") if goals[0].get(key)} if goals else None),
        "next_or_review_or_blocker": _recovery_action(next_actions[0] if next_actions else
            (open_actions.get("review", [])[:1] or open_actions.get("blocked", [])[:1] or
             open_actions.get("waiting", [])[:1] or [None])[0]),
        "experience_count": evidence_base["total"],
        "experience_index": "python -m oriward experience index",
        "job_ids": current_jobs,
        "resume_ids": resume_ids,
        "paused_count": len(session.get("paused_branches", [])),
        "paused_restore": [item.get("id") for item in session.get("paused_branches", [])[:3]],
        "important_corrections": [{"assertion_id": item.get("assertion_id"), "change": item.get("change"),
                                    "at": item.get("at")} for item in recent_changes[:1]],
        "conflicts": [{"assertion_id": item.get("assertion_id"), "status": item.get("status")}
                      for item in uncertainties[:1]],
    }
    data = {
        "generated_at": now(),
        "recovery": recovery,
        "continuation": continuation,
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
            "open_actions": open_actions.get("total_open", len(ranked)),
            "blocked": [{"action_id": row["id"], "title": row["title"], "why": row["why"]}
                        for row in open_actions.get("blocked", [])][:2],
            "waiting": [{"action_id": row["id"], "title": row["title"], "why": row["why"]}
                        for row in open_actions.get("waiting", [])][:2],
            "user_signals": signal_count,
            "recent_signals": recent_signals,
            "needs_review": [{"action_id": r["id"], "title": r["title"], "why": r["why"]}
                             for r in open_actions.get("review", [])][:3],
            "excluded": [{"action_id": r["id"], "title": r["title"], "why": r["why"]}
                         for r in open_actions.get("excluded", [])][:3],
        },
        "what_next": {"actions": next_actions,
                      "rule": "先核实约束、机会和预算；排序仅安排时间，适配依据见 suggestion_reason/decision_id"},
        "why": why,
        "recent_changes": recent_changes,
        "uncertainties": uncertainties,
        "drill_down": {
            "assertion": "python -m oriward context inspect --assertion-id <id>",
            "belief_history": "python -m oriward belief history --id <id>",
            "job": "python -m oriward pipeline show --job-id <id>",
            "decision": "python -m oriward decision show --id <id>",
        },
    }
    recovery["focus"] = resolved_focus[:120]
    if _section is not None:
        if _section not in data or _section in {"generated_at", "context_budget"}:
            raise ValueError(f"Unknown context section: {_section}")
        return _fit({_section: data[_section]}, max_chars)
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


def section(name: str, focus: str | None = None, max_chars: int = 12000) -> dict:
    """Assemble the requested section before fitting, so omitted details return."""
    data = brief(max_chars=max_chars, focus=focus, _section=name)
    return {"section": name, "focus": focus or "current_topic", "data": data[name],
            "context_budget": data["context_budget"]}


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
