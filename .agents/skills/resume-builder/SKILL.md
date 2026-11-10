---
name: resume-builder
description: Translate real career histories into complete, focused Markdown resumes, preserving sources and versions while delivering a full draft for user edits. Use for resume content, not external submission or invented qualifications.
---

# Resume builder

Use STAR-C to translate real work, business, study, projects and informal responsibilities into relevant value. Clear self-report suffices; write confidently within its limits.

Import/input are optional source aids: check extraction against the original; imported text does not update the experience library. Diagnose is optional lint. Deliver a complete `resume rewrite` or `resume compose` draft under the [composition contract](references/resume-review.md).

1. Reuse user requirements and saved career-mapping/search/analysis context. Read the primary JD first: its purpose, 2–4 deliverables and gates control the draft. Optional comparable JDs enrich interpretation without importing other employers' gates. Use `resume tailor-packet --job-id <id> [--reference-job-ids <id> ...]`, then `resume compose` with matching target flags and `--file <json>`. Without a primary job, use references and optional `--target-title` for a direction draft; bind job-specific review/interview/application to a real job.
2. Read the entire experience index, then selected details. Select evidence and necessary chronology anchors semantically; no automatic mapping, keyword scoring or restoration of unselected experiences. Expanded sections need model-written bullets; explicit `bullets: []` permits a brief title/date anchor. Omit irrelevant school-period jobs lacking continuity value. Group only where dates/ownership remain clear; honour exclusions/gaps and invent no explanations.
3. Present identity/contact and known availability in the header, personal strengths (skills/certificates as subsections) and education. Add work/projects/internships where useful. Categories: `工作经历`, `项目经历`, `实习经历`, `教育经历`; business maps to work, `其他经历` is invalid. Bind academic work to the matching degree with `education_key`. Save template choice: explicit `template` → `profile.resume_preferences.template` → `reference`; inherit a saved `section_order` where applicable.
4. Follow [resume-review](references/resume-review.md); save through CLI and report receipt/path. Keep sources internal. Write the complete grounded draft without per-experience approval or exact quotes; ask only about material uncertainty.
5. Read the actual draft with `resume editorial-packet --resume-id <id>` against JD/evidence. Check relevance, timeline, degree placement, STAR-C, template and factuality; save actual findings via `resume editorial-review --file <json>`. Compose requires this review: use `revise` for unresolved findings; reread corrections before `ready`. Saving is not readiness; never fabricate review. This is separate from hiring ratings and adds no user approval gate. Deliver the full draft for edits. Offer exact-version hiring review/interview practice for a primary job, respecting deferrals and saving only actual answers; these do not block writing/export. STAR-C clarifies true contribution, challenges and known results in natural prose; never invent metrics, seniority or impact. Full schema and examples are in the composition contract.
6. For Word/PDF, use [document-export](../document-export/SKILL.md). Inspect each rendered page for density, detached headings, links and breaks. Adjust content before shrinking type. Preserve versions; dry-run cleanup first.

Report local/unsubmitted status, version and paths; keep internal provenance out of candidate-facing content. Draft/export never authorizes sending.

## Career Twin Core contract

- Model guesses remain inferred, not user facts. Faithful professional synthesis of stated actions needs no separate factual approval.
- Register useful preparation/learning follow-ups with `action propose` and `suggestion_reason`; market validation and learning support the new direction without blocking the current resume.
- Use the [decision contract](../../../docs/DECISIONS.md) for actual target/preparation recommendations. Shared privacy and external-action rules remain in `AGENTS.md`.
