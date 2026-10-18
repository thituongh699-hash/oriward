---
name: document-export
description: Convert an already-generated CareerOS resume, or a reviewed career plan, into editable DOCX and readable PDF files, then check the rendered pages. Use for local format conversion only, not for inventing facts, submitting applications or editing arbitrary Word templates.
---

# Career document export

Turn content that already exists into a local DOCX and PDF. This is a format conversion step, not a place to write, revise or approve career content.

## Choose the source

- For a resume, use the exact resume ID produced by `resume build` (or a confirmed revision). Do not retype its facts into a new model-authored document.
- For a learning plan, application plan, interview note or report, prepare the structured JSON described in [references/export-contract.md](references/export-contract.md). Read only the records needed for the document; keep actual feedback, mock feedback and hypotheses labelled.
- Resumes must go through `--resume-id`. A structured input that looks like a resume is refused so a hand-written version cannot pass as a registered one.
- If the wording itself needs to change, go back to `resume-builder` or the relevant career skill first, then export again.

## Generate

1. Use the interpreter selected by the host. Run `scripts/export_documents.py --probe` before choosing a backend. Install the project's `documents` optional dependencies only if the host lacks them; the core CLI must keep working without them.
2. For PDF, use an embeddable local font that covers the document text. Let the helper discover one, or pass `--font <path>` after checking it. Do not replace missing Chinese characters, suppress missing-glyph errors, or download an unknown-licence font.
3. Write to a new directory under `outputs/`, for example `outputs/documents/<name>-<date>`. Never overwrite an earlier export.

```text
python .agents/skills/document-export/scripts/export_documents.py --resume-id <ID> --output-dir <new-directory>
python .agents/skills/document-export/scripts/export_documents.py --input <reviewed-json> --output-dir <new-directory>
```

4. Reopen both outputs and `manifest.json`. Confirm titles, paragraphs, bullets and table cells agree with the source. DOCX and PDF are laid out independently; pagination may differ.

## Check the pages

- Render the PDF with a local renderer and inspect every page for missing glyphs, clipping, overlap, tiny text, broken tables and blank pages.
- Open the DOCX in a local office renderer or the host's document preview and inspect it too. A valid ZIP/XML or extractable text does not prove the layout is fine.
- A successful command means the files were generated, not that the layout was reviewed. Report what was inspected and what remains unchecked.
- If a renderer or font is unavailable, name the missing capability and keep the drafts. Do not rename another file type to claim a successful conversion.

## Boundaries

- Conversion does not create or change any CareerOS record: it does not confirm a claim, change a review grade, complete an action or record an application.
- No export authorises upload, email, login or submission; files stay local unless the user asks otherwise.
- Report the output paths, the source resume or input, and any remaining visual check.
