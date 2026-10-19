# Interview and feedback input

Interview JSON requires `job_id,questions,practice,next_actions`. Recommended: exact `resume_id`, round/date, `company_sources` with URL, retrieved_at, fact and separate inference. Each practice item records the actual question, user's answer, feedback and supporting experience IDs; never save an invented polished answer as observed.

Reuse the latest analysis/review packet's `role_focus.interview_themes` and mapped core deliverables when selecting questions and cases. Mention the deliverable in the question and keep its source requirement ID in the notes; retain direct user evidence separately from inferred transferability. Do not turn an unknown credential, hypothetical competing applicant or unsourced hiring-motive guess into an observed defect. Unresolved dates, numerical definitions and personal/team ownership remain explicit questions. Reuse already confirmed answers instead of re-interviewing the full library.

Use `interview save --file <private-json>` and inspect `interview list`.

Feedback requires `job_id`, exact `resume_id`, `kind:actual|mock|hypothesis`, a stage from [the review contract](../../job-analysis/references/analysis-contract.md), `outcome:pass|reject|pending|withdrawn|unknown`, observation, source, non-future timezone-aware `observed_at`, and at least one `wording|practice|evidence|retarget` action.

Actual employer feedback also needs the matching non-READY application ID. Practice is mock; causal explanations inferred from silence/rejection are hypotheses. Saving feedback changes neither application status nor review grade.
