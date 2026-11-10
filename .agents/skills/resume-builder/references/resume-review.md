# Resume composition and continuity

Use clear user reports and current profile/experience facts. Dates, tools, titles, metrics and personal ownership must stay within those facts. Professional rewriting, synthesis and transferable framing are normal drafting, without per-experience approval, exact-quote work for the user or repeated confirmations. Preserve originals and sources in the background; do not label model guesses as user reports. Draft/export remains local and unsubmitted.

For an imported resume, `resume input --id <id>` returns numbered extracted lines. Compare PDF/DOCX warnings with the original; OCR is outside this command. `resume rewrite --input-id <id> --file <json>` takes `reason`, `display_name`, `identity_line_ids`, optional `contact` and `contact_line_ids`, and nonempty `sections`. Each section has `heading` and nonempty `paragraphs`; every paragraph has `text`, `source_line_ids` referencing actual imported lines and optional `style:entry|meta|bullet|text` for the rendered hierarchy. Example: `{"reason":"突出真实工作","display_name":"林青","identity_line_ids":[1],"sections":[{"heading":"工作经历","paragraphs":[{"text":"整理客户反馈并交付需求清单。","source_line_ids":[5]}]}]}`. This records provenance, not semantic proof: verify facts, role boundaries and metrics against the original and newer user corrections. The receipt reports uncovered line IDs. Add `--base-resume-id` when revising the same import; keep the same target job. Imported documents are not automatically merged into the experience library.

## Complete inventory and presentation

Use one composition workflow. First reuse user requirements and saved career-mapping, search and analysis context. If a primary job exists, read its complete JD before the full experience index; its purpose, 2–4 deliverables and gates control the resume. Optional comparable JDs enrich role interpretation and customary work only; do not import their employers' gates or invent primary-job requirements. Then read every index page and fetch semantically selected details in bounded batches. `resume tailor-packet --job-id <id> [--reference-job-ids <id> ...] --offset <n> --budget <chars>` provides context and paginated index/details requests; follow `next_offset` until complete. Without a primary job, one or more reference JDs can support a direction draft, but do not bind vacancy-specific analysis or application records until an actual job is chosen. Select evidence semantically, never by text similarity or keyword proxy.

Select relevant evidence and necessary career chronology anchors after reading the complete index; inclusion is the Agent's semantic judgment. Expand relevant work and briefly present a stage only when it serves the target or explains necessary continuity. Unrelated school-period jobs can be omitted; do not restore every unused experience. Keep work in reverse chronology; selected projects may prioritise relevance while retaining dates and organisation. Real gaps/overlaps are allowed. Honour explicit exclusions without repeatedly asking. The user reviews the complete output and requests edits.

Respect the user's chosen layout. A supplied personal reference remains that user's preference, not a global requirement. Present identity/contact and known availability in the header, personal strengths with skills/certificates as subsections, and education. Work, projects and internships are optional where needed. Keep each project's dates, ownership and links together, education present and empty sections absent. Academic research, presentations and academic-English work belong inside the matching degree, not a standalone other-experience section. No internal source IDs, evidence ratings, open questions or private paths belong in the resume body.

## CLI composition contract

`resume compose [--job-id <id>] [--reference-job-ids <id> ...] [--target-title <label>] --file <json>` accepts `reason`, optional `headline`, `sections`, source-mapped `summary`/`profile_sections`, and `education_entries`. `--reference-job-ids` may accompany a primary `--job-id` or support a direction draft without one; `--target-title` is for that no-primary direction. Runtime saves Agent-authored context and JD snapshots; it does not judge semantic commonality or select evidence with keywords. The primary JD controls job-specific requirements; references only enrich interpretation. A section uses `experience_id(s)`, optional title/category, `mode:expanded|brief`, explicit `bullets` and links. Expanded sections require actual model-written bullets. A brief section may use explicit `bullets: []` for a title/date anchor; missing prose never falls back to the first raw fact. Bullet strings or claim objects are accepted. Claim fields `source_texts`, `change_type`, `new_facts` and `change_reason` preserve background provenance; sources need not be quoted.

Only selected sections are composed; unused experiences are not automatically restored. Optional `exclude_experience_ids` records explicit per-document omissions, while `selection_notes` stores internal model reasoning about choices, omissions and timeline anchors. Neither field belongs in candidate-facing content. Categories are `工作经历`, `项目经历`, `实习经历` and `教育经历`; `经营经历` is accepted as a work alias and `其他经历` is rejected. Display titles may be rewritten within true role/scope; a heading cannot invent seniority. Optional `section_order` preserves requested ordering or inherits the saved profile preference.

