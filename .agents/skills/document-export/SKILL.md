---
name: document-export
description: Convert existing registered Oriward resumes or reviewed career plans into editable DOCX and PDF with reusable Chinese resume templates. For local conversion only, not content revision or submission.
---

# Career Document Export

Convert approved content; return to the relevant career skill if wording needs revision.

1. For resumes use the registered `--resume-id`. Never invent or rewrite claims during layout. Source freshness and factual approval must pass.
2. For plans and reports, read [references/export-contract.md](references/export-contract.md) and provide reviewed JSON with meaningful source dates and actual/mock/hypothesis labels.
3. Run from the repository root with the host Python and optional document dependencies. `--probe` checks availability without writing.
4. Pick `--template modern-cn` for the optional portrait layout or `--template clean` for a restrained no-photo layout. Interests should be last and omitted when absent. Never synthesize missing sections or facts.
5. Export to a new output directory. `--renderer auto` prefers Word, then LibreOffice, to render the editable DOCX as PDF; it falls back to ReportLab and records the renderer. `--renderer reportlab` selects that fallback directly. Explicit `word` or `libreoffice` choices fail if unavailable.

```text
python .agents/skills/document-export/scripts/export_documents.py --resume-id <ID> --output-dir outputs/<new-dir> --template clean
python .agents/skills/document-export/scripts/export_documents.py --input <reviewed-json> --output-dir outputs/<new-dir> --template modern-cn --photo <local-image>
```

Templates target A4, 16-18 mm margins, 20 pt name, 12.5 pt section headings and at least 10 pt body text. The `a4-1-2` policy allows one- or two-page resumes; `a4-1` rejects larger resume PDFs rather than shrinking type. Use an embeddable local CJK font covering all text. Missing glyphs remain errors; do not download fonts with unknown licences.

Reopen DOCX/PDF and compare content to source. Render and inspect all pages and inspect DOCX through Word, LibreOffice or the host preview. Text extraction and generation status do not establish visual quality. `manifest.json` names the template, page policy, renderer and files. Samples under `docs/assets/resume-templates/` are wholly fictional; regenerate using `scripts/generate_template_samples.py`.

Conversion does not create or change any Oriward record and never submits applications. Report paths and any renderer or visual-review limits.
