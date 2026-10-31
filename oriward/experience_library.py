"""Versioned current experience projection and bounded, selective local reads.

No model or semantic verifier lives here. Labels are exploratory; an explicit
source mapping records an Agent's judgement, never independent verification.
"""
from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
import json

from .db import audit, connect, deserialize, now, one, serialize
from .services import ValidationError, validate_dict

SECTIONS = {"event", "summary", "context", "time_period", "period", "start_date", "end_date", "dates",
            "actions", "outcomes", "evidence", "inferred_skills", "tags", "open_questions",
            "contributions", "decisions", "tools", "metrics", "attachments"}
STATES = {"current", "excluded", "superseded", "retracted"}
FACT_SOURCES = {"user_stated", "user_confirmed", "document_verified"}


def _id(value):
    if type(value) is not int or value < 1:
        raise ValidationError("Experience/assertion IDs must be positive integers")
    return value


def _validate(data):
    validate_dict(data, ["event"])
    if not isinstance(data["event"], str):
        raise ValidationError("event must be text")
    for field in ("actions", "outcomes", "evidence"):
        if field not in data or not isinstance(data[field], list):
            raise ValidationError(f"Experience requires {field} array (empty allowed)")
    for field in ("actions", "outcomes"):
        if any(not isinstance(item, str) for item in data[field]):
            raise ValidationError(f"{field} must contain text")
    if not isinstance(data.get("approved_for_resume", False), bool):
        raise ValidationError("approved_for_resume must be boolean")
    if data.get("status", "current") not in STATES:
        raise ValidationError("status must be current|excluded|superseded|retracted")
    for item in data["evidence"]:
        validate_dict(item, ["claim", "source", "status"])
        if item["status"] not in {"user_stated", "user_confirmed", "document_verified", "unverified"}:
            raise ValidationError("Evidence status invalid")
    if "assertion_ids" in data:
        if not isinstance(data["assertion_ids"], list):
            raise ValidationError("assertion_ids must be an array")
        for aid in data["assertion_ids"]:
            _id(aid)
    if "inferred_skills" in data and not isinstance(data["inferred_skills"], list):
        raise ValidationError("inferred_skills must be an array")
    if "tags" in data and not isinstance(data["tags"], list):
        raise ValidationError("tags must be an array")
    if "summary" in data and not isinstance(data["summary"], str):
        raise ValidationError("summary must be text")
    return data


def _check_assertions(db, data):
    for aid in data.get("assertion_ids", []):
        one(db, "user_assertions", aid)


def create(data):
    """Store ordinary self-reports without approval or attachments."""
    d = deepcopy(data)
    # This API is ordinary experience intake. Imports must retain their source.
    for field in ("actions", "outcomes", "evidence"):
        d.setdefault(field, [])
    if "provenance_status" not in d:
        source = d.get("source_type", "user_message")
        d["provenance_status"] = {"user_message": "user_stated", "document": "document_verified"}.get(source, "unverified")
    d = _validate(d)
    if any(key in d for key in ("version", "superseded_by_id", "needs_review")):
        raise ValidationError("Version/review fields are managed by the library")
    if d.get("status", "current") != "current":
        raise ValidationError("New experiences start current; use exclude/supersede")
    d.update(version=1, status="current")
    d.setdefault("approved_for_resume", False)
    with connect() as db:
        _check_assertions(db, d)
        stamp = now()
        eid = db.execute("INSERT INTO experiences(data,created_at) VALUES (?,?)",
                         (serialize(d), stamp)).lastrowid
        _snapshot(db, eid, d, stamp, "created")
        audit(db, "experiences.created", "experiences", eid)
        return eid


def _snapshot(db, eid, data, stamp, reason):
    db.execute("INSERT OR IGNORE INTO experience_versions(experience_id,version,data,created_at,reason) "
               "VALUES (?,?,?,?,?)", (eid, data.get("version", 1), serialize(data), stamp, reason))


