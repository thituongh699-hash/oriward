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
        state.setdefault("scheduled_learning", "unasked")
        state.setdefault("discovery_offer", "unasked")
        state.setdefault("discovery_clues", [])
        state.setdefault("next_clue_id", 1)
        state.setdefault("history_reads", {})
        return state
    return {"version": 1, "intent": "experience_index", "companies": [], "roles": [],
            "constraints": {}, "prompts": {}, "channels": {}, "preference_sources": {}, "current_topic": None,
            "paused_branches": [], "next_branch_id": 1, "history_intake": {"answer": "unasked", "scope": []},
            "scheduled_search": "unasked", "scheduled_learning": "unasked",
            "discovery_offer": "unasked", "discovery_clues": [], "next_clue_id": 1, "history_reads": {}}


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


def missing_prompts(*, before_search=False, before_learning=False,
                    existing_resume=False, direct_search_and_apply=False):
    """Return prompts once until answered, declined or explicitly deferred.

    Merely displaying a prompt is not an answer; a still-unanswered channel
    choice can therefore be raised again immediately before the first search.
    """
    value = status()
    from .experience_library import list_current
    has_experience = bool(list_current())
    fast_track = before_search and existing_resume and direct_search_and_apply
    if not fast_track and (not has_experience or (not before_search and not before_learning and value["intent"] == "experience_index")):
        next_step = discovery_next(value, force=before_search or not has_experience)
        return {"prompts": [next_step["prompt"]] if next_step.get("prompt") else [],
                "known": {key: value[key] for key in ("intent", "companies", "roles", "constraints", "channels")},
                "default_next_step": "deep_experience_discovery", "blocks_search": False,
                "discovery": next_step}
    if before_learning:
        prompts = []
        if value["scheduled_learning"] == "unasked":
            prompts.append({"field": "scheduled_learning", "question": "是否定期回顾个人提升计划、提醒下一步并更新实际进度？可选现在、稍后或不需要。",
                            "choices": ["now", "later", "no"]})
        return {"prompts": prompts, "known": {"scheduled_learning": value["scheduled_learning"]},
                "default_next_step": "review_learning_progress", "blocks_search": False}
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
    if not fast_track and intake.get("answer", "unasked") == "unasked":
        prompts.append({"field": "history_intake", "question": "是否允许读取你指定的 Agent 对话/导出文件？可授权指定范围、稍后或拒绝；未授权前不会读取。",
                        "choices": ["allow", "later", "decline"]})
    if fast_track and value["discovery_offer"] == "unasked":
        prompts.append({"field": "discovery_offer", "question": "可以先用现有简历搜索和准备投递。是否也要深入挖掘经历、补建可持续复用的经历库？",
                        "choices": ["now", "later", "no"]})
    if (before_search or value["intent"] == "search") and value.get("scheduled_search", "unasked") == "unasked":
        prompts.append({"field": "scheduled_search", "question": "是否定期搜索新的求职机会并回报变化？可选现在、稍后或不需要。",
                        "choices": ["now", "later", "no"]})
    return {"prompts": prompts, "known": {key: value[key] for key in ("intent", "companies", "roles", "constraints", "channels")},
            "default_next_step": "direct_search_and_application" if fast_track else "continue_current_module", "blocks_search": False}


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
                                       "current_topic", "paused_branches", "history_intake", "scheduled_search",
                                       "scheduled_learning", "discovery_offer")}


CLUE_STATES = {"open", "answered", "later", "declined"}


def save_clue(*, title, question, reason, source, experience_id=None, priority=2):
    """Agent-selected recall lead, never an assertion of achievement."""
    title = _text(title, "title", 200, empty=False)
    question = _text(question, "question", 500, empty=False)
    reason = _text(reason, "reason", 500, empty=False)
    source = _text(source, "source", 1000, empty=False)
    if type(priority) is not int or priority not in (1, 2, 3):
        raise ValidationError("priority must be 1, 2 or 3")
    if experience_id is not None:
        from .experience_library import get
        if type(experience_id) is not int:
            raise ValidationError("experience_id must be an integer")
        get(experience_id)
    with connect() as conn:
        state = _load(conn)
        for clue in state["discovery_clues"]:
            if (clue["title"], clue["question"], clue.get("experience_id")) == (title, question, experience_id):
                return clue  # Never reopen a deferred or answered question on re-extraction.
        clue = {"id": state["next_clue_id"], "title": title, "question": question,
                "reason": reason, "source": source, "experience_id": experience_id,
                "priority": priority, "status": "open", "created_at": now(), "updated_at": now()}
        state["next_clue_id"] += 1
        state["discovery_clues"].append(clue)
        _save(conn, state)
    return clue


def set_clue_state(clue_id, status, *, note=""):
    if status not in CLUE_STATES:
        raise ValidationError("Unknown clue status")
    note = _text(note, "note", 1000)
    with connect() as conn:
        state = _load(conn)
        clue = next((row for row in state["discovery_clues"] if row["id"] == clue_id), None)
        if clue is None:
            raise ValidationError("Clue not found")
        clue.update(status=status, note=note, updated_at=now())
        _save(conn, state)
    return clue


def discovery_clues(*, offset=0, limit=10):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 50:
        raise ValidationError("offset >= 0 and limit between 1 and 50 required")
    clues = status()["discovery_clues"]
    items = clues[offset:offset + limit]
    next_offset = offset + len(items)
    return {"items": items, "total": len(clues), "next_offset": next_offset,
            "complete": next_offset >= len(clues)}


