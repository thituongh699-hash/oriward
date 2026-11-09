"""Local resume import, actionable checks and sourced market observations."""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

from . import services as s
from .db import audit, connect, database_path, deserialize, now, one, serialize


ROLE_PACKS = {
    "product": {"label": "产品", "titles": ("产品", "product manager", "product owner"),
                "terms": ("需求分析", "用户研究", "产品规划", "原型", "数据分析", "迭代", "商业化")},
    "operations": {"label": "运营", "titles": ("运营", "operations", "growth"),
                   "terms": ("用户运营", "活动运营", "内容运营", "增长", "转化", "留存", "数据分析")},
    "sales_success": {"label": "销售/客户成功", "titles": ("销售", "客户成功", "客户经理", "sales", "customer success"),
                      "terms": ("客户开发", "商机", "成交", "续约", "客户维护", "需求挖掘")},
    "people_admin": {"label": "人力/行政", "titles": ("人力", "招聘", "行政", "hr", "human resources"),
                     "terms": ("招聘", "培训", "绩效", "员工关系", "行政流程", "组织协调")},
    "finance": {"label": "财务", "titles": ("财务", "会计", "审计", "finance", "accountant"),
                "terms": ("财务分析", "预算", "核算", "报表", "审计", "税务", "成本")},
    "data_tech": {"label": "数据/技术", "titles": ("数据", "开发", "工程师", "算法", "data", "engineer"),
                  "terms": ("sql", "python", "数据建模", "系统设计", "测试", "部署", "性能")},
}


def role_family(title):
    value = str(title or "").casefold()
    for key, pack in ROLE_PACKS.items():
        if any(term in value for term in pack["titles"]):
            return key
    return None


def _source_lines(path, raw):
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = raw.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise s.ValidationError("Text resume is not valid UTF-8 or GB18030") from exc
        return text.splitlines(), []
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                root = ElementTree.fromstring(archive.read("word/document.xml"))
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
            raise s.ValidationError("DOCX cannot be parsed") from exc
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        lines = ["".join(node.text or "" for node in para.iter(ns + "t"))
                 for para in root.iter(ns + "p")]
        return lines, ["DOCX headers, footers and floating text may be missing; compare with the original document."]
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise s.ValidationError("PDF import requires the optional documents dependency: pip install '.[documents]'") from exc
        try:
            reader = PdfReader(io.BytesIO(raw))
            lines = [line for page in reader.pages for line in (page.extract_text() or "").splitlines()]
        except Exception as exc:
            raise s.ValidationError("PDF text cannot be extracted; use a text-based PDF or paste the text") from exc
        return lines, ["PDF text order and columns may differ from the visible page; compare with the original document."]
    raise s.ValidationError("Resume format must be PDF, DOCX, TXT or Markdown")


def import_resume(file):
    path = Path(file).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in {".pdf", ".docx", ".txt", ".md"}:
        raise s.ValidationError("Resume must be an existing PDF, DOCX, TXT or Markdown file")
    if path.stat().st_size > 10 * 1024 * 1024:
        raise s.ValidationError("Resume file exceeds 10 MB")
    raw = path.read_bytes()
    lines, warnings = _source_lines(path, raw)
    numbered = [{"id": index, "text": text.strip()} for index, text in enumerate(lines, 1) if text.strip()]
    if not numbered or sum(len(item["text"]) for item in numbered) < 20:
        raise s.ValidationError("Resume has too little extractable text; OCR or a text copy is needed")
    if len(numbered) < 5:
        warnings.append("Only a few text lines were extracted; check whether content is missing.")
    root = database_path().parent / "resume-inputs"
    destination = None
    with connect() as db:
        cursor = db.execute("INSERT INTO resume_inputs(original_name,format,private_path,source_hash,lines_json,warnings_json,created_at) "
                            "VALUES (?,?,?,?,?,?,?)", (path.name, path.suffix.lower()[1:], "PENDING",
                            hashlib.sha256(raw).hexdigest(), serialize(numbered), serialize(warnings), now()))
        input_id = cursor.lastrowid
        root.mkdir(parents=True, exist_ok=True)
        destination = root / f"resume-{input_id}{path.suffix.lower()}"
        try:
            with destination.open("xb") as handle:
                handle.write(raw)
            db.execute("UPDATE resume_inputs SET private_path=? WHERE id=?", (str(destination), input_id))
            audit(db, "resume.input.imported", "resume_inputs", input_id, path.name)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
    return {"input_id": input_id, "source_name": path.name, "format": path.suffix.lower()[1:],
            "line_count": len(numbered), "warnings": warnings,
            "next": f"resume input --id {input_id}; read the target JD, then select relevant experience details before writing"}