def _projection(db, row):
    d = deserialize(row["data"])
    d.setdefault("version", 1)
    d.setdefault("status", "current")
    # Explicit dependency IDs replace legacy reverse links after reconciliation.
    if "assertion_ids" in d:
        ids = d["assertion_ids"]
    else:
        ids = [r["id"] for r in db.execute(
            "SELECT DISTINCT a.id FROM user_assertions a JOIN assertion_links l ON l.assertion_id=a.id "
            "WHERE l.ref_type='experience' AND l.ref_id=? AND l.relation IN ('supports','derived_from') "
            "AND a.assertion_type='fact' AND a.epistemic_status!='inferred'", (str(row["id"]),))]
    stale = []
    for aid in ids:
        assertion = db.execute("SELECT * FROM user_assertions WHERE id=?", (aid,)).fetchone()
        if assertion is None or assertion["valid_to"] or assertion["epistemic_status"] in {"retracted", "disputed", "inferred"}:
            stale.append(aid)
    d["needs_review"] = bool(stale or d.get("needs_review"))
    d["stale_assertion_ids"] = stale
    return {**dict(row), "data": d}


def list_current(*, conn=None, include_inactive=False):
    """Current rows as decoded objects; stale facts remain explicitly review-only."""
    with (nullcontext(conn) if conn is not None else connect()) as db:
        rows = [_projection(db, r) for r in db.execute("SELECT * FROM experiences ORDER BY id DESC")]
        return [r for r in rows if include_inactive or r["data"]["status"] == "current"]


def revise(experience_id, changes, *, reason, expected_version=None):
    _id(experience_id)
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("A correction reason is required")
    if not isinstance(changes, dict) or not changes:
        raise ValidationError("changes must be a nonempty object")
    if set(changes) & {"version", "status", "superseded_by_id", "needs_review", "stale_assertion_ids"}:
        raise ValidationError("Use lifecycle operations for managed fields")
    with connect() as db:
        row = one(db, "experiences", experience_id)
        old = deserialize(row["data"])
        version = old.get("version", 1)
        if expected_version is not None and expected_version != version:
            raise ValidationError("Experience version changed; reload before correcting")
        if old.get("status", "current") != "current":
            raise ValidationError("Inactive experience cannot be revised")
        d = _validate({**old, **deepcopy(changes), "version": version + 1})
        # A removed action's exact supporting claim must not survive a correction
        # as an alternative current fact. The previous snapshot keeps its source.
        if "evidence" not in changes:
            removed = set()
            for field in ("actions", "outcomes"):
                if field in changes:
                    removed.update(set(old.get(field, [])) - set(d.get(field, [])))
            if removed:
                d["evidence"] = [item for item in d.get("evidence", []) if item.get("claim") not in removed]
        # Corrections invalidate cached summaries, without inventing approval.
        if set(changes) & {"event", "context", "actions", "outcomes", "evidence", "assertion_ids"}:
            # An authored summary is a cache of those facts, not another truth.
            # Regenerate the fallback unless the correction supplies its new text.
            if "summary" not in changes:
                d.pop("summary", None)
        d.pop("needs_review", None)
        d.pop("stale_assertion_ids", None)
        _check_assertions(db, d)
        stamp = now()
        _snapshot(db, experience_id, old, row["created_at"], "legacy/current before correction")
        _snapshot(db, experience_id, d, stamp, reason)
        db.execute("UPDATE experiences SET data=? WHERE id=?", (serialize(d), experience_id))
        audit(db, "experience.revised", "experiences", experience_id, reason)
        return {"id": experience_id, "version": d["version"], "status": d.get("status", "current")}


def _lifecycle(experience_id, status, reason, replacement_id=None):
    _id(experience_id)
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("Lifecycle reason is required")
    with connect() as db:
        row = one(db, "experiences", experience_id)
        old = deserialize(row["data"])
        if replacement_id is not None:
            _id(replacement_id)
            if replacement_id == experience_id:
                raise ValidationError("An experience cannot supersede itself")
            replacement = _projection(db, one(db, "experiences", replacement_id))["data"]
            if replacement["status"] != "current" or replacement["needs_review"]:
                raise ValidationError("Replacement must be current and reconciled")
        if old.get("status", "current") == status and old.get("superseded_by_id") == replacement_id:
            return {"id": experience_id, "version": old.get("version", 1), "status": status, "changed": False}
        if old.get("status", "current") != "current":
            raise ValidationError("Inactive experience lifecycle cannot be overwritten")
        d = {**old, "version": old.get("version", 1) + 1, "status": status,
             "approved_for_resume": False, "lifecycle_reason": reason}
        if replacement_id is not None:
            d["superseded_by_id"] = replacement_id
        _snapshot(db, experience_id, old, row["created_at"], "before lifecycle change")
        _snapshot(db, experience_id, d, now(), reason)
        db.execute("UPDATE experiences SET data=? WHERE id=?", (serialize(d), experience_id))
        audit(db, "experience." + status, "experiences", experience_id, reason)
        return {"id": experience_id, "version": d["version"], "status": status, "changed": True}


