# Experience evidence input

Load when preparing an experience record. Required fields:

- `event`: neutral short title;
- `actions`: strings directly attributable to the user;
- `outcomes`: factual outputs/effects, may be empty;
- `evidence`: objects with `claim`, `source`, `status:user_confirmed|document_verified|unverified`;
- `approved_for_resume`: boolean based on direct user approval of factual wording.

Optional: `context` (setting, dates only if known), `privacy` (e.g. private), `inferred_skills` objects with `name`, `reason`, `confidence:low|medium|high`. Example: `data/examples/experience.json`.

“Used Python to clean data” supports use, not expertise, production ownership, a fabricated metric or independently verified productivity. Put uncertain capabilities in `inferred_skills` or open questions, never factual actions/outcomes. User confirmation is not independent document verification.

Save reviewed JSON under `data/private/`, then use `experience add --file <path>` and verify with `experience list`. Keep the approval and inference boundaries from the entrypoint.
