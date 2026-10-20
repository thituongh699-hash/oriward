"""Persist small, revisable session preferences; never enable a connector.

Preferences record the user's choice. Connection state is a separately supplied
observation, not evidence that a route is generally supported or currently usable.
"""
from __future__ import annotations

from pathlib import Path

from .db import connect, deserialize, now, serialize
from .services import ValidationError

PREFERENCES = {"unasked", "connect_now", "later", "declined", "public_only"}
CONNECTIONS = {"not_connected", "connected", "validation_failed"}
PROMPT_STATES = {"unasked", "answered", "later", "declined"}
INTENTS = {"experience_index", "explore", "search", "specific_jd"}


def _text(value, name, limit=500, *, empty=True):
    if not isinstance(value, str) or len(value.strip()) > limit or (not empty and not value.strip()):
        raise ValidationError(f"{name} must be text of at most {limit} characters")
    return value.strip()


def _strings(value, name):
    if not isinstance(value, list) or len(value) > 30:
        raise ValidationError(f"{name} must be an array of at most 30 strings")
    return list(dict.fromkeys(_text(item, name, 200, empty=False) for item in value))


def _load(conn):
    row = conn.execute("SELECT data FROM career_settings WHERE key='onboarding'").fetchone()
    if row:
        state = deserialize(row["data"])
        state.setdefault("history_intake", {"answer": "unasked", "scope": []})
        state.setdefault("scheduled_search", "unasked")
        return state
    return {"version": 1, "intent": "experience_index", "companies": [], "roles": [],
            "constraints": {}, "prompts": {}, "channels": {}, "preference_sources": {}, "current_topic": None,
            "paused_branches": [], "next_branch_id": 1, "history_intake": {"answer": "unasked", "scope": []},
            "scheduled_search": "unasked"}


def _save(conn, state):
    conn.execute("INSERT INTO career_settings(key,data,updated_at) VALUES ('onboarding',?,?) "
                 "ON CONFLICT(key) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at",
                 (serialize(state), now()))


def _profile_defaults(conn, state):
    # Use the existing assertion-aware projection, never infer a target from a
    # skill tag. Explicit empty/declined answers take precedence over legacy data.
    from .core.profile import read_profile
    profile = read_profile(conn) or {}
    sources = state.setdefault("preference_sources", {})
    for key, value in (("roles", profile.get("target_roles") or profile.get("target_role")),
                       ("companies", profile.get("target_companies") or profile.get("target_company"))):
        if sources.get(key) == "profile":
            state[key] = []
            state["prompts"].pop(key, None)
        if not state[key] and key not in state["prompts"] and value:
            value = value if isinstance(value, list) else [value]
            if all(isinstance(item, str) and item.strip() and len(item.strip()) <= 200 for item in value) and len(value) <= 30:
                state[key] = _strings(value, key)
                state["prompts"][key] = "answered"
                sources[key] = "profile"
    inherited = {key: profile[key] for key in ("location", "target_locations", "availability",
                 "job_type", "exclusions", "hard_constraints") if profile.get(key)}
    origins = state.setdefault("constraint_sources", {
        key: "profile" for key in state["constraints"] if "constraints" not in state["prompts"]})
    for key in list(origins):
        if origins[key] == "profile":
            state["constraints"].pop(key, None)
    for key, value in inherited.items():
        if key not in state["constraints"]:
            state["constraints"][key] = value
            origins[key] = "profile"
    # Partial known arrangements do not imply a completed intake. Explicit
    # per-key user answers override defaults; inherited values keep refreshing.


def status():
    """Persist first-use defaults and return only the small preference state."""
    with connect() as conn:
        state = _load(conn)
        _profile_defaults(conn, state)
        _save(conn, state)
    return state


