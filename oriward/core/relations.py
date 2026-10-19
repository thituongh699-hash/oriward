"""Resolve stored action sources to the jobs and goals they concern."""
from __future__ import annotations

from ..db import deserialize
from .errors import NotFoundError


def _ids(values):
    return sorted({int(value) for value in values if value is not None})


def source_context(conn, source_type: str, source_id: int | None) -> dict:
    """Return sorted job/goal IDs related to a source; None remains unlinked.

    Learning-plan job IDs and goal IDs are read from its stored JSON. A bad
    concrete reference raises NotFoundError so callers cannot silently create
    or report an action attached to an object that does not exist.
    """
    if source_id is None:
        return {"job_ids": [], "goal_ids": []}
    source_id = int(source_id)
    job_ids, goal_ids = [], []
    table = {"goal": "career_goals", "job": "jobs", "application": "applications",
             "learning": "learning_plans", "interview": "interviews",
             "reflection": "reflection_runs"}.get(source_type)
    if table is None:
        return {"job_ids": [], "goal_ids": []}
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (source_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"{source_type} #{source_id} not found")

    if source_type == "goal":
        goal_ids.append(source_id)
        job_ids.extend(item[0] for item in conn.execute(
            "SELECT job_id FROM job_pipeline WHERE goal_id=?", (source_id,)))
    elif source_type == "job":
        job_ids.append(source_id)
    elif source_type in ("application", "interview"):
        job_ids.append(row["job_id"])
    elif source_type == "learning":
        data = deserialize(row["data"])
        raw_jobs = data.get("job_ids", [])
        if not isinstance(raw_jobs, list):
            raise ValueError(f"learning plan #{source_id} job_ids must be an array")
        job_ids.extend(int(value) for value in raw_jobs)
        if data.get("goal_id") is not None:
            goal_ids.append(int(data["goal_id"]))

    for job_id in _ids(job_ids):
        if conn.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone() is None:
            raise NotFoundError(f"job #{job_id} referenced by {source_type} #{source_id} not found")
        pipeline = conn.execute("SELECT goal_id FROM job_pipeline WHERE job_id=?", (job_id,)).fetchone()
        if pipeline and pipeline["goal_id"] is not None:
            goal_ids.append(pipeline["goal_id"])
    for goal_id in _ids(goal_ids):
        if conn.execute("SELECT 1 FROM career_goals WHERE id=?", (goal_id,)).fetchone() is None:
            raise NotFoundError(f"goal #{goal_id} referenced by {source_type} #{source_id} not found")
    return {"job_ids": _ids(job_ids), "goal_ids": _ids(goal_ids)}


def actions_for_job(conn, job_id: int) -> list[dict]:
    """All open actions attached to a job directly or through its goal."""
    job_id = int(job_id)
    pipeline = conn.execute("SELECT goal_id FROM job_pipeline WHERE job_id=?", (job_id,)).fetchone()
    goal_id = pipeline["goal_id"] if pipeline else None
    rows = conn.execute(
        "SELECT * FROM next_actions WHERE status IN ('todo','doing','blocked') ORDER BY id")
    result = []
    for row in rows:
        item = dict(row)
        try:
            context = source_context(conn, item["source_type"], item["source_id"])
        except NotFoundError:
            continue
        # A shared goal does not make an interview/application for another job
        # relevant here. Only tasks without concrete jobs may inherit the goal.
        if job_id in context["job_ids"] or (not context["job_ids"] and goal_id is not None
                                            and goal_id in context["goal_ids"]):
            item["related_job_ids"] = context["job_ids"]
            item["related_goal_ids"] = context["goal_ids"]
            result.append(item)
    return result
