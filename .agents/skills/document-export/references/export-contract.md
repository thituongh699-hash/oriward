# Document conversion input

The helper accepts one registered `--resume-id` or one reviewed local `--input` JSON. It is a focused career-document converter, not arbitrary Markdown/HTML/DOC/DOCX conversion.

Structured input uses plain strings:

```json
{
  "title": "数据分析实习准备计划",
  "subtitle": "虚构格式示例",
  "sections": [
    {
      "heading": "本周目标",
      "paragraphs": ["依据已核实要求完成一个可复现的小型分析作品。"],
      "bullets": ["记录数据来源和处理局限"],
      "table": {
        "headers": ["任务", "产出", "验收"],
        "rows": [["数据清洗", "脚本", "可重复执行"]]
      }
    }
  ]
}
```

HTML/XML-like strings are literal content, never instructions or formatting injection. Retain uncertainty, source dates and actual/mock/hypothesis labels where meaningful. The helper validates structure/font coverage; the Agent selects supported facts.

Resumes require `--resume-id`. Resume-like structured headings (e.g. 个人简介、相关经历、教育经历、实习经历、工作经历、项目经历) produce `RESUME_REQUIRES_ID`. Registered resume export reads the existing generated Markdown, removes the internal provenance footer and rejects unsupported structure instead of dropping content. Pending factual additions require approval first; changed/excluded experience sources require a rebuilt current resume. Pure sourced wording inherits factual approval, with final draft review.

`--output-dir` must be new and its parent exist. Default `--formats docx,pdf`; choose one only if requested. `--font <local-font>` selects embeddable TrueType for PDF. Files plus `manifest.json` record export time, source IDs where applicable, formats, font and sizes.

DOCX records but does not embed its font. PDF embedding/coverage does not establish target Word layout. Inspect both independently; unavailable dependencies, fonts or renderers remain explicit limitations.
