"""Deterministic CareerOS operations. No LLM dependency and no external submissions."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from .db import PROJECT_ROOT, connect, serialize, deserialize, audit, now, one, database_path


class ValidationError(ValueError):
    pass


def validate_dict(value, required: list[str]):
    if not isinstance(value, dict):
        raise ValidationError("Expected JSON object")
    for key in required:
        if key not in value or value[key] is None or (isinstance(value[key], str) and not value[key].strip()):
            raise ValidationError(f"Missing required field: {key}")
    return value


def json_file(filepath):
    with Path(filepath).open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_profile(data):
    validate_dict(data, ["display_name"])
    from .core import assertions
    from .core.profile import IDENTITY_FIELDS

    list_fields = {
        "values": ("user", "value", "value"),
        "preferences": ("user", "preference", "preference"),
        "hard_constraints": ("work_conditions", "hard_constraint", "constraint"),
        "constraints": ("work_conditions", "hard_constraint", "constraint"),
        "skills": ("user", "has_skill", "skill_hypothesis"),
    }
    # The compatibility cache and all assertions change in one transaction.
    with connect() as db:
        row = db.execute("SELECT data FROM profile WHERE id=1").fetchone()
        previous = deserialize(row["data"]) if row else {}
        merged = {**previous, **data}
        for key, (subject, predicate, assertion_type) in list_fields.items():
            old_items = previous.get(key) or []
            new_items = data.get(key, old_items)
            if not isinstance(new_items, list):
                raise ValidationError(f"{key} must be an array")
            old_json = {serialize(v) for v in old_items}
            if not old_json.issubset({serialize(v) for v in new_items}):
                raise ValidationError(f"{key} is append-only here; use belief retract/revise to change an item")
            for item in new_items:
                value = item if isinstance(item, dict) else {"text": str(item).strip()}
                if not value or value == {"text": ""}:
                    raise ValidationError(f"{key} contains an empty claim")
                claim_key = assertions.dedupe_key(subject, predicate, value, assertion_type)
                matching = db.execute("SELECT * FROM user_assertions WHERE dedupe_key=? ORDER BY id DESC LIMIT 1",
                                      (claim_key,)).fetchone()
                if matching:
                    # Repeated cached uploads never resurrect old judgments.
                    if matching["valid_to"] or matching["epistemic_status"] == "retracted":
                        continue
                    continue
                assertions.propose(subject=subject, predicate=predicate, value=value,
                                   assertion_type=assertion_type, source_type="user_message", unique=False,
                                   source_ref="profile:1", explanation="用户通过 profile 提交的陈述", conn=db)
            merged[key] = new_items

        for field in IDENTITY_FIELDS:
            if field not in data:
                continue
            raw = data[field]
            if raw in (None, "", [], {}):
                raise ValidationError(f"{field} cannot be empty; use belief retract to remove it")
            value = raw if isinstance(raw, (dict, list)) else {"text": str(raw).strip()}
            records = db.execute(
                "SELECT * FROM user_assertions WHERE subject='user' AND predicate=? ORDER BY id DESC",
                (field,)).fetchall()
            current = next((r for r in records if not r["valid_to"] and r["epistemic_status"] != "retracted"), None)
            if current is not None:
                if deserialize(current["value_json"]) == value:
                    continue
                if field in previous and raw == previous[field]:
                    raise ValidationError(f"{field} conflicts with a newer Core correction; use belief revise explicitly")
                assertions.revise(current["id"], value=value, source_type="user_message",
                                  explanation="用户通过 profile 修订身份字段", reason="profile identity update", conn=db)
            else:
                claim_key = assertions.dedupe_key("user", field, value, "fact")
                if any(r["dedupe_key"] == claim_key for r in records):
                    raise ValidationError(f"{field} matches a retracted historical value; use belief propose explicitly")
                assertions.propose(subject="user", predicate=field, value=value, assertion_type="fact",
                                   source_type="user_message", source_ref="profile:1",
                                   explanation="用户通过 profile 提交的身份字段", conn=db)
        db.execute("INSERT INTO profile(id,data,updated_at) VALUES (1,?,?) "
                   "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                   (serialize(merged), now()))
        audit(db, "profile.updated", "profile", 1)
    return 1


def get_profile():
    with connect() as db:
        from .core.profile import read_profile
        return read_profile(db)


def add_object(table, data, required):
    allowed = {"experiences", "career_directions", "job_analyses", "learning_plans", "interviews"}
    if table not in allowed:
        raise ValidationError("Unsupported writable object type")
    validate_dict(data, required)
    with connect() as db:
        if table == "experiences":
            if not isinstance(data.get("approved_for_resume"), bool):
                raise ValidationError("Experience must include approved_for_resume (true or false)")
            for key in ("actions", "outcomes", "evidence"):
                if key not in data or not isinstance(data[key], list):
                    raise ValidationError(f"Experience requires {key} array")
            for ev in data["evidence"]:
                validate_dict(ev, ["claim", "source", "status"])
                if ev["status"] not in ("user_confirmed", "document_verified", "unverified"):
                    raise ValidationError("Evidence status invalid")
        if table == "career_directions":
            check_exp_ids(db, data.get("supporting_experience_ids", []))
        if table == "learning_plans":
            for job_id in data.get("job_ids", []):
                one(db, "jobs", int(job_id))
        if table == "job_analyses":
            one(db, "jobs", int(data["job_id"]))
            if data["recommendation"] not in ("explore", "apply", "upskill", "skip"):
                raise ValidationError("recommendation must be explore|apply|upskill|skip")
            if data["confidence"] not in ("low", "medium", "high"):
                raise ValidationError("confidence must be low|medium|high")
            for item in data.get("strengths", []):
                check_exp_ids(db, item.get("experience_ids", []))
        if table == "interviews":
            one(db, "jobs", int(data["job_id"]))
            for item in data.get("practice", []):
                check_exp_ids(db, item.get("evidence_ids", []))
        job_id = int(data["job_id"]) if table in ("job_analyses", "interviews") else None
        if job_id is None:
            cursor = db.execute(f"INSERT INTO {table}(data,created_at) VALUES (?,?)", (serialize(data), now()))
        else:
            cursor = db.execute(f"INSERT INTO {table}(job_id,data,created_at) VALUES (?,?,?)", (job_id, serialize(data), now()))
        result = cursor.lastrowid
        audit(db, f"{table}.created", table, result)
        return result


def check_exp_ids(db, ids):
    if not isinstance(ids, list):
        raise ValidationError("experience IDs must be an array")
    for exp_id in ids:
        one(db, "experiences", int(exp_id))


def list_objects(table):
    allowed = {"experiences", "career_directions", "jobs", "job_analyses", "resumes", "applications", "learning_plans", "interviews"}
    if table not in allowed:
        raise ValidationError("Unsupported list object type")
    with connect() as db:
        rows = db.execute(f"SELECT * FROM {table} ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]


def clean_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    p = urlsplit(url)
    if p.scheme not in {"http", "https"} or not p.netloc:
        raise ValidationError("Only http(s) job URLs are accepted")
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), urlencode(q), ""))


def source_key(d):
    source = str(d.get("source", "")).strip().casefold()
    ref = str(d.get("source_id", "")).strip()
    url = clean_url(d.get("url", ""))
    if ref:
        return f"{source}:id:{ref}"
    if url:
        return f"{source}:url:{url}"
    raw = "|".join(str(d.get(k, "")).strip().casefold() for k in ("title", "company", "location"))
    return f"{source}:fallback:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"


def import_jobs(filepath):
    added = 0
    duplicates = 0
    with Path(filepath).open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) > 10000:
        raise ValidationError("Limit 10,000 jobs per import")
    with connect() as db:
        for i, raw in enumerate(rows, start=2):
            try:
                d = validate_dict(raw, ["source", "title", "company", "description"])
                d = {k: (v or "").strip() for k, v in d.items()}
                d["url"] = clean_url(d.get("url", ""))
                key = source_key(d)
            except ValueError as e:
                raise ValidationError(f"Row {i}: {e}") from e
            result = db.execute("INSERT OR IGNORE INTO jobs(source_key,title,company,url,data,created_at) VALUES (?,?,?,?,?,?)",
                                (key, d["title"], d["company"], d["url"], serialize(d), now()))
            if result.rowcount:
                added += 1
                audit(db, "jobs.imported", "jobs", result.lastrowid)
            else:
                duplicates += 1
    return {"added": added, "duplicate": duplicates}


def get_job(job_id):
    with connect() as db:
        return deserialize(one(db, "jobs", job_id)["data"])


def build_resume(job_id, experience_ids, headline=""):
    if not experience_ids:
        raise ValidationError("Select at least one approved experience")
    experience_ids = list(dict.fromkeys(int(x) for x in experience_ids))
    profile = get_profile()
    if not profile or not profile.get("display_name"):
        raise ValidationError("Save a current user-backed display_name before building a resume")
    with connect() as db:
        job = one(db, "jobs", job_id)
        job_data = deserialize(job["data"])
        experiences = []
        for exp_id in experience_ids:
            d = deserialize(one(db, "experiences", exp_id)["data"])
            if not d.get("approved_for_resume"):
                raise ValidationError(f"Experience {exp_id} not approved for resume")
            if not d.get("evidence"):
                raise ValidationError(f"Experience {exp_id} requires nonempty verified evidence")
            for item in d.get("evidence", []):
                if item.get("status") == "unverified":
                    raise ValidationError(f"Experience {exp_id} has unverified evidence; resolve before resume use")
            experiences.append((exp_id, d))
        person = profile["display_name"].strip()
        contact = profile.get("contact", {})
        lines = [f"# {person}", ""]
        contact_items = [str(contact.get(k, "")).strip() for k in ("email", "phone", "portfolio")]
        if any(contact_items):
            lines += [" · ".join(x for x in contact_items if x), ""]
        if profile.get("summary_verified"):
            lines += ["## 个人简介", str(profile["summary_verified"]), ""]
        if headline:
            lines += [f"*申请方向：{headline}*", ""]
        lines += ["## 相关经历", ""]
        for exp_id, e in experiences:
            lines += [f"### {e['event']}", ""]
            if e.get("context"):
                lines += [str(e["context"]), ""]
            bullets = list(e.get("actions", [])) + list(e.get("outcomes", []))
            for bullet in bullets:
                if str(bullet).strip():
                    lines.append(f"- {str(bullet).strip()}")
            lines.append("")
        lines += ["---", "", f"*来源记录：岗位 {job_id}（{job_data['company']} / {job_data['title']}）；经历 ID {', '.join(map(str, experience_ids))}。*", "*发布/投递前请人工核对内容；未经证实的推断不应当写入简历。*", ""]
        content = "\n".join(lines)
        with db:
            name = re.sub(r"[^a-zA-Z0-9_-]", "-", f"{job_data['company']}-{job_data['title']}")[:45].strip("-") or "job"
            output_dir = resume_output_dir()
            output_dir.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            # ID generated before output_path is updated to ensure stable filename
            cursor = db.execute("INSERT INTO resumes(job_id,experience_ids,output_path,sha256,created_at) VALUES (?,?,?,?,?)",
                                (job_id, serialize(experience_ids), "PENDING", digest, now()))
            resume_id = cursor.lastrowid
            path = output_dir / f"resume_{resume_id}_{name}.md"
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
            db.execute("UPDATE resumes SET output_path=? WHERE id=?", (str(path.resolve()), resume_id))
            audit(db, "resume.built", "resumes", resume_id)
            return {"id": resume_id, "path": str(path), "sha256": digest}


def _validate_channel(channel):
    from .discovery import APPLY_CHANNELS
    if channel in (None, ""):
        return ""
    if channel not in APPLY_CHANNELS:
        raise ValidationError("channel must be one of " + ", ".join(sorted(APPLY_CHANNELS)))
    return channel


def prepare_application(job_id, resume_id, channel="", apply_url=""):
    from .discovery import APPLY_CHANNELS
    with connect() as db:
        job = one(db, "jobs", job_id)
        resume = one(db, "resumes", resume_id)
        if resume["job_id"] != job_id:
            raise ValidationError("Resume does not match job")
        verify_resume(resume)
        # Legacy base resumes already contain approved wording. New revisions
        # may contain unconfirmed rephrasing and must not enter a packet yet.
        from .feedback import ensure_schema
        ensure_schema(db)
        version = db.execute("SELECT factual_status FROM resume_versions WHERE resume_id=?", (resume_id,)).fetchone()
        if version and version["factual_status"] != "approved":
            raise ValidationError("Revision wording requires user factual confirmation before application preparation")
        job_data = deserialize(job["data"])
        if channel:
            channel = _validate_channel(channel)
        else:
            # A provider that is not an application channel (aggregators, fixtures)
            # stays unknown instead of being silently mislabelled.
            source = job_data.get("source", "")
            channel = source if source in APPLY_CHANNELS else ""
        apply_url = clean_url(apply_url or job_data.get("apply_url") or job["url"] or "")
        cursor = db.execute(
            "INSERT INTO applications(job_id,resume_id,status,note,external_reference,channel,apply_url,applied_at,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (job_id, resume_id, "READY_FOR_USER", "", "", channel, apply_url, "", now(), now()))
        aid = cursor.lastrowid
        audit(db, "application.prepared", "applications", aid, channel)
        return aid


def repeat_application_hints(job_id):
    """Report applications already made in the same candidate vacancy group.

    Purely informational: the user decides whether a second channel is a
    duplicate application, and nothing here blocks that decision.
    """
    from . import tracking
    card = tracking.job_card(job_id)
    risk = card["repeat_application_risk"]
    return {"same_vacancy_channels": card["channels"],
            "already_applied_in_group": risk["already_applied_in_group"],
            "decision": risk["decision"], "note": risk["note"]}



def resume_output_dir():
    override = os.environ.get("CAREEROS_OUTPUT_DIR")
    if override:
        return Path(override).expanduser().resolve()
    # An isolated database must never overwrite the real user's resume files.
    if os.environ.get("CAREEROS_DB"):
        return database_path().parent / "outputs" / "resumes"
    return PROJECT_ROOT / "outputs" / "resumes"


def resume_path(row):
    path = Path(row["output_path"])
    return path if path.is_absolute() else PROJECT_ROOT / path


def verify_resume(row):
    path = resume_path(row)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
        raise ValidationError("Resume file missing or changed; register a new revision instead of editing a saved version")
    return path


TRANSITIONS = {
    "READY_FOR_USER": {"SUBMITTED", "WITHDRAWN"},
    "SUBMITTED": {"INTERVIEW", "REJECTED", "WITHDRAWN"},
    "INTERVIEW": {"OFFER", "REJECTED", "WITHDRAWN"},
    "OFFER": {"ACCEPTED", "DECLINED"},
    "REJECTED": set(), "WITHDRAWN": set(), "ACCEPTED": set(), "DECLINED": set(),
}


_STATUS_EVENT = {
    "SUBMITTED": "applied", "INTERVIEW": "interview", "OFFER": "offer",
    "REJECTED": "rejection", "WITHDRAWN": "withdrawal",
}


def update_application(application_id, next_status, *, human_confirmed=False, note="", external_reference="", channel=""):
    next_status = next_status.upper()
    with connect() as db:
        row = one(db, "applications", application_id)
        if next_status not in TRANSITIONS.get(row["status"], set()):
            raise ValidationError(f"Transition {row['status']} -> {next_status} not allowed")
        if next_status == "SUBMITTED" and not human_confirmed:
            raise ValidationError("Only record a submission after the user confirms actual external submission; pass --human-confirmed")
        channel = _validate_channel(channel) if channel else (row["channel"] or "")
        applied_at = row["applied_at"] or (now() if next_status == "SUBMITTED" else "")
        db.execute("UPDATE applications SET status=?,note=?,external_reference=?,channel=?,applied_at=?,updated_at=? WHERE id=?",
                   (next_status, note, external_reference, channel, applied_at, now(), application_id))
        kind = _STATUS_EVENT.get(next_status, "note")
        # Immutable transition record: applications.status stays a rebuildable
        # projection of these events, and the human confirmation is preserved.
        db.execute(
            "INSERT INTO application_events(application_id,kind,label,scheduled_at,occurred_at,data,created_at,"
            "from_status,to_status,human_confirmed,evidence_ref) VALUES (?,?,?,'',?,?,?,?,?,?,?)",
            (application_id, kind, next_status, now(),
             serialize({"status": next_status, "note": note}), now(),
             row["status"], next_status, 1 if human_confirmed else 0, external_reference))
        audit(db, "application.status_changed", "applications", application_id, f"{row['status']}->{next_status}")
        return next_status


def set_application_channel(application_id, channel, apply_url=""):
    """Backfill which platform an application actually went through."""
    channel = _validate_channel(channel)
    if not channel:
        raise ValidationError("channel must be one of the supported application channels")
    with connect() as db:
        row = one(db, "applications", application_id)
        url = clean_url(apply_url) if apply_url else row["apply_url"]
        db.execute("UPDATE applications SET channel=?,apply_url=?,updated_at=? WHERE id=?", (channel, url, now(), application_id))
        audit(db, "application.channel_set", "applications", application_id, channel)
        return {"id": application_id, "channel": channel, "apply_url": url}



def summary():
    from .sources import ensure_source_schema
    from .assessment import _ensure_review_table
    from .feedback import ensure_schema
    tables = ("experiences", "career_directions", "jobs", "job_analyses", "resumes", "applications", "learning_plans", "interviews",
              "job_source_snapshots", "hiring_reviews", "resume_versions", "recruiting_feedback",
              "vacancy_groups", "job_group_members", "application_events")
    with connect() as db:
        ensure_source_schema(db)
        _ensure_review_table(db)
        ensure_schema(db)
        counts = {name: db.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"] for name in tables}
        statuses = {r["status"]: r["n"] for r in db.execute("SELECT status,COUNT(*) AS n FROM applications GROUP BY status")}
        feedback_open = db.execute("SELECT COUNT(*) FROM recruiting_feedback WHERE status='open'").fetchone()[0]
        return {"counts": counts, "application_status": statuses, "open_feedback": feedback_open}
