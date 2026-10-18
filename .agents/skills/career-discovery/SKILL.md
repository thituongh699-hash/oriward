---
name: career-discovery
description: Interview a person about overlooked education, work, projects, hobbies, setbacks and informal responsibilities, then save evidence-backed experience facts separately from inferred skills. Use for personal evidence discovery, not vacancy search or resume embellishment.
---

# Career discovery

Build reusable evidence without turning plausible interpretation into biography.

1. Run `python -m careeros profile show` and `python -m careeros experience list`; read only records needed for the current question. Do not silently inspect accounts or unrelated personal files.
2. Explore 2–3 neglected angles at a time. Ask about context, personally attributable actions, constraints, outcomes, artifacts and uncertainty; separate team output from individual ownership.
3. Write reported facts, evidence and skill hypotheses separately. Interest is not competence; a user statement is confirmation, not independent verification.
4. Draft the JSON in [references/experience-contract.md](references/experience-contract.md). Show every factual phrase that may enter a resume and obtain direct human confirmation before setting `approved_for_resume=true`.
5. Save only reviewed content with `python -m careeros experience add --file data/private/<name>.json`, then verify with `python -m careeros experience list`.
6. Report facts, inferred skills, unknowns, saved IDs and the next high-value questions. Route career options to `$career-mapping`; route a newly evidenced gap closure back into later resume analysis.

Never invent dates, employers, titles, metrics, certificates, skill levels or causal impact. Do not upload personal evidence to a third-party service without explicit authorization for that service and purpose.

## Career Twin Core contract
- Start with `python -m careeros context brief`; drill into only the assertions relevant to the current question.
- Write new claims with `belief propose`: model inference uses `source_type: model_inference` and stays `inferred`.
- Every skill inference needs `links: [{"ref_type": "experience", "ref_id": <id>, "relation": "derived_from"}]`; without it `context why` cannot trace it.
- After the user personally agrees, run `belief confirm --id <id>`. Never confirm on the user's behalf.
- Report the experience ID and every assertion ID with its epistemic status.
