"""Versioned resume revisions and attributed recruiting feedback, entirely local."""
from __future__ import annotations

import json
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
    """Record the author's classification; vocabulary is not a fact verifier."""
    kind = bullet.get("change_type", "exact" if text in facts else "wording_only")
    if kind not in {"exact", "wording_only", "new_facts", "unclassified"}:
        raise s.ValidationError("change_type must be exact|wording_only|new_facts|unclassified")
    additions = bullet.get("new_facts", [])
    if not isinstance(additions, list) or any(not isinstance(v, str) or not v.strip() for v in additions):
        raise s.ValidationError("new_facts must be an array of factual additions")
    if kind == "new_facts" and not additions:
        raise s.ValidationError("new_facts classification requires an explicit nonempty new_facts list")
    if additions and kind != "new_facts":
        raise s.ValidationError("Factual additions must use change_type=new_facts")
    return {"change_type": kind, "new_facts": additions,
            "change_reason": bullet.get("change_reason", ""),
            "classification_source": "agent_declared", "verification": "source_mapping"}, kind == "new_facts"


def revise_resume(data):
    """Compose a complete new draft and append feedback/version provenance."""
    s.validate_dict(data, ["base_resume_id", "reason", "sections"])
    base_id = _id(data["base_resume_id"], "base_resume_id")
    reason = _text(data["reason"], "reason")
    if not isinstance(data["sections"], list) or not data["sections"]:
        raise s.ValidationError("sections must be a nonempty array")
    feedback_ids = _ids(data.get("feedback_ids", []), "feedback_ids")
    review_id = data.get("review_id")
    from . import resume_content
    from .experience_library import resume_validity, validate_for_resume, usable_facts
    with connect() as db:
        ensure_schema(db)
        base = one(db, "resumes", base_id)
        s.verify_resume(base)
        stale_ids = {issue["experience_id"] for issue in resume_validity(db, base)["issues"]}
        if review_id is not None:
            _id(review_id, "review_id")
            from .assessment import list_reviews
            if not any(r["id"] == review_id for r in list_reviews(base_id)):
                raise s.ValidationError("review_id must reference a review of the base resume")
        ancestors = _lineage(db, base_id)
        for feedback_id in feedback_ids:
            row = db.execute("SELECT * FROM recruiting_feedback WHERE id=?", (feedback_id,)).fetchone()
            if row is None or row["job_id"] != base["job_id"] or row["resume_id"] not in ancestors:
                raise s.ValidationError("Feedback must reference this job and a base version")
        baseline = resume_content.composition_for_resume(base_id)
        if baseline is None:
            baseline = {"sections": []}
            for eid in deserialize(base["experience_ids"]):
                if eid in stale_ids:
                    continue
                exp = validate_for_resume(db, eid)
                baseline["sections"].append({"experience_id": eid, "bullets": usable_facts(exp)})
        baseline = json.loads(json.dumps(baseline))
        old_profile = baseline.get("_profile_snapshot")
        if isinstance(old_profile, dict) and "profile_sections" not in data:
            current_profile = s.get_profile()
            heading_fields = {"教育经历": ("education", "education_history", "summary_verified"),
                              "专业技能": ("skills",), "资格证书": ("certifications",),
                              "个人优势": ("summary_verified",)}
            changed_headings = {heading for heading, fields in heading_fields.items()
                                if any(old_profile.get(key) != current_profile.get(key) for key in fields)}
            baseline["profile_sections"] = [item for item in baseline.get("profile_sections", [])
                                            if item.get("heading") not in changed_headings]
        def section_ids(section):
            if not isinstance(section, dict):
                raise s.ValidationError("section must be an object")
            ids = section.get("experience_ids", [section.get("experience_id")])
            if not isinstance(ids, list) or not ids:
                raise s.ValidationError("section needs experience IDs")
            return [_id(eid, "experience_id") for eid in ids]
        replaced = set()
        for section in data["sections"]:
            ids = section_ids(section)
            if replaced.intersection(ids):
                raise s.ValidationError("Duplicate experience section")
            replaced.update(ids)
        def retain_section(section, removed):
            ids = section_ids(section)
            remaining = [eid for eid in ids if eid not in removed]
            if not remaining:
                return None
            if len(remaining) == len(ids):
                return section
            retained = dict(section)
            retained.pop("experience_id", None)
            retained["experience_ids"] = remaining
            facts_by_id = {eid: set(usable_facts(validate_for_resume(db, eid))) for eid in remaining}
            bullets = []
            for original in section.get("bullets", []):
                bullet = {"text": original} if isinstance(original, str) else dict(original)
                owners = bullet.get("experience_ids")
                if owners is None:
                    quotes = bullet.get("source_texts", [bullet.get("text")])
                    owners = [eid for eid, facts in facts_by_id.items() if any(q in facts for q in quotes)]
                    # Unassigned paraphrases/joint claims cannot safely be split.
                    if not owners or any(not any(q in facts for facts in facts_by_id.values()) for q in quotes):
                        continue
                if set(owners).intersection(removed) or not set(owners).issubset(remaining):
                    continue
                bullet["experience_ids"] = owners
                bullets.append(bullet)
            retained["bullets"] = bullets
            return retained
        sections = []
        consumed_replacements = set()
        for section in baseline.get("sections", []):
            group_ids = set(section_ids(section))
            overlap = group_ids & replaced
            candidates = [(index, replacement) for index, replacement in enumerate(data["sections"])
                          if group_ids.intersection(section_ids(replacement))]
            if (overlap and group_ids - overlap and not group_ids.intersection(stale_ids)
                    and all(set(section_ids(replacement)).issubset(group_ids) for _, replacement in candidates)):
                # A wording edit to one source does not establish ownership of
                # unassigned/shared group prose. Retain it and the group metadata;
                # only explicitly source-specific replaced bullets are removed.
                # To rewrite joint prose, the Agent supplies the complete group.
                merged = dict(section)
                merged.pop("experience_id", None)
                merged["experience_ids"] = section_ids(section)
                bullets = []
                for bullet in section.get("bullets", []):
                    owners = bullet.get("experience_ids") if isinstance(bullet, dict) else None
                    if owners and set(owners).issubset(overlap):
                        continue
                    bullets.append(bullet)
                for index, replacement in candidates:
                    ids = section_ids(replacement)
                    additions = replacement.get("bullets")
                    if not additions:
                        additions = [fact for eid in ids for fact in
                                     (validate_for_resume(db, eid).get("actions", []) +
                                      validate_for_resume(db, eid).get("outcomes", []))[:1]]
                    for original in additions:
                        bullet = {"text": original} if isinstance(original, str) else dict(original)
                        bullet.setdefault("experience_ids", ids)
                        bullets.append(bullet)
                    consumed_replacements.add(index)
                merged["bullets"] = bullets
                sections.append(merged)
            else:
                retained = retain_section(section, replaced | stale_ids)
                if retained:
                    sections.append(retained)
        sections.extend(section for index, section in enumerate(data["sections"])
                        if index not in consumed_replacements)
        if stale_ids and "summary" not in data:
            summary = baseline.get("summary")
            ids = summary.get("experience_ids") if isinstance(summary, dict) else None
            if summary and (ids is None or stale_ids.intersection(ids)):
                baseline.pop("summary", None)
        baseline.update({key: value for key, value in data.items()
                         if key not in {"base_resume_id", "review_id", "feedback_ids", "sections"}})
        baseline["sections"] = sections
        job_id = base["job_id"]
    result = resume_content.compose(job_id, baseline)
    with connect() as db:
        # compose owns the full map, including titles, profile and summary.
        # Updating lineage must never replace its factual metadata.
        db.execute("UPDATE resume_versions SET base_resume_id=?, review_id=?, feedback_ids=?, reason=? WHERE resume_id=?",
                   (base_id, review_id, serialize(feedback_ids), reason, result["id"]))
        audit(db, "resume.revised", "resumes", result["id"], f"base={base_id};facts={result['factual_status']}")
    result.update(base_resume_id=base_id, requires_new_review=False, whole_draft_review_required=False)
    return result


def confirm_revision(resume_id, *, human_confirmed=False):
    if not human_confirmed:
        raise s.ValidationError("Optional factual confirmation requires the user agreement; use --human-confirmed only after it")
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
    return {"resume_id": resume_id, "factual_status": "approved", "requires_new_review": False}


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
        resolution = {"review_id": review_id, "resume_id": review["resume_id"], "note": note, "resolved_at": now()}
        db.execute("UPDATE recruiting_feedback SET status='resolved',resolution=? WHERE id=?",
                   (serialize(resolution), feedback_id))
        audit(db, "feedback.resolved", "recruiting_feedback", feedback_id)
        return {"id": feedback_id, "status": "resolved", **resolution}
