"""Source-mapped tailored composition and bounded Markdown artifact retention."""
from __future__ import annotations

import re

from . import services as s
from .db import audit, connect, deserialize, now, one, serialize


def public_context(value):
    """Only public date/organisation context belongs in a candidate document."""
    if isinstance(value, dict):
        return " · ".join(safe_text(str(value[k]), f"context.{k}") for k in
                          ("organization", "organisation", "company", "location", "period", "dates", "date_range")
                          if value.get(k) and isinstance(value[k], (str, int)))
    if isinstance(value, str):
        return safe_text(value, "context")
    return ""


def safe_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise s.ValidationError(f"{label} must be nonempty text")
    value = value.strip()
    if "\n" in value or "\r" in value or re.search(r"[A-Za-z]:[\\/]|(?:^|\s)/(?:home|Users|tmp)/|file://|\{\{.*\}\}|<TODO>|\[待填写\]", value):
        raise s.ValidationError(f"{label} contains internal paths, placeholders or multiple lines")
    return value


def _slug(value):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", str(value)).strip(" .")[:48] or "未注明"


def artifact_path(db, resume_id):
    row = one(db, "resumes", resume_id)
    job = one(db, "jobs", row["job_id"])
    data = deserialize(job["data"])
    version = row["job_version"] or db.execute(
        "SELECT COUNT(*) FROM resumes WHERE job_id=? AND id<=?", (row["job_id"], resume_id)).fetchone()[0]
    db.execute("UPDATE resumes SET job_version=? WHERE id=?", (version, resume_id))
    day = str(row["created_at"])[:10].replace("-", "")
    return s.resume_output_dir() / (f"{_slug(job['company'])}_{_slug(job['title'])}_"
                                    f"{_slug(data.get('location', ''))}_job{row['job_id']}_v{version}_{day}.md")


def tailor_packet(job_id):
    from .experience_library import index
    from .assessment import analysis_packet
    # The index is bounded; the Agent explicitly drills into selected IDs.
    return {"job_id": job_id, "job": s.get_job(job_id), "profile": s.get_profile(),
            "analysis": analysis_packet(job_id), "experience_index": index(budget=6000),
            "next": "Read selected experience detail IDs; identify company purpose and 2-4 deliverables; "
                    "rewrite summary, ordering and bullets for this job, then resume compose --file.",
            "contract": {"sections": [{"experience_id": 1, "title": "optional truthful display title",
                         "bullets": [{"text": "Tailored wording", "source_texts": ["Exact fact quote"],
                                      "change_type": "wording_only", "new_facts": [],
                                      "change_reason": "Why this wording fits the role without adding facts"}]}],
                         "summary": "optional sourced claim object with text, experience_ids, source_texts and classification",
                         "headline": "optional target role label", "reason": "Why selected experiences fit"}}


def _mapped(db, claim, ids):
    from .experience_library import validate_for_resume
    from .feedback import _packaging
    text = safe_text(claim.get("text"), "claim.text")
    facts, sources, versions = [], [], {}
    for eid in ids:
        exp = validate_for_resume(db, eid)
        versions[str(eid)] = exp["version"]
        facts += exp["actions"] + exp["outcomes"] + [exp["event"]]
        sources += exp["actions"] + exp["outcomes"] + [exp["event"]] + [e["claim"] for e in exp["evidence"]]
    quotes = claim.get("source_texts")
    if not isinstance(quotes, list) or not quotes or any(q not in sources for q in quotes):
        raise s.ValidationError("source_texts must quote approved facts from selected experience IDs")
    classification, pending = _packaging(claim, text, facts, quotes)
    return {"text": text, "experience_ids": ids, "experience_versions": versions,
            "source_texts": quotes, **classification}, pending


