# Experience evidence contract

Record accepts these fields:
- `event` (required string): neutral short title.
- `context` (string): project setting, dates only if known.
- `actions` (required array of strings): actions directly attributable to user.
- `outcomes` (required array of strings): factual outputs or verified effects; may be empty.
- `evidence` (required array): `{ "claim": string, "source": string, "status": "user_confirmed|document_verified|unverified" }`.
- `inferred_skills` (array): `{ "name": string, "reason": string, "confidence": "low|medium|high" }`.
- `approved_for_resume` (required boolean): user approved the factual wording, not model inferred approval.
- `privacy` (e.g. `private`).

Example: `data/examples/experience.json`.

## Separate inference from facts
A user who says “used Python to clean data” supplies evidence that they used Python; it does not support “expert in Python”, “engineered a production pipeline”, “drove a 30% increase”, or independently verified productivity. All uncertain qualifications belong in `inferred_skills` or unanswered questions, never `actions`/`outcomes`.

## Persistence
`python -m careeros experience add --file data/private/experience-review.json`
`python -m careeros experience list`
Store reviewed personal JSON under `data/private` to avoid version-control disclosure.
