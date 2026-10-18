---
name: career-mapping
description: Map approved experience evidence to adjacent, cross-industry and hybrid career paths, with sourced market checks and explicit blockers. Use for career pivots and overlooked role families, not vacancy claims or resume writing.
---

# Career mapping

1. Read `python -m careeros experience list` and relevant profile constraints. If the evidence base is thin, use `$career-discovery` first.
2. Build `experience ID -> demonstrated action -> transferable ability -> occupation family`; keep interests and inferences visibly separate.
3. Compare adjacent occupations, cross-industry analogues and hybrid roles. For each direction show supporting IDs, disconfirming evidence, hard gates, feasible entry proof, risks and search keywords.
4. Use current public vacancies or official occupation sources when authorized. Actually open the sources, preserve exact URLs and checked dates, and separate sourced facts from inference. Without market evidence, label the direction `hypothesis`.
5. Save reviewed direction JSON according to [references/career-contract.md](references/career-contract.md) with `python -m careeros career add --file <path>`, then inspect `python -m careeros career list`.
6. Hand validated search terms to `$job-search`; never fabricate an open job, salary, demand level or offer probability.

Keep personal evidence local unless the user explicitly authorizes a named external service and purpose.

## Career Twin Core contract
- Read `context brief`, especially `who_am_i.constraints`: a direction that violates a confirmed hard constraint must be marked as such, citing the assertion ID.
- Each direction becomes one `career_hypothesis` assertion: `subject: career:<slug>`, `predicate: direction_hypothesis`, `source_type: model_inference`.
- Supporting evidence goes in `links(relation=supports, ref_type=experience)`; disconfirming evidence in `links(relation=contradicts)`.
- Record a user-chosen pursuit with `goal add` (`owner: user`); model-suggested exploration uses `owner: agent` and must not drive priority ordering.
- Report each direction with support, contradiction, gap and a concrete validation action (or `action propose` ID).
