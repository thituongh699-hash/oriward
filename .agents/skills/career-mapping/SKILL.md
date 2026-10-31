---
name: career-mapping
description: Map experience evidence to adjacent, cross-industry and hybrid career paths, with sourced market checks and explicit blockers. Use for career exploration or pivots, not vacancy claims or resume writing.
---

# Career mapping

Compare a small, revisable set of directions for career changes, return to work or first entry. Recover transferable work from employment, business, study and informal responsibilities. Check actual gates, availability and feasible entry routes; age, a prior title or one rejection does not set a career ceiling.

On first use, default to `python -m oriward onboarding status` and a lightweight experience index; target companies, roles and constraints can remain open while exploration proceeds. Reuse saved choices through `onboarding missing`; ask only what matters to the current choice, not every empty field. Save a current topic and next action with `onboarding topic`; switch topics without losing work (the prior branch is paused), and later continue it with `onboarding resume --id <branch-id>`. Channel preference is optional and does not block career mapping or enable a connector.

1. Read relevant experiences and constraints. Use `$career-discovery` to recover overlooked actions when helpful; do not require an exhaustive interview.
2. Map `experience ID -> actual action -> transferable ability -> new-role deliverable -> occupation family`. Label interests and inferences separately.
3. For adjacent, cross-industry and hybrid options, show supporting IDs, counterevidence, hard gates, feasible entry proof, risks and search terms.
4. Read current public vacancies or official occupation sources as needed; retain exact URLs and checked dates. Without market evidence, keep the direction a hypothesis. Never invent openings, demand, salaries or offer probabilities.
5. Save reviewed directions using [references/career-contract.md](references/career-contract.md) and `python -m oriward career add --file <private-json>`; inspect `career list`. Hand search terms to `$job-search`.

## Career Twin Core contract

- Each direction becomes a `career_hypothesis` (`subject:career:<slug>`, `predicate:direction_hypothesis`, `source_type:model_inference`), with `supports` and `contradicts` links.
- Cite the assertion ID for any confirmed hard-constraint conflict. A user-chosen pursuit uses `goal add` with `owner:user`; agent exploration uses `owner:agent` and must not drive priority ordering.
- Record recommended direction/validation choices and later reassessment through the [decision contract](../../../docs/DECISIONS.md). Shared privacy and external-action rules remain in `AGENTS.md`.