def exclude(experience_id, *, reason):
    return _lifecycle(experience_id, "excluded", reason)


def supersede(experience_id, replacement_id, *, reason):
    return _lifecycle(experience_id, "superseded", reason, replacement_id)


def history(experience_id):
    with connect() as db:
        current = one(db, "experiences", _id(experience_id))
        rows = [dict(r) for r in db.execute("SELECT * FROM experience_versions WHERE experience_id=? ORDER BY version",
                                          (experience_id,))]
        if not rows:
            rows = [{"experience_id": experience_id, "version": 1, "data": current["data"],
                     "created_at": current["created_at"], "reason": "legacy current"}]
        return [{**r, "data": deserialize(r["data"])} for r in rows]


def get(experience_id, *, version=None, sections=None, include_inactive=False):
    if sections is not None and (not isinstance(sections, (list, tuple)) or set(sections) - SECTIONS):
        raise ValidationError("Unknown experience detail sections")
    with connect() as db:
        current = _projection(db, one(db, "experiences", _id(experience_id)))
        d = current["data"]
        if version is not None:
            match = next((r for r in history(experience_id) if r["version"] == version), None)
            if match is None:
                raise ValidationError("Experience version not found")
            d = match["data"]
        elif not include_inactive and d["status"] != "current":
            raise ValidationError("Experience is inactive; request history explicitly")
        metadata = {k: d.get(k) for k in ("version", "status", "needs_review", "stale_assertion_ids")}
        return {"id": experience_id, **metadata, "historical": version is not None,
                "sections_read": sorted(sections if sections is not None else SECTIONS & d.keys()),
                "data": {k: deepcopy(d[k]) for k in sections if k in d} if sections is not None else d}


def _selected(db, ids, query, include_inactive=False):
    if ids is not None:
        if not isinstance(ids, list):
            raise ValidationError("ids must be an array")
        for eid in ids:
            one(db, "experiences", _id(eid))
    words = str(query).casefold().split()
    return [r for r in list_current(conn=db, include_inactive=include_inactive)
            if (ids is None or r["id"] in ids)
            and all(w in serialize(r["data"]).casefold() for w in words)]


def _tags(data):
    """Normalize exploratory labels without upgrading them to proven mastery."""
    result = []
    for value in data.get("tags", data.get("inferred_skills", [])):
        if isinstance(value, str):
            value = {"name": value, "source": "model_inference"}
        if not isinstance(value, dict):
            continue
        name = str(value.get("name", value.get("tag", ""))).strip()[:60]
        if name:
            result.append({"name": name, "source": value.get("source", "model_inference")})
    return result