def update_preferences(*, companies=None, roles=None, constraints=None, intent=None):
    """None preserves an answer; [] explicitly means no target selected yet."""
    with connect() as conn:
        state = _load(conn)
        _profile_defaults(conn, state)
        for key, value in (("companies", companies), ("roles", roles)):
            if value is not None:
                state[key] = _strings(value, key)
                state["prompts"][key] = "answered"
                state["preference_sources"][key] = "user_preference"
        if constraints is not None:
            if not isinstance(constraints, dict) or len(serialize(constraints)) > 4000:
                raise ValidationError("constraints must be an object of at most 4000 serialized characters")
            state["constraints"].update(constraints)
            state.setdefault("constraint_sources", {}).update({key: "user" for key in constraints})
            state["prompts"]["constraints"] = "answered"
        if intent is not None:
            if intent not in INTENTS:
                raise ValidationError("Unknown onboarding intent")
            state["intent"] = intent
            state["prompts"]["intent"] = "answered"
        _save(conn, state)
    return state


def mark_prompt(field, state):
    if field not in {"intent", "companies", "roles", "constraints", "channels"} or state not in PROMPT_STATES:
        raise ValidationError("Unknown prompt field or state")
    with connect() as conn:
        value = _load(conn)
        value["prompts"][field] = state
        value.setdefault("preference_sources", {}).pop(field, None)
        _save(conn, value)
    return value


def set_channel_preference(provider, preference):
    provider = _text(provider, "provider", 80, empty=False)
    if preference not in PREFERENCES:
        raise ValidationError("Unknown channel preference")
    with connect() as conn:
        state = _load(conn)
        channel = state["channels"].setdefault(provider, {"connection": "not_connected"})
        channel.update(preference=preference, preference_updated_at=now())
        _save(conn, state)
    return {"provider": provider, **channel}


def set_channel_connection(provider, state, *, detail="", validation_receipt=None):
    provider = _text(provider, "provider", 80, empty=False)
    detail = _text(detail, "detail", 1000)
    if state not in CONNECTIONS:
        raise ValidationError("Unknown channel connection state")
    if state == "connected" and (not isinstance(validation_receipt, dict)
            or not validation_receipt.get("checked_at") or not validation_receipt.get("evidence")):
        raise ValidationError("connected requires a validation_receipt with checked_at and evidence")
    if validation_receipt is not None and (not isinstance(validation_receipt, dict)
            or len(serialize(validation_receipt)) > 3000):
        raise ValidationError("validation_receipt must be a small object without credentials")
    with connect() as conn:
        value = _load(conn)
        channel = value["channels"].setdefault(provider, {"preference": "unasked"})
        channel.update(connection=state, connection_detail=detail, connection_checked_at=now(),
                       validation_receipt=validation_receipt)
        _save(conn, value)
    return {"provider": provider, **channel}


def missing_prompts(*, before_search=False):
    """Return prompts once until answered, declined or explicitly deferred.

    Merely displaying a prompt is not an answer; a still-unanswered channel
    choice can therefore be raised again immediately before the first search.
    """
    value = status()
    questions = {"intent": "先简略盘点经历、探索方向，还是处理已有职位/公司/JD？",
                 "companies": "有目标公司吗？暂时没有也可以先探索。",
                 "roles": "有目标职位吗？暂时没有可从经历索引提出少量可修订方向。",
                 "constraints": "还有哪些地点、安排、实习/全职或排除条件需要补充？"}
    prompts = [{"field": field, "question": question} for field, question in questions.items()
               if value["prompts"].get(field, "unasked") == "unasked"
               and not (field in {"companies", "roles"} and value[field])]
    channel_answered = any(c.get("preference", "unasked") != "unasked" for c in value["channels"].values())
    if not channel_answered and value["prompts"].get("channels", "unasked") == "unasked":
        prompts.append({"field": "channels", "question": "是否现在配置并验证猎聘等可用渠道，或稍后接入、先用公开渠道和已有链接？",
                        "stage": "before_search" if before_search else "first_use"})
    intake = value.get("history_intake", {"answer": "unasked", "scope": []})
    if intake.get("answer", "unasked") == "unasked":
        prompts.append({"field": "history_intake", "question": "是否允许读取你指定的 Agent 对话/导出文件？可授权指定范围、稍后或拒绝；未授权前不会读取。",
                        "choices": ["allow", "later", "decline"]})
    if _scheduled_search_ready(value) and value.get("scheduled_search", "unasked") == "unasked":
        prompts.append({"field": "scheduled_search", "question": "经历索引和城市约束已可用。是否安排周期性岗位搜索？可选现在、稍后或不需要。",
                        "choices": ["now", "later", "no"]})
    return {"prompts": prompts, "known": {key: value[key] for key in ("intent", "companies", "roles", "constraints", "channels")},
            "default_next_step": "lightweight_experience_index", "blocks_search": False}


