"""Weekly reflection — proposals only, never silent profile edits.

Every proposal points at the records that produced it and names the command that
would apply it. The run is stored so the user can later see what the system
*wanted* to change and whether they agreed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..db import audit, connect, deserialize, now, serialize
from .errors import NotFoundError
from . import relations

STATUSES = ("proposed", "approved", "partially_approved", "rejected")


def _cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def weekly(days: int = 7) -> dict:
    cutoff = _cutoff(days)
    proposals: list[dict] = []
    inputs: list[str] = []

    with connect() as conn:
        feedback = [dict(row) for row in conn.execute(
            "SELECT * FROM user_feedback WHERE recorded_at >= ? AND promoted_assertion_id IS NULL "
            "ORDER BY id", (cutoff,))]
        inputs.extend(f"user_feedback:{row['id']}" for row in feedback)

        groups: dict[str, list[dict]] = {}
        for row in feedback:
            if row["feedback_type"] not in ("not_interested", "declined", "rejected"):
                continue
            key = " ".join((row["reason"] or "").split()).lower()
            if len(key) < 4:
                continue
            groups.setdefault(key, []).append(row)
        for reason, rows in groups.items():
            if len(rows) < 2:
                continue
            proposals.append({
                "kind": "promote_constraint",
                "summary": f"同一理由出现 {len(rows)} 次：「{reason[:40]}」，是否升级为长期约束？",
                "evidence": [f"user_feedback:{row['id']}" for row in rows],
                "apply_with": f"python -m careeros signal promote --id {rows[0]['id']} --human-confirmed",
                "requires_user_approval": True,
                "confidence": "medium",
            })

        stale_jobs = conn.execute(
            "SELECT p.job_id,j.title,j.company,p.last_checked_at FROM job_pipeline p "
            "JOIN jobs j ON j.id=p.job_id WHERE p.discovery_status='shortlisted' "
            "AND (p.last_checked_at='' OR p.last_checked_at < ?) LIMIT 3", (cutoff,)).fetchall()
        for row in stale_jobs:
            has_action = relations.actions_for_job(conn, row["job_id"])
            if has_action:
                continue
            proposals.append({
                "kind": "stale_shortlist",
                "summary": f"短名单岗位「{row['company']} / {row['title']}」超过 {days} 天没有更新，也没有下一步动作",
                "evidence": [f"job:{row['job_id']}"],
                "apply_with": "python -m careeros pipeline update --job-id "
                              f"{row['job_id']} --status evaluating --reason '重新评估'",
                "requires_user_approval": True,
                "confidence": "low",
            })

        covered_goals = set()
        for action in conn.execute("SELECT source_type,source_id FROM next_actions WHERE status IN ('todo','doing','blocked')"):
            try:
                covered_goals.update(relations.source_context(conn, action["source_type"], action["source_id"])["goal_ids"])
            except ValueError:
                continue
        idle_goals = [row for row in conn.execute(
            "SELECT id,title FROM career_goals WHERE status IN ('active','exploring') ORDER BY id")
                      if row["id"] not in covered_goals][:3]
        for row in idle_goals:
            proposals.append({
                "kind": "goal_without_action",
                "summary": f"目标「{row['title']}」没有任何未完成行动，目标与执行已经脱节",
                "evidence": [f"goal:{row['id']}"],
                "apply_with": "python -m careeros action propose --file <task.json>",
                "requires_user_approval": True,
                "confidence": "medium",
            })

        unconfirmed = conn.execute(
            "SELECT id,value_json FROM user_assertions WHERE valid_to='' AND epistemic_status='inferred' "
            "AND recorded_at < ? ORDER BY id DESC LIMIT 3", (cutoff,)).fetchall()
        for row in unconfirmed:
            proposals.append({
                "kind": "confirm_inference",
                "summary": f"推断「{str(deserialize(row['value_json']))[:40]}」已存在超过 {days} 天仍未确认",
                "evidence": [f"assertion:{row['id']}"],
                "apply_with": f"python -m careeros belief confirm --id {row['id']}",
                "requires_user_approval": True,
                "confidence": "low",
            })

        cursor = conn.execute(
            "INSERT INTO reflection_runs(period_start,period_end,input_event_ids_json,"
            "proposed_updates_json,approved_updates_json,status,created_at) VALUES (?,?,?,?,'[]','proposed',?)",
            (cutoff, now(), serialize(inputs), serialize(proposals), now()),
        )
        run_id = cursor.lastrowid
        audit(conn, "reflection.proposed", "reflection_runs", run_id, f"{len(proposals)} proposals")

    return {"run_id": run_id, "period": {"start": cutoff, "end": now()}, "status": "proposed",
            "proposals": proposals, "applied": False,
            "note": "本次回顾只生成待审批提案；未经用户确认不会改写任何画像或目标"}


def list_runs(limit: int = 10) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM reflection_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["proposed_updates"] = deserialize(item.pop("proposed_updates_json"))
            item["approved_updates"] = deserialize(item.pop("approved_updates_json"))
            item["input_event_ids"] = deserialize(item.pop("input_event_ids_json"))
            result.append(item)
        return result


def decide(run_id: int, *, status: str, note: str = "", accepted=None) -> dict:
    """Record the outcome of a review without applying anything automatically.

    ``accepted`` holds the proposal indexes the user approved. Without it an
    ``approved`` run means "all of them"; an ``approved`` run with a subset is
    stored as ``partially_approved`` instead of silently discarding the detail.
    """
    if status not in STATUSES or status == "proposed":
        raise ValueError("status must be approved, partially_approved or rejected")
    with connect() as conn:
        row = conn.execute("SELECT * FROM reflection_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"reflection run #{run_id} not found")
        proposals = deserialize(row["proposed_updates_json"])
        if status == "rejected":
            chosen = []
        elif accepted is None:
            chosen = list(range(len(proposals)))
        else:
            if isinstance(accepted, str):
                parts = [p.strip() for p in accepted.split(",") if p.strip()]
            else:
                parts = list(accepted)
            chosen = sorted({int(p) for p in parts if 0 <= int(p) < len(proposals)})
        if status == "approved" and len(chosen) != len(proposals):
            status = "partially_approved"
        if status == "partially_approved" and not chosen:
            status = "rejected"
        approved = {"note": note, "accepted": chosen,
                    "items": [proposals[i] for i in chosen]}
        conn.execute("UPDATE reflection_runs SET status=?, decided_at=?, approved_updates_json=? WHERE id=?",
                     (status, now(), serialize(approved), run_id))
        audit(conn, "reflection.decided", "reflection_runs", run_id,
              f"{status} {chosen}")
        return {"run_id": run_id, "status": status, "note": note, "accepted": chosen}
