---
name: document-export
description: Convert existing registered Oriward resumes or career plans into editable DOCX and PDF with reusable Chinese resume templates. For local conversion only, not content revision or submission.
---

# Career Document Export

Convert registered drafts for local use; return to the career skill for wording changes. Preview needs no factual approval or hiring review.

1. For resumes use `--resume-id`; never rewrite claims in layout. Keep diagnostics in the manifest; export does not change status.
2. For plans/reports, follow [export-contract](references/export-contract.md) and supply structured JSON with source dates and actual/mock/hypothesis labels.
3. Run from the repository root with the host Python and optional document dependencies. `--probe` checks availability without writing.
4. For registered resumes, use the template stored with that version unless an explicit `--template` overrides it. Composition selects explicit `data.template`, then `profile.resume_preferences.template`, then `reference`; generic structured documents default to `modern-cn`. Honor supplied photos. Preserve source order, degree nesting and experience grouping; impose no universal order, page count or template. Keep ATS-readable text order and each role, dates, bullets and links together. Finish content before export; never invent claims or sections.
5. Export to a new output directory. `--renderer auto` prefers Word, then LibreOffice, to render the editable DOCX as PDF; it falls back to ReportLab and records the renderer. `--renderer reportlab` selects that fallback directly. Explicit `word` or `libreoffice` choices fail if unavailable.

```text
python .agents/skills/document-export/scripts/export_documents.py --resume-id <ID> --output-dir outputs/<new-dir>
python .agents/skills/document-export/scripts/export_documents.py --input <structured-json> --output-dir outputs/<new-dir> --template modern-cn --photo <local-image>
```

Use A4 with readable hierarchy and a local embeddable CJK font. Missing glyphs remain errors; do not download fonts with unknown licences. Page policies are options, not universal limits.

Reopen files against the source and visually inspect every rendered page for density, hierarchy, dates, breaks and orphan headings. Text extraction alone does not prove layout quality. The manifest records template, renderer and files; samples are fictional.

Conversion does not create or change any Oriward record and never submits applications. Report paths and any renderer or visual-review limits.
