# Resume provenance and revisions

Before building/reviewing, verify every claim against approved experience/profile facts: dates, metrics, titles, tools and personal ownership must exist in the source. Selected experiences must cover analysis items marked `met`; the saved file's bytes must match its stored SHA-256. Label the draft local and unsubmitted.

## Revision input

`resume revise --file <json>` requires `base_resume_id`, `reason`, nonempty `sections`; optional `review_id`/`feedback_ids` link the cause. Each section names one `experience_id`. Each bullet contains one-line `text` and nonempty exact `source_texts` from that same experience's actions, outcomes or evidence claims.

A revision creates a new resume and preserves the base. Reordered exact facts may be approved immediately; semantic rewrites are `pending`. Show pending claims completely, then require direct user factual confirmation before `resume confirm --id <id> --human-confirmed`.

Inspect `resume history --id <id>` for base, review, feedback and claim mappings. Obtain a fresh review packet for the new ID and follow [the analysis/review contract](../../job-analysis/references/analysis-contract.md); never reuse the base grade. External upload, publication or submission requires authorization for the named destination.
