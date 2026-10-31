"""Career Twin Core facade: health, and the one-way bridge from v0.1 blobs.

``sync-legacy`` reads the old documents (``profile``, ``experiences``,
``career_directions``, ``jobs``) and projects them into Core rows *without*
deleting or rewriting anything. Running it twice is safe: identical claims are
reported as skipped instead of duplicated.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from .. import migrations
from ..db import connect, deserialize, now
from . import assertions
from .profile import IDENTITY_FIELDS

_LEGACY_LISTS = (
    ("values", "value", "user", "value"),
    ("preferences", "preference", "user", "preference"),
    ("hard_constraints", "constraint", "work_conditions", "hard_constraint"),
    ("constraints", "constraint", "work_conditions", "hard_constraint"),
    ("skills", "skill_hypothesis", "user", "has_skill"),
)


def _text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "name", "claim", "value"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
    return json.dumps(value, ensure_ascii=False)[:120]


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", text.strip().lower()).strip("-")
    if cleaned:
        return cleaned[:40]
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _already_mapped(source_ref: str, key: str) -> bool:
    """A historical source mapping remains authoritative after revision/retraction."""
    with connect() as conn:
        return conn.execute(
            "SELECT 1 FROM user_assertions WHERE dedupe_key=? LIMIT 1",
            (key,),
        ).fetchone() is not None


def sync_legacy() -> dict:
    with connect() as conn:
        profile_row = conn.execute("SELECT data FROM profile WHERE id=1").fetchone()
        profile = deserialize(profile_row["data"]) if profile_row else {}
        directions = [(row["id"], deserialize(row["data"]))
                      for row in conn.execute("SELECT id,data FROM career_directions ORDER BY id")]
        from ..experience_library import list_current
        experiences = [(row["id"], row["data"]) for row in list_current(conn=conn)
                       if not row["data"]["needs_review"]]
        jobs = [row["id"] for row in conn.execute("SELECT id FROM jobs WHERE source_key NOT LIKE 'oriward:resume-context:%' ORDER BY id")]
        known_pipeline = {row["job_id"] for row in conn.execute("SELECT job_id FROM job_pipeline")}
        applied_jobs = {row["job_id"] for row in conn.execute("SELECT DISTINCT job_id FROM applications")}
        live_claims = conn.execute(
            "SELECT COUNT(*) FROM user_assertions WHERE valid_to=''").fetchone()[0]

    created, skipped, failed = [], 0, []
    for key, assertion_type, subject, predicate in _LEGACY_LISTS:
        for item in profile.get(key) or []:
            text = _text(item)
            if not text:
                continue
            value = item if isinstance(item, dict) else {"text": text}
            claim_key = assertions.dedupe_key(subject, predicate, value, assertion_type)
            if _already_mapped("profile:1", claim_key):
                skipped += 1
                continue
            try:
                result = assertions.propose(
                    subject=subject, predicate=predicate,
                    value=value,
                    assertion_type=assertion_type, source_type="legacy_profile",
                    confidence="medium",
                    source_ref="profile:1",
                    explanation="从 v0.1 profile JSON 迁移，尚未逐条确认",
                    unique=False,
                )
            except ValueError as error:
                failed.append({"source": f"profile.{key}", "error": str(error)})
                continue
            if result["created"]:
                created.append(result["id"])
            else:
                skipped += 1

    for field in IDENTITY_FIELDS:
        if field not in profile or profile[field] in (None, "", [], {}):
            continue
        raw = profile[field]
        with connect() as conn:
            mapped = conn.execute("SELECT 1 FROM user_assertions WHERE subject='user' AND predicate=? LIMIT 1",
                                  (field,)).fetchone()
        if mapped:
            skipped += 1
            continue
        value = raw if isinstance(raw, (dict, list)) else {"text": str(raw).strip()}
        claim_key = assertions.dedupe_key("user", field, value, "fact")
        if _already_mapped("profile:1", claim_key):
            skipped += 1
            continue
        try:
            result = assertions.propose(
                subject="user", predicate=field, value=value, assertion_type="fact",
                source_type="legacy_profile", confidence="medium", source_ref="profile:1",
                explanation="从 v0.1 profile JSON 迁移，尚未逐条确认",
            )
        except ValueError as error:
            failed.append({"source": f"profile.{field}", "error": str(error)})
            continue
        if result["created"]:
            created.append(result["id"])
        else:
            skipped += 1

    for direction_id, data in directions:
        title = str(data.get("title", "")).strip()
        if not title:
            continue
        source_ref = f"career_directions:{direction_id}"
        candidate = {"direction": title, "rationale": data.get("rationale", ""),
                     "validation_status": data.get("validation_status", ""),
                     "legacy_direction_id": direction_id}
        claim_key = assertions.dedupe_key(f"career:{_slug(title)}", "direction_hypothesis",
                                          candidate, "career_hypothesis")
        if _already_mapped(source_ref, claim_key):
            skipped += 1
            continue
        experience_ids = data.get("supporting_experience_ids") or []
        links = [{"ref_type": "experience", "ref_id": int(exp_id), "relation": "supports"}
                 for exp_id in experience_ids]
        for gap in data.get("gaps") or []:
            links.append({"ref_type": "document", "ref_id": f"career_directions:{direction_id}:gap",
                          "relation": "contradicts", "note": str(gap)[:120]})
        try:
            result = assertions.propose(
                subject=f"career:{_slug(title)}", predicate="direction_hypothesis",
                value=candidate,
                assertion_type="career_hypothesis", source_type="model_inference",
                confidence="medium", source_ref=source_ref,
                explanation="v0.1 职业方向，作为待验证假设导入",
                links=links,
            )
        except ValueError as error:
            failed.append({"source": f"career_directions:{direction_id}", "error": str(error)})
            continue
        if result["created"]:
            created.append(result["id"])
        else:
            skipped += 1

    for experience_id, data in experiences:
        for skill in data.get("inferred_skills") or []:
            name = _text(skill)
            if not name:
                continue
            reason = skill.get("reason", "") if isinstance(skill, dict) else ""
            confidence = skill.get("confidence", "medium") if isinstance(skill, dict) else "medium"
            value = {"skill": name, "reason": reason}
            if _already_mapped(f"experiences:{experience_id}", assertions.dedupe_key(
                    f"skill:{_slug(name)}", "has_skill", value, "skill_hypothesis")):
                skipped += 1
                continue
            try:
                result = assertions.propose(
                    subject=f"skill:{_slug(name)}", predicate="has_skill",
                    value=value,
                    assertion_type="skill_hypothesis", source_type="experience",
                    epistemic_status="inferred", confidence=confidence,
                    source_ref=f"experiences:{experience_id}",
                    explanation="由经历中的模型推断技能迁移而来，保留为探索性能力线索",
                    links=[{"ref_type": "experience", "ref_id": experience_id, "relation": "derived_from"}],
                )
            except ValueError as error:
                failed.append({"source": f"experiences:{experience_id}", "error": str(error)})
                continue
            if result["created"]:
                created.append(result["id"])
            else:
                skipped += 1

    pipeline_added = 0
    with connect() as conn:
        for job_id in jobs:
            if job_id in known_pipeline:
                continue
            status = "shortlisted" if job_id in applied_jobs else "discovered"
            conn.execute(
                "INSERT INTO job_pipeline(job_id,discovery_status,decision_reason,priority,last_checked_at,"
                "next_review_at,created_at,updated_at) VALUES (?,?,'',NULL,'','',?,?)",
                (job_id, status, now(), now()),
            )
            pipeline_added += 1

    return {"assertions_created": len(created), "assertion_ids": created[:50],
            "skipped_existing": skipped, "failed": failed,
            "pipeline_rows_added": pipeline_added,
            "claims_before_sync": live_claims,
            "note": "旧表未被修改；迁移只新增 Core 记录，可重复运行"}


def _parse_when(value: str):
    try:
        parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def status() -> dict:
    with connect() as conn:
        version = migrations.current_version(conn)
        applied = [dict(row) for row in conn.execute(
            "SELECT version,name,applied_at FROM schema_migrations ORDER BY version")]
        counts = {}
        for table in ("user_assertions", "assertion_links", "user_feedback", "career_goals",
                      "job_pipeline", "next_actions", "reflection_runs", "applications",
                      "experiences", "jobs", "career_directions", "decision_records", "decision_events",
                      "goal_revisions"):
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        reference = _parse_when(now())
        overdue = 0
        for row in conn.execute(
                "SELECT due_at FROM next_actions WHERE status IN ('todo','doing') AND due_at!=''"):
            due = _parse_when(row["due_at"])
            if due is not None and reference is not None and due < reference:
                overdue += 1
        health = {
            "jobs_without_pipeline": conn.execute(
                "SELECT COUNT(*) FROM jobs j WHERE j.source_key NOT LIKE 'oriward:resume-context:%' AND NOT EXISTS "
                "(SELECT 1 FROM job_pipeline p WHERE p.job_id=j.id)").fetchone()[0],
            "applications_without_events": conn.execute(
                "SELECT COUNT(*) FROM applications a WHERE NOT EXISTS "
                "(SELECT 1 FROM application_events e WHERE e.application_id=a.id)").fetchone()[0],
            "inferred_never_confirmed": conn.execute(
                "SELECT COUNT(*) FROM user_assertions WHERE valid_to='' "
                "AND epistemic_status='inferred'").fetchone()[0],
            "disputed_claims": conn.execute(
                "SELECT COUNT(*) FROM user_assertions WHERE valid_to='' "
                "AND epistemic_status='disputed'").fetchone()[0],
            "overdue_actions": overdue,
            "goals_without_actions": conn.execute(
                "SELECT COUNT(*) FROM career_goals g WHERE g.status IN ('active','exploring') "
                "AND NOT EXISTS (SELECT 1 FROM next_actions a WHERE a.source_type='goal' "
                "AND a.source_id=g.id AND a.status IN ('todo','doing','blocked'))").fetchone()[0],
        }
        from . import relations
        covered_goals = set()
        for action in conn.execute("SELECT source_type,source_id FROM next_actions WHERE status IN ('todo','doing','blocked')"):
            try:
                covered_goals.update(relations.source_context(conn, action["source_type"], action["source_id"])["goal_ids"])
            except ValueError:
                continue
        health["goals_without_actions"] = sum(
            row[0] not in covered_goals for row in conn.execute(
                "SELECT id FROM career_goals WHERE status IN ('active','exploring')"))
    next_steps = []
    if health["jobs_without_pipeline"]:
        next_steps.append("python -m oriward twin sync-legacy")
    if health["inferred_never_confirmed"]:
        next_steps.append("python -m oriward belief list --status inferred")
    if health["overdue_actions"]:
        next_steps.append("python -m oriward action list --sort due")
    if not counts["career_goals"]:
        next_steps.append("python -m oriward goal add --file <goal.json>")
    return {"schema_version": version, "migrations": applied, "counts": counts,
            "health": health, "suggested_next": next_steps}


def export_bundle() -> dict:
    """Portable JSON snapshot for backup or review; contains personal data."""
    with connect() as conn:
        bundle = {"exported_at": now(), "schema_version": migrations.current_version(conn)}
        for table in ("profile", "experiences", "career_directions", "jobs", "job_analyses",
                      "resumes", "applications", "application_events", "learning_plans",
                      "interviews", "user_assertions", "assertion_links", "user_feedback",
                      "career_goals", "job_pipeline", "next_actions", "reflection_runs",
                      "decision_records", "decision_events", "goal_revisions"):
            bundle[table] = [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
    return bundle