def compose(job_id, data):
    from .experience_library import validate_for_resume, record_resume_sources
    from .feedback import ensure_schema, _id
    s.validate_dict(data, ["reason", "sections"])
    if not isinstance(data["sections"], list) or not data["sections"]:
        raise s.ValidationError("sections must be a nonempty array")
    profile = s.get_profile()
    person = safe_text(profile.get("display_name"), "current display_name")
    path = None
    created = False
    try:
        with connect() as db:
            ensure_schema(db)
            job = one(db, "jobs", job_id)
            selected, mapping, sections, pending = [], [], [], False
            for section in data["sections"]:
                eid = _id(section.get("experience_id"), "experience_id")
                if eid in selected:
                    raise s.ValidationError("Duplicate experience section")
                exp = validate_for_resume(db, eid)
                selected.append(eid)
                title = exp["event"]
                if section.get("title") and section["title"] != title:
                    title_claim = section.get("title_claim")
                    if not isinstance(title_claim, dict) or title_claim.get("text") != section["title"]:
                        raise s.ValidationError("Changed display title requires a source-mapped title_claim")
                    entry, needs = _mapped(db, title_claim, [eid])
                    mapping.append({"field": "title", **entry}); pending |= needs
                    title = entry["text"]
                lines = [f"### {safe_text(title, 'experience title')}", ""]
                context = public_context(exp.get("context"))
                if context:
                    lines += [context, ""]
                bullets = section.get("bullets")
                if not isinstance(bullets, list) or not bullets:
                    raise s.ValidationError("Each section requires tailored bullets")
                for bullet in bullets:
                    entry, needs = _mapped(db, bullet, [eid])
                    mapping.append({"field": "bullet", "experience_id": eid,
                                    "experience_version": exp["version"], **entry})
                    pending |= needs
                    lines.append("- " + entry["text"])
                sections += lines + [""]
            lines = [f"# {person}", ""]
            contact = profile.get("contact", {})
            if isinstance(contact, dict):
                values = [safe_text(str(contact[k]), "contact") for k in ("email", "phone", "portfolio") if contact.get(k)]
                if values:
                    lines += [" · ".join(values), ""]
            if data.get("headline"):
                lines += [f"*申请方向：{safe_text(data['headline'], 'headline')}*", ""]
            if data.get("summary"):
                summary = data["summary"]
                if not isinstance(summary, dict):
                    raise s.ValidationError("summary must be a sourced claim object")
                ids = summary.get("experience_ids", [])
                if not isinstance(ids, list) or not ids or any(type(i) is not int or i not in selected for i in ids):
                    raise s.ValidationError("summary experience_ids must be selected IDs")
                entry, needs = _mapped(db, summary, ids)
                mapping.append({"field": "summary", **entry}); pending |= needs
                lines += ["## 个人简介", entry["text"], ""]
            lines += ["## 相关经历", ""] + sections
            lines += ["---", "", f"*来源记录：岗位 {job_id}（{job['company']} / {job['title']}）；经历 ID {', '.join(map(str, selected))}。*",
                      "*发布/投递前请人工核对内容；未经证实的推断不应当写入简历。*", ""]
            content = "\n".join(lines)
            cursor = db.execute("INSERT INTO resumes(job_id,experience_ids,output_path,sha256,created_at) VALUES (?,?,?,?,?)",
                                (job_id, serialize(selected), "PENDING", "", now()))
            rid = cursor.lastrowid
            path = artifact_path(db, rid)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                created = True
                handle.write(content)
            db.execute("UPDATE resumes SET output_path=? WHERE id=?", (str(path.resolve()), rid))
            status = "pending" if pending else "approved"
            db.execute("INSERT INTO resume_versions VALUES (?,?,?,?,?,?,?,?)",
                       (rid, rid, None, "[]", safe_text(data["reason"], "reason"), serialize(mapping), status, now()))
            record_resume_sources(db, rid, selected)
            audit(db, "resume.composed", "resumes", rid, f"facts={status}")
    except Exception:
        if created and path:
            path.unlink(missing_ok=True)
        raise
    return {"id": rid, "path": str(path), "factual_status": status, "requires_new_review": True,
            "whole_draft_review_required": True, "pending_new_facts": [m for m in mapping if m["change_type"] in {"new_facts", "unclassified"}],
            "retention": cleanup(job_id=job_id, apply=True, rename=False)}


def cleanup(*, job_id=None, apply=False, rename=True):
    """Only registered Markdown inside the configured resume root can be touched."""
    root = s.resume_output_dir().resolve()
    operations, skipped = [], []
    with connect() as db:
        if job_id is not None:
            one(db, "jobs", job_id)
        rows = db.execute("SELECT * FROM resumes" + (" WHERE job_id=?" if job_id is not None else "") + " ORDER BY id DESC",
                          (job_id,) if job_id is not None else ()).fetchall()
        groups = {}
        for row in rows:
            groups.setdefault(row["job_id"], []).append(row)
        retained_paths = {s.resume_path(row).resolve() for group in groups.values() for row in group[:4]}
        for group in groups.values():
            for position, row in enumerate(group):
                path = s.resume_path(row)
                resolved = path.resolve()
                if (not resolved.is_relative_to(root) or path.suffix.lower() != ".md"
                        or path.is_symlink() or path.absolute() != resolved):
                    skipped.append({"id": row["id"], "reason": "outside root, symlink or non-Markdown"}); continue
                if position >= 4:
                    if resolved in retained_paths:
                        skipped.append({"id": row["id"], "reason": "path also belongs to a retained version"}); continue
                    if path.exists():
                        operations.append({"id": row["id"], "action": "delete", "path": str(path)})
                        if apply:
                            path.unlink()
                    if apply:
                        db.execute("UPDATE resumes SET artifact_state='pruned' WHERE id=?", (row["id"],))
                    continue
                if not path.exists():
                    skipped.append({"id": row["id"], "reason": "missing retained file"}); continue
                # Dry-run does not allocate versions or modify database rows.
                target = artifact_path(db, row["id"]) if apply else root / path.name
                if rename and not apply:
                    job = one(db, "jobs", row["job_id"])
                    data = deserialize(job["data"])
                    day = row["created_at"][:10].replace("-", "")
                    target = root / f"{_slug(job['company'])}_{_slug(job['title'])}_{_slug(data.get('location', ''))}_job{row['job_id']}_v{row['job_version']}_{day}.md"
                if rename and path != target:
                    if target.exists():
                        skipped.append({"id": row["id"], "reason": "target exists"}); continue
                    operations.append({"id": row["id"], "action": "rename", "path": str(path), "target": str(target)})
                    if apply:
                        path.rename(target)
                        db.execute("UPDATE resumes SET output_path=? WHERE id=?", (str(target), row["id"]))
        if apply:
            audit(db, "resume.cleanup", "resumes", job_id or 0, serialize(operations))
    return {"dry_run": not apply, "keep": "current + 3 historical Markdown per job", "operations": operations, "skipped": skipped}
