---
name: document-export
description: Convert an existing registered Oriward resume or reviewed career plan into editable DOCX and readable PDF, then inspect rendered pages. Use for local format conversion, not content revision, arbitrary Word templates or application submission.
---

# Career document export

Convert existing approved content. If wording needs revision, return to the relevant career skill first.

1. For resumes use the exact registered `--resume-id` from `resume build` or an approved revision. Do not retype claims into structured input; resume-like input is refused.
2. For plans, interview notes or reports, load [references/export-contract.md](references/export-contract.md) and prepare reviewed `--input` JSON, retaining source dates and actual/mock/hypothesis labels.
3. From the repository root, use the host-selected interpreter to run `python .agents/skills/document-export/scripts/export_documents.py --probe`. Use the project's optional document dependencies only if needed; core CLI operation must remain independent.
4. Select an embeddable local PDF font covering all text. Let the helper discover one or pass a checked `--font`. Never replace missing Chinese characters, suppress missing-glyph errors or download an unknown-licence font.
5. Export to a new directory under `outputs/`; never overwrite an earlier export.

```text
python .agents/skills/document-export/scripts/export_documents.py --resume-id <ID> --output-dir <new-directory>
python .agents/skills/document-export/scripts/export_documents.py --input <reviewed-json> --output-dir <new-directory>
```

Reopen both files and `manifest.json`; check titles, paragraphs, bullets and table cells against the source. Render and inspect every PDF page and the DOCX through a local office renderer or host preview for missing glyphs, clipping, overlap, tiny text, broken tables and blank pages. Layouts are independent and pagination may differ; valid XML or extracted text does not prove visual quality.

Generation is not visual approval. If a font or renderer is unavailable, retain drafts and report the missing capability and unperformed checks; never rename another format to claim success.

Conversion does not create or change any Oriward record: it confirms no claim, changes no grade, completes no action and records no application. Upload, email, login and submission need separate authorization. Report output paths, source ID/input and visual inspection limits.
