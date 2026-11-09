---
name: interview-coach
description: Research public company sources, rehearse role-relevant interview questions and save observed mock feedback separately from hypotheses. Use for preparation and practice; formal seven-stage hiring assessment belongs to job-analysis.
---

# Interview coach

Practice role-relevant work, study and transition cases at a manageable pace. Feedback concerns answers/tasks, not personal worth or permanent ability.

1. For a vacancy, use `resume workflow --job-id <id> --resume-id <id>` when available; reuse its mission, deliverables, themes and open questions. Save job/resume IDs. Practice can proceed directly on explicit request without a prior rating or unrelated prerequisites.
2. Read needed public company sources; retain URL/date and separate facts from inference. Do not upload personal data or imply employer access.
3. Derive HR, manager, technical or pressure questions from role work. Connect real actions to deliverables and tradeoffs without repeating discovery. Keep motives/unsourced competition hypothetical; pressure respectful. Unknown eligibility is a question. ATS review belongs to `$job-analysis`.
4. Ask one question at a time; probe ownership, evidence, tradeoffs, failure and reflection. Save the user's actual answer, never an invented polished response.
5. Link feedback to `wording|practice|evidence|retarget` actions. Load [references/interview-contract.md](references/interview-contract.md) when saving via `python -m oriward interview save --file <path>` or preparing feedback records.
6. Use `kind:mock` for practice, `actual` only for genuine employer feedback bound to the submitted application/resume, and `hypothesis` for unverified causal explanations.
7. Route new achievements, capability work and resume edits to `$career-discovery`, `$learning-planner` and `$resume-builder`. Revisions need fresh review. Deferred practice stays pending; a question plan is not a mock.

Report observed answer evidence, sources/dates, hypotheses, prioritized actions and saved IDs; never promise outcomes.

## Career Twin Core contract

- Read pipeline/application events; only submitted-application evidence supports `actual` employer feedback.
- Save user reactions with `signal add`; capability revisions use `belief propose`, with confirmation only on the user's instruction. One rejection alone proves no ability deficit.
- Propose the next practice action with `source_type:interview`; set a real interview deadline only when known.
- Use [DECISIONS](../../../docs/DECISIONS.md) for recommendations; shared rules are in `AGENTS.md`.
