# Resume composition and continuity

Use clear user reports and current profile/experience facts. Dates, tools, titles, metrics and personal ownership must stay within those facts. Professional rewriting, synthesis and transferable framing are normal drafting, without per-experience approval, exact-quote work for the user or repeated confirmations. Preserve originals and sources in the background; do not label model guesses as user reports. Draft/export remains local and unsubmitted.

For an imported resume, `resume input --id <id>` returns numbered extracted lines. Compare PDF/DOCX warnings with the original; OCR is outside this command. `resume rewrite --input-id <id> --file <json>` takes `reason`, `display_name`, `identity_line_ids`, optional `contact` and `contact_line_ids`, and nonempty `sections`. Each section has `heading` and nonempty `paragraphs`; every paragraph has `text`, `source_line_ids` referencing actual imported lines and optional `style:entry|meta|bullet|text` for the rendered hierarchy. Example: `{"reason":"突出真实工作","display_name":"林青","identity_line_ids":[1],"sections":[{"heading":"工作经历","paragraphs":[{"text":"整理客户反馈并交付需求清单。","source_line_ids":[5]}]}]}`. This records provenance, not semantic proof: verify facts, role boundaries and metrics against the original and newer user corrections. The receipt reports uncovered line IDs. Add `--base-resume-id` when revising the same import; keep the same target job. Imported documents are not automatically merged into the experience library.

## Complete inventory and presentation

Use one composition workflow. First reuse user requirements and saved career-mapping, search and analysis context. If a primary job exists, read its complete JD before the full experience index; its purpose, 2–4 deliverables and gates control the resume. Optional comparable JDs enrich role interpretation and customary work only; do not import their employers' gates or invent primary-job requirements. Then read every index page and fetch semantically selected details in bounded batches. `resume tailor-packet --job-id <id> [--reference-job-ids <id> ...] --offset <n> --budget <chars>` provides context and paginated index/details requests; follow `next_offset` until complete. Without a primary job, one or more reference JDs can support a direction draft, but do not bind vacancy-specific analysis or application records until an actual job is chosen. Select evidence semantically, never by text similarity or keyword proxy.

Retain the major career stages and existing education. Expand relevant work, briefly present other stages, and combine small same-stage events where truthful. Keep work in reverse chronology; selected projects may prioritise relevance while retaining dates and organisation. Real gaps/overlaps are allowed. Honour explicit exclusions without repeatedly asking. The user reviews the complete output and requests edits.

Respect the user's chosen layout. A supplied personal reference remains that user's preference, not a global requirement. Otherwise use history-appropriate ordering. Keep each project's dates, ownership and links together, education present and empty sections absent. No internal source IDs, evidence ratings, open questions or private paths belong in the resume body.

## CLI composition contract

`resume compose [--job-id <id>] [--reference-job-ids <id> ...] [--target-title <label>] --file <json>` accepts `reason`, optional `headline`, `sections`, and source-mapped `summary`/`profile_sections`. `--reference-job-ids` may accompany a primary `--job-id` or support a direction draft without one; `--target-title` is for that no-primary direction. Runtime saves Agent-authored context and JD snapshots; it does not judge semantic commonality. The primary JD controls job-specific requirements; references only enrich interpretation. A section uses `experience_id(s)`, optional title/category, `mode:expanded|brief`, bullets and links. Bullet strings or claim objects are accepted. Claim fields `source_texts`, `change_type`, `new_facts` and `change_reason` preserve background provenance; sources need not be quoted.

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

This example assumes those actions were reported; it does not establish any real user's experience. Do not invent cost savings or tools. Use STAR-C (Situation, Task, Action, Result, Challenge/Contribution) as a compact value-writing lens: make actual contribution, constraints and reusable outcomes clear where known. Do not force five-part paragraphs or invent metrics, seniority or results. If a fact is unclear, draft around what is known; one unresolved detail does not block the whole resume. A new term or polished phrase alone is not evidence of an added fact.

The STAR-C framing is informed by [this resume-writing article](https://blog.csdn.net/SJ_HP/article/details/162490861); use its structure as a writing aid only. Do not adopt claims of inferred metrics, tool ratings or performance estimates as evidence about a candidate.

## Revision, assessment and export

`resume revise --file <json>` requires `base_resume_id`, `reason`, `sections`; optional `review_id`/`feedback_ids` link a requested assessment. It creates a new version and preserves the base. Correct source facts via the stable experience ID; change this resume's emphasis in its own version. Corrections/exclusions affect future use without rewriting historical snapshots.

Normal `factual_status:draft` describes progress, not missing approval. Legacy confirmation records remain historical; never manufacture `--human-confirmed` to permit drafting or preview. Deliver a complete local Markdown/DOCX/PDF for user edits before any external sending. Review omissions, scope, chronology, density, hierarchy and every rendered page.

For a primary job, offer `resume workflow --job-id <id> --resume-id <id>` for exact-version review and practice; neither is a prerequisite to writing or export. User-deferred steps stay pending. Use a fresh packet; never reuse a base grade. `resume history --id <id>` retains sources/revision causes. Current plus three historical Markdown files per job are retained; cleanup uses dry-run and touches only registered Markdown. Named-destination authorization is required for external sending.

For a partial wording edit inside a group, shared paragraphs without individual source attribution are retained; explicitly source-owned paragraphs can be replaced locally. To rewrite shared prose, submit the complete group rather than assuming the runtime can infer sentence ownership. Keep per-bullet experience IDs when known. This is Agent bookkeeping, never another question or approval for the user. Actual source corrections remove affected old prose before rebuilding.