`education_entries` contains `{key, title, meta?, paragraphs?: [text]}` objects with stable local keys for the degrees shown. An academic experience section requires the matching `education_key` and renders inside that degree. Inspect all known education for complete names, dates and degree associations; do not scatter academic work across independent project/other sections. Profile paragraphs can be strings or objects with `text` and optional `source_texts`; naturally rewrite actual profile facts instead of copying a fixed summary verbatim. Public links must retain their actual source and correct experience association.

Template selection is `data.template` → `profile.resume_preferences.template` → `reference`, and the resolved choice is stored in the resume snapshot. Registered exports use this stored choice unless explicitly overridden. This resume default does not change generic structured document export's `modern-cn` default.

```json
{
  "reason": "将门店经营中的采购与库存工作接到运营交付",
  "template": "reference",
  "education_entries": [{"key": "degree-1", "title": "示例大学｜示例专业｜本科", "meta": "2014—2018"}],
  "sections": [{
    "experience_id": 1,
    "category": "工作经历",
    "mode": "expanded",
    "bullets": ["负责日常采购与补货安排，结合库存情况调整进货"]
  }]
}
```

This fictional contract excerpt assumes those actions and education were reported; it is not a complete candidate draft or evidence about any real user. Do not invent cost savings or tools. Use STAR-C (Situation, Task, Action, Result, Challenge/Contribution) as a compact value-writing lens: make actual contribution, constraints and reusable outcomes clear where known. Do not force five-part paragraphs or invent metrics, seniority or results. If a fact is unclear, draft around what is known; one unresolved detail does not block the whole resume. A new term or polished phrase alone is not evidence of an added fact.

The STAR-C framing is informed by [this resume-writing article](https://blog.csdn.net/SJ_HP/article/details/162490861); use its structure as a writing aid only. Do not adopt claims of inferred metrics, tool ratings or performance estimates as evidence about a candidate.

## Revision, assessment and export

After composing, read the completed version through `resume editorial-packet --resume-id <id>` and compare the actual draft with the target JD, references and current evidence. The compose receipt returns `editorial_review_required: true`. Record the model's actual review with `resume editorial-review --file <json>`:

```json
{
  "resume_id": 3,
  "verdict": "revise",
  "findings": ["将研究生期间的研究内容移入对应学位，并核对本人贡献表述。"],
  "checked": {"jd_focus": true, "timeline": true, "education_placement": true, "star_c": true, "template": true, "factuality": true}
}
```

Use `ready` only after actually reading the finished version and resolving material findings; `checked` records completed checks, not automated proof. Never save fake readiness or claim editorial review from successful composition, lint or export. Revise and reread the new version when corrections are required. The receipt is an actual model writing review, separate from job-specific simulated hiring ratings. It adds no user approval or export gate.

`resume revise --file <json>` requires `base_resume_id`, `reason`, `sections`; optional `review_id`/`feedback_ids` link a requested assessment. It creates a new version and preserves the base. Correct source facts via the stable experience ID; change this resume's emphasis in its own version. Corrections/exclusions affect future use without rewriting historical snapshots.

Normal `factual_status:draft` describes progress, not missing approval. Legacy confirmation records remain historical; never manufacture `--human-confirmed` to permit drafting or preview. Deliver a complete local Markdown/DOCX/PDF for user edits before any external sending. Review omissions, scope, chronology, density, hierarchy and every rendered page.

For a primary job, offer `resume workflow --job-id <id> --resume-id <id>` for exact-version review and practice; neither is a prerequisite to writing or export. User-deferred steps stay pending. Use a fresh packet; never reuse a base grade. `resume history --id <id>` retains sources/revision causes. Current plus three historical Markdown files per job are retained; cleanup uses dry-run and touches only registered Markdown. Named-destination authorization is required for external sending.

For a partial wording edit inside a group, shared paragraphs without individual source attribution are retained; explicitly source-owned paragraphs can be replaced locally. To rewrite shared prose, submit the complete group rather than assuming the runtime can infer sentence ownership. Keep per-bullet experience IDs when known. This is Agent bookkeeping, never another question or approval for the user. Actual source corrections remove affected old prose before rebuilding.
