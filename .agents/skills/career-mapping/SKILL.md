---
name: career-mapping
description: Map experience evidence to adjacent, cross-industry and hybrid career paths, with sourced market checks and explicit blockers. Use for career exploration or pivots, not vacancy claims or resume writing.帮助用户发现新的工作机会。
---

# Career mapping

This is the default bridge from experience discovery to preference-led job search: identify transferable abilities the user may overlook and explain their value in viable role families. Check actual gates and entry routes; age, prior title or one rejection does not set a career ceiling.

On first use, default to `python -m oriward onboarding status` and the full experience index; targets may remain open. Reuse saved choices, ask only what changes the mapping, and save topic/next action with `onboarding topic`. Channel preference is optional and does not enable a connector.

1. Read the complete experience index and relevant constraints, then inspect details for promising evidence. Use `$career-discovery` to recover overlooked actions when helpful; do not require an exhaustive interview. Reuse stated preferences and ask only for a missing constraint that changes the mapping.
2. Map `experience ID -> action -> transferable ability -> possible deliverable/direction`; distinguish interest and inference without forcing occupational categories.
3. For options, show supporting IDs, counterevidence, gates, feasible entry proof, risks and search terms.
4. Read current public vacancies or official occupation sources as needed; retain exact URLs and checked dates. Without market evidence, keep the direction a hypothesis. Never invent openings, demand, salaries or offer probabilities.
5. Save directions using [references/career-contract.md](references/career-contract.md) and `career add`; inspect `career list`. Hand preferences, direction IDs, evidence, constraints and terms to `$job-search`; unselected directions remain hypotheses.

## Career Twin Core contract

- Each direction becomes a `career_hypothesis` (`subject:career:<slug>`, `predicate:direction_hypothesis`, `source_type:model_inference`), with `supports` and `contradicts` links.
- Cite the assertion ID for any confirmed hard-constraint conflict. A user-chosen pursuit uses `goal add` with `owner:user`; agent exploration uses `owner:agent` and must not drive priority ordering.
- Record recommended direction/validation choices and later reassessment through the [decision contract](../../../docs/DECISIONS.md). Shared privacy and external-action rules remain in `AGENTS.md`.
