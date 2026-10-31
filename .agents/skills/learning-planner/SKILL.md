---
name: learning-planner
description: Convert evidenced role gaps and review findings into prioritized practice, portfolio evidence or retargeting milestones. Use for job-ready development plans, not generic course lists or wording-only fixes.
---

# Learning planner

Fit a small plan to weekly capacity, work, caring responsibilities, time away and real deadlines. Study or personal projects may provide evidence. Revise workload as capacity changes; do not treat an overloaded checklist as a cure for anxiety or claim unsupported background reminders.

1. Read the user's target, transferable actions and any relevant analyses, optional review findings or feedback. A formal review is not a prerequisite. Separate unknown evidence, preparation risk and missing capability.
2. Route `practice` to rehearsal, `evidence` to an artifact/credential, and `retarget` to a role/level change. Structural deficits do not become wording tasks.
3. Draft 2–5 milestones with deliverables, acceptance criteria, effort/date, dependencies and current source URLs where needed. State existing ability, the specific new tool/task to learn, what to produce, how to test it and time needed. Prefer a small practical output to a course list.
4. Save the reviewed plan using [references/plan-contract.md](references/plan-contract.md) and `python -m oriward learning save --file <path>`; inspect `learning list`.
5. Record actual new work through `$career-discovery` and use faithful wording in the next resume without another approval stage. Reassess market fit when needed; finishing a course alone does not establish mastery or improve a simulated grade. Learning and market validation do not block the current draft.

Do not invent progress, guarantee recruiting outcomes or upload private work without authorization for the named service.

## Career Twin Core contract

- Use `goal add` for a user-endorsed target; propose each milestone as a `learn` action with `suggestion_reason` and real `due_at` when a deadline exists.
- Record stalls with `action block --id <id> --reason ...` or `goal update --id <id> --status paused --note ...`. Do not invent agreed priorities or confirm assertions yourself.
- Record recommended plan choices and later reassessment via the [decision contract](../../../docs/DECISIONS.md). Shared rules are in `AGENTS.md`.
