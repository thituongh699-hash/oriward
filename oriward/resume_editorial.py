"""Readback and recorded Agent editorial review, separate from hiring assessment.

This module supplies evidence and stores the host Agent's judgment. It does not
run a model, grade prose, or certify the truth of an Agent's review.
"""
from . import services as s
from .db import connect, deserialize, now, one, serialize


CHECKS = ("jd_focus", "timeline", "education_placement", "star_c", "template", "factuality")


def packet(resume_id):
    from .resume_content import composition_for_resume, _single_target
    from .experience_library import list_current, resume_validity
    composition = composition_for_resume(resume_id) or {}
    profile = s.get_profile()
    with connect() as db:
        resume = dict(one(db, "resumes", resume_id))
        path = s.resume_path(resume)
        if not path.is_file():
            raise s.ValidationError("Resume artifact is missing; compose a current draft first")
        content = path.read_text(encoding="utf-8")
        selected = set(deserialize(resume["experience_ids"]))
        validity = resume_validity(db, resume)
        experiences = list_current(conn=db)
        timeline = [{"id": row["id"], "version": row["data"]["version"],
                     "event": row["data"].get("event"),
                     "time_period": row["data"].get("time_period"),
                     "selected": row["id"] in selected}
                    for row in experiences]
        sources = [{"id": row["id"], "version": row["data"]["version"], "data": row["data"]}
                   for row in experiences if row["id"] in selected]
        version = db.execute("SELECT claim_map FROM resume_versions WHERE resume_id=?", (resume_id,)).fetchone()
        claims = deserialize(version["claim_map"]) if version else []
        imported = db.execute("SELECT detail FROM audit_events WHERE kind='resume.imported_source' "
                              "AND resource_id=? ORDER BY id DESC LIMIT 1", (resume_id,)).fetchone()
        review = db.execute("SELECT id,detail FROM audit_events WHERE kind='resume.editorial_review' "
                            "AND resource_id=? ORDER BY id DESC LIMIT 1", (resume_id,)).fetchone()
        latest = deserialize(review["detail"]) if review else None
        if latest:
            latest = {"id": review["id"], **latest}
            reviewed_text = latest.pop("reviewed_content", None)
            reviewed_sources = latest.pop("source_versions", {})
            reviewed_profile = latest.pop("profile_snapshot", None)
            latest["current"] = (not validity["needs_review"] and reviewed_profile == profile
                                 and reviewed_text == content and reviewed_sources ==
                                 {str(item["id"]): item["version"] for item in sources})
    imported_source = None
    if imported:
        from .resume_workbench import input_record
        imported_source = input_record(deserialize(imported["detail"])["input_id"])
    return {"resume_id": resume_id, "path": str(path), "content": content,
            "target": composition.get("_target_snapshot") or _single_target(resume["job_id"]),
            "profile": profile, "composition": composition,
            "timeline": timeline, "selected_sources": sources, "claim_map": claims,
            "source_validity": validity, "imported_source": imported_source,
            "latest_editorial_review": latest,
            "review_kind": "host_agent_editorial_not_hiring_assessment",
            "checks": list(CHECKS),
            "instructions": (
                "Read the actual draft against its primary JD, selected sources and full timeline. "
                "Judge emphasis, omitted relevant evidence, major career gaps, academic placement, "
                "natural factual STAR-C, personal template and ownership. Brief career anchors need "
                "no forced STAR-C. Do not require every library item or fabricate metrics. "
                "Revise weak prose before recording ready. This packet performs no semantic review.")}


def save_review(data):
    s.validate_dict(data, ["resume_id", "verdict", "findings", "checked"])
    if data["verdict"] not in {"ready", "revise"}:
        raise s.ValidationError("verdict must be ready or revise")
    checked = data["checked"]
    if not isinstance(checked, dict) or any(type(checked.get(key)) is not bool for key in CHECKS):
        raise s.ValidationError("checked must contain boolean values for all editorial checks")
    if data["verdict"] == "ready" and not all(checked[key] for key in CHECKS):
        raise s.ValidationError("ready requires all checks to have been completed by the Agent")
    findings = data["findings"]
    if not isinstance(findings, list) or any(not isinstance(item, str) or not item.strip() for item in findings):
        raise s.ValidationError("findings must be an array of nonempty text")
    if data["verdict"] == "revise" and not findings:
        raise s.ValidationError("revise requires actionable findings")
    current = packet(int(data["resume_id"]))
    if data["verdict"] == "ready" and current["source_validity"]["needs_review"]:
        raise s.ValidationError("Resume sources changed or were retracted; revise the draft before recording ready")
    payload = {"verdict": data["verdict"], "findings": findings, "checked": checked,
               "reviewed_content": current["content"],
               "profile_snapshot": current["profile"],
               "source_versions": {str(item["id"]): item["version"] for item in current["selected_sources"]},
               "reviewer": "host_agent", "review_kind": current["review_kind"]}
    with connect() as db:
        result = db.execute("INSERT INTO audit_events(kind,resource,resource_id,detail,created_at) "
                            "VALUES (?,?,?,?,?)", ("resume.editorial_review", "resumes", current["resume_id"],
                                                   serialize(payload), now()))
        receipt = result.lastrowid
    return {"id": receipt, "resume_id": current["resume_id"], "verdict": data["verdict"],
            "review_kind": current["review_kind"], "recorded": True,
            "next": "Export and inspect rendered pages" if data["verdict"] == "ready" else "Revise and read the new version"}
