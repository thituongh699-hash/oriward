"""Unified vacancy and application record.

One place answers: what was published, where it exists, which channel was used,
what the timeline is, and what came back. Grouping across platforms is
deterministic and informational only — repeating an application is the user's
decision, never a blocked action.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone

from .db import audit, connect, deserialize, now, one, serialize
from .services import ValidationError
from . import sources

GROUP_RULE = "company+title+location 归一化后哈希；属于候选归并，不是同一岗位的证明"

EVENT_KINDS = {
    "applied", "written_test", "interview", "follow_up", "offer", "rejection", "withdrawal", "note",
}
_APPLIED_STATES = {"SUBMITTED", "INTERVIEW", "OFFER", "ACCEPTED"}

_BRACKET_RE = re.compile(r"[【\[（(]([^】\]）)]{1,16})[】\]）)]")
_BRACKET_NOISE = ("急招", "急聘", "热招", "高薪", "猎头", "招聘中", "长期有效", "new")
_TITLE_SUFFIX_RE = re.compile(r"(招聘|急聘|热招)$")
_COMPANY_SUFFIXES = ("股份有限公司", "有限责任公司", "有限公司", "股份公司", "集团有限公司", "集团", "公司")
_LOCATION_SPLIT_RE = re.compile(r"[、,，/|;；\s]+")
_ADMIN_SUFFIX_RE = re.compile(r"(特别行政区|自治区|自治州|市|省)$")
_DROP_RE = re.compile(r"[\s\-_·•・,，。;；:：/\\|、（）()\[\]【】]+")


def _id(value, name="id"):
    if type(value) is not int or value < 1:
        raise ValidationError(f"{name} must be a positive integer")
    return value


def _strip_noise_brackets(text: str) -> str:
    def repl(match):
        inner = match.group(1)
        return "" if any(word in inner.casefold() for word in _BRACKET_NOISE) else match.group(0)

    return _BRACKET_RE.sub(repl, text)


def normalize_company(value: str) -> str:
    text = _DROP_RE.sub("", _strip_noise_brackets(unicodedata.normalize("NFKC", str(value or "")).casefold()))
    for suffix in _COMPANY_SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
            break
    return text


def normalize_title(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = _DROP_RE.sub("", _strip_noise_brackets(text))
    return _TITLE_SUFFIX_RE.sub("", text)


def normalize_location(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    first = _LOCATION_SPLIT_RE.split(text)[0] if text else ""
    return _ADMIN_SUFFIX_RE.sub("", _DROP_RE.sub("", first.casefold()))


def vacancy_key(company: str, title: str, location: str = "") -> tuple[str, str, str, str]:
    company_norm, title_norm, location_norm = normalize_company(company), normalize_title(title), normalize_location(location)
    raw = "\x1f".join((company_norm, title_norm, location_norm))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24], company_norm, title_norm, location_norm


def _rebuild(db) -> dict:
    rows = db.execute("SELECT id, title, company, data FROM jobs WHERE source_key NOT LIKE 'oriward:resume-context:%'").fetchall()
    placed = 0
    for row in rows:
        job = deserialize(row["data"])
        key, company_norm, title_norm, location_norm = vacancy_key(
            row["company"] or job.get("company", ""), row["title"] or job.get("title", ""), job.get("location", ""))
        existing = db.execute("SELECT id FROM vacancy_groups WHERE group_key=?", (key,)).fetchone()
        if existing is None:
            group_id = db.execute(
                "INSERT INTO vacancy_groups(group_key,company_norm,title_norm,location_norm,created_at) VALUES (?,?,?,?,?)",
                (key, company_norm, title_norm, location_norm, now())).lastrowid
        else:
            group_id = existing["id"]
        db.execute("INSERT INTO job_group_members(job_id,group_id,created_at) VALUES (?,?,?) "
                   "ON CONFLICT(job_id) DO UPDATE SET group_id=excluded.group_id",
                   (row["id"], group_id, now()))
        placed += 1
    db.execute("DELETE FROM job_group_members WHERE job_id NOT IN (SELECT id FROM jobs)")
    db.execute("DELETE FROM vacancy_groups WHERE id NOT IN (SELECT group_id FROM job_group_members)")
    return {"grouped_jobs": placed}


def regroup() -> dict:
    with connect() as db:
        return _rebuild(db)


def _ensure_groups(db) -> None:
    jobs = db.execute("SELECT COUNT(*) FROM jobs WHERE source_key NOT LIKE 'oriward:resume-context:%'").fetchone()[0]
    members = db.execute("SELECT COUNT(*) FROM job_group_members").fetchone()[0]
    if jobs != members:
        _rebuild(db)


def _ts(value, name, *, future_ok=False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValidationError(f"{name} must include a timezone")
    if not future_ok and parsed > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValidationError(f"{name} cannot be in the future")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def log_event(application_id, kind, label="", *, scheduled_at="", occurred_at="", data=None) -> int:
    application_id = _id(application_id, "application_id")
    if kind not in EVENT_KINDS:
        raise ValidationError("kind must be one of " + "|".join(sorted(EVENT_KINDS)))
    if not isinstance(label, str) or len(label) > 200:
        raise ValidationError("label must be text of at most 200 characters")
    if scheduled_at:
        scheduled_at = _ts(scheduled_at, "scheduled_at", future_ok=True)
    if occurred_at:
        occurred_at = _ts(occurred_at, "occurred_at")
    if not scheduled_at and not occurred_at:
        occurred_at = now()
    with connect() as db:
        one(db, "applications", application_id)
        event_id = db.execute(
            "INSERT INTO application_events(application_id,kind,label,scheduled_at,occurred_at,data,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (application_id, kind, label.strip(), scheduled_at, occurred_at,
             serialize(data or {}), now())).lastrowid
        audit(db, "application.event", "application_events", event_id, kind)
    return event_id


def list_events(application_id) -> list[dict]:
    application_id = _id(application_id, "application_id")
    with connect() as db:
        one(db, "applications", application_id)
        rows = db.execute("SELECT * FROM application_events WHERE application_id=? ORDER BY id", (application_id,)).fetchall()
        return [_event_row(row) for row in rows]


def _event_row(row) -> dict:
    return {
        "id": row["id"], "kind": row["kind"], "label": row["label"],
        "scheduled_at": row["scheduled_at"] or None, "occurred_at": row["occurred_at"] or None,
        "data": deserialize(row["data"]) if row["data"] else {}, "created_at": row["created_at"],
    }


def _feedback_rows(db, job_id: int) -> list[dict]:
    try:
        rows = db.execute("SELECT * FROM recruiting_feedback WHERE job_id=? ORDER BY id", (job_id,)).fetchall()
    except sqlite3.OperationalError:
        return []
    return [{"id": r["id"], "application_id": r["application_id"], "kind": deserialize(r["data"]).get("kind"),
             "stage": deserialize(r["data"]).get("stage"), "outcome": deserialize(r["data"]).get("outcome"),
             "observation": deserialize(r["data"]).get("observation"), "status": r["status"],
             "observed_at": deserialize(r["data"]).get("observed_at")} for r in rows]


def _application_rows(db, job_id: int) -> list[dict]:
    apps = db.execute("SELECT * FROM applications WHERE job_id=? ORDER BY id", (job_id,)).fetchall()
    result = []
    for row in apps:
        resume = db.execute("SELECT id, sha256, output_path FROM resumes WHERE id=?", (row["resume_id"],)).fetchone()
        events = db.execute("SELECT * FROM application_events WHERE application_id=? ORDER BY id", (row["id"],)).fetchall()
        result.append({
            "id": row["id"],
            "channel": row["channel"] or "",
            "status": row["status"],
            "applied_at": row["applied_at"] or None,
            "apply_url": row["apply_url"] or "",
            "resume_id": row["resume_id"],
            "resume_sha256": resume["sha256"] if resume else "",
            "event_count": len(events),
            "last_note": row["note"] or "",
            "updated_at": row["updated_at"],
        })
    return result


def _group_members(db, job_id: int) -> tuple:
    group = db.execute(
        "SELECT g.* FROM vacancy_groups g JOIN job_group_members m ON m.group_id=g.id WHERE m.job_id=?", (job_id,)
    ).fetchone()
    if group is None:
        return None, []
    rows = db.execute(
        "SELECT j.id, j.title, j.company, j.url, j.data FROM job_group_members m "
        "JOIN jobs j ON j.id=m.job_id WHERE m.group_id=? ORDER BY j.id", (group["id"],)
    ).fetchall()
    return group, rows


def job_card(job_id) -> dict:
    """The single record for one vacancy: JD, channels, applications, timeline."""
    job_id = _id(job_id, "job_id")
    with connect() as db:
        row = one(db, "jobs", job_id)
        job = deserialize(row["data"])
        _ensure_groups(db)
        group, members = _group_members(db, job_id)

        channels, applied_elsewhere = [], []
        for member in members:
            data = deserialize(member["data"])
            member_apps = _application_rows(db, member["id"])
            channels.append({
                "job_id": member["id"],
                "channel": data.get("source", ""),
                "url": member["url"],
                "apply_url": data.get("apply_url") or member["url"],
                "published_at": data.get("published_at") or data.get("listed_at"),
                "availability": data.get("availability", "unknown"),
                "retrieved_at": data.get("retrieved_at"),
                "applications": len(member_apps),
            })
            for app in member_apps:
                if app["status"] in _APPLIED_STATES:
                    applied_elsewhere.append({"job_id": member["id"], "channel": app["channel"] or data.get("source", ""),
                                              "application_id": app["id"], "status": app["status"],
                                              "applied_at": app["applied_at"]})
        channels.sort(key=lambda item: (item["channel"] != job.get("source"), item["job_id"]))

        applications = _application_rows(db, job_id)
        for app in applications:
            events = db.execute("SELECT * FROM application_events WHERE application_id=? ORDER BY id",
                                (app["id"],)).fetchall()
            app["timeline"] = [_event_row(event) for event in events]
        feedback = _feedback_rows(db, job_id)

        published = job.get("published_at") or job.get("listed_at")
        gaps = []
        if not published:
            gaps.append("published_at_missing")
        if not str(job.get("description", "")).strip():
            gaps.append("description_empty")
        if any(not app["channel"] for app in applications):
            gaps.append("application_channel_missing")
        if any(not app["apply_url"] for app in applications):
            gaps.append("apply_url_missing")

        return {
            "job": {
                "id": job_id,
                "title": job.get("title", row["title"]),
                "company": job.get("company", row["company"]),
                "location": job.get("location", ""),
                "published_at": published,
                "published_at_source": "published_at" if job.get("published_at") else ("listed_at" if job.get("listed_at") else "unknown"),
                "retrieved_at": job.get("retrieved_at"),
                "availability": job.get("availability", "unknown"),
                "freshness": sources.freshness(job)["status"],
                "evidence_level": job.get("evidence_level", "full_jd"),
                "source": job.get("source", ""),
                "url": row["url"],
                "valid_through": job.get("valid_through", ""),
            },
            "jd": {
                "characters": len(str(job.get("description", ""))),
                "full_text": str(job.get("description", "")),
            },
            "vacancy_group": {
                "id": group["id"] if group else None,
                "key": group["group_key"] if group else None,
                "rule": GROUP_RULE,
                "members": len(members),
            },
            "channels": channels,
            "applications": applications,
            "feedback": feedback,
            "repeat_application_risk": {
                "already_applied_in_group": applied_elsewhere,
                "decision": "user_decides",
                "note": "同一候选岗位组内已有投递记录，仅供判断；系统不拦截也不自动去重。",
            },
            "gaps": gaps,
            "next_commands": _next_commands(job_id, applications, job),
        }


def _next_commands(job_id: int, applications: list[dict], job: dict) -> list[str]:
    commands = []
    if not applications:
        commands.append(f"analysis draft --job-id {job_id}")
        commands.append(f"resume build --job-id {job_id} --experience-ids <ids>")
        commands.append(f"application prepare --job-id {job_id} --resume-id <resume-id> --channel <channel>")
    else:
        latest = applications[-1]
        if latest["status"] == "READY_FOR_USER":
            commands.append(f"application record --id {latest['id']} --status SUBMITTED --human-confirmed")
        elif latest["status"] in {"SUBMITTED", "INTERVIEW"}:
            commands.append(f'application event --id {latest["id"]} --kind interview --label "一面" --scheduled-at <ISO时间>')
        if not latest["channel"]:
            commands.append(f"application channel --id {latest['id']} --channel <channel>")
    return commands


def agenda(days: int = 30) -> dict:
    """Upcoming schedule nodes plus applications still waiting for the user."""
    if type(days) is not int or not 1 <= days <= 365:
        raise ValidationError("days must be an integer from 1 to 365")
    horizon = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")
    with connect() as db:
        try:
            rows = db.execute(
                "SELECT e.*, a.job_id, a.status, a.channel, j.title, j.company FROM application_events e "
                "JOIN applications a ON a.id=e.application_id JOIN jobs j ON j.id=a.job_id "
                "WHERE e.scheduled_at != '' AND e.scheduled_at >= ? AND e.scheduled_at <= ? ORDER BY e.scheduled_at",
                (now(), horizon)).fetchall()
        except sqlite3.OperationalError:
            rows = []
        scheduled = [{**_event_row(row), "application_id": row["application_id"], "job_id": row["job_id"],
                      "job": f"{row['company']} / {row['title']}", "status": row["status"],
                      "channel": row["channel"]} for row in rows]
        waiting = db.execute("SELECT id, job_id FROM applications WHERE status='READY_FOR_USER' ORDER BY id").fetchall()
        pending = []
        for row in waiting:
            job = db.execute("SELECT title, company FROM jobs WHERE id=?", (row["job_id"],)).fetchone()
            pending.append({"application_id": row["id"], "job_id": row["job_id"],
                            "job": f"{job['company']} / {job['title']}" if job else ""})
    return {"window_days": days, "scheduled": scheduled, "awaiting_submission": pending}


def _multi_groups(db, limit=30) -> list[dict]:
    groups = db.execute(
        "SELECT g.id, g.group_key, g.company_norm, g.title_norm, COUNT(m.job_id) AS n "
        "FROM vacancy_groups g JOIN job_group_members m ON m.group_id=g.id "
        "GROUP BY g.id HAVING n > 1 ORDER BY n DESC, g.id LIMIT ?", (limit,)).fetchall()
    multi = []
    for group in groups:
        members = db.execute(
            "SELECT j.id, j.title, j.company, j.url, j.data FROM job_group_members m JOIN jobs j ON j.id=m.job_id "
            "WHERE m.group_id=? ORDER BY j.id", (group["id"],)).fetchall()
        entry = {"group_id": group["id"], "count": group["n"], "company": members[0]["company"],
                 "title": members[0]["title"], "channels": [], "applied": []}
        for member in members:
            data = deserialize(member["data"])
            entry["channels"].append({"job_id": member["id"], "channel": data.get("source", ""),
                                      "url": member["url"],
                                      "published_at": data.get("published_at") or data.get("listed_at")})
            for app in db.execute("SELECT id, channel, status, applied_at FROM applications WHERE job_id=?",
                                  (member["id"],)).fetchall():
                if app["status"] in _APPLIED_STATES:
                    entry["applied"].append({"application_id": app["id"], "job_id": member["id"],
                                             "channel": app["channel"] or data.get("source", ""),
                                             "status": app["status"], "applied_at": app["applied_at"]})
        multi.append(entry)
    return multi


def groups(limit: int = 50) -> dict:
    """Same vacancy seen on several platforms, grouped for human review."""
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValidationError("limit must be an integer from 1 to 500")
    with connect() as db:
        _ensure_groups(db)
        multi = _multi_groups(db, limit)
        total = db.execute("SELECT COUNT(DISTINCT group_id) FROM job_group_members").fetchone()[0]
    return {"rule": GROUP_RULE, "total_groups": total, "multi_channel_groups": len(multi),
            "decision": "user_decides", "groups": multi}


def pipeline() -> dict:
    """Funnel plus duplicate-application and data-gap warnings."""
    upcoming = agenda()["scheduled"]
    with connect() as db:
        _ensure_groups(db)
        def count(sql, args=()):
            return db.execute(sql, args).fetchone()[0]

        try:
            leads_total = count("SELECT COUNT(*) FROM search_leads")
        except sqlite3.OperationalError:
            leads_total = 0

        jobs = db.execute("SELECT id, title, company, url, data FROM jobs WHERE source_key NOT LIKE 'oriward:resume-context:%'").fetchall()
        jobs_by_channel: dict[str, int] = {}
        published_missing = description_empty = 0
        for row in jobs:
            data = deserialize(row["data"])
            jobs_by_channel[data.get("source", "unknown")] = jobs_by_channel.get(data.get("source", "unknown"), 0) + 1
            if not (data.get("published_at") or data.get("listed_at")):
                published_missing += 1
            if not str(data.get("description", "")).strip():
                description_empty += 1

        status_rows = db.execute("SELECT status, COUNT(*) AS n FROM applications GROUP BY status").fetchall()
        by_status = {row["status"]: row["n"] for row in status_rows}
        app_channels = {row["channel"] or "unspecified": row["n"] for row in
                        db.execute("SELECT channel, COUNT(*) AS n FROM applications GROUP BY channel").fetchall()}

        multi = _multi_groups(db, 30)

        return {
            "generated_at": now(),
            "stages": {
                "leads": leads_total,
                "jobs": len(jobs),
                "analyzed": count("SELECT COUNT(DISTINCT job_id) FROM job_analyses"),
                "resumes": count("SELECT COUNT(*) FROM resumes"),
                "prepared": count("SELECT COUNT(*) FROM applications"),
                "submitted": by_status.get("SUBMITTED", 0) + by_status.get("INTERVIEW", 0)
                             + by_status.get("OFFER", 0) + by_status.get("ACCEPTED", 0),
                "interview": by_status.get("INTERVIEW", 0) + by_status.get("OFFER", 0) + by_status.get("ACCEPTED", 0),
                "offer": by_status.get("OFFER", 0) + by_status.get("ACCEPTED", 0),
            },
            "applications_by_status": by_status,
            "jobs_by_channel": dict(sorted(jobs_by_channel.items(), key=lambda item: -item[1])),
            "applications_by_channel": dict(sorted(app_channels.items(), key=lambda item: -item[1])),
            "same_vacancy_multi_channel": multi,
            "repeat_application_risk": [entry for entry in multi if entry["applied"]],
            "agenda": upcoming,
            "data_gaps": {
                "published_at_missing": published_missing,
                "description_empty": description_empty,
                "application_channel_missing": app_channels.get("unspecified", 0),
            },
            "rule": "同一岗位多平台只做归并展示；是否重复投递由用户判断，系统不拦截。",
        }
