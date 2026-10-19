---
name: career-discovery
description: Discover evidence in education, projects, work and informal responsibilities, then save reported facts separately from inferred skills. Use for personal evidence discovery, not vacancy search or resume embellishment.
---

# Career discovery

Start with one event and a few questions. Coursework, campus roles, volunteering, caring responsibilities and setbacks can supply evidence without formal employment. Accept corrections; never invent titles, ownership, dates, metrics or skill levels, or turn a student project into professional seniority.

1. Inspect relevant profile and `experience list` records only; use `$career-mapping` when the task is choosing directions.
2. Explore context, personally attributable actions, constraints, outcomes and artifacts. Separate team output, individual ownership, interest and competence.
3. Draft reported facts, evidence and inferred skills using [references/experience-contract.md](references/experience-contract.md). A user statement is not independent verification. Show every factual phrase intended for a resume and obtain direct confirmation before `approved_for_resume=true`.
4. Save reviewed content with `python -m careeros experience add --file <private-json>` and inspect the saved record. Keep personal evidence local unless the user authorizes a named external service and purpose.
5. Report saved IDs, facts, hypotheses, unknowns and the next useful question. Newly evidenced gap closure still requires fresh job analysis and resume review.

## Career Twin Core contract

- Propose new capability inferences with `belief propose`, `source_type:model_inference`; they stay `inferred` and need `derived_from` links to their experiences. Other claims retain their actual source, not a blanket model-inference label.
- Keep hedged self-reports at low confidence with original words and circumstances until clarified. Only the user's direct instruction permits `belief confirm`.
- Follow `AGENTS.md` for shared state rules. Read the [decision contract](../../../docs/DECISIONS.md) when recommending or reassessing a course of action.
