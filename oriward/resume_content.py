"""Source-mapped tailored composition and bounded Markdown artifact retention."""
from __future__ import annotations

import hashlib
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


def tailor_packet(job_id=None, *, offset=0, budget=6000):
    """One bounded page, with an explicit continuation; no approval prerequisite."""
    from .experience_library import index
    from .assessment import analysis_packet
    page = index(budget=budget, offset=offset)
    ids = [item["id"] for item in page["items"]]
    return {"job_id": job_id, "job": s.get_job(job_id) if job_id is not None else None,
            "profile": s.get_profile(),
            "analysis": analysis_packet(job_id) if job_id is not None else None,
            "experience_index": page,
            "experience_details": [],
            "detail_requests": {"ids": ids, "sections": ["event", "time_period", "actions", "outcomes"],
                                "command": "experience detail --ids <selected IDs> --sections actions,outcomes,time_period"},
            "required_experience_ids": [],  # deprecated: experience approval is not a coverage rule
            "next_offset": page["next_offset"],
            "has_more": page["next_offset"] < page["total_count"],
            "next": "Read all index pages, then relevant details. Recover the career timeline; translate actual actions "
                    "into the role's 2-4 deliverables. Expand relevant work, briefly retain other history. "
                    "Compose a complete draft directly; user self-report needs no additional approval.",
            "translation_focus": ["What did the person actually do?", "Which working ability does that demonstrate?",
                                  "Which target task uses that ability?", "What small practice could bridge the remaining gap?"],
            "contract": {"sections": [{"experience_id": 1, "category": "工作经历", "mode": "expanded",
                                        "bullets": ["Natural, factual wording for the target role"]}],
                         "experience_ids": "Use instead of experience_id to group events from one career stage",
                         "exclude_experience_ids": "Only histories the user does not want in this resume",
                         "profile_sections": "optional profile paragraphs; existing education is included automatically",
                         "section_order": "optional existing personal template order",
                         "reason": "How the experience supports the target work"}}


def composition_for_resume(resume_id):
    with connect() as db:
        row = db.execute("SELECT detail FROM audit_events WHERE kind='resume.composition' AND resource_id=? "
                         "ORDER BY id DESC LIMIT 1", (resume_id,)).fetchone()
        return deserialize(row["detail"]) if row else None


def _general_job(db):
    key = "oriward:resume-context:general"
    row = db.execute("SELECT id FROM jobs WHERE source_key=?", (key,)).fetchone()
    if row:
        return row["id"]
    return db.execute("INSERT INTO jobs(source_key,title,company,url,data,created_at) VALUES (?,?,?,?,?,?)",
                      (key, "通用简历", "", "", serialize({"kind": "resume_context", "is_vacancy": False,
                       "title": "通用简历", "company": "", "description": "", "location": ""}), now())).lastrowid


def _mapped(db, claim, ids):
    from .experience_library import validate_for_resume, usable_facts
    from .feedback import _packaging
    if isinstance(claim, str):
        claim = {"text": claim}
    if not isinstance(claim, dict):
        raise s.ValidationError("claim must be text or an object")
    text = safe_text(claim.get("text"), "claim.text")
    versions, sources = {}, []
    for eid in ids:
        exp = validate_for_resume(db, eid)
        versions[str(eid)] = exp["version"]
        sources.extend(usable_facts(exp))
    sources = list(dict.fromkeys(sources))
    quotes = claim.get("source_texts") or sources
    if not isinstance(quotes, list) or any(q not in sources for q in quotes):
        raise s.ValidationError("source_texts must refer to the selected experience; omit for automatic mapping")
    classification, pending = _packaging(claim, text, sources, quotes)
    return {"text": text, "experience_ids": ids, "experience_versions": versions,
            "source_texts": quotes, **classification}, pending


def _period(exp):
    context = exp.get("context")
    for key in ("time_period", "period", "dates", "date_range"):
        value = exp.get(key) or (context.get(key) if isinstance(context, dict) else None)
        if value:
            return str(value).strip()
    if exp.get("start_date"):
        return str(exp["start_date"]) + (" — " + str(exp["end_date"]) if exp.get("end_date") else "")
    return context if isinstance(context, str) and re.search(r"\d{4}", context) else ""


def _category(exp):
    if exp.get("category") in EXPERIENCE_CATEGORIES:
        return exp["category"]
    kind = exp.get("kind", exp.get("experience_type", ""))
    if kind in {"work", "employment"}: return "工作经历"
    if kind in {"business", "self_employment"}: return "经营经历"
    if kind == "internship": return "实习经历"
    return "其他经历"


