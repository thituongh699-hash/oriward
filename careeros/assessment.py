"""Deterministic JD analysis and simulated hiring review persistence.

This module deliberately does not infer that a candidate meets a requirement.
It stores a reviewed mapping, validates every evidence reference, and computes
recommendations and simulated grades from that mapping.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from . import services
from .db import audit, connect, deserialize, now, one, serialize


STAGES = (
    "ats",
    "hr",
    "hiring_manager",
    "technical",
    "pressure",
    "background",
    "competition",
)
VERDICTS = {"pass", "risk", "fail", "unknown"}
KINDS = {"hard_gate", "core", "preferred"}
MATCHES = {"met", "gap", "unknown"}
SEVERITIES = {"presentation", "preparation", "structural", "blocker"}
ACTION_TYPES = {"wording", "practice", "evidence", "retarget"}
RESULT_LABEL = "SIMULATED_HIRING_REVIEW_NOT_EMPLOYER_VERDICT"


def _copy_json(value):
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise services.ValidationError("Assessment data must be JSON serializable") from exc


def _require_dict(value, label):
    if not isinstance(value, dict):
        raise services.ValidationError(f"{label} must be an object")
    return value


def _require_list(value, label):
    if not isinstance(value, list):
        raise services.ValidationError(f"{label} must be an array")
    return value


def _nonempty_string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise services.ValidationError(f"{label} must be a non-empty string")
    return value.strip()


def _job_sha256(job):
    # Provider refreshes may update retrieval metadata without changing the JD.
    # Bind analyses to stable role content, including a provider content hash
    # when one exists, rather than to volatile observation timestamps.
    stable_keys = (
        "source", "source_id", "title", "company", "description",
        "location", "url", "content_hash", "availability",
    )
    stable = {key: job.get(key) for key in stable_keys if key in job}
    return hashlib.sha256(serialize(stable).encode("utf-8")).hexdigest()


def _description(job):
    value = job.get("description")
    if not isinstance(value, str) or not value.strip():
        raise services.ValidationError("Job has no usable description")
    return value


def _preliminary_kind(text):
    lowered = text.casefold()
    if re.search(r"\b(must|required|mandatory|license|certification|eligible)\b", lowered) or any(
        word in text for word in ("必须", "必备", "硬性", "资格证", "执照")
    ):
        return "hard_gate"
    if re.search(r"\b(preferred|nice[ -]to[ -]have|plus)\b", lowered) or any(
        word in text for word in ("优先", "加分", "最好")
    ):
        return "preferred"
    return "core"


def draft_analysis(job_id):
    """Return a line-based, explicitly unknown JD analysis template."""
    job_id = int(job_id)
    job = services.get_job(job_id)
    description = _description(job)
    quotes = [line.strip() for line in description.splitlines() if line.strip()]
    if not quotes:
        quotes = [description.strip()]
    requirements = []
    unknowns = []
    for index, quote in enumerate(quotes, start=1):
        requirement_id = f"req-{index:03d}"
        text = re.sub(r"^[\s\-*•·\d.)、]+", "", quote).strip() or quote
        requirements.append({
            "id": requirement_id,
            "text": text,
            "kind": _preliminary_kind(text),
            "quote": quote,
            "match": "unknown",
            "experience_ids": [],
            "rationale": "Preliminary extraction only; compare this JD line with approved evidence.",
        })
        unknowns.append({
            "requirement_id": requirement_id,
            "question": f"What approved evidence, if any, supports: {text}",
        })
    return {
        "job_id": job_id,
        "requirements": requirements,
        "unknowns": unknowns,
        "company_context": [],
        "coverage_confirmed": False,
        "recommendation": "explore",
        "confidence": "low",
        "job_sha256": _job_sha256(job),
        "template_status": "PRELIMINARY_UNKNOWN_MATCHES",
    }


def _parse_retrieved_date(value, label):
    text = _nonempty_string(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise services.ValidationError(f"{label} must be an ISO date or datetime") from exc
    if parsed > datetime.now(timezone.utc).date():
        raise services.ValidationError(f"{label} cannot be in the future")
    return parsed


def _validate_company_context(items):
    items = _require_list(items, "company_context")
    for index, item in enumerate(items):
        item = _require_dict(item, f"company_context[{index}]")
        for key in ("url", "retrieved_at", "fact", "inference"):
            if key not in item:
                raise services.ValidationError(f"company_context[{index}] missing {key}")
        url = _nonempty_string(item["url"], f"company_context[{index}].url")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise services.ValidationError("Company context source URL must be http(s)")
        _parse_retrieved_date(item["retrieved_at"], f"company_context[{index}].retrieved_at")
        _nonempty_string(item["fact"], f"company_context[{index}].fact")
        if not isinstance(item["inference"], str):
            raise services.ValidationError(f"company_context[{index}].inference must be a string")
        if "availability" in item and item["availability"] not in {"listed", "closed", "unknown"}:
            raise services.ValidationError("availability must be listed|closed|unknown")
    return items


def _verified_experience(db, experience_id):
    row = one(db, "experiences", int(experience_id))
    experience = deserialize(row["data"])
    if not experience.get("approved_for_resume"):
        raise services.ValidationError(f"Experience {experience_id} not approved for resume")
    evidence = experience.get("evidence")
    if not isinstance(evidence, list) or not any(
        isinstance(item, dict)
        and item.get("status") in {"user_confirmed", "document_verified"}
        and isinstance(item.get("claim"), str)
        and item["claim"].strip()
        for item in evidence
    ):
        raise services.ValidationError(f"Experience {experience_id} lacks verified non-empty evidence")
    return experience


def _validate_requirements(db, requirements, description):
    requirements = _require_list(requirements, "requirements")
    if not requirements:
        raise services.ValidationError("requirements must not be empty")
    seen = set()
    normalized = []
    for index, raw in enumerate(requirements):
        item = _require_dict(raw, f"requirements[{index}]")
        requirement_id = _nonempty_string(item.get("id"), f"requirements[{index}].id")
        if requirement_id in seen:
            raise services.ValidationError(f"Duplicate requirement id: {requirement_id}")
        seen.add(requirement_id)
        text = _nonempty_string(item.get("text"), f"requirements[{index}].text")
        quote = _nonempty_string(item.get("quote"), f"requirements[{index}].quote")
        if quote not in description:
            raise services.ValidationError(f"Requirement {requirement_id} quote is not an exact JD substring")
        kind = item.get("kind")
        match = item.get("match")
        if kind not in KINDS:
            raise services.ValidationError(f"Requirement {requirement_id} kind must be hard_gate|core|preferred")
        if match not in MATCHES:
            raise services.ValidationError(f"Requirement {requirement_id} match must be met|gap|unknown")
        experience_ids = _require_list(item.get("experience_ids"), f"requirements[{index}].experience_ids")
        try:
            experience_ids = list(dict.fromkeys(int(value) for value in experience_ids))
        except (TypeError, ValueError) as exc:
            raise services.ValidationError(f"Requirement {requirement_id} experience IDs must be integers") from exc
        if match == "met" and not experience_ids:
            raise services.ValidationError(f"Met requirement {requirement_id} needs experience IDs")
        if match == "met":
            for experience_id in experience_ids:
                _verified_experience(db, experience_id)
        elif experience_ids:
            raise services.ValidationError(f"Only met requirement {requirement_id} may cite experience IDs")
        rationale = _nonempty_string(item.get("rationale"), f"requirements[{index}].rationale")
        normalized.append({
            "id": requirement_id,
            "text": text,
            "kind": kind,
            "quote": quote,
            "match": match,
            "experience_ids": experience_ids,
            "rationale": rationale,
        })
    return normalized


def _has_recent_available_source(company_context):
    cutoff = datetime.now(timezone.utc).date().toordinal() - 30
    return any(
        item.get("availability") == "listed"
        and _parse_retrieved_date(item["retrieved_at"], "retrieved_at").toordinal() >= cutoff
        for item in company_context
    )


def _vacancy_status(job, company_context):
    from .sources import freshness
    job_url = services.clean_url(job.get("url", ""))
    sources = [item for item in company_context
               if job_url and services.clean_url(item["url"]) == job_url]
    closed = job.get("availability") == "closed" or any(item.get("availability") == "closed" for item in sources)
    current = bool(job_url) and not closed and (
        (job.get("availability") == "listed" and freshness(job)["status"] == "fresh")
        or _has_recent_available_source(sources))
    return closed, current


def _analysis_outcome(requirements, unknowns, company_context, job):
    closed, current = _vacancy_status(job, company_context)
    if closed or any(item["kind"] == "hard_gate" and item["match"] == "gap" for item in requirements):
        recommendation = "skip"
    elif any(item["kind"] == "core" and item["match"] == "gap" for item in requirements):
        recommendation = "upskill"
    elif any(item["kind"] in {"hard_gate", "core"} and item["match"] == "unknown" for item in requirements):
        recommendation = "explore"
    else:
        recommendation = "apply"

    if unknowns or any(item["match"] == "unknown" for item in requirements):
        confidence = "low"
    elif any(item["match"] == "gap" for item in requirements) or not current:
        confidence = "medium"
    else:
        confidence = "high"
    return recommendation, confidence


def save_analysis(data):
    """Validate and save a structured analysis, returning its row ID."""
    data = _copy_json(_require_dict(data, "analysis"))
    for key in ("job_id", "requirements", "unknowns"):
        if key not in data:
            raise services.ValidationError(f"Missing required field: {key}")
    try:
        job_id = int(data["job_id"])
    except (TypeError, ValueError) as exc:
        raise services.ValidationError("job_id must be an integer") from exc
    unknowns = _require_list(data["unknowns"], "unknowns")
    coverage_confirmed = data.get("coverage_confirmed", False)
    if not isinstance(coverage_confirmed, bool):
        raise services.ValidationError("coverage_confirmed must be boolean")
    company_context = _validate_company_context(data.get("company_context", []))
    job = services.get_job(job_id)
    with connect() as db:
        requirements = _validate_requirements(db, data["requirements"], _description(job))
        recommendation, confidence = _analysis_outcome(requirements, unknowns, company_context, job)
        saved = {
            "job_id": job_id,
            "requirements": requirements,
            "unknowns": unknowns,
            "company_context": company_context,
            "coverage_confirmed": coverage_confirmed,
            "recommendation": recommendation,
            "confidence": confidence,
            "job_sha256": _job_sha256(job),
        }
        cursor = db.execute(
            "INSERT INTO job_analyses(job_id,data,created_at) VALUES (?,?,?)",
            (job_id, serialize(saved), now()),
        )
        analysis_id = cursor.lastrowid
        audit(db, "job_analyses.created", "job_analyses", analysis_id)
        return analysis_id


def _latest_structured_analysis(db, job_id):
    rows = db.execute("SELECT * FROM job_analyses WHERE job_id=? ORDER BY id DESC", (int(job_id),)).fetchall()
    for row in rows:
        data = deserialize(row["data"])
        if isinstance(data.get("requirements"), list) and isinstance(data.get("job_sha256"), str):
            return {"id": row["id"], "created_at": row["created_at"], "data": data}
    return None


def analysis_packet(job_id):
    """Return the current JD, approved evidence, and latest structured analysis."""
    job_id = int(job_id)
    job = services.get_job(job_id)
    with connect() as db:
        experiences = []
        for row in db.execute("SELECT id,data FROM experiences ORDER BY id"):
            data = deserialize(row["data"])
            if not data.get("approved_for_resume"):
                continue
            verified = [
                item for item in data.get("evidence", [])
                if isinstance(item, dict)
                and item.get("status") in {"user_confirmed", "document_verified"}
                and isinstance(item.get("claim"), str)
                and item["claim"].strip()
            ]
            if verified:
                experiences.append({
                    "id": row["id"],
                    "event": data.get("event", ""),
                    "context": data.get("context", ""),
                    "actions": data.get("actions", []),
                    "outcomes": data.get("outcomes", []),
                    "evidence": verified,
                })
        latest = _latest_structured_analysis(db, job_id)
    return {
        "job": {"id": job_id, **job},
        "job_sha256": _job_sha256(job),
        "approved_experiences": experiences,
        "latest_analysis": latest,
    }


def _ensure_review_table(db):
    # Keep schema creation inside the caller's transaction. executescript()
    # performs an implicit commit in sqlite3 and could split a review write.
    db.execute("""CREATE TABLE IF NOT EXISTS hiring_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        resume_id INTEGER NOT NULL REFERENCES resumes(id),
        analysis_id INTEGER NOT NULL REFERENCES job_analyses(id),
        resume_sha256 TEXT NOT NULL,
        job_sha256 TEXT NOT NULL,
        data TEXT NOT NULL,
        grade TEXT,
        status TEXT NOT NULL,
        reasons TEXT NOT NULL,
        result_label TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    db.execute("""CREATE INDEX IF NOT EXISTS idx_hiring_reviews_resume
                  ON hiring_reviews(resume_id, id DESC)""")


