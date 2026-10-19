# Resume provenance and revisions

Before building/reviewing, verify every claim against approved experience/profile facts: dates, metrics, titles, tools and personal ownership must exist in the source. Selected experiences must cover analysis items marked `met`; the saved file's bytes must match its stored SHA-256. Label the draft local and unsubmitted.

## Revision input

`resume revise --file <json>` requires `base_resume_id`, `reason`, nonempty `sections`; optional `review_id`/`feedback_ids` link the cause. Each section names one `experience_id`. Each bullet contains one-line `text` and nonempty exact `source_texts` from that same experience's actions, outcomes or evidence claims.

A revision creates a new resume and preserves the base. Exact actions/outcomes inherit factual approval. A professional rewrite may declare `change_type:wording_only`, `new_facts:[]` and a nonempty `change_reason`, with exact source quotations. This is the Agent's explicit semantic classification, not automatic semantic verification. The runtime checks mappings and a limited set of number/tool/scope markers; it cannot prove every rewrite faithful. Never label added facts as wording-only merely to bypass approval.

For added duties, numbers, dates, tools, ownership or effects use `change_type:new_facts` plus a nonempty `new_facts` array naming additions. These changes remain `pending` for one consolidated factual check. Unclassified semantic changes also remain pending. Do not force exact KPIs when qualitative results or user-approved approximations suffice. Direct self-report counts as evidence; attachments are optional.

Show pending additions completely, then require direct user factual confirmation before `resume confirm --id <id> --human-confirmed`. Every final draft still needs whole-draft user review. `claim_map` retains source text, experience version, classification and additions; an approved wording revision still needs a fresh job-specific review. Corrections/exclusion invalidate dependent snapshots rather than rewriting historical files. Rebuild from corrected current facts before preparing an application packet.

Inspect `resume history --id <id>` for base, review, feedback and claim mappings. Obtain a fresh review packet for the new ID and follow [the analysis/review contract](../../job-analysis/references/analysis-contract.md); never reuse the base grade. External upload, publication or submission requires authorization for the named destination.
