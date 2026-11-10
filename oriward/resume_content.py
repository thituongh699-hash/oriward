"""Source-mapped tailored composition and bounded Markdown artifact retention."""
from __future__ import annotations

import hashlib
import re

from . import services as s
from .db import audit, connect, deserialize, now, one, serialize


def public_context(value):
    """Only public date/organisation context belongs in a candidate document."""
    if isinstance(value, dict):
        raw = " · ".join(str(value[k]) for k in
                         ("organization", "organisation", "company", "location", "period", "dates", "date_range")
                         if value.get(k) and isinstance(value[k], (str, int)))
    elif isinstance(value, str):
        raw = value
    else:
        return ""
    # Recovered contexts can include source locators; keep dates and roles but
    # prevent local paths and provenance notes from entering candidate-facing text.
    raw = re.sub(r"(?:[A-Za-z]:[\\/][^；。]+|/(?:home|Users|tmp)/[^；。]+)", "", raw)
    raw = re.sub(r"(?:详细原始来源见|详细原始来源|原始来源|商业计划书来源|旧记录来源|来源)[：:].*?(?=。|；|$)", "", raw)
    raw = re.sub(r"(?:source_record和evidence|Codex 会话)[^。；]*", "", raw)
    # Free-form recovered contexts often mix dates with internal provenance;
    # expose only date-like fragments and rely on _period for the full timeline.
    endpoint = r"(?:约)?\d{4}(?:年(?:\d{1,2}月(?:\d{1,2}日)?)?|[./-]\d{1,2}(?:[./-]\d{1,2})?)?"
    date = r"(?:约)?\d{4}(?:年\d{1,2}月(?:\d{1,2}日)?|[./-]\d{1,2}(?:[./-]\d{1,2})?)"
    dates = re.findall(rf"{endpoint}\s*(?:[–—~～-]|至)\s*(?:至今|现在|今|{endpoint})|{date}", raw)
    if not dates and re.fullmatch(endpoint, raw.strip()):
        dates = [raw.strip()]
    raw = " · ".join(dict.fromkeys(dates))
    return safe_text(raw, "context") if raw else ""


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


def _build_target(job_id=None, reference_job_ids=None, *, title=None):
    """Build one target from an optional primary JD and supplementary references."""
    from .assessment import _job_sha256, _latest_structured_analysis
    if reference_job_ids is None:
        reference_job_ids = []
    if not isinstance(reference_job_ids, (list, tuple)):
        raise s.ValidationError("reference_job_ids must be a list of saved job IDs")
    try:
        references = list(dict.fromkeys(int(value) for value in reference_job_ids))
        primary_id = int(job_id) if job_id is not None else None
    except (TypeError, ValueError) as exc:
        raise s.ValidationError("target IDs must be saved job IDs") from exc
    references = [value for value in references if value != primary_id]
    if primary_id is not None and not references:
        primary = s.get_job(primary_id)
        if primary.get("kind") == "resume_context":
            if title is not None:
                raise s.ValidationError("target_title requires a vacancy or reference job")
            return {"type": "baseline", "title": "通用简历", "primary_job_id": None,
                    "reference_job_ids": [], "jobs": []}, {"primary": None, "references": []}
    ids = ([primary_id] if primary_id is not None else []) + references
    if not ids:
        if title is not None:
            raise s.ValidationError("target_title requires a primary or reference job")
        return {"type": "baseline", "title": "通用简历", "primary_job_id": None,
                "reference_job_ids": [], "jobs": []}, {"primary": None, "references": []}
    if primary_id is None and not (str(title or "").strip()):
        raise s.ValidationError("target_title is required when no primary job is selected")
    jobs_by_id = {}
    analyses = []
    with connect() as db:
        for selected_id in ids:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (selected_id,)).fetchone()
            if row is None:
                raise s.ValidationError(f"Saved job #{selected_id} not found")
            job = deserialize(row["data"])
            if job.get("kind") == "resume_context" or not str(job.get("description", "")).strip():
                raise s.ValidationError(f"Job #{selected_id} must be a saved vacancy with a nonempty JD")
            jobs_by_id[selected_id] = {"id": selected_id, **job}
            analysis = _latest_structured_analysis(db, selected_id)
            if analysis:
                analysis["freshness"] = "current" if analysis["data"].get("job_sha256") == _job_sha256(job) else "stale"
                analyses.append({"job_id": selected_id, **analysis})
    snapshot_jobs = []
    for selected_id in ids:
        job = jobs_by_id[selected_id]
        snapshot_jobs.append({"id": selected_id, "role": "primary" if selected_id == primary_id else "reference",
                              **{key: job.get(key, "") for key in (
            "id", "title", "company", "location", "description", "url", "source",
            "published_at", "listed_at", "retrieved_at", "valid_through")}})
    title = str(title).strip() if title is not None else jobs_by_id[primary_id]["title"]
    if not title:
        raise s.ValidationError("target_title must be nonempty")
    target_type = "job" if primary_id is not None else "direction"
    snapshot = {"type": target_type, "title": title, "primary_job_id": primary_id,
                "reference_job_ids": references, "jobs": snapshot_jobs}
    analyses_by_id = {item["job_id"]: item for item in analyses}
    return snapshot, {"primary": analyses_by_id.get(primary_id),
                      "references": [analyses_by_id.get(reference_id) for reference_id in references]}


