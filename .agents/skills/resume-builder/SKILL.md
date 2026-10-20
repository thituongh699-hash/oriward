---
name: resume-builder
description: Build, revise and confirm job-specific Markdown resume versions from approved experience, preserving claim provenance and independent review. Use for resume content and versions, not sending applications or inventing qualifications.
---

# Truthful resume builder

Use real coursework, projects, campus roles, volunteering and internships at their actual scope. Distinguish personal ownership from group results; limited work history calls for better evidence or learning tasks, never fabricated employment or seniority.

1. Start with `resume tailor-packet --job-id <id>`: read the bounded experience index, target company/JD and latest analysis, then selected experience details. Identify the role purpose and 2–4 core deliverables. Select facts for their relevance to these deliverables, including transferable coursework and informal projects. Never simply paste the library into every resume.
2. Rewrite the headline, summary, experience emphasis/order and bullets for this company and role. Explain the selection and wording choices. Use `python -m oriward resume compose --job-id <id> --file <json>` to save the final tailored content directly; no raw intermediate resume is required. `resume build` remains a compatibility fallback. Record the returned ID and path.
3. Load [references/resume-review.md](references/resume-review.md) for composition and revision input. Every claim maps to exact source quotations; final wording need not repeat them. Job-specific phrasing stays in the resume, not in universal experience facts. Excluded or stale experiences cannot be sources.
4. Strengthen professional action wording, ordering and transferable relevance while preserving scope. Declare sourced wording-only changes explicitly; they inherit factual approval. List added duties, tools, numbers, causal results or dates separately and show pending facts together. Only after direct factual confirmation run `python -m oriward resume confirm --id <id> --human-confirmed`; never manufacture that confirmation. Ask the user to inspect the whole final draft before use.
5. Inspect `resume history --id <id>`. Use `$job-analysis` for independent review of this exact version before calling it ready; a revision never inherits its base grade. Review procedure and stop conditions live in [the analysis contract](../job-analysis/references/analysis-contract.md).
6. For Word/PDF delivery, read `../document-export/SKILL.md` and export the approved resume ID using its templates. No resume-file hash confirmation is required. Each job retains its current Markdown plus three historical files; older bodies may be pruned while source/version metadata remains queryable. Use cleanup dry-run before applying maintenance to existing files.

Report `DRAFT — not submitted`, exact version IDs, paths, evidence IDs, pending confirmations and risks. External sending requires explicit authorization for the named destination.

## Career Twin Core contract

- A `skill_hypothesis` is not a resume source unless user-confirmed and linked to an experience; nothing in the Twin substitutes for factual wording approval.
- Register follow-up preparation using `action propose` (`action_type:prepare`, with `suggestion_reason`). Report version and pending facts.
- Use the [decision contract](../../../docs/DECISIONS.md) only when recommending or reassessing the preparation/target choice. Shared rules are in `AGENTS.md`.
