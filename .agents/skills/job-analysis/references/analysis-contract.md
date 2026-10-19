# Analysis and simulated hiring review

Load this contract when saving analysis or conducting the formal red/blue review. Stored entities and JSON examples live in [DATA_MODEL](../../../../docs/DATA_MODEL.md).

## Analysis input

`analysis draft` is an all-unknown line template, not semantic understanding. Use `analysis packet --job-id <id> --compact` to read the complete JD and approved evidence.

Required: `job_id`, `requirements`, `unknowns`; include `coverage_confirmed` (default false) and `company_context`. Each requirement has:

- stable unique `id`, semantic `text`, `kind:hard_gate|core|preferred`;
- `quote`: exact substring of the current JD;
- `match:met|gap|unknown`, evidence-based `rationale`;
- `experience_ids`: nonempty approved/verified IDs whenever match is `met`.

Company context items preserve exact `url`, timezone-aware ISO `retrieved_at`, sourced `fact`, separate `inference` and optional `availability:listed|closed|unknown`. Availability evidence must concern the exact vacancy, not a company news page. Set `coverage_confirmed:true` only after full-JD inspection.

Run `analysis save --file <json>` and inspect a fresh packet. The CLI computes/normalizes recommendation, confidence and job hash.

## Red review

Get `review packet --resume-id <id> --compact`; create structured analysis first if `analysis_id` is null. Review only the frozen exact resume, job, analysis and dossier. Prior findings/actions remain available for comparison.

Cover `ats`, `hr`, `hiring_manager`, `technical`, `pressure`, `background`, `competition`. Each stage needs `verdict:pass|risk|fail|unknown`, nonempty rationale, questions and requirement IDs; together they must cover every requirement.

Pressure questions must be job relevant and respectful, without discriminatory criteria. Background review checks supplied evidence consistency, not unauthorized surveillance. Competition uses a hypothetical public-market benchmark, never invented applicants.

Red findings need unique ID, stage, `presentation|preparation|structural|blocker`, issue, observed evidence, requirement IDs and `resolved:false`. A new finding cannot be resolved in the same review.

## Blue response and re-review

Map every finding to `wording|practice|evidence|retarget`. Wording clarifies existing facts; it cannot cure structural deficits or hard gates. Save with `review save --file <json>` and inspect `review list [--resume-id <id>]`. The CLI rejects supplied grade/status/reasons and validates exact resume/job hashes.

After evidence or a resume changes, obtain a fresh packet and conduct an independent review. Omit an old finding only when the new evidence/version removes it. A revision inherits no grade. Stop after two red/blue rounds without new evidence; retain unresolved gaps and route substantive work to practice, evidence or retargeting.

## Results

The CLI computes simulated grades: A requires confirmed full coverage, every requirement met, every stage pass, no unknowns and a listed source no more than 30 days old. B retains preparation risk; C indicates substantive competitive weakness; D indicates a known veto/mismatch. Unknown gates yield `NEEDS_EVIDENCE` unless a known D blocker already decides the result. These are not employer verdicts or offer guarantees.
