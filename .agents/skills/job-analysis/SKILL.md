---
name: job-analysis
description: Understand a saved role's mission and core deliverables, map current evidence and run a simulated hiring review. Use for specific JD fit and resume assessment, not vacancy discovery.
---

# Job analysis and hiring review

1. Obtain `python -m oriward analysis packet --job-id <id> --compact`. The default packet contains a bounded experience index; expand only relevant experience IDs/sections. `analysis draft` is an all-unknown template. Understand why the role exists, whom it supports and its 2–4 most useful deliverables before classifying `hard_gate|core|preferred` requirements.
2. Preserve exact JD quotes. Use current typed evidence for `met`: approved experience versions, clear self-reported or confirmed factual/constraint assertions, or document-verified source assertions. Education and attendance do not need fabricated work experience. Split compound tasks into atomic components; travel arrangements do not establish attendance management. Missing evidence is different from demonstrated absence.
3. Research public company sources when needed; retain URL, retrieval date, fact and separate inference. Vacancy availability evidence must refer to this exact posting: company news cannot prove it is live. Refresh a closed source before reconsideration.
4. Load [references/analysis-contract.md](references/analysis-contract.md) to save analysis and conduct red/blue review. Set coverage confirmed only after checking the full JD. Save with `python -m oriward analysis save --file <json>`, then inspect a fresh packet.
5. Obtain `python -m oriward review packet --resume-id <id> --compact`; assess the exact frozen inputs, save the completed review, and explain whether the role is worth trying, strengths, real gates, next questions, resume themes and interview cases. A–D is supplementary; do not make every minor task `met` to chase a grade. Unknown eligibility needs checking; hypothetical rivals are not objective downgrade evidence. After revision obtain a fresh review; disclose when the same agent performs multiple stages. Stop after two rounds without new evidence.

Use deterministic commands for validation, grading and versions. Keep bulk output on disk via global `--output <path>` before the domain. Grades simulate recruiting risk; they never predict or guarantee offers.

## Career Twin Core contract

- Keep confirmed/document-verified evidence separate from inference. Hiring motives from public business context remain hypotheses unless directly sourced. Reuse `role_focus` deliverables, resume themes and interview themes downstream instead of repeating the whole experience interview.
- Update `pipeline` to `evaluating|shortlisted|parked|discarded` with the reason. Turn missing evidence into `action propose` (`source_type:job`) with `suggestion_reason`.
- Cite confirmed hard-constraint assertion IDs and park/discard a conflicting job. Record recommendations and changed-evidence reassessment through the [decision contract](../../../docs/DECISIONS.md); shared rules are in `AGENTS.md`.
