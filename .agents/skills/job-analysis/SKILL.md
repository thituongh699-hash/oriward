---
name: job-analysis
description: Semantically decompose a saved JD, map exact requirements to approved experience evidence, build a sourced company dossier, and run the seven-stage simulated hiring review. Use for a specific job and resume, not vacancy discovery.
---

# Job analysis and red/blue review

## Structured JD analysis

1. Run `python -m careeros analysis draft --job-id <id>` only for an initial all-unknown template. It is line based and does not autonomously understand or score the JD.
2. Run `python -m careeros analysis packet --job-id <id> --compact`. This removes redundant transport metadata, retaining the complete JD and approved evidence. Read those inputs, then combine/split semantic requirements into `hard_gate|core|preferred`. Use local draft/save/validation/grade commands; do not spend model calls reproducing deterministic calculations. Keep bulk intermediate results on disk with the global `--output <path>` option before the domain.
3. Preserve an exact JD substring as each requirement's `quote`. Use `met` only with direct approved experience IDs; otherwise use `gap|unknown`. Separate missing evidence from demonstrated absence.
4. Research the target company through public sources when needed. Actually read each source and save URL, retrieval date, fact, inference and availability. Do not upload personal data to research services.
   Availability evidence must refer to this exact vacancy URL. A company news page cannot prove the opening is live; a current closed job requires source refresh before reconsideration, not a listed flag in the dossier.
5. Set `coverage_confirmed=true` only after checking the full JD. Save with `python -m careeros analysis save --file <json>` and inspect a fresh packet. The contract is in [references/analysis-contract.md](references/analysis-contract.md).

## Red team

Run `python -m careeros review packet --resume-id <id> --compact` and review only the frozen exact resume, job, structured analysis and dossier. Prior review findings and actions remain available in the compact packet. Cover all seven stages: `ats`, `hr`, `hiring_manager`, `technical`, `pressure`, `background`, `competition`.

- Pressure questions must be job relevant and respectful; never use protected characteristics or discriminatory criteria.
- Background review checks supplied evidence consistency, not unauthorized surveillance.
- Competition uses a hypothetical public-market benchmark, never invented applicants.
- Findings cite observed evidence, requirement IDs and `presentation|preparation|structural|blocker`. A new finding is unresolved; do not mark it resolved in the same review.

## Blue team

Map every finding to `wording|practice|evidence|retarget`. Wording can clarify an existing fact; it cannot cure a structural or hard-gate deficit. Save the completed review with `python -m careeros review save --file <json>` and inspect `review list [--resume-id <id>]`.

Grades are CLI-computed simulations: A requires complete confirmed coverage, all requirements met, all stages pass, no unknowns and a current listed source; B retains preparation risk; C has substantive competitive weakness; D has a known veto or mismatch. Unknown gates produce `NEEDS_EVIDENCE` unless a known D blocker already decides the result. Strong fit never guarantees an offer.

After a revision, obtain a new packet and perform an independent review. Stop after two red/blue rounds when no new evidence appears.

## Career Twin Core contract
- Read `context brief`; keep `user_confirmed` / `document_verified` capability separate from `inferred`, and let `met` cite only approved experience IDs.
- Record the decision so it reaches "where am I now": `pipeline update --job-id <id> --status evaluating|shortlisted|parked|discarded --reason "<why>"`.
- Turn "needs more evidence" into `action propose` (`source_type: job`) with a `suggestion_reason`.
- If the JD conflicts with a confirmed hard constraint, cite the assertion ID and park or discard instead of arguing fit. Shared rules are in `AGENTS.md`.