def index(*, query="", ids=None, budget=2200, offset=0, conn=None):
    """Budget includes metadata and CLI JSON indentation, not its newline."""
    if type(budget) is not int or budget < 500 or type(offset) is not int or offset < 0:
        raise ValidationError("Index requires budget >=500 and offset >=0")
    with (nullcontext(conn) if conn is not None else connect()) as db:
        rows = _selected(db, ids, query)
        result = {"items": [], "total_count": len(rows), "offset": offset, "omitted_count": len(rows),
                  "next_offset": offset, "complete": False, "budget": {"limit": budget, "actual": 0},
                  "detail_hint": "Select IDs and sections; labels are exploratory, not qualifications."}
        for row in rows[offset:]:
            d = row["data"]
            item = {"id": row["id"], "version": d["version"], "event": d["event"][:65],
                    "needs_review": d["needs_review"], "approved": bool(d.get("approved_for_resume")),
                    "usable": bool(usable_facts(d)) and not d["needs_review"]}
            period = next((str(d[key]).strip() for key in ("time_period", "period", "dates", "start_date")
                           if d.get(key)), "")
            if period:
                if d.get("end_date") and str(d["end_date"]) not in period:
                    period += " - " + str(d["end_date"])
                item["period"] = period[:35]
            if not d["needs_review"]:
                facts = usable_facts(d)
                uncertain = [e for e in d.get("evidence", []) if e.get("status") not in FACT_SOURCES]
                summary = d.get("summary") if facts and not uncertain else None
                if not summary:
                    summary = "; ".join([text for text in d.get("actions", []) + d.get("outcomes", []) if text in facts][:2])
                item["summary"] = str(summary)[:130]
                item["tags"] = _tags(d)[:3]
            result["items"].append(item)
            _index_metadata(result, len(rows), offset)
            if _index_size(result) > budget:
                result["items"].pop()
                if not result["items"]:
                    # A tight valid budget still needs a usable directory entry
                    # rather than a zero-progress pagination loop.
                    compact = {key: item[key] for key in ("id", "version", "event", "needs_review")}
                    compact["event"] = compact["event"][:30]
                    compact["compact_card"] = True
                    result["items"].append(compact)
                break
        _index_metadata(result, len(rows), offset)
        return result


def skills(*, query="", budget=2200, offset=0):
    """Derived skill cards link labels to current experience modules only."""
    if type(budget) is not int or budget < 500 or type(offset) is not int or offset < 0:
        raise ValidationError("Skill index requires budget >=500 and offset >=0")
    groups = {}
    with connect() as db:
        for row in list_current(conn=db):
            data = row["data"]
            if data["needs_review"]:
                continue
            for tag in _tags(data):
                key = tag["name"].casefold()
                if query and not all(word in key for word in query.casefold().split()):
                    continue
                card = groups.setdefault(key, {"name": tag["name"], "experience_refs": []})
                ref = {"id": row["id"], "version": data["version"], "label_source": tag["source"]}
                if ref not in card["experience_refs"]:
                    card["experience_refs"].append(ref)
    cards = [groups[key] for key in sorted(groups)]
    result = {"items": [], "total_count": len(cards), "offset": offset, "complete": False,
              "omitted_count": len(cards), "next_offset": offset, "budget": {"limit": budget, "actual": 0},
              "detail_hint": "Exploratory labels. Query experience index by tag, then select detail IDs/sections."}
    for card in cards[offset:]:
        refs = card["experience_refs"]
        item = {"name": card["name"], "experience_refs": refs[:3], "omitted_refs": max(0, len(refs) - 3)}
        result["items"].append(item)
        _index_metadata(result, len(cards), offset)
        if _index_size(result) > budget:
            result["items"].pop()
            if not result["items"]:
                item.update(experience_refs=refs[:1], omitted_refs=max(0, len(refs) - 1))
                result["items"].append(item)
            break
    _index_metadata(result, len(cards), offset)
    if _index_size(result) > budget:
        raise ValidationError("Increase skill index budget to read this card")
    return result


def _index_metadata(result, total, offset):
    count = len(result["items"])
    result.update(omitted_count=max(0, total - count), next_offset=offset + count,
                  complete=offset == 0 and count == total)
    # actual participates in its own serialized size.
    for _ in range(4):
        result["budget"]["actual"] = _index_size(result)