def input_record(input_id):
    with connect() as db:
        row = db.execute("SELECT * FROM resume_inputs WHERE id=?", (int(input_id),)).fetchone()
        if row is None:
            raise s.ValidationError(f"resume input {input_id} not found")
        record = dict(row)
    record["lines"] = deserialize(record.pop("lines_json"))
    record["warnings"] = deserialize(record.pop("warnings_json"))
    return record


def _content(input_id=None, resume_id=None):
    if (input_id is None) == (resume_id is None):
        raise s.ValidationError("Select exactly one --input-id or --resume-id")
    if input_id is not None:
        record = input_record(input_id)
        return {"source": "import", "id": int(input_id), "lines": record["lines"], "warnings": record["warnings"]}
    with connect() as db:
        row = one(db, "resumes", int(resume_id))
        path = s.verify_resume(row)
    lines = [{"id": index, "text": text.strip()} for index, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
             if text.strip()]
    return {"source": "resume", "id": int(resume_id), "lines": lines, "warnings": []}


def diagnose(*, input_id=None, resume_id=None, job_id=None):
    document = _content(input_id, resume_id)
    lines = document["lines"]
    joined = "\n".join(item["text"] for item in lines)
    issues = []

    def add(kind, severity, location, impact, action):
        issues.append({"kind": kind, "severity": severity, "location": location,
                       "impact": impact, "action": action})

    headings = [item for item in lines if re.match(r"^#{1,3}\s+", item["text"])
                or item["text"] in {"工作经历", "项目经历", "教育经历", "专业技能", "实习经历", "个人优势"}]
    if not headings:
        add("structure", "medium", {"line_ids": [], "quote": ""},
            "无法可靠识别栏目，可能是文件解析或标题层级问题。", "对照原文件核对栏目，并使用清晰的普通文本标题。")
    if not re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", joined):
        add("contact", "medium", {"line_ids": [], "quote": ""},
            "提取文本中未定位到邮箱；也可能是解析遗漏。", "核对原件中的联系方式和拼写。")
    if not re.search(r"(?:19|20)\d{2}", joined):
        add("chronology", "medium", {"line_ids": [], "quote": ""},
            "提取文本中未定位到年份；时间线可能不清楚。", "核对教育及主要经历的真实起止时间。")
    vague = re.compile(r"(?:主要负责|参与了|协助了|熟悉|了解|较强的|丰富的经验|显著提升)")
    seen_lines = {}
    for item in lines:
        text = item["text"]
        if text.startswith("#") or len(text) < 12:
            continue
        normalized = re.sub(r"[\s，。；;：:、·•*-]", "", text).casefold()
        if normalized in seen_lines:
            add("redundancy", "low", {"line_ids": [seen_lines[normalized], item["id"]], "quote": text[:120]},
                "相同内容重复出现，挤占相关经历的空间。", "核对两处是否描述同一件事，保留更具体的一处。")
        else:
            seen_lines[normalized] = item["id"]
        if vague.search(text):
            add("action_or_ownership", "medium", {"line_ids": [item["id"]], "quote": text[:120]},
                "表述可能没有说清本人动作、负责边界或可核实结果。",
                "按真实经历补充对象、具体动作、方法和结果；没有数字时写可核实的交付。")
        if len(text) > 180:
            add("readability", "low", {"line_ids": [item["id"]], "quote": text[:120]},
                "单段较长，初读时较难扫描。", "按真实动作和结果拆成短要点。")
        if re.search(r"\d+(?:\.\d+)?%", text) and not re.search(r"(?:期间|截至|相比|从|至|口径|基线|月|年|周|日)", text):
            add("metric_context", "low", {"line_ids": [item["id"]], "quote": text[:120]},
                "百分比缺少可见的时间或比较口径，读者可能难以判断含义。", "仅在已知时补充基线、范围、周期与本人贡献。")
    if job_id is not None:
        job = s.get_job(int(job_id))
        family = role_family(job.get("title"))
        pack = ROLE_PACKS.get(family)
        if pack:
            terms = [term for term in pack["terms"] if term.casefold() in str(job.get("description", "")).casefold()]
            for term in terms[:4]:
                if term.casefold() not in joined.casefold():
                    add("role_alignment", "low", {"line_ids": [], "quote": term, "job_id": int(job_id)},
                        f"JD 提及“{term}”，当前提取文本未定位到同一表达；这不代表候选人缺少能力。",
                        "检查现有经历是否有真实相关动作；只有事实支持时才调整表述。")
    issues.sort(key=lambda item: {"high": 0, "medium": 1, "low": 2}[item["severity"]])
    return {"source": {"type": document["source"], "id": document["id"]}, "job_id": job_id,
            "coverage": {"line_count": len(lines), "parse_warnings": document["warnings"],
                         "conclusion": "text-only checks; verify original layout and facts"},
            "issues": issues, "priority_issues": issues[:3], "score": None,
            "next": "Prepare a complete grounded draft with resume rewrite --input-id and --file, or resume compose/revise for library drafts."}


