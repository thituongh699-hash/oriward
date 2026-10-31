import importlib.util
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents" / "skills" / "document-export" / "scripts" / "export_documents.py"
SPEC = importlib.util.spec_from_file_location("document_export_templates", SCRIPT)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class ResumeTemplateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.doc = {"title": "林青", "subtitle": "数据分析方向 | fictional@example.test", "sections": [
            {"heading": "Training", "paragraphs": ["Fictional University | Statistics | 2022-2026"]},
            {"heading": "Project work", "paragraphs": ["Course survey project", "整理公开样例并汇总结果。"],
             "bullets": ["使用 Python 完成清理和图表制作"]},
            {"heading": "Interests", "bullets": ["徒步"]}]}

    def test_all_templates_record_layout_and_renderer(self):
        try:
            exporter._choose_font(exporter._all_text(exporter._normalise_document(self.doc)), None, require_pdf=True)
        except exporter.ExportError as exc:
            self.skipTest(f"No embeddable local font: {exc}")
        for template in exporter.TEMPLATES:
            output = self.root / template
            manifest = exporter.export_document(document=self.doc, output_dir=output, template=template)
            self.assertEqual(manifest["template"], template)
            self.assertIn(manifest["renderer"]["pdf"], {"Microsoft Word", "LibreOffice", "ReportLab"})
            self.assertNotIn("fallback_reason", manifest["renderer"])
            self.assertTrue((output / "document.docx").is_file())
            self.assertTrue((output / "document.pdf").is_file())

    def test_resume_checks_are_structural_not_keyword_blacklists(self):
        allowed = exporter._normalise_document({"title": "Candidate", "sections": [
            {"heading": "项目经历", "paragraphs": ["分析招聘流程与团队协作"]}]})
        exporter._validate_resume_content(allowed)
        for text, code in (("姓名：[YOUR NAME]", "RESUME_PLACEHOLDER"),
                           (r"文件位于 C:\Users\candidate\resume.docx", "RESUME_LOCAL_PATH")):
            doc = exporter._normalise_document({"title": "Candidate", "sections": [{"paragraphs": [text]}]})
            with self.assertRaisesRegex(exporter.ExportError, code):
                exporter._validate_resume_content(doc)

    def test_renderer_and_page_policy_are_explicit(self):
        try:
            import docx  # noqa: F401 -- optional generation dependency
            import reportlab  # noqa: F401 -- optional generation dependency
            import pypdf  # noqa: F401 -- optional page count dependency
            exporter._choose_font(exporter._all_text(exporter._normalise_document(self.doc)), None, require_pdf=True)
        except ImportError:
            self.skipTest("optional document libraries unavailable")
        except exporter.ExportError as exc:
            self.skipTest(f"No embeddable local font: {exc}")
        if "libreoffice" in dict(exporter._renderer_candidates()):
            result = exporter.export_document(document=self.doc, output_dir=self.root / "lo", renderer="libreoffice")
            self.assertEqual(result["renderer"]["pdf"], "LibreOffice")
        else:
            with self.assertRaisesRegex(exporter.ExportError, "RENDERER_UNAVAILABLE"):
                exporter.export_document(document=self.doc, output_dir=self.root / "lo", renderer="libreoffice")
        result = exporter.export_document(document=self.doc, output_dir=self.root / "one-page", page_policy="a4-1")
        self.assertEqual(result["page_policy"], "a4-1")

    def test_optional_photo_is_embedded_only_in_photo_capable_templates(self):
        try:
            import docx
            exporter._choose_font(exporter._all_text(exporter._normalise_document(self.doc)), None)
        except ImportError:
            self.skipTest("python-docx unavailable")
        except exporter.ExportError as exc:
            self.skipTest(f"No local font: {exc}")
        photo = ROOT / "docs/assets/resume-templates/clean/preview.png"
        if not photo.is_file():
            self.skipTest("bundled preview image unavailable")
        for template in ("modern-cn", "reference"):
            target = self.root / template
            exporter.export_document(document=self.doc, output_dir=target, formats=("docx",),
                                     template=template, photo=photo)
            self.assertEqual(len(docx.Document(target / "document.docx").inline_shapes), 1)
            no_photo = self.root / (template + "-no-photo")
            exporter.export_document(document=self.doc, output_dir=no_photo, formats=("docx",), template=template)
            self.assertEqual(len(docx.Document(no_photo / "document.docx").inline_shapes), 0)
        with self.assertRaisesRegex(exporter.ExportError, "INVALID_PHOTO"):
            exporter.export_document(document=self.doc, output_dir=self.root / "clean-photo", formats=("docx",),
                                     template="clean", photo=photo)

    def test_generator_composes_complete_registered_content_without_markdown_edits(self):
        spec = importlib.util.spec_from_file_location("template_sample_generator", ROOT / "scripts/generate_template_samples.py")
        generator = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(generator)
        except ImportError:
            self.skipTest("Pillow unavailable for sample generator")
        from oriward import resume_content
        with patch.dict(os.environ, {"ORIWARD_DB": str(self.root / "samples.sqlite3"),
                                    "ORIWARD_OUTPUT_DIR": str(self.root / "resumes")}):
            receipt = generator.create_sample_resume()
            text = Path(receipt["path"]).read_text(encoding="utf-8")
            self.assertEqual([line for line in text.splitlines() if line.startswith("## ")],
                             ["## 个人优势", "## 教育经历", "## 项目经历", "## 专业技能", "## 个人兴趣"])
            for expected in ("虚构大学", "统计学学士", "概率统计", "校园出行问卷分析", "2025.03–2025.06",
                             "课程图书借阅观察", "2024.09–2024.12", "Excel 数据透视表", "徒步"):
                self.assertIn(expected, text)
            composition = resume_content.composition_for_resume(receipt["id"])
            self.assertEqual(len(composition["sections"]), 2)
            # The registry digest proves the file is the direct composed artifact.
            import hashlib
            self.assertEqual(receipt["sha256"], hashlib.sha256(Path(receipt["path"]).read_bytes()).hexdigest())

    def test_bundled_samples_are_fictional_and_have_no_external_file_links(self):
        try:
            from pypdf import PdfReader
        except ImportError:
            self.skipTest("pypdf unavailable; run with the documents extra to inspect bundled PDFs")
        import xml.etree.ElementTree as ET
        for template in exporter.TEMPLATES:
            folder = ROOT / "docs/assets/resume-templates" / template
            manifest = (folder / "manifest.json").read_text(encoding="utf-8")
            self.assertIn('"fictional": true', manifest)
            self.assertNotIn(str(ROOT), manifest)
            data = json.loads(manifest)
            self.assertEqual(data["photo_included"], template in {"modern-cn", "reference"})
            self.assertIn(data["renderer"], {"Microsoft Word", "LibreOffice", "ReportLab"})
            with zipfile.ZipFile(folder / "sample.docx") as package:
                for name in package.namelist():
                    if name.endswith(".rels"):
                        rels = ET.fromstring(package.read(name))
                        self.assertFalse(any(item.attrib.get("TargetMode") == "External" for item in rels))
                all_xml = b"\n".join(package.read(name) for name in package.namelist() if name.endswith(".xml"))
                self.assertNotIn(str(ROOT).encode(), all_xml)
                self.assertNotIn(b"C:\\Users\\", all_xml)
                core = ET.fromstring(package.read("docProps/core.xml"))
                values = {item.tag.rsplit("}", 1)[-1]: item.text for item in core}
                self.assertEqual(values["creator"], "Oriward")
                self.assertEqual(values["lastModifiedBy"], "Oriward")
                self.assertEqual(sum(name.startswith("word/media/") for name in package.namelist()),
                                 int(template in {"modern-cn", "reference"}))
            pdf = PdfReader(folder / "sample.pdf")
            self.assertEqual(len(pdf.pages), 1)
            self.assertEqual(pdf.metadata.author, "Oriward")
            self.assertEqual(pdf.metadata.title, "Fictional resume template sample")
            self.assertIsNone(pdf.xmp_metadata)
            self.assertNotIn(str(ROOT), str(pdf.metadata))
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            self.assertNotRegex(text + str(pdf.metadata), r"(?i)\b[a-z]:[\\/]|file://")
            for page in pdf.pages:
                for reference in page.get("/Annots", []):
                    action = reference.get_object().get("/A", {})
                    self.assertNotIn(action.get("/S"), {"/Launch", "/GoToR"})
                    self.assertNotRegex(str(action.get("/URI", "")), r"(?i)^file:|^[a-z]:[\\/]")
            for heading in ("教育经历", "项目经历", "专业技能", "个人兴趣"):
                self.assertIn(heading, text)
            self.assertLess(text.index("技能"), text.index("兴趣"))
            for expected in ("校园出行问卷分析", "课程图书借阅观察", "2025.03", "2024.09", "虚构大学", "fictional@example.test"):
                self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
