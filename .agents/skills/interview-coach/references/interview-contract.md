# Interview and feedback input

Interview JSON requires `job_id,questions,practice,next_actions`. Recommended: exact `resume_id`, round/date, `company_sources` with URL, retrieved_at, fact and separate inference. Each practice item records the actual question, user's answer, feedback and supporting experience IDs; never save an invented polished answer as observed.

Use `interview save --file <private-json>` and inspect `interview list`.

Feedback requires `job_id`, exact `resume_id`, `kind:actual|mock|hypothesis`, a stage from [the review contract](../../job-analysis/references/analysis-contract.md), `outcome:pass|reject|pending|withdrawn|unknown`, observation, source, non-future timezone-aware `observed_at`, and at least one `wording|practice|evidence|retarget` action.

Actual employer feedback also needs the matching non-READY application ID. Practice is mock; causal explanations inferred from silence/rejection are hypotheses. Saving feedback changes neither application status nor review grade.
