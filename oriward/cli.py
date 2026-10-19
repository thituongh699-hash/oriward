"""Oriward commands for use by the user or Agent skill workflows."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import hashlib
from .db import connect, database_path, deserialize
from . import services as s
from . import sources, assessment, feedback, discovery, tracking, official
from . import migrations
from . import experience_library, onboarding, search_runs
from .core import actions as core_actions, assertions as core_belief, context as core_context
from .core import goals as core_goals, pipeline as core_pipeline, reflection as core_reflection
from .core import signals as core_signals, twin as core_twin
from .core import decisions as core_decisions

_OUTPUT_PATH = None


def p(obj):
    payload = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    if _OUTPUT_PATH:
        path = Path(_OUTPUT_PATH).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = payload.encode("utf-8")
        path.write_bytes(data)
        print(json.dumps({"saved": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}, ensure_ascii=False))
    else:
        print(payload)


def _ids(value):
    return [int(item.strip()) for item in value.split(",") if item.strip()] if value is not None else None


def _sections(value):
    return [item.strip() for item in value.split(",") if item.strip()] if value is not None else None


BELIEF_FIELDS = ("subject", "predicate", "value", "assertion_type", "source_type",
                 "confidence", "epistemic_status", "source_ref", "explanation", "links")
REVISE_FIELDS = ("id", "value", "confidence", "explanation", "source_type", "source_ref", "reason", "links")
GOAL_FIELDS = ("title", "direction_id", "priority", "status", "target_date", "success_criteria",
               "time_budget_hours", "owner", "rationale")
ACTION_FIELDS = ("title", "source_type", "source_id", "action_type", "due_at", "priority",
                 "depends_on", "suggestion_reason", "requires_approval", "effort_hours")
SIGNAL_FIELDS = ("target_type", "target_id", "feedback_type", "reason", "source", "scope")
GOAL_UPDATE_FIELDS = ("title", "direction_id", "priority", "status", "target_date", "success_criteria",
                      "time_budget_hours", "rationale", "note")
DECISION_FIELDS = ("action_id", "reason", "factors", "constraint_checks", "alternatives")


def pick(data, fields, label):
    """Reject unknown keys so a typo never silently becomes a default."""
    if not isinstance(data, dict):
        raise ValueError(f"{label} file must contain a JSON object")
    unknown = sorted(set(data) - set(fields))
    if unknown:
        raise ValueError(f"unknown fields in {label} file: {', '.join(unknown)}")
    return data


def belief_command(args):
    if args.action == "propose":
        return core_belief.propose(**pick(s.json_file(args.file), BELIEF_FIELDS, "belief"))
    if args.action == "revise":
        data = pick(s.json_file(args.file), REVISE_FIELDS, "belief revision")
        assertion_id = data.pop("id")
        return core_belief.revise(assertion_id, **data)
    if args.action == "confirm":
        return core_belief.confirm(args.id, note=args.note)
    if args.action == "dispute":
        return core_belief.dispute(args.id, args.reason)
    if args.action == "retract":
        return core_belief.retract(args.id, args.reason)
    if args.action == "list":
        return core_belief.list_assertions(assertion_type=args.type, status=args.status,
                                           subject=args.subject, live_only=not args.all,
                                           limit=args.limit)
    if args.action == "history":
        return core_belief.history(assertion_id=args.id, subject=args.subject, predicate=args.predicate)
    return core_belief.add_link(args.id, args.ref_type, args.ref_id, args.relation, args.note)


def run(argv=None):
    global _OUTPUT_PATH
    parser = argparse.ArgumentParser(prog="python -m oriward", description="Oriward local evidence-backed career toolkit")
    parser.add_argument("--output", help="Save full JSON locally and print only path/size/hash")
    sub = parser.add_subparsers(dest="domain", required=True)
    sub.add_parser("init", help="Create or migrate the local SQLite schema")
    sub.add_parser("brief", help="Legacy object counts; prefer `context brief`")
    pipe = sub.add_parser("pipeline", help="Opportunity pipeline; without an action prints the legacy funnel")
    pipe_sub = pipe.add_subparsers(dest="action")
    x = pipe_sub.add_parser("list"); x.add_argument("--status")
    x.add_argument("--include-discarded", action="store_true")
    x.add_argument("--limit", type=int, default=50)
    x = pipe_sub.add_parser("show"); x.add_argument("--job-id", type=int, required=True)
    x = pipe_sub.add_parser("update")
    x.add_argument("--job-id", type=int, required=True); x.add_argument("--status", required=True)
    x.add_argument("--reason", default=""); x.add_argument("--priority", type=int)
    x.add_argument("--next-review-at", default=None)
    x.add_argument("--goal-id", type=int, help="Career goal this opportunity serves")
    x = pipe_sub.add_parser("ensure")
    x.add_argument("--job-id", type=int, required=True); x.add_argument("--status", default="discovered")
    x.add_argument("--priority", type=int); x.add_argument("--goal-id", type=int)
    for domain, has_add in (("profile", False), ("experience", True), ("career", True), ("jobs", False), ("analysis", True), ("resume", False), ("application", False), ("learning", True), ("interview", True), ("review", False), ("feedback", False), ("leads", False), ("official", False)):
        a = sub.add_parser(domain)
        actions = a.add_subparsers(dest="action", required=True)
        if domain == "profile":
            x = actions.add_parser("save"); x.add_argument("--file", required=True)
            actions.add_parser("show")
        elif domain == "experience":
            x = actions.add_parser("add"); x.add_argument("--file", required=True)
            for name in ("list", "index", "skills"):
                x = actions.add_parser(name)
                x.add_argument("--query", default=""); x.add_argument("--ids")
                x.add_argument("--budget", type=int, default=2200)
                x.add_argument("--offset", type=int, default=0)
            x = actions.add_parser("detail")
            x.add_argument("--ids"); x.add_argument("--query", default="")
            x.add_argument("--sections"); x.add_argument("--include-inactive", action="store_true")
            x = actions.add_parser("show")
            x.add_argument("--id", type=int, required=True); x.add_argument("--version", type=int)
            x.add_argument("--sections"); x.add_argument("--include-inactive", action="store_true")
            x = actions.add_parser("revise")
            x.add_argument("--id", type=int, required=True); x.add_argument("--file", required=True)
            x.add_argument("--reason", required=True); x.add_argument("--expected-version", type=int)
            for name in ("exclude", "supersede"):
                x = actions.add_parser(name)
                x.add_argument("--id", type=int, required=True); x.add_argument("--reason", required=True)
                if name == "supersede": x.add_argument("--replacement-id", type=int, required=True)
            x = actions.add_parser("history"); x.add_argument("--id", type=int, required=True)
        elif domain == "jobs":
            x = actions.add_parser("import")
            files = x.add_mutually_exclusive_group(required=True)
            files.add_argument("--csv"); files.add_argument("--json")
            actions.add_parser("list")
            x = actions.add_parser("show"); x.add_argument("--id", type=int, required=True)
            x = actions.add_parser("snapshots"); x.add_argument("--id", type=int, required=True)
            x = actions.add_parser("sync")
            x.add_argument("--provider", choices=["greenhouse", "lever"], required=True)
            x.add_argument("--board", required=True); x.add_argument("--company")
            x.add_argument("--limit", type=int, default=100)
            actions.add_parser("channels")
            x = actions.add_parser("browser-record"); x.add_argument("--file", required=True)
            x = actions.add_parser("browser-runs"); x.add_argument("--limit", type=int, default=10)
            for name in ("search", "search-plan", "shortlist", "browser-plan"):
                x = actions.add_parser(name)
                x.add_argument("--query", required=True); x.add_argument("--location", default="")
                if name == "search-plan":
                    x.add_argument("--providers", help="Comma-separated channel IDs")
                else:
                    x.add_argument("--limit", type=int, default=10)
                if name == "search":
                    x.add_argument("--provider", default="zhiye", choices=list(discovery.CHANNELS))
                    x.add_argument("--refresh", action="store_true")
                if name == "browser-plan":
                    x.add_argument("--provider", choices=["boss", "zhilian"], required=True)
                if name == "shortlist":
                    x.add_argument("--exclude", default="", help="Space-separated exclusion terms")
            x = actions.add_parser("card"); x.add_argument("--id", type=int, required=True)
            x = actions.add_parser("group"); x.add_argument("--rebuild", action="store_true")
            x.add_argument("--limit", type=int, default=50)
            x = actions.add_parser("route")
            x.add_argument("--provider", required=True, choices=list(discovery.CHANNELS))
            x.add_argument("--query", default=""); x.add_argument("--location", default="")
        elif domain == "leads":
            x = actions.add_parser("import"); x.add_argument("--file", required=True)
            x = actions.add_parser("list")
            x.add_argument("--provider", choices=list(discovery.CHANNELS)); x.add_argument("--limit", type=int, default=20)
            x = actions.add_parser("promote"); x.add_argument("--id", type=int, required=True); x.add_argument("--file", required=True)
            x = actions.add_parser("fetch"); x.add_argument("--id", type=int, required=True); x.add_argument("--refresh", action="store_true")
        elif domain == "resume":
            x = actions.add_parser("build")
            x.add_argument("--job-id", type=int, required=True)
            x.add_argument("--experience-ids", required=True, help="Comma-separated evidence IDs")
            x.add_argument("--headline", default="")
            actions.add_parser("list")
            x = actions.add_parser("revise"); x.add_argument("--file", required=True)
            x = actions.add_parser("history"); x.add_argument("--id", type=int, required=True)
            x = actions.add_parser("confirm"); x.add_argument("--id", type=int, required=True)
            x.add_argument("--human-confirmed", action="store_true")
        elif domain == "review":
            x = actions.add_parser("packet"); x.add_argument("--resume-id", type=int, required=True)
            x.add_argument("--compact", action="store_true")
            x = actions.add_parser("save"); x.add_argument("--file", required=True)
            x = actions.add_parser("list"); x.add_argument("--resume-id", type=int)
        elif domain == "feedback":
            x = actions.add_parser("save"); x.add_argument("--file", required=True)
            x = actions.add_parser("list"); x.add_argument("--job-id", type=int)
            x = actions.add_parser("plan"); x.add_argument("--job-id", type=int, required=True)
            x = actions.add_parser("resolve")
            x.add_argument("--id", type=int, required=True); x.add_argument("--review-id", type=int, required=True)
            x.add_argument("--note", required=True)
        elif domain == "application":
            x = actions.add_parser("prepare")
            x.add_argument("--job-id", type=int, required=True)
            x.add_argument("--resume-id", type=int, required=True)
            x.add_argument("--channel", default="", help="Channel the application will be submitted through")
            x.add_argument("--apply-url", default="", help="Exact posting URL the application goes to")
            x = actions.add_parser("record")
            x.add_argument("--id", type=int, required=True)
            x.add_argument("--status", required=True)
            x.add_argument("--human-confirmed", action="store_true")
            x.add_argument("--note", default="")
            x.add_argument("--external-reference", default="")
            x.add_argument("--channel", default="")
            x = actions.add_parser("channel")
            x.add_argument("--id", type=int, required=True)
            x.add_argument("--channel", required=True)
            x.add_argument("--apply-url", default="")
            x = actions.add_parser("event")
            x.add_argument("--id", type=int, required=True)
            x.add_argument("--kind", required=True)
            x.add_argument("--label", default="")
            x.add_argument("--scheduled-at", default="")
            x.add_argument("--occurred-at", default="")
            x = actions.add_parser("timeline"); x.add_argument("--id", type=int, required=True)
            x = actions.add_parser("agenda"); x.add_argument("--days", type=int, default=30)
            actions.add_parser("list")
        elif domain == "official":
            x = actions.add_parser("plan")
            x.add_argument("--company", required=True)
            x.add_argument("--query", default="")
            x.add_argument("--url", default="")
            x = actions.add_parser("fetch")
            x.add_argument("--url", required=True)
            x.add_argument("--company", default="")
            x.add_argument("--refresh", action="store_true")
            x.add_argument("--record-only", action="store_true", help="Read and return the JD without importing it")
        elif has_add:
            x = actions.add_parser("add" if domain in ("experience", "career") else "save")
            x.add_argument("--file", required=True)
            actions.add_parser("list")
            if domain == "analysis":
                for name in ("draft", "packet"):
                    x = actions.add_parser(name); x.add_argument("--job-id", type=int, required=True)
                    if name == "packet": x.add_argument("--compact", action="store_true")

    setup = sub.add_parser("onboarding", help="Lightweight first use, targets and optional channels")
    oa = setup.add_subparsers(dest="action", required=True)
    oa.add_parser("status")
    x = oa.add_parser("missing"); x.add_argument("--before-search", action="store_true")
    x = oa.add_parser("preferences"); x.add_argument("--file", required=True)
    x = oa.add_parser("prompt"); x.add_argument("--field", required=True)
    x.add_argument("--state", required=True, choices=sorted(onboarding.PROMPT_STATES))
    x = oa.add_parser("channel-intent"); x.add_argument("--provider", required=True)
    x.add_argument("--preference", required=True, choices=sorted(onboarding.PREFERENCES))
    x = oa.add_parser("channel-state"); x.add_argument("--provider", required=True)
    x.add_argument("--state", required=True, choices=sorted(onboarding.CONNECTIONS))
    x.add_argument("--detail", default=""); x.add_argument("--receipt")
    x = oa.add_parser("topic"); x.add_argument("--title", required=True)
    x.add_argument("--next-action", default=""); x.add_argument("--blocker", default="")
    x = oa.add_parser("pause"); x.add_argument("--reason", default="")
    x = oa.add_parser("resume"); x.add_argument("--id", type=int, required=True)

    sr = sub.add_parser("search-run", help="Search receipts and Markdown reports, including partial failures")
    sa = sr.add_subparsers(dest="action", required=True)
    x = sa.add_parser("start"); x.add_argument("--file", required=True)
    x = sa.add_parser("record"); x.add_argument("--id", type=int, required=True); x.add_argument("--file", required=True)
    x = sa.add_parser("candidates"); x.add_argument("--id", type=int, required=True); x.add_argument("--file", required=True)
    x = sa.add_parser("finish"); x.add_argument("--id", type=int, required=True); x.add_argument("--file")
    x = sa.add_parser("show"); x.add_argument("--id", type=int, required=True)
    x = sa.add_parser("list"); x.add_argument("--limit", type=int, default=20)

    ctx = sub.add_parser("context", help="Bounded user context assembled from Career Twin Core")
    ca = ctx.add_subparsers(dest="action", required=True)
    x = ca.add_parser("brief", help="Five-question session brief with IDs for drill-down")
    x.add_argument("--max-chars", type=int, default=3200)
    for name in ("inspect", "why", "history"):
        x = ca.add_parser(name); x.add_argument("--assertion-id", type=int, required=True)

    belief = sub.add_parser("belief", help="Versioned claims about the user (facts, preferences, hypotheses)")
    ba = belief.add_subparsers(dest="action", required=True)
    x = ba.add_parser("propose"); x.add_argument("--file", required=True)
    x = ba.add_parser("revise"); x.add_argument("--file", required=True)
    x = ba.add_parser("confirm"); x.add_argument("--id", type=int, required=True); x.add_argument("--note", default="")
    x = ba.add_parser("dispute"); x.add_argument("--id", type=int, required=True); x.add_argument("--reason", required=True)
    x = ba.add_parser("retract"); x.add_argument("--id", type=int, required=True); x.add_argument("--reason", required=True)
    x = ba.add_parser("list"); x.add_argument("--type"); x.add_argument("--status"); x.add_argument("--subject")
    x.add_argument("--all", action="store_true", help="Include superseded and retracted rows")
    x.add_argument("--limit", type=int, default=50)
    x = ba.add_parser("history"); x.add_argument("--id", type=int); x.add_argument("--subject"); x.add_argument("--predicate")
    x = ba.add_parser("link")
    x.add_argument("--id", type=int, required=True); x.add_argument("--ref-type", required=True)
    x.add_argument("--ref-id", required=True); x.add_argument("--relation", default="supports"); x.add_argument("--note", default="")

    goal = sub.add_parser("goal", help="Career goals with priority and status")
    ga = goal.add_subparsers(dest="action", required=True)
    x = ga.add_parser("add"); x.add_argument("--file", required=True)
    x = ga.add_parser("list"); x.add_argument("--status")
    x = ga.add_parser("update")
    x.add_argument("--id", type=int, required=True); x.add_argument("--status"); x.add_argument("--priority", type=int)
    x.add_argument("--target-date"); x.add_argument("--note", default="")
    x.add_argument("--file"); x.add_argument("--title"); x.add_argument("--rationale")
    x.add_argument("--time-budget-hours", type=float)
    x = ga.add_parser("history"); x.add_argument("--id", type=int, required=True)

    decision = sub.add_parser("decision", help="Frozen six-factor reasoning and subsequent user choices/results")
    da = decision.add_subparsers(dest="action", required=True)
    x = da.add_parser("record"); x.add_argument("--file", required=True)
    x = da.add_parser("show"); x.add_argument("--id", type=int, required=True)
    x = da.add_parser("history"); x.add_argument("--action-id", type=int, required=True)
    x = da.add_parser("outcome")
    x.add_argument("--id", type=int, required=True)
    x.add_argument("--kind", choices=core_decisions.EVENT_KINDS, required=True)
    x.add_argument("--note", required=True); x.add_argument("--evidence", default="")
    x.add_argument("--human-confirmed", action="store_true")

    action = sub.add_parser("action", help="Next actions; ranking is explainable, not a probability")
    aa = action.add_subparsers(dest="action", required=True)
    x = aa.add_parser("list"); x.add_argument("--status"); x.add_argument("--sort", default="rank", choices=["rank", "due"])
    x.add_argument("--limit", type=int, default=20)
    x = aa.add_parser("propose"); x.add_argument("--file", required=True)
    x = aa.add_parser("complete")
    x.add_argument("--id", type=int, required=True); x.add_argument("--human-confirmed", action="store_true")
    x.add_argument("--evidence", default="")
    x = aa.add_parser("block"); x.add_argument("--id", type=int, required=True); x.add_argument("--reason", required=True)
    x = aa.add_parser("unblock"); x.add_argument("--id", type=int, required=True)

    signal = sub.add_parser("signal", help="User reactions recorded where they happened")
    sa = signal.add_subparsers(dest="action", required=True)
    x = sa.add_parser("add"); x.add_argument("--file", required=True)
    x = sa.add_parser("list"); x.add_argument("--target-type"); x.add_argument("--target-id", type=int)
    x.add_argument("--limit", type=int, default=50)
    x = sa.add_parser("promote")
    x.add_argument("--id", type=int, required=True); x.add_argument("--subject", default="work_conditions")
    x.add_argument("--predicate", default="hard_constraint"); x.add_argument("--assertion-type", default="constraint")
    x.add_argument("--confidence", default="medium"); x.add_argument("--value")
    x.add_argument("--human-confirmed", action="store_true",
                   help="Required: only the user can turn one reaction into a standing constraint")

    reflection = sub.add_parser("reflection", help="Periodic review that only proposes changes")
    ra = reflection.add_subparsers(dest="action", required=True)
    x = ra.add_parser("weekly"); x.add_argument("--days", type=int, default=7)
    ra.add_parser("list")
    x = ra.add_parser("decide")
    x.add_argument("--id", type=int, required=True)
    x.add_argument("--status", required=True, choices=["approved", "partially_approved", "rejected"])
    x.add_argument("--accept", help="Comma-separated proposal indexes the user approved, e.g. 0,2")
    x.add_argument("--note", default="")

    twin = sub.add_parser("twin", help="Career Twin Core health and legacy bridge")
    ta = twin.add_subparsers(dest="action", required=True)
    ta.add_parser("status")
    ta.add_parser("sync-legacy")
    ta.add_parser("export")

    args = parser.parse_args(argv)
    _OUTPUT_PATH = args.output
    if args.domain == "init":
        with connect() as db:
            sources.ensure_source_schema(db)
            assessment._ensure_review_table(db)
            feedback.ensure_schema(db)
            discovery.ensure_schema(db)
            version = migrations.current_version(db)
            applied = [row["name"] for row in db.execute("SELECT name FROM schema_migrations ORDER BY version")]
        p({"ok": True, "db": str(database_path()), "schema_version": version, "migrations": applied}); return
    if args.domain == "brief":
        p(s.summary()); return
    if args.domain == "pipeline":
        if args.action is None:
            p(tracking.pipeline())
        elif args.action == "list":
            p({"counts": core_pipeline.counts(),
               "items": core_pipeline.list_pipeline(status=args.status,
                                                    include_discarded=args.include_discarded,
                                                    limit=args.limit)})
        elif args.action == "show":
            p(core_pipeline.show(args.job_id))
        elif args.action == "update":
            p(core_pipeline.update(args.job_id, status=args.status, reason=args.reason,
                                   priority=args.priority, next_review_at=args.next_review_at,
                                   goal_id=args.goal_id))
        else:
            p(core_pipeline.ensure(args.job_id, status=args.status, priority=args.priority,
                                   goal_id=args.goal_id))
        return
    if args.domain == "context":
        if args.action == "brief":
            p(core_context.brief(max_chars=args.max_chars))
        elif args.action == "inspect":
            p(core_context.inspect(args.assertion_id))
        elif args.action == "why":
            p(core_context.why(args.assertion_id))
        else:
            p(core_belief.history(assertion_id=args.assertion_id))
        return
    if args.domain == "belief":
        p(belief_command(args)); return
    if args.domain == "goal":
        if args.action == "add":
            p(core_goals.add(**pick(s.json_file(args.file), GOAL_FIELDS, "goal")))
        elif args.action == "list":
            p(core_goals.list_goals(status=args.status))
        elif args.action == "history":
            p(core_goals.history(args.id))
        else:
            updates = pick(s.json_file(args.file), GOAL_UPDATE_FIELDS, "goal update") if args.file else {}
            for key in ("status", "priority", "target_date", "title", "rationale", "time_budget_hours"):
                if getattr(args, key) is not None:
                    updates[key] = getattr(args, key)
            if args.note:
                updates["note"] = args.note
            p(core_goals.update(args.id, **updates))
        return
    if args.domain == "decision":
        if args.action == "record":
            p(core_decisions.record(**pick(s.json_file(args.file), DECISION_FIELDS, "decision")))
        elif args.action == "show":
            p(core_decisions.get(args.id))
        elif args.action == "history":
            p(core_decisions.history(args.action_id))
        else:
            p(core_decisions.outcome(args.id, kind=args.kind, note=args.note, evidence=args.evidence,
                                     human_confirmed=args.human_confirmed))
        return
    if args.domain == "action":
        if args.action == "list":
            p(core_actions.list_actions(status=args.status, sort=args.sort, limit=args.limit))
        elif args.action == "propose":
            p(core_actions.propose(**pick(s.json_file(args.file), ACTION_FIELDS, "action")))
        elif args.action == "complete":
            p(core_actions.complete(args.id, human_confirmed=args.human_confirmed, evidence=args.evidence))
        elif args.action == "block":
            p(core_actions.block(args.id, args.reason))
        else:
            p(core_actions.unblock(args.id))
        return
    if args.domain == "signal":
        if args.action == "add":
            p(core_signals.add(**pick(s.json_file(args.file), SIGNAL_FIELDS, "signal")))
        elif args.action == "list":
            p(core_signals.list_feedback(target_type=args.target_type, target_id=args.target_id,
                                         limit=args.limit))
        else:
            p(core_signals.promote(args.id, subject=args.subject, predicate=args.predicate,
                                   assertion_type=args.assertion_type, confidence=args.confidence,
                                   value=args.value, human_confirmed=args.human_confirmed))
        return
    if args.domain == "reflection":
        if args.action == "weekly":
            p(core_reflection.weekly(args.days))
        elif args.action == "list":
            p(core_reflection.list_runs())
        else:
            p(core_reflection.decide(args.id, status=args.status, note=args.note, accepted=args.accept))
        return
    if args.domain == "twin":
        if args.action == "status":
            p(core_twin.status())
        elif args.action == "sync-legacy":
            p(core_twin.sync_legacy())
        else:
            p(core_twin.export_bundle())
        return
    if args.domain == "profile":
        p({"id": s.save_profile(s.json_file(args.file))} if args.action == "save" else s.get_profile()); return
    if args.domain == "experience":
        if args.action == "add":
            p({"id": experience_library.create(s.json_file(args.file))})
        elif args.action == "skills":
            p(experience_library.skills(query=args.query, budget=args.budget, offset=args.offset))
        elif args.action in ("list", "index"):
            p(experience_library.index(query=args.query, ids=_ids(args.ids), budget=args.budget, offset=args.offset))
        elif args.action == "detail":
            p(experience_library.detail(ids=_ids(args.ids), query=args.query, sections=_sections(args.sections),
                                        include_inactive=args.include_inactive))
        elif args.action == "show":
            p(experience_library.get(args.id, version=args.version, sections=_sections(args.sections),
                                     include_inactive=args.include_inactive))
        elif args.action == "revise":
            p(experience_library.revise(args.id, s.json_file(args.file), reason=args.reason,
                                        expected_version=args.expected_version))
        elif args.action == "exclude":
            p(experience_library.exclude(args.id, reason=args.reason))
        elif args.action == "supersede":
            p(experience_library.supersede(args.id, args.replacement_id, reason=args.reason))
        else:
            p(experience_library.history(args.id))
        return
    if args.domain == "onboarding":
        if args.action == "status": p(onboarding.status())
        elif args.action == "missing": p(onboarding.missing_prompts(before_search=args.before_search))
        elif args.action == "preferences":
            p(onboarding.update_preferences(**pick(s.json_file(args.file), ("companies", "roles", "constraints", "intent"), "preferences")))
        elif args.action == "prompt": p(onboarding.mark_prompt(args.field, args.state))
        elif args.action == "channel-intent": p(onboarding.set_channel_preference(args.provider, args.preference))
        elif args.action == "channel-state":
            p(onboarding.set_channel_connection(args.provider, args.state, detail=args.detail,
                                                validation_receipt=s.json_file(args.receipt) if args.receipt else None))
        elif args.action == "topic": p(onboarding.set_topic(args.title, next_action=args.next_action, blocker=args.blocker))
        elif args.action == "pause": p(onboarding.pause_topic(reason=args.reason))
        else: p(onboarding.resume_topic(args.id))
        return
    if args.domain == "search-run":
        if args.action == "start":
            p(search_runs.create_run(**pick(s.json_file(args.file), ("scope", "planned_channels", "output_dir"), "search run")))
        elif args.action == "record":
            fields = ("provider", "status", "attempted", "reason", "coverage", "counts", "next_action", "source_url", "observed_at")
            p(search_runs.record_channel(args.id, **pick(s.json_file(args.file), fields, "channel receipt")))
        elif args.action == "candidates": p(search_runs.add_candidates(args.id, s.json_file(args.file)))
        elif args.action == "finish":
            values = pick(s.json_file(args.file), ("counts", "coverage", "next_action"), "search completion") if args.file else {}
            p(search_runs.finish_run(args.id, **values))
        elif args.action == "show": p(search_runs.show(args.id))
        else: p(search_runs.list_runs(args.limit))
        return
    if args.domain == "jobs":
        if args.action == "channels": p(discovery.channels())
        elif args.action == "search":
            p(search_runs.execute_search(args.provider, {"query": args.query, "location": args.location, "limit": args.limit},
                                         lambda: discovery.search_local(args.query, args.location, args.provider, args.limit, args.refresh)))
        elif args.action == "search-plan": p(discovery.search_plan(args.query, args.location, args.providers.split(",") if args.providers else None))
        elif args.action == "browser-plan": p(discovery.browser_plan(args.query, args.location, args.provider, args.limit))
        elif args.action == "browser-record":
            data = s.json_file(args.file)
            scope = {key: data[key] for key in ("query", "location", "limit") if key in data}
            p(search_runs.execute_search(data.get("provider", "browser"), scope,
                                         lambda: discovery.record_browser_observation(data)))
        elif args.action == "browser-runs": p(discovery.browser_runs(args.limit))
        elif args.action == "shortlist": p(discovery.shortlist(args.query, args.location, args.exclude, args.limit))
        elif args.action == "import":
            if args.json:
                p(sources.import_records(s.json_file(args.json)))
            else:
                import csv
                with open(args.csv, encoding="utf-8-sig", newline="") as handle:
                    records = list(csv.DictReader(handle))
                p(sources.import_records([{k: v for k, v in r.items() if v not in (None, "")} for r in records]))
        elif args.action == "sync":
            p(search_runs.execute_search(args.provider, {"board": args.board, "company": args.company, "limit": args.limit},
                                         lambda: sources.sync_jobs(args.provider, args.board, args.company, args.limit)))
        elif args.action == "card": p(tracking.job_card(args.id))
        elif args.action == "route": p(discovery.channel_route(args.provider, args.query, args.location))
        elif args.action == "group":
            if args.rebuild:
                tracking.regroup()
            p(tracking.groups(args.limit))
        elif args.action == "snapshots": p(sources.list_snapshots(args.id))
        elif args.action == "show":
            job = s.get_job(args.id)
            p({**job, "freshness": sources.freshness(job)})
        else:
            with connect() as db:
                p([{"id": r["id"], "source": deserialize(r["data"])["source"], "title": r["title"], "company": r["company"], "url": r["url"]} for r in db.execute("SELECT * FROM jobs ORDER BY id DESC")])
        return
    if args.domain == "leads":
        if args.action == "import": p(discovery.import_leads(s.json_file(args.file)))
        elif args.action == "list": p(discovery.list_leads(args.provider, args.limit))
        elif args.action == "fetch":
            p(search_runs.execute_search("lead_detail", {"filters": {"lead_id": args.id}},
                                         lambda: discovery.fetch_lead(args.id, args.refresh)))
        else: p(discovery.promote_lead(args.id, s.json_file(args.file)))
        return
    if args.domain == "resume":
        if args.action == "build":
            ids = [int(x.strip()) for x in args.experience_ids.split(",") if x.strip()]
            p(s.build_resume(args.job_id, ids, args.headline))
        elif args.action == "revise": p(feedback.revise_resume(s.json_file(args.file)))
        elif args.action == "history": p(feedback.version_history(args.id))
        elif args.action == "confirm": p(feedback.confirm_revision(args.id, human_confirmed=args.human_confirmed))
        else: p(s.list_objects("resumes"))
        return
    if args.domain == "review":
        if args.action == "packet":
            packet = assessment.review_packet(args.resume_id)
            p(compact_packet(packet) if args.compact else packet)
        elif args.action == "save": p(assessment.save_review(s.json_file(args.file)))
        else: p(assessment.list_reviews(args.resume_id))
        return
    if args.domain == "feedback":
        if args.action == "save": p(feedback.save_feedback(s.json_file(args.file)))
        elif args.action == "plan": p(feedback.feedback_plan(args.job_id))
        elif args.action == "resolve": p(feedback.resolve_feedback(args.id, args.review_id, args.note))
        else: p(feedback.list_feedback(args.job_id))
        return
    if args.domain == "analysis":
        if args.action == "draft":
            p(assessment.draft_analysis(args.job_id)); return
        if args.action == "packet":
            packet = assessment.analysis_packet(args.job_id)
            p(compact_packet(packet) if args.compact else packet); return
        if args.action == "save":
            data = s.json_file(args.file)
            if isinstance(data, dict) and "requirements" in data:
                p({"id": assessment.save_analysis(data)}); return
    if args.domain == "application":
        if args.action == "prepare":
            hints = s.repeat_application_hints(args.job_id)
            aid = s.prepare_application(args.job_id, args.resume_id, args.channel, args.apply_url)
            p({"id": aid, "status": "READY_FOR_USER", "externally_submitted": False,
               "repeat_application_hints": hints,
               "next_command": f"application record --id {aid} --status SUBMITTED --human-confirmed"})
        elif args.action == "record":
            p({"status": s.update_application(args.id, args.status, human_confirmed=args.human_confirmed,
                                              note=args.note, external_reference=args.external_reference,
                                              channel=args.channel),
               "next_command": f"application event --id {args.id} --kind interview --label \"一面\" --scheduled-at <ISO时间>"})
        elif args.action == "channel": p(s.set_application_channel(args.id, args.channel, args.apply_url))
        elif args.action == "event":
            p({"id": tracking.log_event(args.id, args.kind, args.label,
                                        scheduled_at=args.scheduled_at, occurred_at=args.occurred_at)})
        elif args.action == "timeline": p(tracking.list_events(args.id))
        elif args.action == "agenda": p(tracking.agenda(args.days))
        else: p(s.list_objects("applications"))
        return
    if args.domain == "official":
        if args.action == "plan":
            p(official.plan(args.company, args.query, args.url))
        else:
            def read_official():
                record = official.fetch(args.url, args.company, args.refresh)
                return record if args.record_only else official.import_official(record)
            p(search_runs.execute_search("official", {"source_url": args.url, "company": args.company}, read_official))
        return
    mapping = {
        "experience": ("experiences", ["event", "actions", "outcomes", "evidence", "approved_for_resume"]),
        "career": ("career_directions", ["title", "rationale", "supporting_experience_ids", "gaps", "validation_status"]),
        "analysis": ("job_analyses", ["job_id", "strengths", "gaps", "unknowns", "recommendation", "confidence"]),
        "learning": ("learning_plans", ["target_role", "gaps", "milestones", "review_date"]),
        "interview": ("interviews", ["job_id", "questions", "practice", "next_actions"]),
    }
    table, required = mapping[args.domain]
    if args.action == "list":
        p([{**{key: val for key, val in row.items() if key not in {"data"}}, "data": deserialize(row["data"])} for row in s.list_objects(table)])
    else:
        p({"id": s.add_object(table, s.json_file(args.file), required)})


def compact_packet(packet):
    """Drop redundant transport data; retain the complete JD, resume and evidence."""
    result = dict(packet)
    if "job" in packet:
        # Keep unknown provider fields: they may contain deadlines or hard gates.
        redundant = {"raw_html", "description_raw_html"}
        result["job"] = {k: v for k, v in packet["job"].items() if k not in redundant}
    if "prior_reviews" in packet:
        result["prior_reviews"] = [{**{k: r[k] for k in ("id", "resume_id", "grade", "status", "reasons", "created_at") if k in r},
                                    "review": r.get("review", {})}
                                   for r in packet["prior_reviews"]]
        result["history_detail_command"] = "review list --resume-id <id>"
    result["compact"] = True
    return result


def main():
    # JSON output remains UTF-8 when redirected under a Windows legacy code page.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        run()
    except (ValueError, OSError, json.JSONDecodeError) as e:
        error = {"error": str(e)}
        if hasattr(e, "search_run_id"):
            error.update(search_run_id=e.search_run_id, report_path=e.report_path)
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
