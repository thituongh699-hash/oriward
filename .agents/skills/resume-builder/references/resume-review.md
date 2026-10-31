# Resume composition and continuity

Use clear user reports and current profile/experience facts. Dates, tools, titles, metrics and personal ownership must stay within those facts. Professional rewriting, synthesis and transferable framing are normal drafting, without per-experience approval, exact-quote work for the user or repeated confirmations. Preserve originals and sources in the background; do not label model guesses as user reports. Draft/export remains local and unsubmitted.

## Complete inventory and presentation

Read the complete experience index, following pagination, then relevant details in bounded batches. `resume tailor-packet [--job-id <id>] --offset <n> --budget <chars>` supplies profile, target/analysis if present, `translation_focus`, a bounded index and `detail_requests`; fetch selected details separately. Follow `next_offset` while `has_more` instead of assuming one packet is complete. Without a job ID this is a general-resume context, not a vacancy. Understand the role purpose and 2–4 deliverables, then connect actual actions to those deliverables across industry/title differences.

Retain the major career stages and existing education. Expand relevant work, briefly present other stages, and combine small same-stage events where truthful. Keep work in reverse chronology; selected projects may prioritise relevance while retaining dates and organisation. Real gaps/overlaps are allowed. Honour explicit exclusions without repeatedly asking. The user reviews the complete output and requests edits.

Respect the user's chosen layout. A supplied personal reference remains that user's preference, not a global requirement. Otherwise use history-appropriate ordering. Keep each project's dates, ownership and links together, education present and empty sections absent. No internal source IDs, evidence ratings, open questions or private paths belong in the resume body.

## CLI composition contract

`resume compose [--job-id <id>] --file <json>` accepts `reason`, optional `headline`, `sections` (empty is allowed to start from a complete brief history), and source-mapped `summary`/`profile_sections`. A section uses `experience_id` or `experience_ids` for same-stage consolidation, optional `title`, `category` (such as 工作经历、经营经历、项目经历、其他经历), `mode:expanded|brief`, `bullets` and `links`. Bullet strings or claim objects are accepted. Existing claim fields `source_texts`, `change_type`, `new_facts` and `change_reason` preserve background provenance; source texts are optional and maintained by the Agent/runtime, not a user assignment. Wording need not reproduce quotations.

Optional `exclude_experience_ids` records explicit per-document omissions. Unused current usable histories are restored briefly; the Agent still checks whether they are grouped and expressed sensibly. Optional `section_order` preserves the requested layout. Display titles may be rewritten within true role/scope; a heading cannot invent seniority. Existing education in `education`/`education_history` or the legacy summary is included automatically; inspect that it is complete. Profile paragraphs can be strings or objects with `text` and optional `source_texts`; naturally rewrite actual profile facts instead of copying a fixed summary verbatim. Public links must retain their actual source and correct experience association.

```json
{
  "reason": "将门店经营中的采购与库存工作接到运营交付",
  "sections": [{
    "experience_id": 1,
    "category": "经营经历",
    "mode": "expanded",
    "bullets": ["负责日常采购与补货安排，结合库存情况调整进货"]
  }]
}
```

This example assumes those actions were reported; it does not establish any real user's experience. Do not invent cost savings or tools. If a fact is unclear, draft around what is known; one unresolved detail does not block the whole resume. A new term or polished phrase alone is not evidence of an added fact.

## Revision, assessment and export

`resume revise --file <json>` requires `base_resume_id`, `reason`, `sections`; optional `review_id`/`feedback_ids` link a requested assessment. It creates a new version and preserves the base. Correct source facts via the stable experience ID; change this resume's emphasis in its own version. Corrections/exclusions affect future use without rewriting historical snapshots.

Normal `factual_status:draft` describes progress, not missing approval. Legacy confirmation records remain historical; never manufacture `--human-confirmed` to permit drafting or preview. Deliver a complete local Markdown/DOCX/PDF for user edits before any external sending. Review omissions, scope, chronology, density, hierarchy and every rendered page.

Formal seven-stage assessment is optional. When requested, use a fresh packet for the exact version and [analysis contract](../../job-analysis/references/analysis-contract.md); never reuse the base grade. A new draft does not require this exercise. `resume history --id <id>` retains sources/revision causes. Current plus three historical Markdown files per job are retained; older bodies may be pruned while metadata remains. Cleanup uses dry-run first and touches only registered Markdown under the output root, never unrelated PDF/DOCX/photos. Named-destination authorization is still required for upload, publication or submission.

For a partial wording edit inside a group, shared paragraphs without individual source attribution are retained; explicitly source-owned paragraphs can be replaced locally. To rewrite shared prose, submit the complete group rather than assuming the runtime can infer sentence ownership. Keep per-bullet experience IDs when known. This is Agent bookkeeping, never another question or approval for the user. Actual source corrections remove affected old prose before rebuilding.
