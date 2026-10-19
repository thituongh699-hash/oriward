---
name: resume-builder
description: Build, revise and confirm job-specific Markdown resume versions from approved experience, preserving claim provenance and independent review. Use for resume content and versions, not sending applications or inventing qualifications.
---

# Truthful resume builder

Use real coursework, projects, campus roles, volunteering and internships at their actual scope. Distinguish personal ownership from group results; limited work history calls for better evidence or learning tasks, never fabricated employment or seniority.

1. Read the target job, latest analysis and bounded experience index, then only relevant detail sections. Use role_focus core deliverables and resume themes to select/order current approved facts. Excluded, superseded or stale assertion-dependent experiences cannot be sources; old resume files remain history and may require review.
2. Run `python -m oriward resume build --job-id <id> --experience-ids 1,2 --headline "<role>"`; record ID, path and SHA-256.
3. For revision, load [references/resume-review.md](references/resume-review.md), then run `python -m oriward resume revise --file <json>`. Every bullet must map to exact source text from the same experience.
4. Strengthen professional action wording, ordering and transferable relevance while preserving scope. Declare sourced wording-only changes explicitly; they inherit factual approval. List added duties, tools, numbers, causal results or dates separately and show pending facts together. Only after direct factual confirmation run `python -m oriward resume confirm --id <id> --human-confirmed`; never manufacture that confirmation. Ask the user to inspect the whole final draft before use.
5. Inspect `resume history --id <id>`. Use `$job-analysis` for independent review of this exact version before calling it ready; a revision never inherits its base grade. Review procedure and stop conditions live in [the analysis contract](../job-analysis/references/analysis-contract.md).
6. For Word/PDF delivery, read `../document-export/SKILL.md` and export the registered, approved resume ID. Preserve the saved Markdown; do not retype an untracked replacement.

Report `DRAFT — not submitted`, exact version IDs, paths, evidence IDs, pending confirmations and risks. External sending requires explicit authorization for the named destination.

## Career Twin Core contract

- A `skill_hypothesis` is not a resume source unless user-confirmed and linked to an experience; nothing in the Twin substitutes for factual wording approval.
- Register follow-up preparation using `action propose` (`action_type:prepare`, with `suggestion_reason`). Report version and SHA-256.
- Use the [decision contract](../../../docs/DECISIONS.md) only when recommending or reassessing the preparation/target choice. Shared rules are in `AGENTS.md`.