def record_history_read(receipt):
    """Keep only extraction progress, not chat bodies or semantic completion."""
    if receipt["source_filter"] not in {"user", "all"}:
        return
    with connect() as conn:
        state = _load(conn)
        path = receipt["source_file"]
        previous = state["history_reads"].get(path, {})
        signature = ("source_sha256", "source_filter", "query", "max_chars")
        same = all(previous.get(key) == receipt[key] for key in signature)
        covered = previous.get("next_offset", 0) if same else 0
        # A changed snapshot or extraction layout starts a fresh prefix. A
        # later page must not retain an older snapshot's completed receipt.
        next_offset = covered if receipt["offset"] > covered else max(covered, receipt["next_offset"])
        state["history_reads"][path] = {key: receipt[key] for key in signature}
        state["history_reads"][path].update(next_offset=next_offset,
                                             total_chunks=receipt["total_chunks"], read_at=now())
        _save(conn, state)


def discovery_next(state=None, *, force=False):
    """Suggest one question, not a questionnaire or a library-completion gate."""
    from .experience_library import list_current
    value = state if state is not None else status()
    current_ids = {row["id"] for row in list_current()}
    eligible = [row for row in value["discovery_clues"] if row["status"] == "open"
                and (row.get("experience_id") is None or row["experience_id"] in current_ids)]
    eligible.sort(key=lambda row: (row["priority"], row["id"]))
    result = {"open_count": len(eligible),
              "deferred_count": sum(row["status"] == "later" for row in value["discovery_clues"]),
              "library_complete": False, "clue_id": None, "prompt": None,
              "history_action": None}
    intake = value.get("history_intake", {})
    if intake.get("answer", "unasked") == "allow":
        pending = []
        for path in intake["scope"]:
            read = value["history_reads"].get(path)
            if read is None or read["next_offset"] < read["total_chunks"]:
                pending.append({"file": path, "offset": read["next_offset"] if read else 0,
                                "source": read["source_filter"] if read else "user",
                                "query": read["query"] if read else "",
                                "max_chars": read["max_chars"] if read else 12000})
        if pending:
            result["history_action"] = {"action": "extract_authorized_history", "files": pending,
                                        "rule": "Read the next page, save clear self-reports and recall clues; extraction is not semantic verification."}
    if value["intent"] != "experience_index" and value["discovery_offer"] != "now" and not force:
        result["next_action"] = "follow_current_task"
        return result
    if eligible:
        clue = eligible[0]
        result.update(clue_id=clue["id"], next_action="ask_one_question",
                      prompt={"field": "experience_clue", "question": clue["question"],
                              "reason": clue["reason"], "experience_id": clue.get("experience_id")})
    elif intake.get("answer", "unasked") == "unasked":
        result.update(next_action="offer_history_recovery", prompt={"field": "history_intake",
                      "question": "为了先帮你搭起经历库，是否允许从你指定的历史聊天或导出文件开始整理？也可以稍后或直接聊。",
                      "choices": ["allow", "later", "decline"]})
    elif result["history_action"]:
        result["next_action"] = "review_authorized_history_and_existing_library"
    elif not current_ids and not value["discovery_clues"]:
        result.update(next_action="start_from_story", prompt={"field": "experience_story",
                      "question": "先从你愿意聊的一段经历开始：有没有一件主要由你负责或推动的事？工作、学习、帮家里做事都算。"})
    else:
        result["next_action"] = "summarize_known_experiences_offer_next_topic_or_pause"
    return result


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


def set_discovery_offer(answer):
    if answer not in {"now", "later", "no"}:
        raise ValidationError("discovery offer answer must be now, later, or no")
    with connect() as conn:
        state = _load(conn)
        state["discovery_offer"] = answer
        state["discovery_offer_answered_at"] = now()
        _save(conn, state)
    return {"answer": answer, "next_action": "intake next" if answer == "now" else None}


def _set_schedule(kind, answer):
    if answer not in {"now", "later", "no"}:
        raise ValidationError("schedule answer must be now, later, or no")
    field = f"scheduled_{kind}"
    with connect() as conn:
        state = _load(conn)
        state[field] = answer
        state[f"{field}_answered_at"] = now()
        _save(conn, state)
    search = kind == "search"
    return {"answer": answer, "host_task": {
        "requested": answer == "now", "max_new_tailored_resumes_per_day": 3 if search else 0,
        "create_automation": False,
        "setup": ("Check the user's actual environment and available scheduling tools; agree on frequency, time, timezone and scope. "
                  "If a calendar is available or deadlines make it useful, ask whether to link it before creating calendar events. "
                  "Do not claim an automation or calendar link exists until the host confirms creation.") if answer == "now" else None,
        "reusable_task": (("Use the available resume, saved experience library and confirmed city/availability constraints to run a sourced job search; "
                          "report channels, failures and retrieval dates, shortlist evidence-fit roles, and prepare at most three new tailored "
                          "resume drafts per day for local review. Include a sourced resume market-report when enough distinct JDs exist; "
                          "treat its patterns as candidate market observations, never as user skills or automatic profile updates. "
                          "Never submit applications or claim unconfirmed facts. Stay quiet while results "
                          "are unchanged; report only new matches, material changes, failures or required user action.") if search else
                          ("Review the user's current learning plan, actual milestones and capacity; ask for progress rather than assuming completion. "
                           "If a sourced resume market-report shows repeated new role requirements, offer a focused practice or resume review. "
                           "Report the next practical step, blockers and any needed plan adjustment; record updates only from user-confirmed activity."))
                         if answer == "now" else None}}


def set_scheduled_search(answer):
    return _set_schedule("search", answer)


def set_scheduled_learning(answer):
    return _set_schedule("learning", answer)
