---
name: document-export
description: Convert existing registered Oriward resumes or career plans into editable DOCX and PDF with reusable Chinese resume templates. For local conversion only, not content revision or submission.
---

# Career Document Export

Convert existing drafts and revisions for local reading; return to the relevant career skill if wording needs revision. No factual approval or simulated hiring review is required for preview.

1. For resumes use the registered `--resume-id`. Never invent or rewrite claims during layout. Keep source/version diagnostics in the manifest; historical or pending drafts remain exportable without changing their recorded status.
2. For plans and reports, read [references/export-contract.md](references/export-contract.md) and provide structured JSON with meaningful source dates and actual/mock/hypothesis labels.
3. Run from the repository root with the host Python and optional document dependencies. `--probe` checks availability without writing.
4. Use `--template modern-cn` as the generic default. Honor a user's established personal template preference, including explicit `--template reference` for the supplied `个人参考 PDF`; `--photo` adds a supplied portrait where available. `clean` also remains available. Preserve the source section order and chronological/grouped experience headings; do not force every user into a fixed student section order. Keep each role/title, period, bullets and project link together. Never synthesize missing sections or facts.
5. Export to a new output directory. `--renderer auto` prefers Word, then LibreOffice, to render the editable DOCX as PDF; it falls back to ReportLab and records the renderer. `--renderer reportlab` selects that fallback directly. Explicit `word` or `libreoffice` choices fail if unavailable.

```text
python .agents/skills/document-export/scripts/export_documents.py --resume-id <ID> --output-dir outputs/<new-dir> --template modern-cn
python .agents/skills/document-export/scripts/export_documents.py --input <structured-json> --output-dir outputs/<new-dir> --template modern-cn --photo <local-image>
```

Templates target A4, a 20 pt name, 12.5 pt section headings and at least 10 pt body text. The reference template uses tighter margins from the supplied PDF and `a4-1-3` permits up to three pages to preserve all included experiences without shrinking type; `a4-1-2` and `a4-1` remain available for explicit one/two-page limits. Use an embeddable local CJK font covering all text. Missing glyphs remain errors; do not download fonts with unknown licences.

Reopen DOCX/PDF and compare content to source. Render and inspect all pages and inspect DOCX through Word, LibreOffice or the host preview. Check first-page density, category/project hierarchy, right-aligned dates, page balance and headings that would otherwise be orphaned. Text extraction and generation status do not establish visual quality. `manifest.json` names the template, page policy, renderer and files. Samples under `docs/assets/resume-templates/` are wholly fictional; regenerate using `scripts/generate_template_samples.py`.

Conversion does not create or change any Oriward record and never submits applications. Report paths and any renderer or visual-review limits.
