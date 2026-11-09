---
name: resume-builder
description: Translate real career histories into complete, focused Markdown resumes, preserving sources and versions while delivering a full draft for user edits. Use for resume content, not external submission or invented qualifications.
---

# Resume builder

Translate real work, business, study, projects and informal responsibilities into relevant value. Clear self-report suffices; write confidently within its limits.

For an existing resume, import/input are optional source aids. Check extraction against the original; imported text does not update the experience library. Diagnose only as optional text lint. Deliver a complete `resume rewrite` or `resume compose` draft. See [rewrite contract](references/resume-review.md).

1. Reuse user requirements and saved career-mapping/job-search/job-analysis context. Read the primary JD first when present: its purpose, 2–4 deliverables and gates control the draft. Comparable JDs are optional references that enrich interpretation and customary work; they never add their employers' gates or silently create primary requirements. Then read the full experience index and selected details in batches. Use `resume tailor-packet --job-id <id> [--reference-job-ids <id> ...]` and `resume compose` with the same target flags and `--file <json>`. Without a primary job, use one or more `--reference-job-ids` for a direction draft and optional `--target-title`; choose a real job only when binding job-specific review, interview or application records.
2. Include known contact, education and career stages. Select evidence semantically, never by similarity/keywords. Connect actions to deliverables, expand relevant work and briefly retain other stages. Group events only when time and ownership remain clear. Honour exclusions/gaps; invent no dates or explanations.
3. Respect personal template preferences without making them universal. Order sections for this history; omit empty sections and preserve known education.
4. Follow [resume-review](references/resume-review.md); save through CLI and report receipt/path. Keep sources internal. Write the complete grounded draft without per-experience approval or exact quotes; ask only about material uncertainty.
5. Repair omissions, chronology, scope, repetition and readability. Deliver the full draft for edits. For a primary job, offer exact-version review and interview practice as next steps, not prerequisites to writing or export; save only actual answers and respect deferrals. `resume market-report` offers sourced trends, never personal facts. STAR-C (Situation, Task, Action, Result, Challenge/Contribution) is a compact value-writing lens: clarify true contribution, constraints and outcomes where known. Do not force five-part prose or invent metrics, seniority or impact.
6. For Word/PDF, use [document-export](../document-export/SKILL.md). Inspect each rendered page for density, detached headings, links and breaks. Adjust content before shrinking type. Preserve versions; dry-run cleanup first.

Report local/unsubmitted status, version and paths briefly; keep source IDs, ratings and internal paths out of candidate-facing content. Drafting/export never authorizes upload or submission to a destination.

## Career Twin Core contract

- Model guesses remain inferred, not user facts. Faithful professional synthesis of stated actions needs no separate factual approval.
- Register useful preparation/learning follow-ups with `action propose` and `suggestion_reason`; market validation and learning support the new direction without blocking the current resume.
- Use the [decision contract](../../../docs/DECISIONS.md) for actual target/preparation recommendations. Shared privacy and external-action rules remain in `AGENTS.md`.
