"""Assertion ledger — the single write path for claims about the user.

A claim is never edited in place. Changing what the system believes means
inserting a new assertion that points at the one it replaces (``supersedes_id``)
and closing the old row (``valid_to``/``superseded_by_id``). That is what makes
"why do you think so" and "how did this belief change" answerable.

Epistemic rules enforced here:

* a model inference can never present itself as ``user_confirmed``;
* a claim can only reach ``user_confirmed`` through an explicit user action
  (``belief confirm``), never as a side effect of re-reading a document;
* conflicting restatements of a *user-owned* fact require ``revise`` instead of
  silently overwriting the earlier statement;
* a retracted claim stays in the ledger but is excluded from every live view.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext

from ..db import audit, connect, deserialize, now, serialize
from .errors import ConflictError, NotFoundError

ASSERTION_TYPES = (
    "fact", "preference", "value", "constraint", "skill_hypothesis", "career_hypothesis",
)
EPISTEMIC_STATUSES = (
    "user_stated", "user_confirmed", "document_verified", "inferred", "disputed", "retracted",
)
CONFIDENCE = ("low", "medium", "high")
SOURCE_TYPES = (
    "user_message", "interview", "document", "experience", "feedback",
    "external_source", "model_inference", "reflection", "legacy_profile",
)
REF_TYPES = (
    "assertion", "experience", "feedback", "job", "application", "goal",
    "action", "document", "message",
)
RELATIONS = ("supports", "contradicts", "derived_from", "about")

#: The strongest status a source may produce on its own.
DEFAULT_STATUS = {
    "user_message": "user_stated",
    "interview": "user_stated",
    "legacy_profile": "user_stated",
    "feedback": "user_stated",
    "document": "document_verified",
    "experience": "user_confirmed",
    "model_inference": "inferred",
    "reflection": "inferred",
    "external_source": "inferred",
}
#: Sources that describe the user from the outside; they may never self-confirm.
NON_USER_SOURCES = {"model_inference", "reflection", "external_source"}
#: Statuses that count as "the user stands behind this".
USER_BACKED = {"user_stated", "user_confirmed", "document_verified"}
#: Predicates that can hold only one live value; other types are naturally sets
#: (several constraints, several values, several candidate directions).
DEFAULT_UNIQUE = {"fact", "preference"}

_COLUMNS = (
    "id", "subject", "predicate", "value_json", "assertion_type", "epistemic_status",
    "confidence", "source_type", "source_ref", "explanation", "recorded_at",
    "last_confirmed_at", "valid_from", "valid_to", "supersedes_id", "superseded_by_id",
    "retracted_at", "retract_reason", "dedupe_key",
)


def _row(row) -> dict:
    data = {key: row[key] for key in _COLUMNS}
    data["value"] = deserialize(data.pop("value_json"))
    return data


def _require_choice(name: str, value: str, allowed) -> str:
    if value not in allowed:
        raise ValueError(f"{name} must be one of " + ", ".join(allowed))
    return value


def _clean(text: str, field: str) -> str:
    value = (text or "").strip()
    if not value:
        raise ValueError(f"{field} is required")
    return value


def dedupe_key(subject: str, predicate: str, value, assertion_type: str) -> str:
    payload = json.dumps(
        [subject.strip().lower(), predicate.strip().lower(), assertion_type, value],
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _live(conn, key: str):
    return conn.execute(
        "SELECT * FROM user_assertions WHERE dedupe_key=? AND valid_to='' "
        "AND epistemic_status!='retracted' ORDER BY id DESC LIMIT 1",
        (key,),
    ).fetchone()


def _insert(conn, *, subject, predicate, value, assertion_type, epistemic_status,
            confidence, source_type, source_ref, explanation, at, key, supersedes_id=None):
    cursor = conn.execute(
        "INSERT INTO user_assertions(subject,predicate,value_json,assertion_type,epistemic_status,"
        "confidence,source_type,source_ref,explanation,recorded_at,last_confirmed_at,valid_from,"
        "valid_to,supersedes_id,dedupe_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'',?,?)",
        (subject, predicate, serialize(value), assertion_type, epistemic_status, confidence,
         source_type, source_ref, explanation, at,
         at if epistemic_status == "user_confirmed" else "", at, supersedes_id, key),
    )
    new_id = cursor.lastrowid
    if supersedes_id:
        conn.execute(
            "UPDATE user_assertions SET valid_to=?, superseded_by_id=? WHERE id=? AND valid_to=''",
            (at, new_id, supersedes_id),
        )
    audit(conn, "assertion.proposed", "user_assertions", new_id, f"{subject}.{predicate}")
    return new_id


def propose(*, subject: str, predicate: str, value, assertion_type: str,
            source_type: str, confidence: str = "medium", epistemic_status: str | None = None,
            source_ref: str = "", explanation: str = "", links=None, at: str | None = None,
            unique: bool | None = None, conn=None) -> dict:
    """Add a claim, or report that an identical live claim already exists.

    ``unique`` decides what a *different* value under the same subject.predicate
    means: with ``unique=True`` it is a conflict that needs an explicit revise;
    with ``unique=False`` the claim coexists (two constraints, two values).
    """
    subject = _clean(subject, "subject")
    predicate = _clean(predicate, "predicate")
    _require_choice("assertion_type", assertion_type, ASSERTION_TYPES)
    _require_choice("source_type", source_type, SOURCE_TYPES)
    _require_choice("confidence", confidence, CONFIDENCE)
    status = epistemic_status or DEFAULT_STATUS[source_type]
    _require_choice("epistemic_status", status, EPISTEMIC_STATUSES)
    if status == "retracted":
        raise ValueError("Use belief retract to end a claim; do not propose a retracted one")
    if source_type == "document" and status in ("user_stated", "user_confirmed"):
        raise ValueError("A document verifies facts, not user agreement; use belief confirm for user confirmation")
    if source_type in NON_USER_SOURCES and status in USER_BACKED:
        raise ValueError("Non-user sources cannot create user-backed claims; propose the claim as inferred")
    if source_type in NON_USER_SOURCES and status != "inferred":
        raise ValueError("Non-user sources may only propose inferred claims")
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("value is required")
    stamp = at or now()
    key = dedupe_key(subject, predicate, value, assertion_type)
    unique = (assertion_type in DEFAULT_UNIQUE) if unique is None else bool(unique)

    with (nullcontext(conn) if conn is not None else connect()) as conn:
        prepared_links = _prepare_links(conn, links)
        existing = _live(conn, key)
        if existing is not None:
            return {
                "id": existing["id"], "created": False, "conflict": False,
                "epistemic_status": existing["epistemic_status"],
                "dedupe_key": key,
                "hint": "已有相同主张；如需确认请运行 belief confirm --id "
                        f"{existing['id']}，如需改值请运行 belief revise",
            }
        same_topic = conn.execute(
            "SELECT * FROM user_assertions WHERE subject=? AND predicate=? AND valid_to='' "
            "AND epistemic_status!='retracted' ORDER BY id DESC LIMIT 1",
            (subject, predicate),
        ).fetchone()
        if same_topic is not None and existing is None:
            replaces = same_topic["epistemic_status"] == "inferred" and status in USER_BACKED
            if not replaces and not unique:
                same_topic = None
            elif not replaces:
                raise ConflictError(
                    f"live assertion #{same_topic['id']} already states {subject}.{predicate} "
                    "differently; use belief revise --id to supersede it explicitly"
                )
        if same_topic is not None and existing is None:
            new_id = _insert(
                conn, subject=subject, predicate=predicate, value=value,
                assertion_type=assertion_type, epistemic_status=status, confidence=confidence,
                source_type=source_type, source_ref=source_ref,
                explanation=explanation or "用户以新表述替换了此前的推断",
                at=stamp, key=key, supersedes_id=same_topic["id"],
            )
            _insert_links(conn, new_id, prepared_links)
            return {"id": new_id, "created": True, "conflict": False, "supersedes": same_topic["id"],
                    "auto_superseded_inference": True, "dedupe_key": key,
                    "epistemic_status": status}
        new_id = _insert(
            conn, subject=subject, predicate=predicate, value=value,
            assertion_type=assertion_type, epistemic_status=status, confidence=confidence,
            source_type=source_type, source_ref=source_ref, explanation=explanation,
            at=stamp, key=key,
        )
        _insert_links(conn, new_id, prepared_links)
        return {"id": new_id, "created": True, "conflict": False, "supersedes": None,
                "dedupe_key": key, "epistemic_status": status}


def revise(assertion_id: int, *, value=None, confidence: str | None = None,
           explanation: str = "", source_type: str = "user_message", source_ref: str = "",
           reason: str = "", links=None, at: str | None = None, conn=None) -> dict:
    """Supersede a claim with a new version, preserving the old row."""
    _require_choice("source_type", source_type, SOURCE_TYPES)
    with (nullcontext(conn) if conn is not None else connect()) as conn:
        old = conn.execute("SELECT * FROM user_assertions WHERE id=?", (assertion_id,)).fetchone()
        if old is None:
            raise NotFoundError(f"assertion #{assertion_id} not found")
        if old["epistemic_status"] == "retracted":
            raise ValueError(f"assertion #{assertion_id} is retracted; propose a new claim instead")
        if old["valid_to"] and old["superseded_by_id"]:
            raise ValueError(f"assertion #{assertion_id} already superseded by #{old['superseded_by_id']}")
        new_value = deserialize(old["value_json"]) if value is None else value
        new_confidence = confidence or old["confidence"]
        _require_choice("confidence", new_confidence, CONFIDENCE)
        status = DEFAULT_STATUS[source_type] if source_type in NON_USER_SOURCES else "user_stated"
        inherited_links = links_of(conn, assertion_id) if links is None else links
        prepared_links = _prepare_links(conn, inherited_links)
        new_source_ref = source_ref or old["source_ref"]
        new_explanation = explanation or old["explanation"] or reason or "用户修订"
        stamp = at or now()
        key = dedupe_key(old["subject"], old["predicate"], new_value, old["assertion_type"])
        new_id = _insert(
            conn, subject=old["subject"], predicate=old["predicate"], value=new_value,
            assertion_type=old["assertion_type"], epistemic_status=status,
            confidence=new_confidence, source_type=source_type, source_ref=new_source_ref,
            explanation=new_explanation, at=stamp, key=key,
            supersedes_id=assertion_id,
        )
        _insert_links(conn, new_id, prepared_links)
        audit(conn, "assertion.revised", "user_assertions", new_id,
              f"{assertion_id}->{new_id} {reason or new_explanation}"[:200])
        return {"id": new_id, "supersedes": assertion_id, "epistemic_status": status,
                "value": new_value}


def _closed(row, action: str) -> None:
    """A superseded row is history; acting on it would fork the live version."""
    if row["superseded_by_id"] or (row["valid_to"] and row["epistemic_status"] != "retracted"):
        raise ValueError(
            f"assertion #{row['id']} is no longer current (superseded by #{row['superseded_by_id']}); "
            f"{action} the live version instead"
        )


def confirm(assertion_id: int, *, source_ref: str = "", note: str = "") -> dict:
    """Record that the user personally stands behind this claim."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM user_assertions WHERE id=?", (assertion_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"assertion #{assertion_id} not found")
        if row["epistemic_status"] == "retracted":
            raise ValueError(f"assertion #{assertion_id} is retracted and cannot be confirmed")
        _closed(row, "confirm")
        stamp = now()
        conn.execute(
            "UPDATE user_assertions SET epistemic_status='user_confirmed', last_confirmed_at=?, "
            "valid_to='' WHERE id=?",
            (stamp, assertion_id),
        )
        audit(conn, "assertion.confirmed", "user_assertions", assertion_id, note or source_ref)
        return {"id": assertion_id, "epistemic_status": "user_confirmed", "confirmed_at": stamp}


