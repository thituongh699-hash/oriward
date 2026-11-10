import os
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from oriward import resume_workbench as workbench, services, sources
from oriward.db import connect


class ResumeWorkbenchTests(unittest.TestCase):
    def test_align_command_is_removed(self):
        result = subprocess.run([sys.executable, "-m", "oriward", "resume", "align", "--help"],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)
        self.assertFalse(hasattr(workbench, "align_import"))

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        environment = patch.dict(os.environ, {"ORIWARD_DB": str(self.root / "test.sqlite3"),
                                            "ORIWARD_OUTPUT_DIR": str(self.root / "resumes")})
        environment.start()
        self.addCleanup(environment.stop)

    def _text_input(self, suffix=".txt"):
        path = self.root / ("fictional" + suffix)
        path.write_text("林青\nfiction@example.invalid\n工作经历\n2024-2025 虚构公司\n"
                        "参与了客户反馈整理，并交付需求清单。\n教育经历\n虚构大学 本科 2024\n", encoding="utf-8")
        return workbench.import_resume(path)

    def test_text_import_diagnosis_and_complete_revision(self):
        imported = self._text_input()
        self.assertEqual(imported["line_count"], 7)
        diagnosis = workbench.diagnose(input_id=imported["input_id"])
        self.assertTrue(any(issue["kind"] == "action_or_ownership" and issue["location"]["line_ids"] == [5]
                            for issue in diagnosis["issues"]))
        self.assertIsNone(diagnosis["score"])
        source = workbench.input_record(imported["input_id"])
        self.assertTrue(Path(source["private_path"]).is_file())
        self.assertNotIn("outputs", source["private_path"])
        job_id = sources.import_records([{"source": "fixture", "source_id": "role", "title": "产品经理",
            "company": "虚构岗位公司", "description": "负责需求分析与用户研究。",
            "url": "https://example.invalid/role"}])["job_ids"][0]
        targeted = workbench.diagnose(input_id=imported["input_id"], job_id=job_id)
        self.assertTrue(any(issue["kind"] == "role_alignment" for issue in targeted["issues"]))
        draft = {"reason": "按真实动作整理完整简历", "display_name": "林青", "identity_line_ids": [1],
                 "contact": "fiction@example.invalid", "contact_line_ids": [2],
                 "sections": [
                     {"heading": "工作经历", "paragraphs": [{"text": "2024-2025 虚构公司", "source_line_ids": [4], "style": "entry"},
                                                   {"text": "整理客户反馈并交付需求清单。", "source_line_ids": [5]}]},
                     {"heading": "教育经历", "paragraphs": [{"text": "虚构大学 本科 2024", "source_line_ids": [7]}]}]}
        first = workbench.rewrite_import(imported["input_id"], draft, job_id=job_id)
        self.assertIn("整理客户反馈", Path(first["path"]).read_text(encoding="utf-8"))
        self.assertEqual(first["factual_status"], "draft")
        corrected = {**draft, "sections": [dict(section) for section in draft["sections"]]}
        corrected["sections"][0] = {**corrected["sections"][0], "paragraphs": [
            corrected["sections"][0]["paragraphs"][0],
            {"text": "参与整理客户反馈，并交付需求清单。", "source_line_ids": [5]}]}
        second = workbench.rewrite_import(imported["input_id"], corrected, base_resume_id=first["id"])
        self.assertNotIn("参与整理客户反馈", Path(first["path"]).read_text(encoding="utf-8"))
        self.assertIn("参与整理客户反馈", Path(second["path"]).read_text(encoding="utf-8"))
        from oriward.feedback import version_history
        self.assertEqual(len(version_history(second["id"])), 2)
        self.assertEqual(workbench.diagnose(resume_id=second["id"])["source"]["type"], "resume")
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM experiences").fetchone()[0], 0)
        self._check_export(second["id"])

    def _check_export(self, resume_id):
        try:
            import pypdf
            import docx  # noqa: F401
            import reportlab  # noqa: F401
        except ImportError:
            self.skipTest("Optional document dependencies unavailable")
        script = Path(__file__).resolve().parents[1] / ".agents/skills/document-export/scripts/export_documents.py"
        spec = importlib.util.spec_from_file_location("workbench_export", script)
        exporter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(exporter)
        try:
            manifest = exporter.export_document(resume_id=resume_id, output_dir=self.root / "export",
                                                template="clean", renderer="reportlab")
        except exporter.ExportError as exc:
            if "FONT" in str(exc) or "font" in str(exc).lower():
                self.skipTest(f"No usable CJK font: {exc}")
            raise
        self.assertEqual(manifest["source"]["resume_id"], resume_id)
        self.assertTrue((self.root / "export/document.docx").is_file())
        reader = pypdf.PdfReader(self.root / "export/document.pdf")
        self.assertGreaterEqual(len(reader.pages), 1)
        self.assertIn("整理客户反馈", "\n".join(page.extract_text() or "" for page in reader.pages))

    def test_docx_and_markdown_import_and_invalid_source(self):
        self.assertEqual(self._text_input(".md")["format"], "md")
        path = self.root / "fictional.docx"
        xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
               '<w:body><w:p><w:r><w:t>林青</w:t></w:r></w:p>'
               '<w:p><w:r><w:t>fiction@example.invalid</w:t></w:r></w:p>'
               '<w:p><w:r><w:t>工作经历 2024-2025 虚构公司 整理客户反馈并交付需求清单</w:t></w:r></w:p>'
               '</w:body></w:document>')
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", xml)
        imported = workbench.import_resume(path)
        self.assertEqual(imported["format"], "docx")
        self.assertTrue(imported["warnings"])
        with self.assertRaisesRegex(ValueError, "too little extractable"):
            bad = self.root / "bad.txt"
            bad.write_text("Hi", encoding="utf-8")
            workbench.import_resume(bad)
        with self.assertRaisesRegex(ValueError, "source_line_ids"):
            workbench.rewrite_import(imported["input_id"], {"reason": "test", "display_name": "林青",
                "identity_line_ids": [1], "sections": [{"heading": "工作经历", "paragraphs": [
                    {"text": "编造经历", "source_line_ids": [99]}]}]})

    def test_pdf_import_with_optional_dependency(self):
        try:
            import pypdf  # noqa: F401
        except ImportError:
            self.skipTest("pypdf optional dependency unavailable")
        sample = Path(__file__).resolve().parents[1] / "docs/assets/resume-templates/clean/sample.pdf"
        imported = workbench.import_resume(sample)
        self.assertEqual(imported["format"], "pdf")
        self.assertTrue(imported["warnings"])

    def test_cli_import_diagnose_and_rewrite(self):
        source = self.root / "cli.txt"
        source.write_text("林青\nfiction@example.invalid\n工作经历\n2024 虚构公司\n整理客户反馈并交付清单。\n",
                          encoding="utf-8")

        def run(*arguments):
            result = subprocess.run([sys.executable, "-m", "oriward", "resume", *arguments],
                                    cwd=Path(__file__).resolve().parents[1],
                                    capture_output=True, text=True, encoding="utf-8", check=True)
            return json.loads(result.stdout)

        imported = run("import", "--file", str(source))
        self.assertEqual(run("diagnose", "--input-id", str(imported["input_id"]))["source"]["type"], "import")
        payload = {"reason": "虚构 CLI 测试", "display_name": "林青", "identity_line_ids": [1],
                   "contact": "fiction@example.invalid", "contact_line_ids": [2],
                   "sections": [{"heading": "工作经历", "paragraphs": [
                       {"text": "虚构公司 2024", "source_line_ids": [4], "style": "entry"},
                       {"text": "整理客户反馈并交付清单。", "source_line_ids": [5]}]}]}
        data_file = self.root / "rewrite.json"
        data_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        rewritten = run("rewrite", "--input-id", str(imported["input_id"]), "--file", str(data_file))
        self.assertTrue(Path(rewritten["path"]).is_file())
        self.assertEqual(run("market-report", "--days", "30")["status"], "observation_only")

    def test_market_report_deduplicates_snapshots_and_employers(self):
        current = datetime.now(timezone.utc).isoformat(timespec="seconds")
        records = [{"source": "fixture", "source_id": str(index), "title": "产品经理", "company": f"虚构公司{index}",
                    "description": "负责需求分析和产品规划；熟悉 Kubernetes 集群。", "url": f"https://example.invalid/{index}",
                    "retrieved_at": current} for index in range(3)]
        sources.import_records(records[:2])
        low_sample = workbench.market_observations(days=30, family="product")
        self.assertFalse(next(item for item in low_sample["signals"] if item["requirement"] == "需求分析")["candidate"])
        sources.import_records(records[2:])
        sources.import_records(records)
        report = workbench.market_observations(days=30, family="product")
        signal = next(item for item in report["signals"] if item["requirement"] == "需求分析")
        self.assertEqual(signal["current_jobs"], 3)
        self.assertEqual(signal["current_employers"], 3)
        self.assertTrue(signal["candidate"])
        self.assertTrue(signal["new_in_window"])
        self.assertFalse(report["profile_updated"])
        self.assertEqual(report["emerging_phrases"][0]["requirement_phrase"], "kubernetes")
        old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat(timespec="seconds")
        sources.import_records([{"source": "fixture", "source_id": "old", "title": "产品经理", "company": "虚构旧公司",
                                 "description": "负责需求分析。", "url": "https://example.invalid/old", "retrieved_at": old}])
        report = workbench.market_observations(days=30, family="product")
        signal = next(item for item in report["signals"] if item["requirement"] == "需求分析")
        self.assertEqual(signal["previous_jobs"], 1)
        self.assertFalse(signal["new_in_window"])

    def test_targeted_workflow_keeps_rating_and_practice_on_exact_version(self):
        from oriward import assessment, resume_content
        services.save_profile({"display_name": "虚构候选人"})
        jobs = sources.import_records([{"source": "fixture", "source_id": str(i),
            "title": "产品经理", "company": f"虚构公司{i}", "description": "整理用户反馈。",
            "url": f"https://example.invalid/workflow/{i}"} for i in range(2)])["job_ids"]
        job_id, other = jobs
        with patch.object(workbench, "diagnose", side_effect=AssertionError("Text lint must be optional")):
            start = workbench.workflow(job_id=job_id)
        self.assertEqual(start["stage"], "target_required")
        self.assertEqual(start["reasoning_owner"], "host_agent")
        self.assertIn("document_export", [stage["id"] for stage in start["stages"]])
        imported = self._text_input()
        with patch.object(workbench, "diagnose", side_effect=AssertionError("Text lint must be optional")):
            imported_flow = workbench.workflow(job_id=job_id, input_id=imported["input_id"])
        self.assertEqual(imported_flow["stage"], "rewrite_pending")
        self.assertIn("resume tailor-packet", imported_flow["next"][1])
        self.assertIn("optional_text_check", imported_flow)
        with self.assertRaisesRegex(services.ValidationError, "not found"):
            workbench.workflow(job_id=job_id, input_id=99999)
        exp = services.add_object("experiences", {"event": "反馈整理", "actions": ["整理用户反馈。"]}, ["event"])
        draft = resume_content.compose(job_id, {"reason": "定向稿", "sections": [{"experience_id": exp, "bullets": ["整理用户反馈。"]}]})
        rid = draft["id"]
        self.assertIn("resume workflow", draft["workflow"]["command"])
        self.assertEqual(workbench.workflow(job_id=job_id, resume_id=rid)["rating"]["status"], "waiting_for_job_analysis")
        analysis = assessment.draft_analysis(job_id)
        aid = assessment.save_analysis(analysis)
        report = workbench.workflow(job_id=job_id, resume_id=rid)
        self.assertEqual(report["rating"]["status"], "ready")
        review = report["review_packet"]["review_template"]
        self.assertEqual(review["analysis_id"], aid)
        review["stages"]["ats"]["requirement_ids"] = [r["id"] for r in analysis["requirements"]]
        assessment.save_review(review)
        reviewed = workbench.workflow(job_id=job_id, resume_id=rid)
        self.assertEqual(reviewed["rating"]["status"], "completed")
        self.assertEqual(reviewed["stage"], "mock_interview_pending")
        practice = {"job_id": job_id, "resume_id": rid, "questions": ["你做了什么？"],
                    "practice": [], "next_actions": []}
        services.add_object("interviews", practice, ["job_id", "questions", "practice", "next_actions"])
        self.assertEqual(workbench.workflow(job_id=job_id, resume_id=rid)["mock_interview"]["status"], "ready")
        practice["practice"] = [{"question": "你做了什么？", "answer": "我整理反馈。", "feedback": "补充方法"}]
        services.add_object("interviews", practice, ["job_id", "questions", "practice", "next_actions"])
        self.assertEqual(len(workbench.workflow(job_id=job_id, resume_id=rid)["mock_interview"]["records"]), 1)
        self.assertEqual(workbench.workflow(job_id=job_id, resume_id=rid)["stage"], "feedback_and_application")
        with self.assertRaisesRegex(ValueError, "must match"):
            services.add_object("interviews", {**practice, "job_id": other}, ["job_id"])
        with self.assertRaisesRegex(ValueError, "must match"):
            workbench.workflow(job_id=other, resume_id=rid)
        new = resume_content.compose(job_id, {"reason": "新版本", "sections": [{"experience_id": exp, "bullets": ["整理用户反馈。"]}]})
        fresh = workbench.workflow(job_id=job_id, resume_id=new["id"])
        self.assertEqual(fresh["rating"]["status"], "ready")
        self.assertEqual(fresh["mock_interview"]["records"], [])
        # A new analysis invalidates the old rating; an updated JD also needs new analysis.
        assessment.save_analysis(analysis)
        self.assertEqual(workbench.workflow(job_id=job_id, resume_id=rid)["rating"]["status"], "ready")
        sources.import_records([{"source": "fixture", "source_id": "0", "title": "产品经理", "company": "虚构公司0",
            "description": "整理用户反馈。\n补充新要求。", "url": "https://example.invalid/workflow/0"}])
        self.assertEqual(workbench.workflow(job_id=job_id, resume_id=rid)["rating"]["status"], "waiting_for_job_analysis")
        general = resume_content.compose(None, {"reason": "底稿", "sections": [{"experience_id": exp, "bullets": ["整理用户反馈。"]}]})
        self.assertEqual(general["workflow"]["mode"], "baseline_only")
        with connect() as db:
            general_job = db.execute("SELECT job_id FROM resumes WHERE id=?", (general["id"],)).fetchone()[0]
        with self.assertRaisesRegex(ValueError, "real vacancy"):
            workbench.workflow(job_id=general_job, resume_id=general["id"])


if __name__ == "__main__":
    unittest.main()
