---
name: application-assistant
description: Assemble local application packets, bind the exact resume version, and record user-confirmed submission and outcomes. Use for preparation and tracking; never submit or contact recruiters autonomously.
---

# Application assistant

1. Inspect the exact job, resume history and requested review. Confirm the resume is bound to this vacancy and check source currency/material risks; no formal assessment or per-experience approval is required. A direction draft becomes job-bound here. Explicit preparation can use available context directly.
2. Assemble official URL, exact resume ID, grounded answers and open questions locally. `application prepare --job-id <id> --resume-id <id>` creates `READY_FOR_USER` only; no hash or wording confirmation gates preparation.
3. Give manual submission steps. Do not log in, upload, final-click, contact a recruiter or bypass CAPTCHA.
4. Only after direct confirmation of this version's submission, record `SUBMITTED` with `--human-confirmed`. A prepared packet is not submission.
5. Record later supported states from evidence. Route feedback through `feedback save`; actual feedback binds the application and exact sent resume. Saving feedback changes neither status nor grade automatically.

Report IDs, exact document version, status, evidence and pending user action. Keep ready, submitted and employer acknowledged distinct.

## Career Twin Core contract

- Read `pipeline show --job-id <id>` for stage, verified event, next action, deadline and blocker.
- Update related actions from the observed state (`action propose` or `action complete --evidence ...`); record user reactions with `signal add`.
- Use [DECISIONS](../../../docs/DECISIONS.md) for recommendations; shared rules are in `AGENTS.md`. No state write authorizes submission.
