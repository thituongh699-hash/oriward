---
name: application-assistant
description: Assemble local application packets, bind the exact resume version, and record user-confirmed submission and outcomes. Use for preparation and tracking; never submit or contact recruiters autonomously.
---

# Application assistant

1. Inspect the job, `resume history` and latest review. Verify the job/resume relationship, factual approval and remaining risks.
2. Assemble the official application URL, exact resume ID/hash, approved answers and unresolved questions locally. Run `python -m careeros application prepare --job-id <id> --resume-id <id>`; it creates `READY_FOR_USER` only.
3. Give manual submission steps. Do not log in, upload, final-click, contact a recruiter or bypass CAPTCHA.
4. Only after the user directly confirms actual submission of this exact version, run `python -m careeros application record --id <id> --status SUBMITTED --human-confirmed --note "User confirmed actual submission"`. Never infer submission from a prepared packet.
5. Record later supported states from evidence. Route feedback through `feedback save`; actual feedback binds the application and exact sent resume. Saving feedback changes neither status nor grade automatically.

Report IDs, exact document version, status, evidence and pending user action. Keep ready, submitted and employer acknowledged distinct.

## Career Twin Core contract

- Read `pipeline show --job-id <id>` for stage, verified event, next action, deadline and blocker.
- Update related actions from the observed state (`action propose` or `action complete --evidence ...`); record user reactions with `signal add`.
- Read the [decision contract](../../../docs/DECISIONS.md) when recommending or reassessing an application choice. Shared rules are in `AGENTS.md`; no state write authorizes external submission.
