---
name: resume-builder
description: Translate real career histories into complete, focused Markdown resumes, preserving sources and versions while delivering a full draft for user edits. Use for resume content, not external submission or invented qualifications.
---

# Resume builder

Turn what the user actually did into language a new role understands. Work, business, projects, education and informal responsibilities can carry transferable value. Clear self-report is sufficient; write confidently within it. Never invent duties, titles, tools, dates, metrics or personal ownership.

For an existing resume, use `resume import`, `resume input`, `resume align`, then `resume diagnose`; check extraction against the original. Deliver a full draft with `resume rewrite`, using `--base-resume-id` for later versions. Imported text does not update the experience library. See [rewrite contract](references/resume-review.md).

1. Read `context brief`, profile and every experience-index page; fetch relevant details in bounded batches. Final resumes target a saved job and full JD. Use `resume workflow --job-id <id>`, then `resume tailor-packet --job-id <id>`, following `next_offset` until complete. Understand its purpose and 2–4 core deliverables. Without a target, help choose one; any general draft is only an experience baseline.
2. Include known contact, education and major career stages. Link real actions to target work, expand relevant and transferable experience, and briefly retain other stages. Group small events only when time and ownership remain clear. Honour exclusions and real gaps; invent neither dates nor private explanations.
3. Respect personal template preferences without making them universal. Order sections for this history; omit empty sections and preserve known education.
4. Read [resume-review](references/resume-review.md); save through CLI and report the receipt ID/path. Keep sources internally. Write a full grounded draft without per-experience approval or exact quotes. Ask only about material uncertainty; do not freeze the whole draft.
5. Repair omissions, chronology, scope, repetition and readability. Deliver the complete draft for user edits, then run `resume workflow --job-id <id> --resume-id <id>`. Continue through job-analysis rating and interview-coach practice for this exact version by default; save actual user answers one at a time. Do not invent a completed practice session. Respect a user's explicit deferral and keep that step pending.
   For saved jobs, check the full JD and role focus. `resume market-report` offers sourced candidate trends, never personal facts. Balance skills and experience; use STAR/C-STAR only where facts support it.
6. For Word/PDF, use [document-export](../document-export/SKILL.md). Inspect each rendered page for density, detached headings, links and breaks. Adjust content before shrinking type. Preserve versions; dry-run cleanup first.

Report local/unsubmitted status, version and paths briefly; keep source IDs, ratings and internal paths out of candidate-facing content. Drafting/export never authorizes upload or submission to a destination.

## Career Twin Core contract

- Model guesses remain inferred, not user facts. Faithful professional synthesis of stated actions needs no separate factual approval.
- Register useful preparation/learning follow-ups with `action propose` and `suggestion_reason`; market validation and learning support the new direction without blocking the current resume.
- Use the [decision contract](../../../docs/DECISIONS.md) for actual target/preparation recommendations. Shared privacy and external-action rules remain in `AGENTS.md`.
