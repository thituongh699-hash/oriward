# Structured analysis and hiring review contract

## Analysis

Start from `python -m careeros analysis draft --job-id <id>`, but treat it only as an all-unknown line template. Use `analysis packet` to perform the semantic pass.

Required analysis fields: `job_id`, `requirements`, `unknowns`. Include `coverage_confirmed` (default false) and `company_context`.

Each requirement contains:

- `id`: stable unique string within the analysis;
- `text`: semantic requirement;
- `kind`: `hard_gate|core|preferred`;
- `quote`: exact substring of the current JD;
- `match`: `met|gap|unknown`;
- `experience_ids`: nonempty approved/verified IDs only when match is met;
- `rationale`: evidence-based reason.

Each company context item contains `url`, ISO `retrieved_at`, sourced `fact`, separate `inference`, and optional `availability=listed|closed|unknown`. Keep the exact linked source. Set `coverage_confirmed=true` only after inspecting the full JD.

Save with `python -m careeros analysis save --file data/private/analysis.json`. Recommendation/confidence/job hash are computed or normalized by the CLI; do not pretend the draft is autonomous AI scoring.

## Review

Obtain `python -m careeros review packet --resume-id <id>`. Its template has all seven stages and may have `analysis_id=null` if no structured analysis exists; create the analysis first.

Every stage has `verdict=pass|risk|fail|unknown`, nonempty rationale, questions and requirement IDs. Across stages, every requirement ID must be covered. Red findings contain unique ID, stage, `presentation|preparation|structural|blocker`, issue, evidence, requirement IDs and `resolved=false`. A finding discovered in the current review cannot be marked resolved there. Blue actions cite a finding and use `wording|practice|evidence|retarget`.

The CLI rejects caller-supplied grade/status/reasons and validates exact resume/job hashes. Use `review save --file`, then `review list [--resume-id ID]`. A revised resume needs a new independent review; omit obsolete findings only after the new evidence/version actually removes them.

A requires coverage confirmed, every requirement met, every stage pass, no unknowns and a <=30-day listed source. Known D blockers take precedence over unresolved unknown gates. All results remain simulated, never employer verdicts or offer guarantees.
