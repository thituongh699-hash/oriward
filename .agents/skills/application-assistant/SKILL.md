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
- Open with `python -m careeros pipeline show --job-id <id>` and use its six slots: current stage, last verified event, next action, deadline, blocking issue, source.
- Submission stays human: only after the user directly reports it, run `application record --id <id> --status SUBMITTED --human-confirmed`. The event stores `from_status`, `to_status` and `human_confirmed`.
- Every state change gets an action: an interview invitation becomes `action propose --file <json>` (`source_type: interview`, `due_at` = interview time); finishing a step becomes `action complete --id <id>`.
- Record negative reactions to a job with `signal add`, never as a statement about the user's ability.
