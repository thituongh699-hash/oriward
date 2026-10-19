"""Projection of identity fields from the assertion ledger over the v0.1 cache."""
from __future__ import annotations

from ..db import deserialize
from .assertions import USER_BACKED, NON_USER_SOURCES


IDENTITY_FIELDS = ("display_name", "location", "target_role", "target_roles", "contact", "summary_verified")


def _plain(value):
    if isinstance(value, dict) and set(value) == {"text"}:
        return value["text"]
    return value


def _settled(claim):
    return (not claim["valid_to"] and claim["epistemic_status"] in USER_BACKED
            and not (claim["epistemic_status"] == "user_stated" and claim["confidence"] == "low")
            and not (claim["source_type"] in NON_USER_SOURCES
                     and claim["epistemic_status"] != "user_confirmed"))


def read_profile(conn) -> dict | None:
    """Return the legacy profile overlaid by authoritative mapped assertions.

    A field with any ledger history no longer falls back to its cache value if
    its latest assertion is retracted, disputed, inferred, or otherwise not
    user-backed.
    """
    row = conn.execute("SELECT data FROM profile WHERE id=1").fetchone()
    projected = deserialize(row["data"]) if row else {}
    for field in IDENTITY_FIELDS:
        history = conn.execute(
            "SELECT * FROM user_assertions WHERE subject='user' AND predicate=? "
            "ORDER BY id DESC", (field,),
        ).fetchall()
        if not history:
            continue
        current = next((claim for claim in history if _settled(claim)), None)
        if current is None:
            projected.pop(field, None)
            continue
        projected[field] = _plain(deserialize(current["value_json"]))
    for field, subject, predicate in (
            ("values", "user", "value"), ("preferences", "user", "preference"),
            ("skills", "user", "has_skill"), ("constraints", "work_conditions", "hard_constraint"),
            ("hard_constraints", "work_conditions", "hard_constraint")):
        claims = conn.execute("SELECT * FROM user_assertions WHERE subject=? AND predicate=? ORDER BY id",
                              (subject, predicate)).fetchall()
        if claims:
            projected[field] = [_plain(deserialize(claim["value_json"])) for claim in claims if _settled(claim)]
    # Singular/plural target-role aliases represent one current selection.
    role = conn.execute("SELECT * FROM user_assertions WHERE subject='user' "
                        "AND predicate IN ('target_role','target_roles') ORDER BY id DESC LIMIT 1").fetchone()
    if role:
        projected.pop("target_role", None)
        projected.pop("target_roles", None)
        if _settled(role):
            projected[role["predicate"]] = _plain(deserialize(role["value_json"]))
    return projected if projected or row else None