EXPERIENCE_CATEGORIES = ("工作经历", "经营经历", "项目经历", "实习经历", "其他经历")
PROFILE_CATEGORIES = ("个人优势", "教育经历", "专业技能", "资格证书", "到岗安排", "个人兴趣")


def _profile_paragraphs(value):
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [line for item in value for line in _profile_paragraphs(item)]
    if isinstance(value, dict):
        if value.get("text"):
            return _profile_paragraphs(value["text"])
        keys = ("school", "institution", "degree", "major", "period", "start_date", "end_date",
                "graduation", "status", "name", "level")
        parts = [str(value[k]) for k in keys if value.get(k)]
        return [" · ".join(parts)] if parts else []
    return []


def _profile_defaults(profile):
    groups = {}
    for field, heading in (("education", "教育经历"), ("education_history", "教育经历"),
                           ("skills", "专业技能"), ("certifications", "资格证书")):
        groups.setdefault(heading, []).extend(_profile_paragraphs(profile.get(field)))
    summary = profile.get("summary_verified", "")
    summary_parts = [part.strip() for part in re.split(r"[。\n；]", summary) if part.strip()] if isinstance(summary, str) else []
    education_parts = [part for part in summary_parts
                       if re.search(r"大学|学院|中专|高中|本科|硕士|博士|专科|学士", part)]
    if not groups.get("教育经历"):
        # Legacy profiles put education in prose; preserve the entire matching sentence.
        groups["教育经历"] = education_parts
    groups["个人优势"] = [part for part in summary_parts if part not in education_parts
                          and not re.search(r"https?://|项目链接", part)]
    return {key: list(dict.fromkeys(values)) for key, values in groups.items() if values}


