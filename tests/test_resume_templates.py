import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path

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

    def test_both_templates_record_layout_and_renderer(self):
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
        if "libreoffice" in dict(exporter._renderer_candidates()):
            result = exporter.export_document(document=self.doc, output_dir=self.root / "lo", renderer="libreoffice")
            self.assertEqual(result["renderer"]["pdf"], "LibreOffice")
        else:
            with self.assertRaisesRegex(exporter.ExportError, "RENDERER_UNAVAILABLE"):
                exporter.export_document(document=self.doc, output_dir=self.root / "lo", renderer="libreoffice")
        result = exporter.export_document(document=self.doc, output_dir=self.root / "one-page", page_policy="a4-1")
        self.assertEqual(result["page_policy"], "a4-1")

    def test_optional_photo_is_embedded_only_in_modern_template(self):
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
        target = self.root / "photo"
        exporter.export_document(document=self.doc, output_dir=target, formats=("docx",),
                                 template="modern-cn", photo=photo)
        self.assertEqual(len(docx.Document(target / "document.docx").inline_shapes), 1)

    def test_bundled_samples_are_fictional_and_have_no_external_file_links(self):
        import xml.etree.ElementTree as ET
        for template in exporter.TEMPLATES:
            folder = ROOT / "docs/assets/resume-templates" / template
            manifest = (folder / "manifest.json").read_text(encoding="utf-8")
            self.assertIn('"fictional": true', manifest)
            self.assertNotIn(str(ROOT), manifest)
            with zipfile.ZipFile(folder / "sample.docx") as package:
                for name in package.namelist():
                    if name.endswith(".rels"):
                        rels = ET.fromstring(package.read(name))
                        self.assertFalse(any(item.attrib.get("TargetMode") == "External" for item in rels))
                all_xml = b"\n".join(package.read(name) for name in package.namelist() if name.endswith(".xml"))
                self.assertNotIn(str(ROOT).encode(), all_xml)
                self.assertNotIn(b"C:\\Users\\", all_xml)
            from pypdf import PdfReader
            text = "\n".join(page.extract_text() or "" for page in PdfReader(folder / "sample.pdf").pages)
            for heading in ("教育经历", "项目经历", "技能", "兴趣"):
                self.assertIn(heading, text)
            self.assertLess(text.index("技能"), text.index("兴趣"))
            if template == "modern-cn":
                self.assertIn("校园出行问卷分析", text)
                self.assertIn("课程图书借阅观察", text)
                self.assertIn('"renderer": "Microsoft Word"', manifest)


if __name__ == "__main__":
    unittest.main()
