# Structured document input

The helper accepts either one registered `--resume-id` or one local `--input` JSON file. It is a focused career-document converter, not a general Markdown, HTML, legacy DOC or arbitrary DOCX conversion service.

```json
{
  "title": "数据分析实习准备计划",
  "subtitle": "虚构示例 供格式演示",
  "sections": [
    {
      "heading": "本周目标",
      "paragraphs": ["根据已核实的岗位要求，完成一个可复现的小型分析作品。"],
      "bullets": ["整理数据来源与处理规则", "记录结果和局限性"]
    },
    {
      "heading": "行动安排",
      "table": {
        "headers": ["任务", "产出", "验收"],
        "rows": [["数据清洗", "处理脚本", "可重复执行并解释缺失值处理"]]
      }
    }
  ]
}
```

Use plain strings. HTML/XML-looking text is literal document content, never executable instructions or a way to insert formatting. Keep uncertainty, source dates and actual/mock/hypothesis labels in the text whenever they change its meaning. The helper validates structure and font coverage; the Agent remains responsible for choosing supported facts and explaining inferences.

Resumes use `--resume-id` only. A structured input whose headings read like a resume (`个人简介`, `相关经历`, `教育经历`, `实习经历`, `工作经历`, `项目经历`) is refused with `RESUME_REQUIRES_ID`, so a hand-written draft cannot pose as a registered resume.

The required output directory must not exist. `--formats docx,pdf` is the default; request a single format only when the user wants it. `--font <local-font>` selects an embeddable TrueType font for PDF. Outputs are the requested files plus `manifest.json`, which records the export time, the source resume and job IDs where applicable, the formats, the font family and the output file sizes.

For a saved resume, the existing generated Markdown is the content source. The helper supports only its known structure, excludes internal provenance footer text from the applicant-facing document, and reports unsupported structure instead of silently dropping content.

The editable DOCX records a font choice but does not embed the font file. PDF font embedding and text coverage do not guarantee that the target Word installation renders the DOCX identically; inspect both formats independently. A missing package, unsuitable font or renderer must remain a stated limitation, not be turned into a false success.
