---
name: learning-planner
description: Convert evidenced target-role gaps and review findings into prioritized practice, portfolio evidence or retargeting milestones. Use for job-ready development plans, not course lists or wording-only fixes.
---

# Learning planner

For students and recent graduates, first ask about available weekly hours, exams, coursework, internship availability and application deadlines where relevant. Fit a small number of milestones into that capacity, use course or personal projects as evidence when appropriate, and review the plan as capacity changes. Do not present an overloaded checklist as a cure for anxiety or schedule notifications/background work that the host cannot provide.

1. Read target job analyses, review findings and feedback plan. Distinguish unknown evidence, preparation risk and actual missing capability.
2. Route `practice` to rehearsal, `evidence` to a demonstrable artifact/credential, and `retarget` to a role/level change. Do not turn `structural|blocker` into a wording task.
3. Draft 2–5 milestones with deliverable, acceptance criteria, effort/date, dependencies and current source URLs where relevant. Prefer portfolio-quality proof over passive course completion.
4. Save the reviewed plan following [references/plan-contract.md](references/plan-contract.md) with `python -m careeros learning save --file <path>` and inspect `python -m careeros learning list`.
5. When evidence is complete, use `$career-discovery` to verify it as a new experience. It does not automatically enter a resume or improve a grade; rerun analysis/review with the new evidence.

Do not guarantee recruiting outcomes, invent progress, or upload private work to third-party platforms without explicit authorization.

## Career Twin Core contract
- Plans land in the Twin: `goal add` for a user-endorsed target, `action propose` (`action_type: learn`) for each milestone, always with `suggestion_reason`.
- Give every milestone with a deadline a `due_at`; do not invent priorities the user did not agree to.
- When a plan stalls, use `action block --id <id> --reason` or `goal update --status paused`; the trajectory is the point.
- Completed learning becomes evidence through `career-discovery`; never flip an assertion to confirmed yourself. Shared rules are in `AGENTS.md`.
