---
name: resume-builder
description: Build, revise and confirm job-specific Markdown resume versions from approved experience, preserving claim provenance and independent review. Use for resume content and versions, not sending applications or inventing qualifications.
---

# Evidence-locked resume builder

Use real coursework, projects, campus roles, volunteering and internships at their actual scope. Distinguish personal ownership from group results; limited work history calls for better evidence or learning tasks, never fabricated employment or seniority.

1. Read the target job, latest analysis and relevant approved experiences. Select facts the user personally owns and has approved.
2. Run `python -m careeros resume build --job-id <id> --experience-ids 1,2 --headline "<role>"`; record ID, path and SHA-256.
3. For revision, load [references/resume-review.md](references/resume-review.md), then run `python -m careeros resume revise --file <json>`. Every bullet must map to exact source text from the same experience.
4. Show the complete rewritten claims if the version is `pending`. Only after direct factual confirmation run `python -m careeros resume confirm --id <id> --human-confirmed`; the Agent cannot supply that confirmation.
5. Inspect `resume history --id <id>`. Use `$job-analysis` for independent review of this exact version before calling it ready; a revision never inherits its base grade. Review procedure and stop conditions live in [the analysis contract](../job-analysis/references/analysis-contract.md).
6. For Word/PDF delivery, read `../document-export/SKILL.md` and export the registered, approved resume ID. Preserve the saved Markdown; do not retype an untracked replacement.

Report `DRAFT — not submitted`, exact version IDs, paths, evidence IDs, pending confirmations and risks. External sending requires explicit authorization for the named destination.

## Career Twin Core contract

- A `skill_hypothesis` is not a resume source unless user-confirmed and linked to an experience; nothing in the Twin substitutes for factual wording approval.
- Register follow-up preparation using `action propose` (`action_type:prepare`, with `suggestion_reason`). Report version and SHA-256.
- Use the [decision contract](../../../docs/DECISIONS.md) only when recommending or reassessing the preparation/target choice. Shared rules are in `AGENTS.md`.
