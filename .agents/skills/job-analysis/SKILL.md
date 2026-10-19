---
name: job-analysis
description: Decompose a saved JD, map requirements to approved experience, build a sourced company dossier and run a seven-stage simulated hiring review. Use for specific job fit and resume assessment, not vacancy discovery.
---

# Job analysis and hiring review

1. Obtain `python -m careeros analysis packet --job-id <id> --compact`. `analysis draft` is only an all-unknown line template. Read the complete JD and approved evidence, then split/combine semantic requirements into `hard_gate|core|preferred`.
2. Preserve an exact JD substring for each requirement; use `met` only with direct approved experience IDs, otherwise `gap|unknown`. Missing evidence is different from demonstrated absence.
3. Research public company sources when needed; retain URL, retrieval date, fact and separate inference. Vacancy availability evidence must refer to this exact posting: company news cannot prove it is live. Refresh a closed source before reconsideration.
4. Load [references/analysis-contract.md](references/analysis-contract.md) to save analysis and conduct red/blue review. Set coverage confirmed only after checking the full JD. Save with `python -m careeros analysis save --file <json>`, then inspect a fresh packet.
5. Obtain `python -m careeros review packet --resume-id <id> --compact`; assess the exact frozen inputs, save the completed review, and report CLI-computed grade/status with remaining evidence gaps. After revision, use a new independent review; stop after two rounds without new evidence.

Use deterministic commands for validation, grading and versions. Keep bulk output on disk via global `--output <path>` before the domain. Grades simulate recruiting risk; they never predict or guarantee offers.

## Career Twin Core contract

- Keep confirmed/document-verified capabilities separate from inference. Only approved experience can support `met`.
- Update `pipeline` to `evaluating|shortlisted|parked|discarded` with the reason. Turn missing evidence into `action propose` (`source_type:job`) with `suggestion_reason`.
- Cite confirmed hard-constraint assertion IDs and park/discard a conflicting job. Record recommendations and changed-evidence reassessment through the [decision contract](../../../docs/DECISIONS.md); shared rules are in `AGENTS.md`.
