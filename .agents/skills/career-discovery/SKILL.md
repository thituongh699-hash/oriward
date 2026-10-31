---
name: career-discovery
description: Recover work, business, education, projects and informal responsibilities through natural conversation, preserving user reports separately from inferred directions. Use for experience discovery and translation, not vacancy search.
---

# Career discovery

Help people recover rich or fragmented histories, including career changes and return after time away. Employment, self-employment, caring, volunteering, study and setbacks can matter. Start wherever the user wants; do not require a chronological form or a finished resume. Never invent titles, ownership, dates, tools, metrics or outcomes.

1. Read `context brief`, its current topic and `experience index`; reuse answers and materials. Page the index when recovering the whole career history, then load details in bounded batches. Use `$career-mapping` for directions. Save topic/next step with `onboarding topic`; allow pauses and resumptions without restarting intake.
2. Listen for the setting, actual actions, responsibility and known result. Ask one useful question only when it helps recall or resolves an ambiguity that changes the wording. Missing dates or outcomes can stay open. No attachment, precise KPI, evidence rating or per-experience approval is required.
3. Preserve the original account and distinguish personal work, team output and AI assistance. Identify transferable actions: what was organised, analysed, delivered, negotiated or improved, and for whom. Professional wording and grounded synthesis are normal Agent work; the user need not approve each phrase or supply exact quotations.
4. Save through [references/experience-contract.md](references/experience-contract.md). Clear user self-report is sufficient to save and draft from immediately; it is not independent verification. Do not fabricate confirmation or turn legacy `approved_for_resume=false` into rejection. Model guesses retain their real source and are not user statements.
5. Update the same stable event ID when the user adds detail or corrects it; exclude or supersede on their instruction without another approval. Keep original/version history. Role-specific wording belongs in resume versions, not over the original account. Reconcile changed source links; do not silently copy an inference into factual history.
6. Offer the complete organised account or resume for reading and edits. Report saved IDs/versions and the next useful step briefly; keep provenance in the background. An uncertain number should lead to a draft using known facts, not a blocked experience library.

Read Agent chat/export files only with explicit scoped consent (`allow` with exact files, `later`, or `decline`). `history extract --file` preserves role/time/source and returns bounded chunks; assistant/tool text is context, never proof of user achievements. Ask search or channel intent only when relevant; a deferred answer does not block discovery or enable connectors.

## Career Twin Core contract

- Save capability/direction hypotheses with `belief propose`, `source_type:model_inference` and links to actual experiences. They remain hypotheses; grounded factual wording needs no new confirmation stage.
- Preserve meaningful uncertainty in hedged reports without downgrading ordinary clear self-reports. `belief confirm` records direct user agreement only, never a drafting prerequisite.
- Follow `AGENTS.md`; use the [decision contract](../../../docs/DECISIONS.md) for recommended courses of action, not ordinary experience organisation.