def _single_target(job_id):
    if job_id is None or s.get_job(job_id).get("kind") == "resume_context":
        return {"type": "baseline", "title": "通用简历", "primary_job_id": None,
                "reference_job_ids": [], "jobs": []}
    return _build_target(job_id)[0]


def tailor_packet(job_id=None, *, reference_job_ids=None, target_title=None, offset=0, budget=6000):
    """One bounded page, with an explicit continuation; no approval prerequisite."""
    from .experience_library import index
    target, target_analyses = _build_target(job_id, reference_job_ids, title=target_title)
    job = s.get_job(job_id) if job_id is not None else None
    if job_id is not None and target["type"] == "job":
        from .assessment import analysis_packet
        analysis = {**target_analyses, "primary": analysis_packet(job_id)}
    else:
        analysis = target_analyses
    page = index(budget=budget, offset=offset)
    ids = [item["id"] for item in page["items"]]
    profile = s.get_profile()
    template, section_order = _layout({}, profile)
    return {"job_id": job_id, "reference_job_ids": target["reference_job_ids"], "target": target,
            "job": job,
            "profile": profile,
            "resume_preferences": profile.get("resume_preferences", {}),
            "template": template, "section_order": section_order,
            "template_path": f"docs/assets/resume-templates/{template}/preview.png",
            "layout_guidance": "Keep the selected template; skills and certificates are H3 under 个人优势; arrival belongs in the header. Education entries are degree H3 blocks with their assigned academic bullets.",
            "analysis": analysis,
            "experience_index": page,
            "experience_details": [],
            "detail_requests": {"ids": ids, "sections": ["event", "time_period", "actions", "outcomes"],
                                "command": "experience detail --ids <selected IDs> --sections actions,outcomes,time_period"},
            "required_experience_ids": [],  # deprecated: experience approval is not a coverage rule
            "next_offset": page["next_offset"],
            "has_more": page["next_offset"] < page["total_count"],
            "next": ("Read the primary JD first when present; references are supplementary context, not extra gates. "
                     "With a direction target, use its references to understand the intended work. Then read all "
                     "experience index pages, request selective details, map requirements to evidence, build compact "
                     "STAR-C examples, compose a complete resume, and check semantic fit and readability. Optional "
                     "text lint is separate. Do not rank or keyword-score JDs automatically. "
                     "Compose a complete draft directly; user self-report needs no additional approval."),
            "translation_focus": ["What did the person actually do?", "Which working ability does that demonstrate?",
                                  "Which target task uses that ability?", "What small practice could bridge the remaining gap?"],
            "contract": {"sections": [{"experience_id": 1, "category": "工作经历", "mode": "expanded",
                                        "bullets": ["Natural, factual wording for the target role"]}],
                         "experience_ids": "Use instead of experience_id to group events from one career stage",
                         "section_fields": ["experience_id OR experience_ids", "category", "mode", "title?", "title_claim?", "bullets", "links?", "education_key?"],
                         "claim": {"text": "Authored wording", "experience_ids": [1], "source_texts": ["Optional exact source fact"], "change_type": "exact | wording_only | new_facts | unclassified", "new_facts": "Explicit nonempty array only for new_facts"},
                         "links": [{"label": "Public project link", "url": "https://example.invalid/project"}],
                         "headline": "Optional application direction in header",
                         "summary": "Optional text or source-mapped claim; experience_ids must belong to selected sections",
                         "categories": list(EXPERIENCE_CATEGORIES),
                         "mode": "expanded requires explicit nonempty bullets; brief requires explicit bullets and may use [] for title/date chronology",
                         "exclude_experience_ids": "Optional explicit exclusions; unselected experiences stay omitted",
                         "education_entries": [{"key": "degree-key", "title": "School · degree · major grounded in profile", "meta": "Known dates/status", "paragraphs": ["Optional grounded education prose"]}],
                         "education_key": "Required on 教育经历 sections; must match an education_entries key; academic bullets are rendered under that degree",
                         "profile_sections": "optional profile paragraphs; legacy education is preserved only when education_entries is absent",
                         "profile_section_fields": {"heading": "个人优势 | 教育经历 | 专业技能 | 资格证书 | 到岗安排 | 个人兴趣", "paragraphs": ["Grounded profile wording; skills/certificates nest under strengths; arrival appears in header"]},
                         "template": "reference | modern-cn | clean; data then saved preference then reference",
                         "section_order": "optional top-level headings; data then saved preference then default strengths/education/work/project/internship",
                         "selection_notes": "Optional background object/text: model rationale, omissions, timeline decisions; never asks user to approve a coverage table",
                         "chronology": "Read the complete index, decide expanded/brief/omitted stages, explain important omissions or gaps in selection_notes; Python never restores omitted items",
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


def _direction_job(db, title, reference_job_ids):
    key = "oriward:resume-context:direction:" + serialize({"title": title, "reference_job_ids": sorted(reference_job_ids)})
    row = db.execute("SELECT id FROM jobs WHERE source_key=?", (key,)).fetchone()
    if row:
        return row["id"]
    data = {"kind": "resume_context", "is_vacancy": False, "title": title, "company": "",
            "description": "", "location": "", "reference_job_ids": sorted(reference_job_ids)}
    return db.execute("INSERT INTO jobs(source_key,title,company,url,data,created_at) VALUES (?,?,?,?,?,?)",
                      (key, title, "", "", serialize(data), now())).lastrowid


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
    if isinstance(context, str) and re.search(r"(?:^|[^0-9A-Za-z])(?:约)?\d{4}", context):
        return public_context(context)
    return ""


def _category(exp):
    if exp.get("category"):
        return _canonical_category(exp["category"])
    kind = exp.get("kind", exp.get("experience_type", ""))
    if kind in {"work", "employment"}: return "工作经历"
    if kind in {"business", "self_employment"}: return "工作经历"
    if kind == "internship": return "实习经历"
    if kind == "education": return "教育经历"
    return "项目经历"


EXPERIENCE_CATEGORIES = ("工作经历", "项目经历", "实习经历", "教育经历")
PROFILE_CATEGORIES = ("个人优势", "教育经历", "专业技能", "资格证书", "到岗安排", "个人兴趣")
DEFAULT_SECTION_ORDER = ["个人优势", "教育经历", "工作经历", "项目经历", "实习经历"]


def _canonical_category(value):
    aliases = {"work": "工作经历", "business": "工作经历", "经营经历": "工作经历",
               "project": "项目经历", "internship": "实习经历", "education": "教育经历"}
    category = aliases.get(value, value)
    if category == "其他经历":
        raise s.ValidationError("其他经历 is not a resume category; reclassify as 工作经历/项目经历/实习经历, or attach academic content to 教育经历 with education_key")
    if category not in EXPERIENCE_CATEGORIES:
        raise s.ValidationError("Unknown experience category; use 工作经历/项目经历/实习经历/教育经历")
    return category


def _layout(data, profile):
    preferences = profile.get("resume_preferences", {})
    if not isinstance(preferences, dict):
        preferences = {}
    template = data.get("template", preferences.get("template", "reference"))
    if template not in {"reference", "modern-cn", "clean"}:
        raise s.ValidationError("template must be reference|modern-cn|clean")
    order = data.get("section_order", preferences.get("section_order", DEFAULT_SECTION_ORDER))
    if not isinstance(order, list):
        raise s.ValidationError("section_order must be an array of known headings")
    normalized = []
    for heading in order:
        if heading in {"专业技能", "资格证书"}:
            heading = "个人优势"
        elif heading == "到岗安排":
            continue
        elif heading == "经营经历":
            heading = "工作经历"
        if heading not in (*DEFAULT_SECTION_ORDER, "个人兴趣"):
            raise s.ValidationError("section_order must contain known top-level headings")
        if heading not in normalized:
            normalized.append(heading)
    return template, list(dict.fromkeys([*normalized, *DEFAULT_SECTION_ORDER]))


def _education_entries(data):
    entries = data.get("education_entries", [])
    if not isinstance(entries, list):
        raise s.ValidationError("education_entries must be an array")
    result, keys = [], set()
    for item in entries:
        if not isinstance(item, dict):
            raise s.ValidationError("education entry must be an object")
        key = safe_text(item.get("key"), "education.key")
        if key in keys:
            raise s.ValidationError("education_entries keys must be unique")
        keys.add(key)
        paragraphs = item.get("paragraphs", [])
        if not isinstance(paragraphs, list):
            raise s.ValidationError("education paragraphs must be an array")
        result.append({"key": key, "title": safe_text(item.get("title"), "education.title"),
                       "meta": safe_text(item["meta"], "education.meta") if item.get("meta") else "",
                       "paragraphs": [safe_text(p, "education paragraph") for p in paragraphs]})
    return result


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
                           ("skills", "专业技能"), ("certifications", "资格证书"),
                           ("availability", "到岗安排")):
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


def compose(job_id, data, *, reference_job_ids=None, target_title=None):
    from copy import deepcopy
    from .experience_library import validate_for_resume, record_resume_sources
    from .feedback import ensure_schema, _id
    s.validate_dict(data, ["reason", "sections"])
    if not isinstance(data["sections"], list):
        raise s.ValidationError("sections must be an array")
    saved_snapshot = data.get("_target_snapshot")
    if target_title is not None or reference_job_ids is not None:
        target_snapshot, _ = _build_target(job_id, reference_job_ids, title=target_title)
    elif isinstance(saved_snapshot, dict) and saved_snapshot.get("type") in {"job", "direction"}:
        saved_primary = saved_snapshot.get("primary_job_id")
        context_target = job_id is not None and _single_target(job_id)["type"] == "baseline"
        if (saved_primary is not None and int(job_id or 0) == saved_primary) or (saved_primary is None and context_target):
            # Feedback revisions keep the exact JD inputs used by the base version.
            target_snapshot = saved_snapshot
        else:
            target_snapshot, _ = _build_target(
                job_id, saved_snapshot.get("reference_job_ids", []))
    else:
        target_snapshot, _ = _build_target(job_id)
    profile = s.get_profile()
    person = safe_text(profile.get("display_name"), "current display_name")
    requested = deepcopy(data)
    template, order = _layout(data, profile)
    education_entries = _education_entries(data)
    if "education_entries" in data and not education_entries and _profile_defaults(profile).get("教育经历"):
        raise s.ValidationError("education_entries cannot be empty when profile education exists; supply grounded degree entries or omit the field to preserve legacy education")
    education_keys = {item["key"] for item in education_entries}
    excluded = data.get("exclude_experience_ids", [])
    if not isinstance(excluded, list):
        raise s.ValidationError("exclude_experience_ids must be an array")
    excluded = {_id(eid, "exclude_experience_id") for eid in excluded}
    path, created = None, False
    with connect() as db:
        ensure_schema(db)
        if target_snapshot["type"] == "direction":
            job_id = _direction_job(db, target_snapshot["title"], target_snapshot["reference_job_ids"])
        elif job_id is None:
            job_id = _general_job(db)
        one(db, "jobs", job_id)
        section_data = deepcopy(data["sections"])
        supplied_ids = set()
        for section in section_data:
            if not isinstance(section, dict):
                raise s.ValidationError("section must be an object")
            ids = section.get("experience_ids", [section.get("experience_id")])
            if not isinstance(ids, list) or not ids:
                raise s.ValidationError("Each section requires experience_id or experience_ids")
            ids = [_id(eid, "experience_id") for eid in ids]
            if len(set(ids)) != len(ids) or supplied_ids.intersection(ids):
                raise s.ValidationError("Duplicate experience section")
            supplied_ids.update(ids)
            section["experience_ids"] = ids
        mapping, rendered, selected, coverage, pending, effective_sections = [], [], [], [], False, []
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
                if not section["bullets"]:
                    section["mode"] = "brief"
            exps = [validate_for_resume(db, eid) for eid in ids]
            selected.extend(ids)
            category = _canonical_category(section["category"]) if "category" in section else _category(exps[0])
            section["category"] = category
            education_key = section.get("education_key")
            if category == "教育经历" and education_key not in education_keys:
                raise s.ValidationError("Academic 教育经历 sections require education_key matching an education_entries degree")
            mode = section.get("mode", "expanded")
            if mode not in {"expanded", "brief"}:
                raise s.ValidationError("mode must be expanded or brief")
            title = safe_text(section.get("title") or exps[0]["event"], "experience title")
            entry, needs = _mapped(db, section.get("title_claim") or title, ids)
            if entry["text"] != title:
                raise s.ValidationError("title_claim text must match title")
            mapping.append({"field": "title", **entry}); pending |= needs
            # Academic claims are assigned to their degree, never a separate research H3.
            lines = [] if category == "教育经历" else [f"### {title}"]
            metas = []
            for exp in exps:
                context_value, period = exp.get("context"), _period(exp)
                explicit_period = any(exp.get(key) for key in ("time_period", "period", "dates", "date_range", "start_date"))
                if isinstance(context_value, dict):
                    explicit_period = explicit_period or any(context_value.get(key) for key in ("time_period", "period", "dates", "date_range"))
                    # Structured organisation is public metadata; free prose
                    # dates can instead identify interviews or recollections.
                    organization = " · ".join(safe_text(str(context_value[key]), "experience organization")
                                              for key in ("organization", "organisation", "company", "location")
                                              if context_value.get(key) and isinstance(context_value[key], (str, int)))
                else:
                    organization = ""
                context = organization if organization or explicit_period else public_context(context_value)
                meta = context
                if period and period not in context:
                    meta = " · ".join(filter(None, [context, period]))
                if meta and meta not in metas:
                    metas.append(meta)
            if category != "教育经历":
                lines.extend(f"*{safe_text(meta, 'experience context')}*" for meta in metas)
            lines.append("")
            bullets = section.get("bullets")
            if not isinstance(bullets, list):
                raise s.ValidationError("bullets must be an explicit array; write expanded bullets or choose brief with []")
            if mode == "expanded" and not bullets:
                raise s.ValidationError("expanded sections require explicit nonempty bullets; choose brief with [] for title/date chronology")
            effective_sections.append(section)
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
            rendered.append((category, sort_key, lines + [""], education_key))
            coverage.extend({"experience_id": eid, "mode": mode, "title": title,
                             "automatically_retained": False} for eid in ids)
        profile_groups = _profile_defaults(profile)
        if "education_entries" in data:
            profile_groups.pop("教育经历", None)
        for item in data.get("profile_sections", []):
            heading, paragraphs = item.get("heading"), item.get("paragraphs")
            if heading not in PROFILE_CATEGORIES or not isinstance(paragraphs, list):
                raise s.ValidationError("profile sections require a known heading and paragraphs")
            if heading == "教育经历" and "education_entries" in data:
                raise s.ValidationError("Use education_entries paragraphs for education when degree entries are supplied")
            profile_groups[heading] = [safe_text(p.get("text") if isinstance(p, dict) else p,
                                               "profile paragraph") for p in paragraphs]
            if heading == "个人兴趣" and paragraphs and heading not in order:
                order.append(heading)
        for heading, paragraphs in profile_groups.items():
            for paragraph in paragraphs:
                mapping.append({"field": "profile_section", "heading": heading, "text": paragraph,
                                "source": "profile", "source_snapshot": profile,
                                "change_type": "wording_only"})
        for degree in education_entries:
            for field in ("title", "meta", "paragraphs"):
                values = degree[field] if isinstance(degree[field], list) else [degree[field]]
                for text in filter(None, values):
                    mapping.append({"field": "education_entry", "education_key": degree["key"], "text": text,
                                    "source": "profile", "source_snapshot": profile, "change_type": "wording_only"})
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
        if profile_groups.get("到岗安排"):
            lines += [" · ".join(profile_groups.pop("到岗安排")), ""]
        if summary_text:
            if not any(item.get("heading") == "个人优势" for item in data.get("profile_sections", [])):
                profile_groups["个人优势"] = []
            profile_groups.setdefault("个人优势", []).insert(0, summary_text)
        for heading in order:
            paragraphs = profile_groups.get(heading, [])
            group = [item for item in rendered if item[0] == heading]
            if heading in {"工作经历", "实习经历"}:
                group.sort(key=lambda item: item[1], reverse=True)
            subgroups = [(subheading, profile_groups.get(subheading, [])) for subheading in ("专业技能", "资格证书")] if heading == "个人优势" else []
            if paragraphs or group or any(values for _, values in subgroups) or (heading == "教育经历" and education_entries):
                lines += [f"## {heading}", ""]
            lines.extend(line for paragraph in paragraphs for line in (paragraph, ""))
            for subheading, values in subgroups:
                if values:
                    lines += [f"### {subheading}", ""]
                    lines.extend(line for paragraph in values for line in (paragraph, ""))
            if heading == "教育经历":
                for degree in education_entries:
                    lines += [f"### {degree['title']}", ""]
                    if degree["meta"]:
                        lines += [f"*{degree['meta']}*", ""]
                    lines.extend(line for paragraph in degree["paragraphs"] for line in (paragraph, ""))
                    for _, _, content_lines, key in group:
                        if key == degree["key"]:
                            lines += content_lines
            else:
                for _, _, content_lines, _ in group:
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
            requested["sections"] = effective_sections
            requested["_profile_snapshot"] = profile
            requested["_target_snapshot"] = target_snapshot
            requested["template"] = template
            requested["section_order"] = order
            if "education_entries" in data:
                requested["education_entries"] = education_entries
            # audit() truncates human log messages to 200 chars; these are full version snapshots.
            for kind, payload in (("resume.composition", requested), ("resume.coverage", coverage)):
                db.execute("INSERT INTO audit_events(kind,resource,resource_id,detail,created_at) VALUES (?,?,?,?,?)",
                           (kind, "resumes", rid, serialize(payload), now()))
            audit(db, "resume.composed", "resumes", rid, "draft generated")
        except Exception:
            if created and path:
                path.unlink(missing_ok=True)
            raise
    targeted = target_snapshot["type"] == "job"
    return {"id": rid, "path": str(path), "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "factual_status": status, "requires_new_review": False,
            "whole_draft_review_required": False, "review_suggested": targeted,
            "editorial_review_required": True, "next": f"resume editorial-packet --resume-id {rid}",
            "template": template, "section_order": order,
            "workflow": {"mode": ("job_targeted" if targeted else
                                    "direction_targeted" if target_snapshot["type"] == "direction" else "baseline_only"),
                          "command": f"resume workflow --job-id {job_id} --resume-id {rid}" if targeted else None,
                          "next": ("当前是方向性草稿；选定主岗位后可沿用该经历组织，为主岗位补充专版"
                                   if target_snapshot["type"] == "direction" else
                                   "评级与模拟面试必须绑定本岗位和这个简历版本" if targeted else
                                   "先选择真实岗位，再进入评级和模拟面试")},
            "pending_new_facts": [m for m in mapping if m.get("change_type") == "new_facts"],
            "coverage": coverage, "automatically_retained_ids": [],
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