def _index_size(result):
    return len(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def detail(*, ids=None, query="", sections=None, include_inactive=False):
    if ids is None and not str(query).strip():
        raise ValidationError("Select detail IDs or a query; no implicit full-library load")
    with connect() as db:
        rows = _selected(db, ids, query, include_inactive)
    return {"items": [get(r["id"], sections=sections, include_inactive=include_inactive) for r in rows],
            "selected_count": len(rows), "sections_requested": sections,
            "selection": {"ids": ids, "query": query}}


def _body_provenance(data):
    if "provenance_status" in data:
        return data["provenance_status"]
    if data.get("source_type"):
        return {"user_message": "user_stated", "interview": "user_stated",
                "document": "document_verified"}.get(data["source_type"], "unverified")
    return None  # Legacy source absent: known self-report evidence may supply it.


def usable_facts(data):
    """Return usable factual texts; provenance is retained, never upgraded.

    A mixed record does not lose its usable statements because another claim
    is uncertain. Explicitly unverified claims are omitted from factual text.
    Legacy records need a known source; approval booleans carry no provenance.
    """
    evidence = data.get("evidence", [])
    trusted = [e.get("claim", "") for e in evidence
               if e.get("status") in FACT_SOURCES and str(e.get("claim", "")).strip()]
    uncertain = {e.get("claim") for e in evidence if e.get("status") not in FACT_SOURCES}
    source = _body_provenance(data)
    body_usable = source in FACT_SOURCES or (source is None and bool(trusted))
    facts = list(trusted)
    if body_usable:
        facts = [text for text in data.get("actions", []) + data.get("outcomes", [])
                 if text not in uncertain] + facts
        facts += [data.get("event", ""), data.get("context", "")]
    return list(dict.fromkeys(text for text in facts if isinstance(text, str) and text.strip()))


def validate_for_resume(db, experience_id):
    _id(experience_id)
    d = _projection(db, one(db, "experiences", experience_id))["data"]
    if d["status"] != "current":
        raise ValidationError(f"Experience {experience_id} is inactive ({d['status']})")
    if d["needs_review"]:
        raise ValidationError(f"Experience {experience_id} needs_review: stale linked assertions or correction")
    facts = usable_facts(d)
    if not facts and d.get("provenance_status") not in FACT_SOURCES:
        raise ValidationError(f"Experience {experience_id} has no user-stated factual material")
    result = deepcopy(d)
    source = _body_provenance(d)
    if source is not None and source not in FACT_SOURCES:
        # A supported claim does not substantiate the surrounding model/import
        # metadata (employer, title, dates, tools or inferred responsibilities).
        operational = {"version", "status", "provenance_status", "source_type", "assertion_ids",
                       "needs_review", "stale_assertion_ids", "approved_for_resume", "evidence"}
        result = {key: deepcopy(value) for key, value in d.items() if key in operational}
        result["event"] = d["event"] if d.get("event") in facts else "相关经历"
        if isinstance(d.get("context"), str) and d["context"] in facts:
            result["context"] = d["context"]
        for field in ("time_period", "period", "dates", "date_range", "start_date", "end_date"):
            if isinstance(d.get(field), str) and d[field] in facts:
                result[field] = d[field]
    for field in ("actions", "outcomes"):
        result[field] = [text for text in d.get(field, []) if text in facts]
    result["evidence"] = [e for e in d.get("evidence", []) if e.get("status") in FACT_SOURCES]
    if source is not None and source not in FACT_SOURCES:
        for evidence in result["evidence"]:
            claim = evidence["claim"]
            if claim not in result["actions"] + result["outcomes"]:
                result["actions"].append(claim)
    # A summary may cache the uncertain statement that was just omitted.
    if result["actions"] != d.get("actions", []) or result["outcomes"] != d.get("outcomes", []):
        result.pop("summary", None)
    return result


def record_resume_sources(db, resume_id, experience_ids):
    versions = {str(eid): _projection(db, one(db, "experiences", eid))["data"]["version"] for eid in experience_ids}
    db.execute("INSERT INTO audit_events(kind,resource,resource_id,detail,created_at) VALUES (?,?,?,?,?)",
               ("resume.sources", "resumes", resume_id, serialize(versions), now()))


def resume_validity(db, resume_row):
    snapshot = db.execute("SELECT detail FROM audit_events WHERE kind='resume.sources' AND resource_id=? "
                          "ORDER BY id DESC LIMIT 1", (resume_row["id"],)).fetchone()
    expected = deserialize(snapshot["detail"]) if snapshot else {}
    issues = []
    for eid in deserialize(resume_row["experience_ids"]):
        try:
            d = validate_for_resume(db, eid)
            if d["version"] != expected.get(str(eid), 1):
                issues.append({"experience_id": eid, "reason": "source version changed"})
        except ValueError as exc:
            issues.append({"experience_id": eid, "reason": str(exc)})
    return {"needs_review": bool(issues), "issues": issues}


def ensure_resume_current(db, resume_row):
    status = resume_validity(db, resume_row)
    if status["needs_review"]:
        raise ValidationError("Resume needs_review: " + serialize(status["issues"]))
    return status