def compose(job_id, data):
    from copy import deepcopy
    from .experience_library import validate_for_resume, record_resume_sources, list_current, usable_facts
    from .feedback import ensure_schema, _id
    s.validate_dict(data, ["reason", "sections"])
    if not isinstance(data["sections"], list):
        raise s.ValidationError("sections must be an array")
    profile = s.get_profile()
    person = safe_text(profile.get("display_name"), "current display_name")
    requested = deepcopy(data)
    excluded = data.get("exclude_experience_ids", [])
    if not isinstance(excluded, list):
        raise s.ValidationError("exclude_experience_ids must be an array")
    excluded = {_id(eid, "exclude_experience_id") for eid in excluded}
    path, created = None, False
    with connect() as db:
        ensure_schema(db)
        if job_id is None:
            job_id = _general_job(db)
        one(db, "jobs", job_id)
        available = {row["id"]: validate_for_resume(db, row["id"]) for row in list_current(conn=db)
                     if not row["data"]["needs_review"] and usable_facts(row["data"])}
        section_data = deepcopy(data["sections"])
        supplied_ids = set()
        for section in section_data:
            ids = section.get("experience_ids", [section.get("experience_id")])
            if not isinstance(ids, list) or not ids:
                raise s.ValidationError("Each section requires experience_id or experience_ids")
            ids = [_id(eid, "experience_id") for eid in ids]
            if len(set(ids)) != len(ids) or supplied_ids.intersection(ids):
                raise s.ValidationError("Duplicate experience section")
            supplied_ids.update(ids)
            section["experience_ids"] = ids
        # Repair editorial omissions, without asking the user to approve a coverage table.
        restored = []
        for eid, exp in available.items():
            if eid not in supplied_ids and eid not in excluded:
                section_data.append({"experience_ids": [eid], "category": _category(exp), "mode": "brief"})
                restored.append(eid)
        mapping, rendered, selected, coverage, pending = [], [], [], [], False
        for section in section_data:
            original_ids = section["experience_ids"]
            ids = [eid for eid in original_ids if eid not in excluded]
            if not ids:
                continue
            if ids != original_ids:
                # Excluding one source must neither drop its neighbours nor retain its claims.
                section = {**section, "experience_ids": ids}
                section.pop("title", None)
                section.pop("title_claim", None)
                section.pop("links", None)
                section["bullets"] = [bullet for bullet in section.get("bullets", [])
                                      if isinstance(bullet, dict) and bullet.get("experience_ids")
                                      and set(bullet["experience_ids"]).issubset(ids)]
            exps = [validate_for_resume(db, eid) for eid in ids]
            selected.extend(ids)
            category = section.get("category", _category(exps[0]))
            if category not in EXPERIENCE_CATEGORIES:
                raise s.ValidationError("Unknown experience category")
            mode = section.get("mode", "expanded")
            if mode not in {"expanded", "brief"}:
                raise s.ValidationError("mode must be expanded or brief")
            title = safe_text(section.get("title") or exps[0]["event"], "experience title")
            entry, needs = _mapped(db, section.get("title_claim") or title, ids)
            if entry["text"] != title:
                raise s.ValidationError("title_claim text must match title")
            mapping.append({"field": "title", **entry}); pending |= needs
            lines = [f"### {title}"]
            metas = []
            for exp in exps:
                context, period = public_context(exp.get("context")), _period(exp)
                meta = context
                if period and period not in context:
                    meta = " · ".join(filter(None, [context, period]))
                if meta and meta not in metas:
                    metas.append(meta)
            lines.extend(f"*{safe_text(meta, 'experience context')}*" for meta in metas)
            lines.append("")
            bullets = section.get("bullets")
            if not bullets:
                bullets = []
                for exp in exps:
                    facts = exp.get("actions", []) + exp.get("outcomes", [])
                    if facts:
                        bullets.append(facts[0])
            if not isinstance(bullets, list):
                raise s.ValidationError("bullets must be an array")
            for bullet in bullets:
                bullet_ids = bullet.get("experience_ids", ids) if isinstance(bullet, dict) else ids
                if not isinstance(bullet_ids, list) or not bullet_ids or not set(bullet_ids).issubset(ids):
                    raise s.ValidationError("bullet experience_ids must belong to its section")
                entry, needs = _mapped(db, bullet, bullet_ids)
                mapping.append({"field": "bullet", "experience_id": bullet_ids[0],
                                "experience_version": entry["experience_versions"][str(bullet_ids[0])], **entry})
                pending |= needs
                lines.append("- " + entry["text"])
            for link in section.get("links", []):
                label, url = safe_text(link.get("label"), "link.label"), link.get("url")
                if not isinstance(url, str) or not re.fullmatch(r"https://[^\s)]+", url):
                    raise s.ValidationError("experience link must be an HTTPS URL")
                mapping.append({"field": "project_link", "experience_id": ids[0], "experience_ids": ids,
                                "text": label, "url": url, "source": "composition", "change_type": "wording_only"})
                lines.append(f"- 项目主页：[{label}]({url})")
            years = re.findall(r"\d{4}(?:[.\-/年]\d{1,2})?", _period(exps[0]))
            # Only known dates are sorted; no invented start/end dates for gaps.
            sort_key = tuple(int(n) for n in re.findall(r"\d+", years[0])) if years else (0,)
            rendered.append((category, sort_key, lines + [""]))
            coverage.extend({"experience_id": eid, "mode": mode, "title": title,
                             "automatically_retained": eid in restored} for eid in ids)
        profile_groups = _profile_defaults(profile)
        for item in data.get("profile_sections", []):
            heading, paragraphs = item.get("heading"), item.get("paragraphs")
            if heading not in PROFILE_CATEGORIES or not isinstance(paragraphs, list):
                raise s.ValidationError("profile sections require a known heading and paragraphs")
            if paragraphs:
                profile_groups[heading] = [safe_text(p.get("text") if isinstance(p, dict) else p,
                                                   "profile paragraph") for p in paragraphs]
        for heading, paragraphs in profile_groups.items():
            for paragraph in paragraphs:
                mapping.append({"field": "profile_section", "heading": heading, "text": paragraph,
                                "source": "profile", "source_snapshot": profile,
                                "change_type": "wording_only"})
        summary_text = None
        if data.get("summary"):
            summary = data["summary"]
            ids = summary.get("experience_ids", selected) if isinstance(summary, dict) else selected
            if isinstance(ids, list) and set(ids).intersection(excluded):
                ids = []  # Do not revive an explicitly excluded source through an old summary.
            elif not isinstance(ids, list) or not ids or not set(ids).issubset(selected):
                raise s.ValidationError("summary experience_ids must belong to the resume")
            if ids:
                entry, needs = _mapped(db, summary, ids)
                mapping.append({"field": "summary", **entry}); pending |= needs
                summary_text = entry["text"]
        lines = [f"# {person}", ""]
        contact = profile.get("contact", {})
        if isinstance(contact, dict):
            values = [safe_text(str(contact[k]), "contact") for k in ("email", "phone", "portfolio") if contact.get(k)]
            if values: lines += [" · ".join(values), ""]
        if data.get("headline"):
            lines += [f"*申请方向：{safe_text(data['headline'], 'headline')}*", ""]
        if summary_text:
            if not any(item.get("heading") == "个人优势" for item in data.get("profile_sections", [])):
                profile_groups["个人优势"] = []
            profile_groups.setdefault("个人优势", []).insert(0, summary_text)
        work_first = any(category in {"工作经历", "经营经历"} for category, _, _ in rendered)
        default_order = (("个人优势", "工作经历", "经营经历", "项目经历", "实习经历", "其他经历", "教育经历", "专业技能")
                         if work_first else ("个人优势", "教育经历", "专业技能", *EXPERIENCE_CATEGORIES))
        order = data.get("section_order", list(default_order))
        if not isinstance(order, list) or any(h not in (*PROFILE_CATEGORIES, *EXPERIENCE_CATEGORIES) for h in order):
            raise s.ValidationError("section_order must contain known section headings")
        order = list(dict.fromkeys([*order, *PROFILE_CATEGORIES, *EXPERIENCE_CATEGORIES]))
        for heading in order:
            paragraphs = profile_groups.get(heading, [])
            group = [item for item in rendered if item[0] == heading]
            if heading in {"工作经历", "经营经历", "实习经历", "其他经历"}:
                group.sort(key=lambda item: item[1], reverse=True)
            if paragraphs or group:
                lines += [f"## {heading}", ""]
            lines.extend(line for paragraph in paragraphs for line in (paragraph, ""))
            for _, _, content_lines in group:
                lines += content_lines
        content = "\n".join(lines)
        try:
            cursor = db.execute("INSERT INTO resumes(job_id,experience_ids,output_path,sha256,created_at) VALUES (?,?,?,?,?)",
                                (job_id, serialize(selected), "PENDING", hashlib.sha256(content.encode("utf-8")).hexdigest(), now()))
            rid = cursor.lastrowid
            path = artifact_path(db, rid)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                created = True
                handle.write(content)
            db.execute("UPDATE resumes SET output_path=? WHERE id=?", (str(path.resolve()), rid))
            status = "pending" if pending else "draft"
            db.execute("INSERT INTO resume_versions VALUES (?,?,?,?,?,?,?,?)",
                       (rid, rid, None, "[]", safe_text(data["reason"], "reason"), serialize(mapping), status, now()))
            record_resume_sources(db, rid, selected)
            # Persist resolved coverage and composition separately from candidate-facing prose.
            requested["sections"] = section_data
            requested["_profile_snapshot"] = profile
            # audit() truncates human log messages to 200 chars; these are full version snapshots.
            for kind, payload in (("resume.composition", requested), ("resume.coverage", coverage)):
                db.execute("INSERT INTO audit_events(kind,resource,resource_id,detail,created_at) VALUES (?,?,?,?,?)",
                           (kind, "resumes", rid, serialize(payload), now()))
            audit(db, "resume.composed", "resumes", rid, "draft generated")
        except Exception:
            if created and path:
                path.unlink(missing_ok=True)
            raise
    return {"id": rid, "path": str(path), "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "factual_status": status, "requires_new_review": False,
            "whole_draft_review_required": False, "review_suggested": True,
            "pending_new_facts": [m for m in mapping if m.get("change_type") == "new_facts"],
            "coverage": coverage, "automatically_retained_ids": restored,
            "excluded_experience_ids": sorted(excluded), "required_experience_ids": [],
            "retention": cleanup(job_id=job_id, apply=True, rename=False)}


