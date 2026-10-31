# Experience input and continuity

Load when saving an experience. Required: `event` (neutral title). `actions`, `outcomes`, `evidence` arrays may be omitted and default empty. Record known context/dates and the original account without guessing. An event is a meaningful episode, not one record per sentence.

Evidence items use `claim`, `source`, `status:user_stated|user_confirmed|document_verified|unverified`. Direct conversation is a sufficient ordinary source (`user_stated`); attachments and precise metrics are optional. The Agent maintains provenance while organising the account. The user does not fill an evidence form or clear a verification queue.

`approved_for_resume` is a legacy optional boolean, default false. It is not a new-flow usage gate: do not set it true to manufacture approval, and do not interpret false as withdrawal. Respect explicit exclusions, retractions and superseded versions. Unknown-source imports and model suggestions must not be relabelled as user reports.

Ordinary conversation intake uses user-message provenance and records `provenance_status:user_stated` automatically. For imports retain the real source, including document or unverified provenance; do not exploit the default to convert model text into self-report.

Optional: `context`, `privacy`, `inferred_skills` objects with `name`, `reason`, `confidence:low|medium|high` and actual source. `assertion_ids` links supporting facts; after a factual correction use current IDs. Example: `data/examples/experience.json`. Status/version fields are library-managed. Tool use supports the stated task, not expertise or fabricated production responsibility. Keep guesses in inferred skills or open questions.

Save JSON under `data/private/`, then `experience add --file <path>`. Use `experience revise --id <id> --file <changes-only-json> --reason <text> --expected-version <n>` for additions/corrections to the same event. The user's correction directly updates future use, without repeated approval. Resume wording changes alone do not overwrite the underlying history.

Read `experience index --budget 2200`; omission metadata counts in the budget. Page with `--offset`/next offset until complete for a full career inventory; filters alone do not establish full coverage. `experience skills` groups exploratory labels with current ID/version refs; `complete=false` and `omitted_refs` disclose missing scope. Load details in batches with `experience detail --ids 1,2 --sections actions,outcomes`; inspect actual read receipts.

`experience exclude --id <id> --reason <text>` and `experience supersede --id <id> --replacement-id <id> --reason <text>` honour explicit display/removal choices. `experience history --id <id>` preserves originals. Changed linked assertions can mark dependencies `needs_review`: reconcile the affected fact without imposing a whole-library approval queue. Unlinked semantic conflicts still need Agent judgement.
