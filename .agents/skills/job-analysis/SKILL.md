---
name: job-analysis
description: Understand a saved role's mission and core deliverables, map current evidence and run a simulated hiring review. Use for specific JD fit and resume assessment, not vacancy discovery.
---

# Job analysis and hiring review

When analysis is requested, explain the role's purpose and 2–4 deliverables before rating. Reuse this context downstream; review is optional and never a writing/export prerequisite. Respect deferral without claiming completion.

1. Obtain `analysis packet --job-id <id> --compact`. Read the primary JD first; references can enrich interpretation, but its purpose, 2–4 deliverables and gates control this analysis. Then read the full experience index and relevant details in batches. Select evidence semantically, never by similarity/keywords. `analysis draft` is all-unknown.
2. Preserve primary-JD quotes. Internally map requirements to evidence, factual status and truthful wording; no rigid per-requirement prose. Mark `met` only with current sourced experience, self-reports/confirmed assertions or document-verified sources. Split compound tasks; missing evidence is not absence.
3. When needed, research public company sources; retain URL/date and separate fact from inference. Availability must refer to this posting. Refresh closed sources.
4. Load [references/analysis-contract.md](references/analysis-contract.md) to save analysis and conduct red/blue review. Set coverage confirmed only after checking the full JD. Save with `python -m oriward analysis save --file <json>`, then inspect a fresh packet.
5. If review is requested after drafting, use `review packet --resume-id <id> --compact` on the exact version; explain fit, strengths, gates, questions and interview themes. Continue with interview-coach using the same IDs. A–D is supplementary; do not inflate `met`. Re-review revisions; stop after two rounds without new evidence.

Use deterministic commands for validation, grading and versions. Keep bulk output on disk via global `--output <path>` before the domain. Grades simulate recruiting risk; they never predict or guarantee offers.

## Career Twin Core contract

- Keep confirmed/document-verified evidence separate from inference. Hiring motives from public business context remain hypotheses unless directly sourced. Reuse `role_focus` deliverables, resume themes and interview themes downstream instead of repeating the whole experience interview.
- Update `pipeline` to `evaluating|shortlisted|parked|discarded` with the reason. Propose only useful targeted follow-ups with `action propose` (`source_type:job`) and `suggestion_reason`; do not create a whole-library evidence/approval queue.
- Cite confirmed hard-constraint assertion IDs and park/discard a conflicting job. Record recommendations and changed-evidence reassessment through the [decision contract](../../../docs/DECISIONS.md); shared rules are in `AGENTS.md`.
