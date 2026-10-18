---
name: application-assistant
description: Assemble local application packets, bind the exact resume version, and record user-confirmed submission and outcomes. Use for application preparation and tracking; never log in, upload, contact recruiters or submit autonomously.
---

# Application assistant

1. Inspect `jobs show --id <job-id>`, `resume history --id <resume-id>` and the latest `review list --resume-id <resume-id>`. Confirm job/resume relationship, factual approval and remaining risks.
2. Assemble a local packet with official application URL, exact resume ID/hash, user-approved answers and unresolved questions. Do not send it to a third party.
3. Run `python -m careeros application prepare --job-id <id> --resume-id <id>`; this creates `READY_FOR_USER` only.
4. Give the user manual submission steps. Do not log in, upload, final-click, email/message a recruiter or bypass CAPTCHA.
5. Only after the user directly confirms that the exact version was actually submitted run `python -m careeros application record --id <id> --status SUBMITTED --human-confirmed --note "User confirmed actual submission"`.
6. Record later allowed states with `application record`; never infer a state from a prepared packet or draft.
7. Route observed recruiting feedback through `feedback save`. Actual feedback must bind this application and exact sent resume; saving it never changes application status or grade.

Report local IDs, current status, exact document version, outstanding user action and evidence. Keep “ready”, “submitted” and “employer acknowledged” distinct.

## Career Twin Core contract
- Open with `pipeline show --job-id <id>`; use its stage, last verified event, next action, deadline, blocker and source.
- Submission stays human: only after the user directly reports it, run `application record --id <id> --status SUBMITTED --human-confirmed`.
- Turn each state change into an action (`action propose` / `action complete --evidence ...`), and record negative reactions with `signal add`. Shared rules are in `AGENTS.md`.
