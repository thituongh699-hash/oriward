---
name: resume-builder
description: Translate real career histories into complete, focused Markdown resumes, preserving sources and versions while delivering a full draft for user edits. Use for resume content, not external submission or invented qualifications.
---

# Resume builder

Turn what the user actually did into language a new role understands. Work, business, projects, education and informal responsibilities can carry transferable value. Clear self-report is sufficient; write confidently within it. Never invent duties, titles, tools, dates, metrics or personal ownership.

1. Read `context brief`, current profile and the complete experience index, paging until complete; load detail in bounded batches. Use `resume tailor-packet` for a general resume, or add `--job-id <id>` for a saved job and understand the role purpose and 2–4 core deliverables. Follow its `next_offset`/`has_more` with `--offset` and `--budget`; a bounded packet is not proof that the whole library was read. Without a target, prepare a general draft from known history; choosing a direction or completing formal analysis is not a prerequisite.
2. Build a complete skeleton: existing name/contact details, education and major career stages. Connect actual actions to the target's deliverables rather than matching titles or keywords. Expand direct relevance, explain transferable work across industries and summarise other major stages. Consolidate small events only with clear organisation/time/ownership and source links. Honour explicit exclusions. Keep work chronology, real overlaps and gaps; do not invent dates or expose private gap reasons.
3. Respect explicit template preferences, including an existing personal reference layout. That person's template is not a universal structure. Otherwise arrange sections for this history: experienced workers may lead with work; students may lead with education/projects. Do not create empty certificate or interest sections. Preserve education already supplied.
4. Read [references/resume-review.md](references/resume-review.md); save through supported CLI composition/revision commands and report the actual receipt ID/path. Maintain sources internally; users need not provide exact quotes, approve experiences or repeat facts. Professional rewriting and grounded synthesis go directly into the full draft. If a number or ownership point is unclear, use known facts and ask only that point if needed; never freeze the entire draft.
5. Check omissions, chronology, scope, repetition, readable headings and natural language; repair what can be repaired. Deliver the complete draft for reading and edits without a confirmation gate. User corrections take effect directly. Formal simulated hiring review is optional when requested for assessment; a draft does not require seven stages or a grade.
6. For Word/PDF, use [document-export](../document-export/SKILL.md), including local initial-draft preview. Inspect every rendered page for sparse content, detached headings, incorrect links and forced breaks. Adjust detail/density before shrinking type or forcing one page. Preserve version/source history; cleanup maintenance uses dry-run first.

Report local/unsubmitted status, version and paths briefly; keep source IDs, ratings and internal paths out of candidate-facing content. Drafting/export never authorizes upload or submission to a destination.

## Career Twin Core contract

- Model guesses remain inferred, not user facts. Faithful professional synthesis of stated actions needs no separate factual approval.
- Register useful preparation/learning follow-ups with `action propose` and `suggestion_reason`; market validation and learning support the new direction without blocking the current resume.
- Use the [decision contract](../../../docs/DECISIONS.md) for actual target/preparation recommendations. Shared privacy and external-action rules remain in `AGENTS.md`.