def workflow(*, job_id, resume_id=None, input_id=None):
    """Assemble the job-bound resume, rating and mock-interview handoff.

    This is an orchestration/read-only packet. Semantic hiring judgments and
    observed interview answers are still supplied and saved by the Agent;
    the packet keeps every step attached to the same job and resume version.
    """
    if resume_id is not None and input_id is not None:
        raise s.ValidationError("Select at most one --resume-id or --input-id")
    job_id = int(job_id)
    job = s.get_job(job_id)
    if job.get("kind") == "resume_context":
        raise s.ValidationError("A workflow requires a real vacancy, not a general resume context")

    base = {
        "workflow": "job_targeted_resume",
        "job": {"id": job_id, **job},
        "stages": [
            {"id": "job_analysis", "owner": "job-analysis", "purpose": "确认岗位目的、核心交付和门槛"},
            {"id": "targeted_resume", "owner": "resume-builder", "purpose": "围绕当前岗位交付完整简历"},
            {"id": "resume_review", "owner": "resume-builder", "purpose": "由 Agent 复核岗位交付、事实边界、STAR-C 表达和栏目布局；文本体检可选"},
            {"id": "simulated_rating", "owner": "job-analysis", "purpose": "针对当前简历版本进行可追溯的模拟评级"},
            {"id": "mock_interview", "owner": "interview-coach", "purpose": "用当前简历和岗位交付开展模拟面试"},
            {"id": "document_export", "owner": "document-export", "purpose": "按需导出当前版本并检查逐页排版与文本顺序"},
            {"id": "application", "owner": "application-assistant", "purpose": "绑定精确岗位和简历版本，留在本地待用户提交"},
        ],
        "upstream": ["career-discovery", "career-mapping", "job-search", "job-analysis"],
        "reasoning_owner": "host_agent",
        "local_unsubmitted": True,
    }
    if input_id is not None:
        input_id = int(input_id)
        input_record(input_id)
        base.update({
            "stage": "rewrite_pending",
            "resume_input_id": input_id,
            "optional_text_check": f"resume diagnose --input-id {input_id} --job-id {job_id}",
            "next": [
                f"analysis packet --job-id {job_id} --compact",
                f"resume tailor-packet --job-id {job_id}",
                f"resume input --id {input_id}",
                f"resume rewrite --input-id {input_id} --job-id {job_id} --file <complete-draft.json>",
                f"resume workflow --job-id {job_id} --resume-id <new-resume-id>",
            ],
            "rating": {"status": "waiting_for_targeted_resume", "command": None},
            "mock_interview": {"status": "waiting_for_targeted_resume", "command": None},
        })
        return base

    if resume_id is None:
        base.update({
            "stage": "target_required",
            "next": [
                f"analysis packet --job-id {job_id} --compact",
                f"resume tailor-packet --job-id {job_id}",
                f"resume compose --job-id {job_id} --file <complete-draft.json>",
            ],
            "note": "最终简历、评级和模拟面试都必须绑定这个岗位；通用底稿不能直接进入投递。",
        })
        return base

    resume_id = int(resume_id)
    with connect() as db:
        resume = one(db, "resumes", resume_id)
        if int(resume["job_id"]) != job_id:
            raise s.ValidationError("Resume and job must match the same targeted workflow")
        interview_rows = db.execute("SELECT data FROM interviews WHERE job_id=? ORDER BY id DESC", (job_id,)).fetchall()
    from . import assessment
    from .resume_content import composition_for_resume
    composition = composition_for_resume(resume_id) or {}
    packet = assessment.review_packet(resume_id)
    prior_reviews = packet.get("prior_reviews", [])
    latest_analysis = packet.get("latest_analysis")
    latest_review = next((item for item in prior_reviews
                          if item["job_sha256"] == packet["job_sha256"]
                          and item["resume_sha256"] == packet["resume"]["actual_sha256"]
                          and latest_analysis and item["analysis_id"] == latest_analysis["id"]), None)
    analysis_current = bool(latest_analysis and latest_analysis["data"]["job_sha256"] == packet["job_sha256"])
    interview_records = []
    for row in interview_rows:
        data = deserialize(row["data"])
        if str(data.get("resume_id")) == str(resume_id) and data.get("practice"):
            interview_records.append(data)
    role_focus = packet.get("role_focus") or {}
    if not analysis_current:
        stage = "job_analysis_pending"
        next_commands = [f"analysis packet --job-id {job_id} --compact",
                         "analysis save --file <completed-analysis.json>"]
    elif latest_review is None:
        stage = "rating_pending"
        next_commands = [f"review packet --resume-id {resume_id} --compact",
                         "review save --file <completed-review.json>"]
    elif not interview_records:
        stage = "mock_interview_pending"
        next_commands = ["interview save --file <mock-interview.json>"]
    else:
        stage = "feedback_and_application"
        next_commands = [f"feedback plan --job-id {job_id}",
                         f"application prepare --job-id {job_id} --resume-id {resume_id} --channel <channel> --apply-url <exact-url>"]
    base.update({
        "stage": stage,
        "resume_id": resume_id,
        "writing_context": composition.get("_target_snapshot"),
        "optional_text_check": f"resume diagnose --resume-id {resume_id} --job-id {job_id}",
        "rating": {
            "status": "completed" if latest_review else ("ready" if analysis_current else "waiting_for_job_analysis"),
            "latest": latest_review,
            "packet_command": f"review packet --resume-id {resume_id} --compact",
            "save_command": "review save --file <completed-review.json>",
        },
        "mock_interview": {
            "status": "completed_records_available" if interview_records else "ready",
            "resume_id": resume_id,
            "job_id": job_id,
            "core_deliverables": role_focus.get("core_deliverables", []),
            "themes": role_focus.get("interview_themes", []),
            "records": interview_records,
            "next_action": "围绕岗位核心交付和评级问题，每次问一个问题；保存用户实际回答和反馈。",
            "save_command": "interview save --file <mock-interview.json>",
        },
        "review_packet": packet,
        "next": next_commands,
        "resume_command": f"resume workflow --job-id {job_id} --resume-id {resume_id}",
    })
    return base


