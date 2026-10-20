"""Optional CLI wiring helpers for first-use consent and bounded history intake."""
from __future__ import annotations

from pathlib import Path

from . import history, onboarding


def register(subparsers):
    intake = subparsers.add_parser("intake", help="First-use consent and local history intake")
    actions = intake.add_subparsers(dest="intake_action", required=True)
    x = actions.add_parser("history-consent")
    x.add_argument("--answer", choices=("allow", "later", "decline"), required=True)
    x.add_argument("--scope", action="append", default=[])
    x = actions.add_parser("search-schedule")
    x.add_argument("--answer", choices=("now", "later", "no"), required=True)
    history_cmd = subparsers.add_parser("history", help="Extract relevant chunks from an authorized export")
    history_actions = history_cmd.add_subparsers(dest="history_action", required=True)
    x = history_actions.add_parser("extract")
    x.add_argument("--file", required=True)
    x.add_argument("--query", default="")
    x.add_argument("--max-chars", type=int, default=12000)
    return intake, history_cmd


def dispatch(args):
    if args.domain == "intake":
        if args.intake_action == "history-consent":
            return onboarding.set_history_intake(args.answer, scope=args.scope)
        return onboarding.set_scheduled_search(args.answer)
    if args.domain == "history" and args.history_action == "extract":
        approved = onboarding.continuation().get("history_intake", {})
        path = Path(args.file).expanduser().resolve(strict=True)
        allowed = {str(Path(item).expanduser().resolve()) for item in approved.get("scope", [])}
        if approved.get("answer") != "allow" or str(path) not in allowed:
            raise PermissionError("This exact file was not included in an explicit history-intake consent")
        if isinstance(args.max_chars, bool) or args.max_chars < 1:
            raise ValueError("max_chars must be a positive integer")
        return history.extract_file(path, query=args.query, max_chars=args.max_chars)
    raise ValueError("Unsupported intake command")