def cleanup(*, job_id=None, apply=False, rename=True, purge=False):
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
        retained_paths = ({s.resume_path(row).resolve() for group in groups.values() for row in group[:4]}
                          if not purge else set())
        selected_ids = {row["id"] for group in groups.values() for row in group}
        handled_paths = set()
        for group in groups.values():
            for position, row in enumerate(group):
                path = s.resume_path(row)
                resolved = path.resolve()
                if (not resolved.is_relative_to(root) or path.suffix.lower() != ".md"
                        or path.is_symlink() or path.absolute() != resolved):
                    skipped.append({"id": row["id"], "reason": "outside root, symlink or non-Markdown"}); continue
                if purge:
                    if resolved in handled_paths:
                        if apply:
                            db.execute("UPDATE resumes SET artifact_state='pruned' WHERE id=?", (row["id"],))
                        continue
                    external_refs = db.execute("SELECT id FROM resumes WHERE output_path=? AND id NOT IN (" +
                                               ",".join("?" for _ in selected_ids) + ")",
                                               (str(resolved), *selected_ids)).fetchall() if selected_ids else []
                    if external_refs:
                        skipped.append({"id": row["id"], "reason": "path also belongs to a resume outside purge scope"})
                        continue
                    if path.exists():
                        operations.append({"id": row["id"], "action": "delete", "path": str(path)})
                        if apply:
                            path.unlink()
                    elif not path.exists():
                        operations.append({"id": row["id"], "action": "mark_pruned", "path": str(path)})
                    handled_paths.add(resolved)
                    if apply:
                        db.execute("UPDATE resumes SET artifact_state='pruned' WHERE id=?", (row["id"],))
                    continue
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
    keep = "no Markdown files; records retained" if purge else "current + 3 historical Markdown per job"
    return {"dry_run": not apply, "keep": keep, "operations": operations, "skipped": skipped}
