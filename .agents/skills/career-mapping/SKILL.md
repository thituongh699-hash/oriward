---
name: career-mapping
description: Map experience evidence to adjacent, cross-industry and hybrid career paths, with sourced market checks and explicit blockers. Use for career exploration or pivots, not vacancy claims or resume writing.
---

# Career mapping

Compare a small, revisable set of directions. Distinguish exploration, internship and graduate-entry roles; verify graduation-year and availability requirements rather than assuming eligibility. A major or one rejection does not set a career ceiling.

1. Read relevant experiences and constraints. If evidence is thin, use `$career-discovery` first.
2. Map `experience ID -> demonstrated action -> transferable ability -> occupation family`. Label interests and inferences separately.
3. For adjacent, cross-industry and hybrid options, show supporting IDs, counterevidence, hard gates, feasible entry proof, risks and search terms.
4. Read current public vacancies or official occupation sources as needed; retain exact URLs and checked dates. Without market evidence, keep the direction a hypothesis. Never invent openings, demand, salaries or offer probabilities.
5. Save reviewed directions using [references/career-contract.md](references/career-contract.md) and `python -m careeros career add --file <private-json>`; inspect `career list`. Hand search terms to `$job-search`.

## Career Twin Core contract

- Each direction becomes a `career_hypothesis` (`subject:career:<slug>`, `predicate:direction_hypothesis`, `source_type:model_inference`), with `supports` and `contradicts` links.
- Cite the assertion ID for any confirmed hard-constraint conflict. A user-chosen pursuit uses `goal add` with `owner:user`; agent exploration uses `owner:agent` and must not drive priority ordering.
- Record recommended direction/validation choices and later reassessment through the [decision contract](../../../docs/DECISIONS.md). Shared privacy and confirmation rules remain in `AGENTS.md`.
