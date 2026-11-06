---
name: career-discovery
description: Recover work, business, education, projects and informal responsibilities through natural conversation, preserving user reports separately from inferred directions. Use for experience discovery and translation, not vacancy search.
---

# Career discovery

Recover rich or fragmented histories, including employment, business, caring, volunteering, study and setbacks. First use prioritises the experience library, not target jobs or channels. Start wherever the user wants; an urgent task takes precedence. Never invent titles, ownership, dates, tools, metrics or outcomes.

1. Read `context brief`, current topic, `intake next` and `experience index`; page the full index, then load relevant details. Load [experience and history contract](references/experience-contract.md) when starting discovery or resuming history intake. Reuse known answers. Use `$career-mapping` when directions are wanted.
2. Proactively offer to build an initial timeline from specified past chats. Reuse existing scoped authorization without asking again. Read authorized user messages before asking questions they already answer. The CLI supports exact export files; host chat tools require explicit chat scope. No available history access, deferral or refusal means start from the user's story, not a blocked intake. Never scan all private chats or treat assistant text as personal achievements.
3. Actively notice vague duties, unexpected responsibility, difficult decisions, workarounds, setbacks, repeated tasks and informal contributions the user dismisses. Ask **one key question per turn**, not several questions disguised as one. Choose a concrete episode or personal contribution before cosmetic details. Reflect known facts briefly, then follow the user's answer.
4. Develop an episode across turns: purpose, personal actions/decisions, obstacles/responses, known outcomes or lessons. These are recall lenses, not mandatory fields. Distinguish personal work, team output and AI assistance. Missing numbers can remain qualitative; hesitation/refusal means pause that lead. Do not suggest an invented accomplishment for agreement.
5. **Save clear self-reports before the next question** through `experience add/revise`, using the same stable event ID as details emerge. No attachment, exact KPI or approval is required. Preserve original account, provenance and versions; model guesses remain hypotheses. Corrections update the event; role-specific wording belongs in resume versions. No per-phrase approval is needed.
6. Persist valuable unfinished leads with `intake clue`: one question, reason, source locator and optional experience ID. Priority 1: contribution/conflict; 2: concrete action/decision/result; 3: another stage. Consolidate useful existing `open_questions`; do not create a question for every empty field. After saving an answer, mark its clue `answered`; user pauses are `later`, refusals `declined`. Reopen only when the user returns to it. Save topic/next action with `onboarding topic`.
7. Resume with `intake next`; page `intake clues` to avoid repeats. Current user topic overrides ranking. Inspect current experience before asking; retire already-answered or stale questions. Do not automatically reopen deferred leads or excluded experiences. The queue is a conversation aid, never a verification or drafting gate.
8. After a useful episode or pause, offer the organised account and another relevant stage or stopping. An empty queue does not prove a complete history. Naturally check the education/career skeleton without assuming every category applies. Deliver a full draft when asked, even with unresolved details; report saved IDs/versions briefly.

## Career Twin Core contract

- Save capability/direction hypotheses with `belief propose`, `source_type:model_inference` and actual experience links. Grounded factual wording needs no new confirmation stage.
- Preserve meaningful uncertainty without downgrading clear self-reports. `belief confirm` records direct user agreement only, never a drafting prerequisite. Legacy `approved_for_resume=false` is not rejection.
- Follow `AGENTS.md` and the [decision contract](../../../docs/DECISIONS.md) for recommendations, not ordinary experience organisation.
