# Resume provenance and revisions

Before composing/reviewing, verify every claim against approved experience/profile facts: dates, metrics, titles, tools and personal ownership must exist in the source. Selected experiences must cover analysis items marked `met`. Resume file hashes are not a confirmation or review gate. Label the draft local and unsubmitted.

## Direct tailored composition

Read the experience index before selecting details. Analyse the company's context, role purpose and 2–4 deliverables. Choose the facts that demonstrate those deliverables, then write the version for this role. Preserve personal/team contribution boundaries; stronger phrasing is encouraged when defensible in interview.

`resume compose --job-id <id> --file <json>` accepts `reason`, optional `headline`, nonempty `sections`, and optional source-mapped `summary`. A section has `experience_id`, optional display `title`, and `bullets` using the same claim contract below. Changing the title requires `title_claim` with matching text and its source mapping, so a display label cannot create seniority. Summary uses a claim object plus selected `experience_ids`; an unsupported free-text summary is rejected. Do not place local file paths, private source metadata or open questions in candidate-facing content. Structured context exports only public organisation/location/date fields.

```json
{
  "reason": "突出目标岗位的数据整理与报告交付",
  "headline": "数据分析实习生",
  "sections": [{
    "experience_id": 1,
    "bullets": [{
      "text": "使用 Python 完成数据整理与报告交付",
      "source_texts": ["用 Python 整理数据并输出报告"],
      "change_type": "wording_only",
      "new_facts": [],
      "change_reason": "保持工具和职责，突出岗位交付"
    }]
  }]
}
```

## Revision input

`resume revise --file <json>` requires `base_resume_id`, `reason`, nonempty `sections`; optional `review_id`/`feedback_ids` link the cause. Each section names one `experience_id`. Each bullet contains one-line `text` and nonempty exact `source_texts` from that same experience's actions, outcomes or evidence claims.

A revision creates a new resume and preserves the base. Exact actions/outcomes inherit factual approval. A professional rewrite may declare `change_type:wording_only`, `new_facts:[]` and a nonempty `change_reason`, with exact source quotations. This is the Agent's explicit semantic classification, not automatic semantic verification. The runtime checks mappings and a limited set of number/tool/scope markers; it cannot prove every rewrite faithful. Never label added facts as wording-only merely to bypass approval.

For added duties, numbers, dates, tools, ownership or effects use `change_type:new_facts` plus a nonempty `new_facts` array naming additions. These changes remain `pending` for one consolidated factual check. Unclassified semantic changes also remain pending. Do not force exact KPIs when qualitative results or user-approved approximations suffice. Direct self-report counts as evidence; attachments are optional.

Show pending additions completely, then require direct user factual confirmation before `resume confirm --id <id> --human-confirmed`. Every final draft still needs whole-draft user review. `claim_map` retains source text, experience version, classification and additions; an approved wording revision still needs a fresh job-specific review. Corrections/exclusion invalidate dependent snapshots rather than rewriting historical files. Rebuild from corrected current facts before preparing an application packet.

Inspect `resume history --id <id>` for base, review, feedback and claim mappings. Obtain a fresh review packet for the new ID and follow [the analysis/review contract](../../job-analysis/references/analysis-contract.md); never reuse the base grade. Metadata for pruned historical Markdown remains available. `resume cleanup --all --dry-run` previews descriptive renaming and retention; `--apply` touches only registered Markdown inside the configured output root, never PDF/DOCX/photos. New saves prune only after successful persistence. External upload, publication or submission requires authorization for the named destination.
