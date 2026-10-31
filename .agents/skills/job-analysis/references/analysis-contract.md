# Analysis and simulated hiring review

Load this contract when saving requested analysis or conducting an optional formal red/blue review. Neither analysis nor seven-stage assessment is a gate before resume drafting or local export. Stored entities and JSON examples live in [DATA_MODEL](../../../../docs/DATA_MODEL.md).

## Analysis input

`analysis draft` is an all-unknown line template, not semantic understanding. Use `analysis packet --job-id <id> --compact` to read the complete JD and current source-grounded experience material.

Required: `job_id`, `requirements`, `unknowns`; include `coverage_confirmed` (default false) and `company_context`. Each requirement has:

- stable unique `id`, semantic `text`, `kind:hard_gate|core|preferred`;
- `quote`: exact substring of the current JD;
- `match:met|gap|unknown`, evidence-based `rationale`;
- `evidence_refs`: nonempty for `met`, with `{type:experience_version,id,version?}`, `{type:assertion,id}` or `{type:document,id}`. The CLI freezes content fingerprints; reuse saved tokens so stale references are rejected. `experience_ids` remains a compatibility input/output and is normalized into experience-version refs.

Assertion refs must be current `user_stated|user_confirmed|document_verified` factual or constraint claims. A clear self-report is enough; low-confidence vague statements and outside/model inferences are not settled evidence. Document IDs identify ledger assertions with `source_type:document`, `epistemic_status:document_verified` and a nonempty `source_ref`; an absolute local source path must exist and its bytes are frozen too. A document cannot create user confirmation. Cite the source's actual wording; a valid ID alone does not prove semantic fit.

For a compound requirement add `components`, each with unique `id`, atomic `text`, exact parent-quote substring `quote`, `match`, `rationale` and its own evidence refs or experience IDs. The parent can be `met` only when every component is met and covers its clauses. Partial coverage leaves the parent `unknown` or `gap`; do not replace missing component evidence with a parent experience ID. The CLI catches explicit conjunctions, but the Agent still owns semantic decomposition, including conjunctions the heuristic cannot recognize.

Optional `role_focus` records `mission`, `hiring_motive:{fact,inference,sources}`, 2–4 `core_deliverables:[{id,text,requirement_ids}]`, `resume_themes:[string]` and `interview_themes:[string]`. An empty draft is allowed; an active focus requires the mission and 2–4 mapped deliverables. Motive facts require company-context-shaped sources; unknown reasons belong in inference. This is reviewed interpretation, not verified inside information. Hard gates remain binding; ancillary gaps outside the mapped deliverables remain preparation work rather than automatically proving overall unfitness.

Company context items preserve exact `url`, timezone-aware ISO `retrieved_at`, sourced `fact`, separate `inference` and optional `availability:listed|closed|unknown`. Availability evidence must concern the exact vacancy, not a company news page. Set `coverage_confirmed:true` only after full-JD inspection.

Run `analysis save --file <json>` and inspect a fresh packet. The CLI computes/normalizes recommendation, confidence and job hash.

## Red review

Get `review packet --resume-id <id> --compact`; create structured analysis first if `analysis_id` is null. Read the current content of that resume ID, job, analysis and dossier. Prior findings/actions remain available for comparison.

Cover `ats`, `hr`, `hiring_manager`, `technical`, `pressure`, `background`, `competition`. Each stage needs `verdict:pass|risk|fail|unknown`, nonempty rationale, questions and requirement IDs; together they must cover every requirement.

Pressure questions must be job relevant and respectful, without discriminatory criteria. Background review checks supplied evidence consistency, including dates, number definitions and personal/team ownership, not unauthorized surveillance. Unresolved conflicts must stay visible. Competition defaults to `evidence_basis:hypothetical`; its scenario verdict/findings do not cap the computed grade. A sourced candidate-pool comparison uses `evidence_basis:candidate_pool` and company-context-shaped `sources`; a known JD difference uses `evidence_basis:jd_gap` and linked requirement IDs. Public market speculation does not establish the actual applicant pool.

Red findings need unique ID, stage, `presentation|preparation|structural|blocker`, issue, observed evidence, requirement IDs and `resolved:false`. A new finding cannot be resolved in the same review.

A blocker only produces a veto when linked to a known requirement `gap`, or marked `evidence_basis:verified_disqualification` with valid typed `evidence_refs` establishing an independent failure. Missing/unknown credentials are not proven failures. Competition findings require `evidence_basis:candidate_pool` plus sources, or `requirement_gap` plus a known linked gap, to affect grades; otherwise retain them as hypothetical preparation scenarios. The CLI checks reference validity and declared coverage; it does not verify natural-language causality or create independent reviewers.

## Blue response and re-review

Map every finding to `wording|practice|evidence|retarget`. Wording clarifies existing facts; it cannot cure structural deficits or hard gates. Save with `review save --file <json>` and inspect `review list [--resume-id <id>]`. The CLI rejects supplied grade/status/reasons and validates current sources and the JD fingerprint. No resume hash is required; legacy supplied hashes are ignored.

When formal reassessment is requested after evidence or a resume changes, obtain a fresh packet and conduct a fresh review. Omit an old finding only when the new evidence/version removes it. A revision inherits no grade. Stop after two red/blue rounds without new evidence; retain unresolved gaps and route substantive work to practice, evidence or retargeting.

## Results

The CLI computes simulated grades: A requires confirmed full coverage, every requirement met, all supported stages passing, no unknowns and a listed source no more than 30 days old. B retains preparation risk; C indicates a core deliverable gap or another supported substantive risk; D indicates a known veto/mismatch. Without role focus, legacy core/preferred gap grading remains available. Unknown gates yield `NEEDS_EVIDENCE` unless an independent known D cause already decides the result. A higher simulated preparation grade after removing unsupported competition input does not imply better real hiring odds. Report the mission, core deliverables, main strengths, true gates and uncertainty before this auxiliary label.
