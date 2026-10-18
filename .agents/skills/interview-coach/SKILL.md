---
name: interview-coach
description: Build a dated public-source company dossier, run role-relevant seven-stage interview practice, and save actual mock feedback separately from hypotheses. Use for interview preparation and rehearsal, not claims of employer access.
---

# Interview coach

1. Read `jobs show --id <id>`, the exact resume/version, structured analysis, review and open feedback plan.
2. Research public company sources as needed. Actually open them; preserve exact URL, retrieval date and fact, with inference in a separate field. Do not upload personal data or imply access to employer systems.
3. Derive questions from JD requirements and red findings across HR, hiring manager, technical, pressure, background and competition. Pressure questions stay job relevant and respectful; no protected-characteristic or discriminatory questions. Competition is hypothetical, not invented applicant intelligence.
4. Ask one question at a time. Probe ownership, evidence, tradeoffs, failure and reflection; never script fabricated achievements. Save only the user's actual answer.
5. Give finding-to-action feedback as wording, practice, evidence or retarget. Store the session with [references/interview-contract.md](references/interview-contract.md) and `python -m careeros interview save --file <path>`.
6. If recording feedback, use `kind=mock`; use `actual` only for genuine employer feedback bound to the submitted application/resume, and `hypothesis` for unverified causal explanations.
7. Route new factual achievements to `$career-discovery`, capability work to `$learning-planner`, and resume changes to `$resume-builder` followed by independent review.

Report sources/dates, observed answer evidence, hypotheses, three prioritized actions and any saved IDs. Never promise interview or offer outcomes.

## Career Twin Core contract
- Read `pipeline show --job-id <id>` and the latest `application_events` first. Without a submitted application, treat the session as `mock`, not as employer contact.
- After a session, record the user's own reactions with `signal add`; capability revisions go through `belief propose` with `links` to the experience or interview that supports them, then wait for `belief confirm`.
- Schedule the next round as `action propose` (`source_type: interview`, `due_at` = interview time), so it appears in "what next".
- A rejection or a poor interview never proves low ability on its own; the cause may be competition or a hiring freeze.
