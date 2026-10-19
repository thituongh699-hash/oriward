# Experience evidence input

Load when preparing an experience record. Required fields:

- `event`: neutral short title;
- `actions`: strings directly attributable to the user, may be empty at intake;
- `outcomes`: factual outputs/effects, may be empty;
- `evidence`: array, initially empty allowed; items have `claim`, `source`, `status:user_stated|user_confirmed|document_verified|unverified`. A direct self-report may use `user_stated`; no attachment is required;
- `approved_for_resume`: optional boolean, defaults false; actual approval of factual content is required for true.

Optional: `context` (setting, dates only if known), `privacy`, `inferred_skills` objects with `name`, `reason`, `confidence:low|medium|high`, actual `source` if user-stated (otherwise model inference). `assertion_ids` explicitly freezes supporting fact assertions; after correction list their current IDs. Example: `data/examples/experience.json`. Status/version/review fields are library-managed.

“Used Python to clean data” supports use, not expertise, production ownership, a fabricated metric or independently verified productivity. Put uncertain capabilities in `inferred_skills` or open questions, never factual actions/outcomes. User confirmation is not independent document verification.

Save intake JSON under `data/private/`, then use `experience add --file <path>`. An empty evidence list is valid intake but cannot back a resume until at least the user's self-report is recorded. Do not force screenshots, metrics or deep interviews.

Read `experience index --budget 2200` first; its actual pretty-JSON character count includes omission metadata. Page with `--offset` or filter with `--query`/`--ids`. `experience skills` groups exploratory labels into cards with current experience ID/version refs; omitted_refs is explicit. `complete=false` means more records exist; inferred tags are a searchable skill index, not verified mastery. Load relevant sections using `experience detail --ids 1,2 --sections actions,outcomes`; receipts identify actual IDs, versions and sections read.

`experience revise --id <id> --file <changes-only-json> --reason <text> --expected-version <n>` keeps the ID/history. Factual changes reset resume approval unless actual user approval is provided with that correction. `experience exclude --id <id> --reason <text>` and `experience supersede --id <id> --replacement-id <id> --reason <text>` remove obsolete entries from default reads. `experience history --id <id>` preserves old snapshots. Stale linked assertions mark `needs_review`; explicitly reconcile the experience and its dependency IDs, never automatically copy a new assertion into old prose. Unlinked semantic conflicts cannot be detected automatically.