def _pause(state, reason):
    if state["current_topic"]:
        topic = state["current_topic"]
        topic.update(status="paused", pause_reason=reason)
        state["paused_branches"].append(topic)
        state["current_topic"] = None


def set_topic(topic, *, next_action="", blocker=""):
    topic = _text(topic, "topic", 200, empty=False)
    next_action = _text(next_action, "next_action")
    blocker = _text(blocker, "blocker")
    with connect() as conn:
        state = _load(conn)
        if state["current_topic"] and state["current_topic"]["title"] == topic:
            current = state["current_topic"]
        else:
            if len(state["paused_branches"]) >= 50:
                raise ValidationError("Too many paused branches; resume an existing branch first")
            _pause(state, "topic_switched")
            current = {"id": state["next_branch_id"], "title": topic, "created_at": now()}
            state["next_branch_id"] += 1
        current.update(status="active", next_action=next_action, blocker=blocker, updated_at=now())
        state["current_topic"] = current
        _save(conn, state)
    return current


def pause_topic(*, reason=""):
    reason = _text(reason, "reason")
    with connect() as conn:
        state = _load(conn)
        if state["current_topic"] and len(state["paused_branches"]) >= 50:
            raise ValidationError("Too many paused branches")
        _pause(state, reason)
        _save(conn, state)
    return {"current_topic": state["current_topic"], "paused_branches": state["paused_branches"]}


def resume_topic(branch_id):
    with connect() as conn:
        state = _load(conn)
        index = next((i for i, item in enumerate(state["paused_branches"]) if item["id"] == branch_id), None)
        if index is None:
            raise ValidationError("Paused branch not found")
        current = state["paused_branches"].pop(index)
        _pause(state, "topic_switched")
        current.pop("pause_reason", None)
        current.update(status="active", updated_at=now())
        state["current_topic"] = current
        _save(conn, state)
    return current


def continuation():
    value = status()
    return {key: value[key] for key in ("intent", "companies", "roles", "constraints", "channels",
                                       "current_topic", "paused_branches", "history_intake", "scheduled_search")}


def set_history_intake(answer, *, scope=None):
    """Record permission for later host-side reads; this function never opens files."""
    if answer not in {"allow", "later", "decline"}:
        raise ValidationError("history intake answer must be allow, later, or decline")
    scope = _strings(scope or [], "scope")
    if answer == "allow" and not scope:
        raise ValidationError("allow requires one or more explicit scope source paths")
    scope = [str(Path(item).expanduser().resolve()) for item in scope]
    with connect() as conn:
        state = _load(conn)
        state["history_intake"] = {"answer": answer, "scope": scope if answer == "allow" else [],
                                   "answered_at": now()}
        _save(conn, state)
    return state["history_intake"]


def _scheduled_search_ready(state):
    from .experience_library import list_current
    try:
        has_library = bool(list_current())
    except Exception:
        has_library = False
    constraints = state.get("constraints", {})
    has_location = any(key in constraints and constraints[key] for key in ("location", "target_locations", "city"))
    return has_library and has_location


def set_scheduled_search(answer):
    if answer not in {"now", "later", "no"}:
        raise ValidationError("scheduled search answer must be now, later, or no")
    with connect() as conn:
        state = _load(conn)
        state["scheduled_search"] = answer
        state["scheduled_search_answered_at"] = now()
        _save(conn, state)
    # Host task is a reusable request only; no automation is created here.
    return {"answer": answer, "host_task": {
        "requested": answer == "now", "max_new_tailored_resumes_per_day": 3,
        "create_automation": False,
        "reusable_task": ("Use the saved experience library and confirmed city/availability constraints to run a sourced job search; "
                          "report channels, failures and retrieval dates, shortlist evidence-fit roles, and prepare at most three new tailored "
                          "resume drafts per day for local review. Never submit applications or claim unconfirmed facts. Stay quiet while results "
                          "are unchanged; report only new matches, material changes, failures or required user action.") if answer == "now" else None}}
