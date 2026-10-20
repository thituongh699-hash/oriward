import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oriward import services as s, sources, resume_content as r, feedback
from oriward.db import connect


class TailoredResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"ORIWARD_DB": str(self.root / "test.sqlite3"),
                                     "ORIWARD_OUTPUT_DIR": str(self.root / "resumes")})
        env.start(); self.addCleanup(env.stop)
        s.save_profile({"display_name": "虚构候选人", "contact": {"email": "fiction@example.invalid"}})
        self.eid = s.add_object("experiences", {"event": "数据项目", "actions": ["用 Python 整理数据并输出报告"],
            "outcomes": ["形成可复用流程"], "context": {"period": "2025.01–2025.06", "source": "C:/private/notes", "open_questions": ["private"]},
            "evidence": [{"claim": "用 Python 整理数据并输出报告", "source": "虚构测试", "status": "user_confirmed"}],
            "approved_for_resume": True}, ["event"])
        self.jid = sources.import_records([{"source": "fixture", "source_id": "tailor1", "title": "分析实习生", "company": "虚构公司",
            "location": "苏州", "description": "Python 数据报告", "url": "https://example.invalid/job/1"}])["job_ids"][0]

    def data(self):
        return {"reason": "突出岗位所需的数据整理与交付", "headline": "分析实习生", "sections": [{"experience_id": self.eid,
            "bullets": [{"text": "使用 Python 完成数据整理与报告交付", "source_texts": ["用 Python 整理数据并输出报告"],
                         "change_type": "wording_only", "new_facts": [], "change_reason": "保持工具与职责，突出岗位交付"}]}]}

    def test_direct_tailoring_has_sources_and_no_raw_intermediate(self):
        out = r.compose(self.jid, self.data())
        self.assertEqual(out["factual_status"], "approved")
        text = Path(out["path"]).read_text(encoding="utf-8")
        self.assertIn("使用 Python 完成数据整理与报告交付", text)
        self.assertIn("2025.01", text)
        self.assertNotIn("private", text)
        self.assertNotIn("open_questions", text)
        self.assertEqual(len(s.list_objects("resumes")), 1)
        self.assertEqual(len(feedback.version_history(out["id"])), 1)
        self.assertTrue(s.prepare_application(self.jid, out["id"]))
        self.assertIn("experience_index", r.tailor_packet(self.jid))

    def test_added_facts_pending_and_source_errors_rejected(self):
        data = self.data()
        bullet = data["sections"][0]["bullets"][0]
        bullet.update(text="交付 30 份数据报告", change_type="new_facts", new_facts=["报告数量30份"])
        out = r.compose(self.jid, data)
        self.assertEqual(out["factual_status"], "pending")
        with self.assertRaises(s.ValidationError):
            s.prepare_application(self.jid, out["id"])
        bullet["source_texts"] = ["不存在的事实"]
        with self.assertRaises(s.ValidationError):
            r.compose(self.jid, data)

    def test_summary_and_title_cannot_bypass_source_contract(self):
        data = self.data(); data["summary"] = "无来源的简介"
        with self.assertRaises(s.ValidationError):
            r.compose(self.jid, data)
        data.pop("summary"); data["sections"][0]["title"] = "项目总监"
        with self.assertRaises(s.ValidationError):
            r.compose(self.jid, data)

    def test_keep_current_and_three_history_only_markdown(self):
        outputs = [r.compose(self.jid, self.data()) for _ in range(6)]
        self.assertEqual(len(list((self.root / "resumes").glob("*.md"))), 4)
        self.assertFalse(Path(outputs[0]["path"]).exists())
        self.assertTrue(Path(outputs[-1]["path"]).exists())
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM resumes WHERE artifact_state='pruned'").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM resume_versions").fetchone()[0], 6)
        self.assertIn("虚构公司_分析实习生_苏州_job", outputs[-1]["path"])
        self.assertIn("_v6_", outputs[-1]["path"])
        pdf = self.root / "resumes" / "keep.pdf"; pdf.write_bytes(b"demo")
        r.cleanup(job_id=self.jid, apply=True)
        self.assertTrue(pdf.exists())

    def test_cleanup_dryrun_and_outside_root_never_delete(self):
        out = r.compose(self.jid, self.data())
        outside = self.root / "keep.md"; outside.write_text("private", encoding="utf-8")
        with connect() as db:
            db.execute("UPDATE resumes SET output_path=? WHERE id=?", (str(outside), out["id"]))
        result = r.cleanup(job_id=self.jid)
        self.assertTrue(result["dry_run"])
        self.assertTrue(result["skipped"])
        r.cleanup(job_id=self.jid, apply=True)
        self.assertTrue(outside.exists())

    def test_cleanup_never_deletes_a_path_shared_with_retained_version(self):
        outputs = [r.compose(self.jid, self.data()) for _ in range(5)]
        newest = Path(outputs[-1]["path"])
        with connect() as db:
            db.execute("UPDATE resumes SET output_path=? WHERE id=?", (str(newest), outputs[0]["id"]))
        result = r.cleanup(job_id=self.jid, apply=True)
        self.assertTrue(newest.exists())
        self.assertIn("path also belongs", str(result["skipped"]))


if __name__ == "__main__":
    unittest.main()