def rewrite_import(input_id, data, *, job_id=None, base_resume_id=None):
    """Register an Agent-authored complete draft with explicit imported-line provenance."""
    from .feedback import ensure_schema
    from .resume_content import _general_job, artifact_path, safe_text

    if not isinstance(data, dict) or not isinstance(data.get("sections"), list) or not data["sections"]:
        raise s.ValidationError("rewrite needs a nonempty sections array")
    reason = safe_text(data.get("reason"), "reason")
    record = input_record(input_id)
    known = {item["id"] for item in record["lines"]}
    sections, mapping, covered = [], [], set()
    for section in data["sections"]:
        if not isinstance(section, dict):
            raise s.ValidationError("section must be an object")
        heading = safe_text(section.get("heading"), "section.heading")
        if re.search(r"[#\n\r]", heading):
            raise s.ValidationError("section heading cannot contain Markdown markers")
        paragraphs = section.get("paragraphs", [])
        if not isinstance(paragraphs, list) or not paragraphs:
            raise s.ValidationError("Each section needs complete paragraphs")
        rendered = [f"## {heading}", ""]
        for paragraph in paragraphs:
            if not isinstance(paragraph, dict):
                raise s.ValidationError("paragraph must include text and source_line_ids")
            text = safe_text(paragraph.get("text"), "paragraph.text")
            refs = paragraph.get("source_line_ids")
            if not isinstance(refs, list) or not refs or any(type(ref) is not int or ref not in known for ref in refs):
                raise s.ValidationError("Each paragraph needs real imported source_line_ids")
            refs = list(dict.fromkeys(refs))
            style = paragraph.get("style", "text" if heading in {"教育经历", "个人优势", "专业技能", "资格证书"} else "bullet")
            if style not in {"entry", "meta", "bullet", "text"}:
                raise s.ValidationError("paragraph.style must be entry|meta|bullet|text")
            covered.update(refs)
            rendered.extend([{"entry": "### ", "meta": "*", "bullet": "- ", "text": ""}[style] + text +
                             ("*" if style == "meta" else ""), ""])
            mapping.append({"field": "imported_paragraph", "text": text, "input_id": int(input_id),
                            "source_line_ids": refs, "source_hash": record["source_hash"], "style": style})
        sections.extend(rendered)
    name = safe_text(data.get("display_name"), "display_name")
    identity_refs = data.get("identity_line_ids")
    if not isinstance(identity_refs, list) or not identity_refs or any(type(ref) is not int or ref not in known for ref in identity_refs):
        raise s.ValidationError("display_name needs real identity_line_ids")
    mapping.append({"field": "imported_identity", "text": name, "input_id": int(input_id),
                    "source_line_ids": identity_refs, "source_hash": record["source_hash"]})
    covered.update(identity_refs)
    contact = data.get("contact", "")
    if contact:
        contact = safe_text(contact, "contact")
        contact_refs = data.get("contact_line_ids")
        if not isinstance(contact_refs, list) or not contact_refs or any(type(ref) is not int or ref not in known for ref in contact_refs):
            raise s.ValidationError("contact needs real contact_line_ids")
        mapping.append({"field": "imported_contact", "text": contact, "input_id": int(input_id),
                        "source_line_ids": contact_refs, "source_hash": record["source_hash"]})
        covered.update(contact_refs)
    content = "\n".join([f"# {name}", "", *([contact, ""] if contact else []), *sections]).strip() + "\n"
    path, created = None, False
    with connect() as db:
        ensure_schema(db)
        if base_resume_id is not None:
            base = one(db, "resumes", int(base_resume_id))
            s.verify_resume(base)
            source = db.execute("SELECT detail FROM audit_events WHERE kind='resume.imported_source' AND resource_id=? "
                                "ORDER BY id DESC LIMIT 1", (base_resume_id,)).fetchone()
            if source is None or deserialize(source["detail"])["input_id"] != input_id:
                raise s.ValidationError("Base resume must use the same imported source")
            if job_id is None:
                job_id = base["job_id"]
            elif int(job_id) != base["job_id"]:
                raise s.ValidationError("Revision must keep the base resume's job")
        if job_id is None:
            job_id = _general_job(db)
        one(db, "jobs", int(job_id))
        cursor = db.execute("INSERT INTO resumes(job_id,experience_ids,output_path,sha256,created_at) VALUES (?,?,?,?,?)",
                            (job_id, "[]", "PENDING", hashlib.sha256(content.encode()).hexdigest(), now()))
        resume_id = cursor.lastrowid
        path = artifact_path(db, resume_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                created = True
                handle.write(content)
            db.execute("UPDATE resumes SET output_path=? WHERE id=?", (str(path.resolve()), resume_id))
            db.execute("INSERT INTO resume_versions VALUES (?,?,?,?,?,?,?,?)",
                       (resume_id, base_resume_id or resume_id, None, "[]", reason, serialize(mapping), "draft", now()))
            db.execute("INSERT INTO audit_events(kind,resource,resource_id,detail,created_at) VALUES (?,?,?,?,?)",
                       ("resume.imported_source", "resumes", resume_id,
                        serialize({"input_id": input_id, "source_hash": record["source_hash"],
                                   "covered_line_ids": sorted(covered)}), now()))
            audit(db, "resume.rewritten", "resumes", resume_id, reason)
        except Exception:
            if created:
                path.unlink(missing_ok=True)
            raise
    from .resume_content import cleanup
    targeted = s.get_job(job_id).get("kind") != "resume_context"
    return {"id": resume_id, "path": str(path), "source_input_id": input_id,
            "covered_line_ids": sorted(covered), "uncovered_line_ids": sorted(known - covered),
            "factual_status": "draft", "local_unsubmitted": True,
            "workflow": {"mode": "job_targeted" if targeted else "baseline_only",
                          "command": f"resume workflow --job-id {job_id} --resume-id {resume_id}" if targeted else None,
                          "next": ("先选择真实岗位，再进入评级和模拟面试" if not targeted
                                   else "评级与模拟面试必须绑定本岗位和这个简历版本")},
            "retention": cleanup(job_id=job_id, apply=True, rename=False)}


def market_observations(*, days=30, family=None):
    """Read-only JD signals; repeated snapshots and employers never inflate counts."""
    if not isinstance(days, int) or not 7 <= days <= 365:
        raise s.ValidationError("days must be between 7 and 365")
    if family is not None and family not in ROLE_PACKS:
        raise s.ValidationError("Unknown role family")
    from .sources import ensure_source_schema

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    previous = start - timedelta(days=days)
    with connect() as db:
        ensure_source_schema(db)
        rows = db.execute("SELECT * FROM job_source_snapshots WHERE retrieved_at>=? AND retrieved_at<=? ORDER BY id",
                          (previous.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"))).fetchall()
    latest = {}
    for row in rows:
        timestamp = datetime.fromisoformat(row["retrieved_at"].replace("Z", "+00:00"))
        window = "current" if timestamp >= start else "previous"
        latest[(window, row["job_id"])] = (row, timestamp)
    observations = defaultdict(lambda: {"current": {}, "previous": {}})
    emerging = defaultdict(lambda: {"current": {}, "previous": {}})
    total_jobs = defaultdict(set)
    for (window, job_id), (row, _) in latest.items():
        data = deserialize(row["data"])
        title = data.get("title", "")
        key = role_family(title)
        if not key or (family and key != family):
            continue
        company = " ".join(str(data.get("company", "")).casefold().split())
        description = str(data.get("description", ""))
        if not company or not description:
            continue
        dedupe = (company, " ".join(title.casefold().split()), hashlib.sha256(description.casefold().encode()).hexdigest())
        total_jobs[(key, window)].add(dedupe)
        for term in ROLE_PACKS[key]["terms"]:
            if term.casefold() not in description.casefold():
                continue
            slot = observations[(key, term)][window]
            slot[dedupe] = {"job_id": job_id, "company": data["company"], "title": title,
                            "url": data.get("url", ""), "retrieved_at": row["retrieved_at"],
                            "snapshot_id": row["id"]}
        for raw_line in re.split(r"[\n；;。]", description):
            match = re.search(r"(?:熟悉|掌握|具备|使用|了解)\s*([A-Za-z][A-Za-z0-9+.#/-]{1,24}|[\u4e00-\u9fff]{4,12})", raw_line)
            if not match:
                continue
            term = match.group(1).strip().casefold()
            if term in {value.casefold() for value in ROLE_PACKS[key]["terms"]}:
                continue
            emerging[(key, term)][window][dedupe] = {"job_id": job_id, "company": data["company"],
                "title": title, "url": data.get("url", ""), "retrieved_at": row["retrieved_at"],
                "snapshot_id": row["id"], "quote": raw_line.strip()[:160]}
    signals = []
    for (key, term), windows in observations.items():
        current = list(windows["current"].values())
        previous_count = len(windows["previous"])
        employers = {item["company"].casefold() for item in current}
        if not current:
            continue
        sufficient = len(current) >= 3 and len(employers) >= 3
        signals.append({"family": key, "family_label": ROLE_PACKS[key]["label"], "requirement": term,
                        "current_jobs": len(current), "current_employers": len(employers),
                        "previous_jobs": previous_count, "candidate": sufficient,
                        "new_in_window": sufficient and previous_count == 0,
                        "sources": current[:10],
                        "suggestion": "核对已有真实经历是否支持该要求，再决定是否调整简历或练习计划。" if sufficient else None})
    signals.sort(key=lambda item: (-item["current_jobs"], item["family"], item["requirement"]))
    emerging_signals = []
    for (key, term), windows in emerging.items():
        current = list(windows["current"].values())
        employers = {item["company"].casefold() for item in current}
        if len(current) < 3 or len(employers) < 3:
            continue
        emerging_signals.append({"family": key, "requirement_phrase": term, "current_jobs": len(current),
                                 "current_employers": len(employers), "previous_jobs": len(windows["previous"]),
                                 "sources": current[:10], "status": "review_candidate"})
    emerging_signals.sort(key=lambda item: (-item["current_jobs"], item["family"], item["requirement_phrase"]))
    return {"window_days": days, "generated_at": end.isoformat(timespec="seconds"),
            "sample_jobs": {key: {window: len(total_jobs[(key, window)]) for window in ("current", "previous")}
                            for key in ROLE_PACKS if not family or key == family},
            "signals": signals, "emerging_phrases": emerging_signals, "status": "observation_only", "profile_updated": False,
            "note": "Counts describe available saved JDs, not the whole market or the person's skills. A scheduled host run must include this report explicitly."}
