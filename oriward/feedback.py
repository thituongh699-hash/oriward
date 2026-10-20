"""Versioned resume revisions and attributed recruiting feedback, entirely local."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from .db import connect, one, serialize, deserialize, now, audit
from . import services as s

STAGES = {"ats", "hr", "hiring_manager", "technical", "pressure", "background", "competition"}


def ensure_schema(db):
    # Additive tables preserve all v0.1 records. Execute separately so an
    # executescript implicit commit cannot split a surrounding transaction.
    db.execute("""CREATE TABLE IF NOT EXISTS recruiting_feedback (
        id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id),
        resume_id INTEGER NOT NULL REFERENCES resumes(id),
        application_id INTEGER REFERENCES applications(id),
        data TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
        resolution TEXT, created_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS resume_versions (
        resume_id INTEGER PRIMARY KEY REFERENCES resumes(id),
        base_resume_id INTEGER NOT NULL REFERENCES resumes(id),
        review_id INTEGER, feedback_ids TEXT NOT NULL, reason TEXT NOT NULL,
        claim_map TEXT NOT NULL, factual_status TEXT NOT NULL,
        created_at TEXT NOT NULL)""")


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise s.ValidationError(f"{name} must be nonempty text")
    return value.strip()


def _id(value, name):
    if type(value) is not int or value < 1:
        raise s.ValidationError(f"{name} must be a positive integer")
    return value


def _ids(value, name):
    if not isinstance(value, list):
        raise s.ValidationError(f"{name} must be an array")
    return list(dict.fromkeys(_id(v, name) for v in value))


def save_feedback(data):
    s.validate_dict(data, ["job_id", "resume_id", "kind", "stage", "outcome", "observation", "source", "observed_at", "actions"])
    d = dict(data)
    for key in ("job_id", "resume_id"):
        _id(d[key], key)
    if d["kind"] not in {"actual", "mock", "hypothesis"}:
        raise s.ValidationError("kind must be actual|mock|hypothesis")
    if d["stage"] not in STAGES:
        raise s.ValidationError("Unknown recruitment stage")
    if d["outcome"] not in {"pass", "reject", "pending", "withdrawn", "unknown"}:
        raise s.ValidationError("outcome must be pass|reject|pending|withdrawn|unknown")
    for key in ("observation", "source", "observed_at"):
        d[key] = _text(d[key], key)
    try:
        timestamp = datetime.fromisoformat(d["observed_at"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp > datetime.now(timezone.utc):
            raise ValueError()
    except ValueError as exc:
        raise s.ValidationError("observed_at must be a non-future ISO timestamp with timezone") from exc
    if not isinstance(d["actions"], list) or not d["actions"]:
        raise s.ValidationError("Provide at least one feedback action")
    for action in d["actions"]:
        s.validate_dict(action, ["category", "text"])
        if action["category"] not in {"wording", "practice", "evidence", "retarget"}:
            raise s.ValidationError("Action category must be wording|practice|evidence|retarget")
        _text(action["text"], "action.text")
    with connect() as db:
        ensure_schema(db)
        resume = one(db, "resumes", d["resume_id"])
        if resume["job_id"] != d["job_id"]:
            raise s.ValidationError("Feedback resume does not match job")
        s.verify_resume(resume)
        application_id = d.get("application_id")
        if d["kind"] == "actual" and application_id is None:
            raise s.ValidationError("Actual employer feedback requires its application_id")
        if application_id is not None:
            _id(application_id, "application_id")
            app = one(db, "applications", application_id)
            if app["job_id"] != d["job_id"] or app["resume_id"] != d["resume_id"]:
                raise s.ValidationError("Feedback does not match the application version")
            if d["kind"] == "actual" and app["status"] == "READY_FOR_USER":
                raise s.ValidationError("Cannot record actual employer feedback for an unsubmitted application")
        d["resume_sha256"] = resume["sha256"]
        cursor = db.execute("INSERT INTO recruiting_feedback(job_id,resume_id,application_id,data,created_at) VALUES (?,?,?,?,?)",
                            (d["job_id"], d["resume_id"], application_id, serialize(d), now()))
        audit(db, "feedback.saved", "recruiting_feedback", cursor.lastrowid, d["kind"])
        return {"id": cursor.lastrowid, "status": "open", "application_status_changed": False}


def list_feedback(job_id=None):
    with connect() as db:
        ensure_schema(db)
        query = "SELECT * FROM recruiting_feedback"
        args = ()
        if job_id is not None:
            one(db, "jobs", job_id)
            query += " WHERE job_id=?"
            args = (job_id,)
        return [{**dict(r), "data": deserialize(r["data"]),
                 "resolution": deserialize(r["resolution"]) if r["resolution"] else None}
                for r in db.execute(query + " ORDER BY id DESC", args)]


def feedback_plan(job_id):
    records = list_feedback(job_id)
    grouped = {k: [] for k in ("wording", "practice", "evidence", "retarget")}
    for r in records:
        if r["status"] == "resolved":
            continue
        for action in r["data"]["actions"]:
            grouped[action["category"]].append({"feedback_id": r["id"], "kind": r["data"]["kind"],
                                                "resume_id": r["resume_id"], "stage": r["data"]["stage"],
                                                "text": action["text"]})
    return {"job_id": job_id, "open_count": sum(r["status"] != "resolved" for r in records),
            "actions": grouped, "note": "反馈是观察或假设；拒绝原因不自动成为事实，修改简历不自动提高评级。"}


def _lineage(db, resume_id):
    ids = {resume_id}
    while True:
        row = db.execute("SELECT base_resume_id FROM resume_versions WHERE resume_id=?", (resume_id,)).fetchone()
        if row is None:
            return ids
        if row["base_resume_id"] == resume_id:
            return ids
        resume_id = row["base_resume_id"]
        if resume_id in ids:
            raise s.ValidationError("Invalid resume lineage")
        ids.add(resume_id)


def _packaging(bullet, text, facts, quotes):
    """Validate the declared change contract; this is not semantic verification.

    Exact mappings and a few obvious numeric/tool/scope additions are checkable
    deterministically. The source Agent owns semantic classification and the
    user still reviews the complete draft before use.
    """
    kind = bullet.get("change_type", "exact" if text in facts else "unclassified")
    if kind not in {"exact", "wording_only", "new_facts", "unclassified"}:
        raise s.ValidationError("change_type must be exact|wording_only|new_facts|unclassified")
    additions = bullet.get("new_facts", [])
    if not isinstance(additions, list) or any(not isinstance(v, str) or not v.strip() for v in additions):
        raise s.ValidationError("new_facts must be an array of factual additions")
    rationale = bullet.get("change_reason", "")
    if kind == "exact" and text not in facts:
        raise s.ValidationError("exact wording must be an existing factual action/outcome")
    if kind == "wording_only":
        if "new_facts" not in bullet or additions or not isinstance(rationale, str) or not rationale.strip():
            raise s.ValidationError("wording_only requires explicit new_facts:[] and change_reason")
        # A limited guard, deliberately not advertised as semantic proof.
        pattern = (r"\d+(?:[.,]\d+)*|\b(?:Python|SQL|Excel|VBA|SPSS|PowerBI|Tableau|Java|"
                   r"manager|director|leader|expert|led|managed|owned)\b|"
                   r"负责人|总监|经理|主管|精通|独立负责|主导|付费成交|原账号")
        target_tokens = set(re.findall(pattern, text, re.IGNORECASE))
        source_tokens = set(re.findall(pattern, " ".join(quotes), re.IGNORECASE))
        if {t.casefold() for t in target_tokens} - {t.casefold() for t in source_tokens}:
            raise s.ValidationError("wording_only includes a new number, tool or scope marker; classify as new_facts")
    if kind == "new_facts" and not additions:
        raise s.ValidationError("new_facts classification requires an explicit nonempty new_facts list")
    if additions and kind != "new_facts":
        raise s.ValidationError("Factual additions must use change_type=new_facts")
    return {"change_type": kind, "new_facts": additions, "change_reason": rationale,
            "classification_source": "agent_declared", "verification": "source_mapping_and_limited_lexical_guards"}, kind in {"new_facts", "unclassified"}


def revise_resume(data):
    """Persist sourced wording; declared factual additions stay pending."""
    s.validate_dict(data, ["base_resume_id", "reason", "sections"])
    base_id = _id(data["base_resume_id"], "base_resume_id")
    reason = _text(data["reason"], "reason")
    if not isinstance(data["sections"], list) or not data["sections"]:
        raise s.ValidationError("sections must be a nonempty array")
    feedback_ids = _ids(data.get("feedback_ids", []), "feedback_ids")
    new_path = None
    try:
        with connect() as db:
            ensure_schema(db)
            base = one(db, "resumes", base_id)
            base_content = s.verify_resume(base).read_text(encoding="utf-8")
            from .experience_library import ensure_resume_current, validate_for_resume, record_resume_sources
            ensure_resume_current(db, base)
            base_version = db.execute("SELECT factual_status FROM resume_versions WHERE resume_id=?", (base_id,)).fetchone()
            if base_version and base_version["factual_status"] != "approved":
                raise s.ValidationError("Base revision facts are pending; confirm or use an approved base")
            review_id = data.get("review_id")
            if review_id is not None:
                _id(review_id, "review_id")
                from .assessment import list_reviews
                reviews = list_reviews(base_id)
                if not any(r["id"] == review_id for r in reviews):
                    raise s.ValidationError("review_id must reference a review of the base resume")
            ancestors = _lineage(db, base_id)
            for feedback_id in feedback_ids:
                row = db.execute("SELECT * FROM recruiting_feedback WHERE id=?", (feedback_id,)).fetchone()
                if row is None or row["job_id"] != base["job_id"] or row["resume_id"] not in ancestors:
                    raise s.ValidationError("Feedback must reference this job and a base version")
            prefix, marker, tail = base_content.partition("\n## 相关经历\n")
            if not marker or "\n---\n" not in tail:
                raise s.ValidationError("Base resume lacks supported section structure")
            selected = []
            lines = []
            pending = False
            mapping = []
            for section in data["sections"]:
                s.validate_dict(section, ["experience_id", "bullets"])
                eid = _id(section["experience_id"], "experience_id")
                if eid in selected:
                    raise s.ValidationError("Duplicate experience section")
                selected.append(eid)
                exp = validate_for_resume(db, eid)
                facts = exp["actions"] + exp["outcomes"]
                sources = facts + [e["claim"] for e in exp["evidence"]]
                if not isinstance(section["bullets"], list) or not section["bullets"]:
                    raise s.ValidationError("Every section requires bullets")
                lines += ["", f"### {exp['event']}", ""]
                if exp.get("context"):
                    from .resume_content import public_context
                    if public_context(exp["context"]):
                        lines += [public_context(exp["context"]), ""]
                for bullet in section["bullets"]:
                    s.validate_dict(bullet, ["text", "source_texts"])
                    text = _text(bullet["text"], "bullet.text")
                    if "\n" in text or "\r" in text:
                        raise s.ValidationError("A bullet must be one line")
                    quotes = bullet["source_texts"]
                    if not isinstance(quotes, list) or not quotes or any(q not in sources for q in quotes):
                        raise s.ValidationError("source_texts must quote verified facts from the same experience")
                    classification, needs_confirmation = _packaging(bullet, text, facts, quotes)
                    pending = pending or needs_confirmation
                    lines.append(f"- {text}")
                    mapping.append({"experience_id": eid, "experience_version": exp["version"],
                                    "text": text, "source_texts": quotes, **classification})
            content = prefix + marker + "\n".join(lines) + "\n\n---\n\n"
            job = one(db, "jobs", base["job_id"])
            content += f"*来源记录：岗位 {job['id']}（{job['company']} / {job['title']}）；经历 ID {', '.join(map(str, selected))}。*\n"
            content += "*发布/投递前请人工核对内容；未经证实的推断不应当写入简历。*\n"
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            cursor = db.execute("INSERT INTO resumes(job_id,experience_ids,output_path,sha256,created_at) VALUES (?,?,?,?,?)",
                                (base["job_id"], serialize(selected), "PENDING", digest, now()))
            rid = cursor.lastrowid
            output_dir = s.resume_output_dir()
            output_dir.mkdir(parents=True, exist_ok=True)
            from .resume_content import artifact_path
            new_path = artifact_path(db, rid)
            # Exclusive create prevents accidental overwrite on mismatched databases.
            with new_path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
            db.execute("UPDATE resumes SET output_path=? WHERE id=?", (str(new_path.resolve()), rid))
            status = "pending" if pending else "approved"
            db.execute("INSERT INTO resume_versions VALUES (?,?,?,?,?,?,?,?)",
                       (rid, base_id, review_id, serialize(feedback_ids), reason, serialize(mapping), status, now()))
            audit(db, "resume.revised", "resumes", rid, f"base={base_id};facts={status}")
            record_resume_sources(db, rid, selected)
            result = {"id": rid, "path": str(new_path), "sha256": digest, "base_resume_id": base_id,
                    "factual_status": status, "requires_new_review": True,
                    "whole_draft_review_required": True,
                    "pending_new_facts": [m for m in mapping if m["change_type"] in {"new_facts", "unclassified"}]}
    except Exception:
        # Only delete the new artifact if this call actually created it.
        if new_path is not None and new_path.exists() and 'rid' in locals():
            # A collision existed before exclusive open: never delete that file.
            if 'handle' in locals():
                new_path.unlink()
        raise
    from .resume_content import cleanup
    result["retention"] = cleanup(job_id=base["job_id"], apply=True, rename=False)
    return result


def confirm_revision(resume_id, *, human_confirmed=False):
    if not human_confirmed:
        raise s.ValidationError("Reworded claims require direct user confirmation; pass --human-confirmed only after it")
    with connect() as db:
        ensure_schema(db)
        resume = one(db, "resumes", resume_id)
        s.verify_resume(resume)
        from .experience_library import ensure_resume_current
        ensure_resume_current(db, resume)
        if db.execute("SELECT 1 FROM resume_versions WHERE resume_id=?", (resume_id,)).fetchone() is None:
            raise s.ValidationError("Resume is not a revision")
        db.execute("UPDATE resume_versions SET factual_status='approved' WHERE resume_id=?", (resume_id,))
        audit(db, "resume.facts_confirmed", "resumes", resume_id)
    return {"resume_id": resume_id, "factual_status": "approved", "requires_new_review": True}


def version_history(resume_id):
    with connect() as db:
        ensure_schema(db)
        one(db, "resumes", resume_id)
        rows = []
        for rid in sorted(_lineage(db, resume_id)):
            resume = dict(one(db, "resumes", rid))
            from .experience_library import resume_validity
            resume.update(resume_validity(db, resume))
            version = db.execute("SELECT * FROM resume_versions WHERE resume_id=?", (rid,)).fetchone()
            resume["version"] = dict(version) if version else None
            if version:
                resume["version"]["feedback_ids"] = deserialize(version["feedback_ids"])
                resume["version"]["claim_map"] = deserialize(version["claim_map"])
            rows.append(resume)
        return rows


def resolve_feedback(feedback_id, review_id, note):
    _text(note, "resolution note")
    from .assessment import list_reviews, _job_sha256
    reviews = list_reviews()
    review = next((r for r in reviews if r["id"] == review_id), None)
    if review is None:
        raise s.ValidationError("Review not found")
    if review["status"] == "NEEDS_EVIDENCE" or review["grade"] is None:
        raise s.ValidationError("Resolution requires a completed review, not a pending evidence assessment")
    with connect() as db:
        ensure_schema(db)
        feedback = db.execute("SELECT * FROM recruiting_feedback WHERE id=?", (feedback_id,)).fetchone()
        if feedback is None:
            raise s.ValidationError("Feedback not found")
        version = db.execute("SELECT * FROM resume_versions WHERE resume_id=?", (review["resume_id"],)).fetchone()
        if version is None or feedback_id not in deserialize(version["feedback_ids"]):
            raise s.ValidationError("Resolution requires a new review of a revision linked to this feedback")
        resume = one(db, "resumes", review["resume_id"])
        s.verify_resume(resume)
        from .experience_library import ensure_resume_current
        ensure_resume_current(db, resume)
        current_job = deserialize(one(db, "jobs", resume["job_id"])["data"])
        if review["job_sha256"] != _job_sha256(current_job):
            raise s.ValidationError("Resolution review is stale because the JD changed")
        if version["factual_status"] != "approved":
            raise s.ValidationError("Confirm revised facts before resolving feedback")
        resolution = {"review_id": review_id, "resume_id": review["resume_id"], "note": note, "resolved_at": now()}
        db.execute("UPDATE recruiting_feedback SET status='resolved',resolution=? WHERE id=?",
                   (serialize(resolution), feedback_id))
        audit(db, "feedback.resolved", "recruiting_feedback", feedback_id)
        return {"id": feedback_id, "status": "resolved", **resolution}
