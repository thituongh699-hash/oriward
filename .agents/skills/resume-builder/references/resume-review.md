# Resume revision and review checklist

## Before the base review

1. Each claim traces to an approved experience or approved profile fact.
2. Metrics, dates, titles, tools and ownership occur in the source; no inferred expertise.
3. Selected experience IDs are relevant to this exact job and cover all analysis items marked met.
4. The file exists and its bytes match the stored SHA-256.
5. The draft is clearly local and unsubmitted.

## Revision input

`resume revise --file JSON` requires `base_resume_id`, `reason`, nonempty `sections`, and optional `review_id`/`feedback_ids`. Each section names one `experience_id`; each bullet has one-line `text` plus nonempty exact `source_texts` from that same experience's actions, outcomes or evidence claims.

The revision creates a new resume and preserves the base. Reordered exact facts may be immediately approved; semantic rewrites are `pending`. Present pending text to the user and require direct factual confirmation before `resume confirm --id ID --human-confirmed`.

## After revision

1. Inspect `resume history --id ID` for base, review, feedback and claim mapping.
2. Obtain a new `review packet` for the revised ID; never reuse the old result.
3. Have the red review independently test all seven stages and the blue response map every finding to wording/practice/evidence/retarget.
4. Structural gaps survive wording changes. Stop after two rounds without new evidence.
5. Do not upload, publish or submit the version without explicit authorization for the destination.
