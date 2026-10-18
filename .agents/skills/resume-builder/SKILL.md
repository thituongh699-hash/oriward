---
name: resume-builder
description: Build, revise, confirm and independently re-review job-specific Markdown resumes using approved, source-linked experience records. Use for evidence-locked resume versions, not sending applications or inventing claims.
---

# Evidence-locked resume builder

For students and recent graduates, use honest coursework, projects, campus roles, volunteering and internships with their actual scope. Distinguish personal ownership from group results. Limited work history is a reason to choose better evidence and identify learning tasks, never to invent employment or inflate a student role into professional seniority.

1. Read the target job, latest structured analysis and approved experiences. Select only facts the user personally owns and has approved.
2. Build a base with `python -m careeros resume build --job-id <id> --experience-ids 1,2 --headline "<role>"`. Record its ID, path and SHA-256.
3. Run `python -m careeros review packet --resume-id <id> --compact` and follow `$job-analysis` for a seven-stage red/blue review before treating the draft as ready. Use local commands for rendering, hashes, version comparison and rule-based grading; reserve model work for evidence interpretation and defensible wording. Global `--output <path>` stores bulk results locally without expanding them into context.
4. To revise, create JSON that names `base_resume_id`, optional review/feedback IDs, reason, sections, and for every bullet the exact same-experience `source_texts`. See [references/resume-review.md](references/resume-review.md). Run `python -m careeros resume revise --file <json>`.
5. If the new version is `pending`, show the full rewritten claims to the user. Only after direct factual confirmation run `python -m careeros resume confirm --id <id> --human-confirmed`. Agent cannot infer or provide that confirmation.
6. Inspect `python -m careeros resume history --id <id>`, then obtain a new review packet and conduct an independent review. A revision never inherits its base grade.
7. Stop after two red/blue rounds without new evidence. Use practice/evidence/retarget for substantive gaps; wording cannot manufacture qualification.
8. When the user requests editable Word or PDF delivery, read `../document-export/SKILL.md` and export the registered resume ID after factual approval. Do not retype the resume into a new untracked document or replace the saved Markdown source.

Output `DRAFT — not submitted`, exact resume/version IDs, paths, evidence IDs, pending confirmations and remaining risks. Never upload or send a resume without explicit authorization for the named destination.

## Career Twin Core contract
- Only approved experiences may be used. A `skill_hypothesis` is not a resume source unless it is `user_confirmed` and links to an experience.
- Register the follow-up work with `action propose` (`action_type: prepare`), so the resume step is visible in "what next".
- Rewritten wording still requires `resume confirm --id <id> --human-confirmed`; nothing in the Twin counts as factual confirmation.
- Report resume ID, version, SHA-256 and any wording still awaiting the user. Shared rules are in `AGENTS.md`.