def _review_template(resume_id, analysis_id, resume_sha256):
    return {
        "resume_id": int(resume_id),
        "analysis_id": int(analysis_id) if analysis_id is not None else None,
        "resume_sha256": resume_sha256,
        "stages": {
            stage: {"verdict": "unknown", "rationale": "Evidence review pending.", "questions": [], "requirement_ids": []}
            for stage in STAGES
        },
        "red_findings": [],
        "blue_actions": [],
        "company_mismatch": {"demonstrated": False, "evidence": ""},
        "result_label": RESULT_LABEL,
    }


def review_packet(resume_id):
    """Return the exact saved resume and all inputs needed for a review."""
    resume_id = int(resume_id)
    with connect() as db:
        resume = one(db, "resumes", resume_id)
        resume_data = dict(resume)
        job = services.get_job(resume["job_id"])
        latest = _latest_structured_analysis(db, resume["job_id"])
        _ensure_review_table(db)
        revision = None
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='resume_versions'").fetchone():
            row = db.execute("SELECT * FROM resume_versions WHERE resume_id=?", (resume_id,)).fetchone()
            if row:
                revision = dict(row)
                for key in ("feedback_ids", "claim_map"):
                    revision[key] = deserialize(revision[key])
    path = services.verify_resume(resume_data)
    content = path.read_text(encoding="utf-8")
    prior = list_reviews(resume_id)
    analysis_id = latest["id"] if latest else None
    return {
        "resume": {
            **resume_data,
            "experience_ids": deserialize(resume["experience_ids"]),
            "content": content,
            "actual_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
        "job": {"id": resume["job_id"], **job},
        "job_sha256": _job_sha256(job),
        "latest_analysis": latest,
        "revision": revision,
        "prior_reviews": prior,
        "review_template": _review_template(resume_id, analysis_id, resume["sha256"]),
    }


def _load_analysis(db, analysis_id):
    try:
        analysis_id = int(analysis_id)
    except (TypeError, ValueError) as exc:
        raise services.ValidationError("analysis_id must be an integer") from exc
    row = db.execute("SELECT * FROM job_analyses WHERE id=?", (analysis_id,)).fetchone()
    if row is None:
        raise services.ValidationError(f"job_analyses ID={analysis_id} not found")
    data = deserialize(row["data"])
    if not isinstance(data.get("requirements"), list) or not data.get("job_sha256"):
        raise services.ValidationError("Review requires a structured analysis saved by save_analysis")
    return row, data


def _validate_review_shape(data, requirement_ids):
    stages = _require_dict(data.get("stages"), "stages")
    missing = set(STAGES) - set(stages)
    extra = set(stages) - set(STAGES)
    if missing or extra:
        raise services.ValidationError(
            f"stages must contain exactly {', '.join(STAGES)}; missing={sorted(missing)} extra={sorted(extra)}"
        )
    covered = set()
    normalized_stages = {}
    for stage in STAGES:
        item = _require_dict(stages[stage], f"stages.{stage}")
        verdict = item.get("verdict")
        if verdict not in VERDICTS:
            raise services.ValidationError(f"stages.{stage}.verdict must be pass|risk|fail|unknown")
        rationale = _nonempty_string(item.get("rationale"), f"stages.{stage}.rationale")
        questions = _require_list(item.get("questions"), f"stages.{stage}.questions")
        if not all(isinstance(question, str) and question.strip() for question in questions):
            raise services.ValidationError(f"stages.{stage}.questions must contain non-empty strings")
        refs = _require_list(item.get("requirement_ids"), f"stages.{stage}.requirement_ids")
        if not all(isinstance(ref, str) and ref in requirement_ids for ref in refs):
            raise services.ValidationError(f"stages.{stage}.requirement_ids contains an unknown requirement")
        refs = list(dict.fromkeys(refs))
        covered.update(refs)
        normalized_stages[stage] = {
            "verdict": verdict,
            "rationale": rationale,
            "questions": questions,
            "requirement_ids": refs,
        }
    if covered != requirement_ids:
        raise services.ValidationError(f"Review stages do not cover requirements: {sorted(requirement_ids - covered)}")

    red_findings = _require_list(data.get("red_findings", []), "red_findings")
    finding_ids = set()
    normalized_findings = []
    for index, raw in enumerate(red_findings):
        item = _require_dict(raw, f"red_findings[{index}]")
        finding_id = _nonempty_string(item.get("id"), f"red_findings[{index}].id")
        if finding_id in finding_ids:
            raise services.ValidationError(f"Duplicate red finding id: {finding_id}")
        finding_ids.add(finding_id)
        stage = item.get("stage")
        severity = item.get("severity")
        if stage not in STAGES:
            raise services.ValidationError(f"Red finding {finding_id} stage is invalid")
        if severity not in SEVERITIES:
            raise services.ValidationError(f"Red finding {finding_id} severity is invalid")
        refs = _require_list(item.get("requirement_ids"), f"red_findings[{index}].requirement_ids")
        if not all(isinstance(ref, str) and ref in requirement_ids for ref in refs):
            raise services.ValidationError(f"Red finding {finding_id} cites an unknown requirement")
        resolved = item.get("resolved", False)
        if not isinstance(resolved, bool):
            raise services.ValidationError(f"Red finding {finding_id} resolved must be boolean")
        if resolved:
            raise services.ValidationError(
                "Do not mark a red finding resolved in the same review; after evidence changes, save a new review without it"
            )
        normalized_findings.append({
            "id": finding_id,
            "stage": stage,
            "severity": severity,
            "issue": _nonempty_string(item.get("issue"), f"red_findings[{index}].issue"),
            "evidence": _nonempty_string(item.get("evidence"), f"red_findings[{index}].evidence"),
            "requirement_ids": list(dict.fromkeys(refs)),
            "resolved": resolved,
        })

    blue_actions = _require_list(data.get("blue_actions", []), "blue_actions")
    normalized_actions = []
    for index, raw in enumerate(blue_actions):
        item = _require_dict(raw, f"blue_actions[{index}]")
        finding_id = _nonempty_string(item.get("finding_id"), f"blue_actions[{index}].finding_id")
        if finding_id not in finding_ids:
            raise services.ValidationError(f"Blue action references unknown finding: {finding_id}")
        action_type = item.get("type")
        if action_type not in ACTION_TYPES:
            raise services.ValidationError(f"Blue action {finding_id} type is invalid")
        normalized_actions.append({
            "finding_id": finding_id,
            "action": _nonempty_string(item.get("action"), f"blue_actions[{index}].action"),
            "type": action_type,
        })

    mismatch = data.get("company_mismatch", {"demonstrated": False, "evidence": ""})
    mismatch = _require_dict(mismatch, "company_mismatch")
    demonstrated = mismatch.get("demonstrated", False)
    if not isinstance(demonstrated, bool):
        raise services.ValidationError("company_mismatch.demonstrated must be boolean")
    evidence = mismatch.get("evidence", "")
    if not isinstance(evidence, str) or (demonstrated and not evidence.strip()):
        raise services.ValidationError("Demonstrated company mismatch requires evidence")
    return normalized_stages, normalized_findings, normalized_actions, {
        "demonstrated": demonstrated,
        "evidence": evidence.strip(),
    }


def _grade_review(analysis, stages, red_findings, company_mismatch, job, *, revision_pending=False):
    requirements = analysis["requirements"]
    reasons = []
    unresolved = [item for item in red_findings if not item["resolved"]]
    hard_gap = any(item["kind"] == "hard_gate" and item["match"] == "gap" for item in requirements)
    hard_unknown = any(item["kind"] == "hard_gate" and item["match"] == "unknown" for item in requirements)
    # Availability evidence must describe the target vacancy, not an unrelated
    # opening or a generic company page. Current closed state takes precedence.
    closed, current_source = _vacancy_status(job, analysis.get("company_context", []))

    d_causes = []
    if hard_gap:
        d_causes.append("hard-gate requirement gap")
    if stages["ats"]["verdict"] == "fail" or stages["hr"]["verdict"] == "fail":
        d_causes.append("ATS or HR gate failed")
    if stages["background"]["verdict"] == "fail":
        d_causes.append("background stage failed")
    if company_mismatch["demonstrated"]:
        d_causes.append("company mismatch is demonstrated")
    if closed:
        d_causes.append("the sourced vacancy is closed")
    if any(item["severity"] == "blocker" for item in unresolved):
        d_causes.append("an unresolved blocker remains")
    if d_causes:
        return "D", "SIMULATED", list(dict.fromkeys(d_causes))

    if revision_pending:
        reasons.append("Revised resume wording is pending factual confirmation")
        return None, "NEEDS_EVIDENCE", reasons
    if hard_unknown:
        reasons.append("A hard-gate requirement remains unknown")
        return None, "NEEDS_EVIDENCE", reasons
    if stages["ats"]["verdict"] in {"risk", "unknown"} or stages["hr"]["verdict"] in {"risk", "unknown"}:
        reasons.append("ATS or HR gate lacks a pass verdict")
        return None, "NEEDS_EVIDENCE", reasons

    substantive_gap = any(
        item["kind"] in {"core", "preferred"} and item["match"] == "gap" for item in requirements
    )
    competition_weakness = stages["competition"]["verdict"] in {"risk", "fail"}
    other_fail = any(
        stages[stage]["verdict"] == "fail"
        for stage in ("hiring_manager", "technical", "pressure", "competition")
    )
    structural_finding = any(item["severity"] == "structural" for item in unresolved)
    if substantive_gap or competition_weakness or other_fail or structural_finding:
        if substantive_gap:
            reasons.append("A substantive core or preferred requirement gap remains")
        if competition_weakness:
            reasons.append("Competition stage shows weakness")
        if other_fail:
            reasons.append("A non-gate review stage failed")
        if structural_finding:
            reasons.append("An unresolved structural finding remains")
        return "C", "SIMULATED", list(dict.fromkeys(reasons))

    all_met = all(item["match"] == "met" for item in requirements)
    all_pass = all(item["verdict"] == "pass" for item in stages.values())
    no_unknowns = not analysis.get("unknowns") and all(item["match"] != "unknown" for item in requirements)
    coverage_confirmed = analysis.get("coverage_confirmed") is True
    presentation_cap = any(item["severity"] in {"presentation", "preparation"} for item in unresolved)
    if all_met and all_pass and no_unknowns and current_source and coverage_confirmed and not presentation_cap:
        return "A", "SIMULATED", ["All mapped requirements and seven simulated stages pass with a current availability source"]

    if not current_source:
        reasons.append("No source confirms current availability within 30 days")
    if not no_unknowns:
        reasons.append("Non-hard-gate unknowns remain for interview preparation")
    if not coverage_confirmed:
        reasons.append("An analyst has not confirmed that the requirements cover the full JD")
    if not all_pass:
        reasons.append("One or more non-gate stages remain risk or unknown")
    if presentation_cap:
        reasons.append("An unresolved presentation or preparation finding caps the result")
    if not reasons:
        reasons.append("The evidence supports the role but does not satisfy every A-grade condition")
    provisional = not current_source or not no_unknowns or not coverage_confirmed
    return "B", "PROVISIONAL" if provisional else "SIMULATED", list(dict.fromkeys(reasons))


def save_review(data):
    """Persist one evidence-bound simulated review and return its computed result."""
    data = _copy_json(_require_dict(data, "review"))
    forbidden = {"grade", "status", "reasons"} & set(data)
    if forbidden:
        raise services.ValidationError(f"Review result fields are computed, not accepted: {sorted(forbidden)}")
    for key in ("resume_id", "analysis_id", "resume_sha256", "stages"):
        if key not in data:
            raise services.ValidationError(f"Missing required field: {key}")
    try:
        resume_id = int(data["resume_id"])
    except (TypeError, ValueError) as exc:
        raise services.ValidationError("resume_id must be an integer") from exc

    with connect() as db:
        _ensure_review_table(db)
        resume = one(db, "resumes", resume_id)
        resume_data = dict(resume)
        path = services.verify_resume(resume_data)
        actual_resume_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        supplied_resume_sha256 = _nonempty_string(data["resume_sha256"], "resume_sha256")
        if supplied_resume_sha256 != resume["sha256"] or actual_resume_sha256 != supplied_resume_sha256:
            raise services.ValidationError("Review resume hash is stale or does not match the exact saved file")

        analysis_row, analysis = _load_analysis(db, data["analysis_id"])
        if analysis_row["job_id"] != resume["job_id"] or analysis["job_id"] != resume["job_id"]:
            raise services.ValidationError("Analysis and resume belong to different jobs")
        job = services.get_job(resume["job_id"])
        current_job_sha256 = _job_sha256(job)
        if analysis.get("job_sha256") != current_job_sha256:
            raise services.ValidationError("Analysis is stale because the saved job changed")

        requirements = {item["id"]: item for item in analysis["requirements"]}
        stages, findings, actions, mismatch = _validate_review_shape(data, set(requirements))
        selected_ids = set(int(value) for value in deserialize(resume["experience_ids"]))
        for requirement_id, requirement in requirements.items():
            if requirement["match"] == "met" and not set(requirement["experience_ids"]).issubset(selected_ids):
                raise services.ValidationError(
                    f"Met requirement {requirement_id} cites evidence not selected into this resume"
                )

        revision_pending = False
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='resume_versions'").fetchone():
            version = db.execute(
                "SELECT factual_status FROM resume_versions WHERE resume_id=?", (resume_id,)
            ).fetchone()
            revision_pending = bool(version and version["factual_status"] != "approved")
        grade, status, reasons = _grade_review(
            analysis, stages, findings, mismatch, job, revision_pending=revision_pending
        )
        saved = {
            "resume_id": resume_id,
            "analysis_id": analysis_row["id"],
            "resume_sha256": actual_resume_sha256,
            "job_sha256": current_job_sha256,
            "stages": stages,
            "red_findings": findings,
            "blue_actions": actions,
            "company_mismatch": mismatch,
            "grade": grade,
            "status": status,
            "reasons": reasons,
            "result_label": RESULT_LABEL,
        }
        cursor = db.execute(
            """INSERT INTO hiring_reviews(
                   resume_id,analysis_id,resume_sha256,job_sha256,data,grade,status,reasons,result_label,created_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                resume_id,
                analysis_row["id"],
                actual_resume_sha256,
                current_job_sha256,
                serialize(saved),
                grade,
                status,
                serialize(reasons),
                RESULT_LABEL,
                now(),
            ),
        )
        review_id = cursor.lastrowid
        audit(db, "hiring_reviews.created", "hiring_reviews", review_id, f"{status}:{grade or 'none'}")
    return {"id": review_id, "grade": grade, "status": status, "reasons": reasons}


def list_reviews(resume_id=None):
    """List simulated reviews newest first, optionally for one resume."""
    with connect() as db:
        _ensure_review_table(db)
        if resume_id is None:
            rows = db.execute("SELECT * FROM hiring_reviews ORDER BY id DESC").fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM hiring_reviews WHERE resume_id=? ORDER BY id DESC", (int(resume_id),)
            ).fetchall()
        return [
            {
                "id": row["id"],
                "resume_id": row["resume_id"],
                "analysis_id": row["analysis_id"],
                "resume_sha256": row["resume_sha256"],
                "job_sha256": row["job_sha256"],
                "grade": row["grade"],
                "status": row["status"],
                "reasons": deserialize(row["reasons"]),
                "result_label": row["result_label"],
                "created_at": row["created_at"],
                "review": deserialize(row["data"]),
            }
            for row in rows
        ]