def dispute(assertion_id: int, reason: str) -> dict:
    reason = _clean(reason, "reason")
    with connect() as conn:
        row = conn.execute("SELECT * FROM user_assertions WHERE id=?", (assertion_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"assertion #{assertion_id} not found")
        if row["epistemic_status"] == "retracted":
            raise ValueError(f"assertion #{assertion_id} is retracted")
        _closed(row, "dispute")
        conn.execute("UPDATE user_assertions SET epistemic_status='disputed' WHERE id=?", (assertion_id,))
        audit(conn, "assertion.disputed", "user_assertions", assertion_id, reason)
        return {"id": assertion_id, "epistemic_status": "disputed", "reason": reason}


def retract(assertion_id: int, reason: str) -> dict:
    reason = _clean(reason, "reason")
    with connect() as conn:
        row = conn.execute("SELECT * FROM user_assertions WHERE id=?", (assertion_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"assertion #{assertion_id} not found")
        if row["epistemic_status"] == "retracted":
            raise ValueError(f"assertion #{assertion_id} is already retracted")
        _closed(row, "retract")
        stamp = now()
        conn.execute(
            "UPDATE user_assertions SET epistemic_status='retracted', retracted_at=?, retract_reason=?, "
            "valid_to=? WHERE id=?",
            (stamp, reason, stamp, assertion_id),
        )
        audit(conn, "assertion.retracted", "user_assertions", assertion_id, reason)
        return {"id": assertion_id, "epistemic_status": "retracted", "retracted_at": stamp}


def add_link(assertion_id: int, ref_type: str, ref_id: str, relation: str = "supports",
             note: str = "", conn=None) -> int:
    _require_choice("ref_type", ref_type, REF_TYPES)
    _require_choice("relation", relation, RELATIONS)
    if conn is not None:
        _check_ref(conn, ref_type, ref_id)
        cursor = conn.execute(
            "INSERT INTO assertion_links(assertion_id,ref_type,ref_id,relation,note,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (assertion_id, ref_type, str(ref_id), relation, note, now()),
        )
        return cursor.lastrowid
    with connect() as own:
        return add_link(assertion_id, ref_type, ref_id, relation, note, conn=own)


def _prepare_links(conn, links) -> list[dict]:
    """Validate every provenance link before the caller writes any rows."""
    prepared = []
    for link in links or []:
        if not isinstance(link, dict):
            raise ValueError("each link must be an object")
        ref_type = _require_choice("ref_type", link.get("ref_type"), REF_TYPES)
        ref_id = str(link.get("ref_id", ""))
        if not ref_id:
            raise ValueError("ref_id is required")
        relation = _require_choice("relation", link.get("relation", "supports"), RELATIONS)
        note = link.get("note", "")
        if not isinstance(note, str):
            raise ValueError("link note must be a string")
        _check_ref(conn, ref_type, ref_id)
        prepared.append({"ref_type": ref_type, "ref_id": ref_id, "relation": relation, "note": note})
    return prepared


def _insert_links(conn, assertion_id: int, links: list[dict]) -> None:
    for link in links:
        add_link(assertion_id, link["ref_type"], link["ref_id"], link["relation"],
                 link["note"], conn=conn)


#: Reference types that must point at a real row; `document`/`message` are free-form.
_REF_TABLES = {
    "assertion": "user_assertions", "experience": "experiences", "feedback": "user_feedback",
    "job": "jobs", "application": "applications", "goal": "career_goals",
    "action": "next_actions",
}


def _check_ref(conn, ref_type: str, ref_id: str) -> None:
    """A provenance link to a non-existent row is worse than no link at all."""
    table = _REF_TABLES.get(ref_type)
    if table is None:
        return
    try:
        numeric = int(ref_id)
    except (TypeError, ValueError):
        raise ValueError(f"ref_id for {ref_type} must be a numeric id") from None
    if conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (numeric,)).fetchone() is None:
        raise NotFoundError(
            f"{ref_type} #{numeric} does not exist; a link must point at a stored record"
        )


def links_of(conn, assertion_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM assertion_links WHERE assertion_id=? ORDER BY "
        "CASE relation WHEN 'supports' THEN 0 WHEN 'derived_from' THEN 1 "
        "WHEN 'about' THEN 2 ELSE 3 END, id",
        (assertion_id,),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        reference = describe_ref(conn, row["ref_type"], row["ref_id"])
        item["ref"] = reference
        item["label"] = reference.get("label", row["ref_id"])
        result.append(item)
    return result


def describe_ref(conn, ref_type: str, ref_id: str) -> dict:
    """Resolve a provenance pointer into a short human-readable label."""
    try:
        if ref_type == "assertion":
            row = conn.execute("SELECT subject,predicate,epistemic_status,recorded_at FROM user_assertions WHERE id=?",
                               (int(ref_id),)).fetchone()
            if row:
                return {"kind": "assertion", "id": int(ref_id),
                        "label": f"{row['subject']}.{row['predicate']}（{row['epistemic_status']}）",
                        "at": row["recorded_at"]}
        elif ref_type == "experience":
            row = conn.execute("SELECT id,data FROM experiences WHERE id=?", (int(ref_id),)).fetchone()
            if row:
                data = deserialize(row["data"])
                return {"kind": "experience", "id": row["id"],
                        "label": f"经历「{data.get('event', '未命名')}」"}
        elif ref_type == "feedback":
            row = conn.execute("SELECT id,feedback_type,target_type,target_id,reason,recorded_at "
                               "FROM user_feedback WHERE id=?", (int(ref_id),)).fetchone()
            if row:
                return {"kind": "feedback", "id": row["id"],
                        "label": f"反馈 {row['feedback_type']}@{row['target_type']}:{row['target_id']}"
                                 + (f"（{row['reason'][:40]}）" if row["reason"] else ""),
                        "at": row["recorded_at"]}
        elif ref_type == "job":
            row = conn.execute("SELECT id,title,company FROM jobs WHERE id=?", (int(ref_id),)).fetchone()
            if row:
                return {"kind": "job", "id": row["id"], "label": f"{row['company']} / {row['title']}"}
        elif ref_type == "application":
            row = conn.execute("SELECT id,job_id,status FROM applications WHERE id=?", (int(ref_id),)).fetchone()
            if row:
                return {"kind": "application", "id": row["id"],
                        "label": f"申请 #{row['id']}（岗位 {row['job_id']}，{row['status']}）"}
        elif ref_type == "goal":
            row = conn.execute("SELECT id,title,status FROM career_goals WHERE id=?", (int(ref_id),)).fetchone()
            if row:
                return {"kind": "goal", "id": row["id"], "label": f"目标「{row['title']}」（{row['status']}）"}
        elif ref_type == "action":
            row = conn.execute("SELECT id,title,status FROM next_actions WHERE id=?", (int(ref_id),)).fetchone()
            if row:
                return {"kind": "action", "id": row["id"], "label": f"行动「{row['title']}」（{row['status']}）"}
        elif ref_type == "document":
            return {"kind": "document", "id": ref_id, "label": str(ref_id)[:80]}
    except (TypeError, ValueError):
        pass
    return {"kind": ref_type, "id": ref_id, "label": str(ref_id)}


def get(assertion_id: int, *, with_links: bool = True, with_audit: bool = True) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM user_assertions WHERE id=?", (assertion_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"assertion #{assertion_id} not found")
        data = _row(row)
        data["chain"] = _chain(conn, assertion_id)
        if with_links:
            data["links"] = links_of(conn, assertion_id)
        if with_audit:
            data["audit"] = [dict(r) for r in conn.execute(
                "SELECT kind,detail,created_at FROM audit_events WHERE resource='user_assertions' "
                "AND resource_id=? ORDER BY id", (assertion_id,))]
        return data


def _chain(conn, assertion_id: int) -> list[dict]:
    """Walk supersede pointers in both directions; oldest first."""
    seen: list[int] = []
    current = assertion_id
    while current and current not in seen:
        seen.append(current)
        row = conn.execute("SELECT supersedes_id FROM user_assertions WHERE id=?", (current,)).fetchone()
        if row is None:
            break
        current = row["supersedes_id"]
    seen.reverse()
    current = assertion_id
    while True:
        row = conn.execute("SELECT superseded_by_id FROM user_assertions WHERE id=?", (current,)).fetchone()
        if not row or not row["superseded_by_id"] or row["superseded_by_id"] in seen:
            break
        current = row["superseded_by_id"]
        seen.append(current)
    chain = []
    for item_id in seen:
        row = conn.execute(
            "SELECT id,value_json,epistemic_status,confidence,source_type,source_ref,explanation,"
            "recorded_at,valid_from,valid_to "
            "FROM user_assertions WHERE id=?", (item_id,)).fetchone()
        if row is None:
            continue
        chain.append({
            "id": row["id"], "value": deserialize(row["value_json"]),
            "epistemic_status": row["epistemic_status"], "confidence": row["confidence"],
            "source_type": row["source_type"], "recorded_at": row["recorded_at"],
            "valid_from": row["valid_from"], "valid_to": row["valid_to"],
            "source_ref": row["source_ref"], "explanation": row["explanation"],
            "links": links_of(conn, item_id),
            "audit": [dict(event) for event in conn.execute(
                "SELECT kind,detail,created_at FROM audit_events WHERE resource='user_assertions' "
                "AND resource_id=? ORDER BY id", (item_id,)).fetchall()],
        })
    return chain


def history(*, assertion_id=None, subject=None, predicate=None) -> dict:
    """Version trajectory for one claim (by id) or for a subject.predicate."""
    with connect() as conn:
        if assertion_id is not None:
            anchor = conn.execute("SELECT 1 FROM user_assertions WHERE id=?",
                                  (int(assertion_id),)).fetchone()
            if anchor is None:
                raise NotFoundError(f"assertion #{assertion_id} not found")
            chain = _chain(conn, int(assertion_id))
            return {"anchor": int(assertion_id), "versions": chain}
        if not subject or not predicate:
            raise ValueError("Provide assertion_id, or both subject and predicate")
        rows = conn.execute(
            "SELECT id FROM user_assertions WHERE subject=? AND predicate=? ORDER BY recorded_at, id",
            (subject, predicate)).fetchall()
        if not rows:
            return {"anchor": {"subject": subject, "predicate": predicate}, "versions": []}
        return {"anchor": {"subject": subject, "predicate": predicate},
                "versions": _chain(conn, rows[0]["id"])}


def live(conn, *, assertion_type: str | None = None, statuses=None, subject: str | None = None,
         limit: int = 200) -> list[dict]:
    """Live (not superseded, not retracted) assertions, newest first."""
    clauses = ["valid_to=''", "epistemic_status!='retracted'"]
    params: list = []
    if assertion_type:
        clauses.append("assertion_type=?")
        params.append(assertion_type)
    if statuses:
        clauses.append("epistemic_status IN (%s)" % ",".join("?" * len(statuses)))
        params.extend(statuses)
    if subject:
        clauses.append("subject=?")
        params.append(subject)
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM user_assertions WHERE {' AND '.join(clauses)} "
            "ORDER BY recorded_at DESC, id DESC LIMIT ?", params).fetchall()
        return [_row(row) for row in rows]


def list_assertions(*, assertion_type=None, status=None, subject=None, live_only=True,
                    limit: int = 50) -> list[dict]:
    clauses, params = [], []
    if assertion_type:
        _require_choice("assertion_type", assertion_type, ASSERTION_TYPES)
        clauses.append("assertion_type=?")
        params.append(assertion_type)
    if status:
        _require_choice("epistemic_status", status, EPISTEMIC_STATUSES)
        clauses.append("epistemic_status=?")
        params.append(status)
    if subject:
        clauses.append("subject=?")
        params.append(subject)
    if live_only:
        clauses.append("valid_to=''")
        clauses.append("epistemic_status!='retracted'")
    params.append(limit)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM user_assertions {where} ORDER BY recorded_at DESC, id DESC LIMIT ?",
            params).fetchall()
        result = []
        for row in rows:
            item = _row(row)
            item["link_count"] = conn.execute(
                "SELECT COUNT(*) FROM assertion_links WHERE assertion_id=?", (row["id"],)).fetchone()[0]
            result.append(item)
        return result
