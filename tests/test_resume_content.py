import os
import hashlib
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
            "approved_for_resume": False}, ["event"])
        self.jid = sources.import_records([{"source": "fixture", "source_id": "tailor1", "title": "分析实习生", "company": "虚构公司",
            "location": "苏州", "description": "Python 数据报告", "url": "https://example.invalid/job/1"}])["job_ids"][0]

    def data(self):
        return {"reason": "突出岗位所需的数据整理与交付", "headline": "分析实习生", "sections": [{"experience_id": self.eid, "category": "项目经历",
            "bullets": [{"text": "使用 Python 完成数据整理与报告交付", "source_texts": ["用 Python 整理数据并输出报告"],
                         "change_type": "wording_only", "new_facts": [], "change_reason": "保持工具与职责，突出岗位交付"}]}]}

    def test_direct_tailoring_has_sources_and_no_raw_intermediate(self):
        out = r.compose(self.jid, self.data())
        self.assertEqual(out["factual_status"], "draft")
        text = Path(out["path"]).read_text(encoding="utf-8")
        self.assertIn("使用 Python 完成数据整理与报告交付", text)
        self.assertIn("2025.01", text)
        self.assertNotIn("private", text)
        self.assertNotIn("open_questions", text)
        self.assertEqual(len(s.list_objects("resumes")), 1)
        self.assertEqual(len(feedback.version_history(out["id"])), 1)
        with connect() as db:
            row = db.execute("SELECT sha256 FROM resumes WHERE id=?", (out["id"],)).fetchone()
        self.assertEqual(row["sha256"], hashlib.sha256(text.encode("utf-8")).hexdigest())
        self.assertTrue(s.prepare_application(self.jid, out["id"]))
        self.assertIn("experience_index", r.tailor_packet(self.jid))

    def test_added_facts_pending_and_source_errors_rejected(self):
        data = self.data()
        bullet = data["sections"][0]["bullets"][0]
        bullet.update(text="交付 30 份数据报告", change_type="new_facts", new_facts=["报告数量30份"])
        out = r.compose(self.jid, data)
        self.assertEqual(out["factual_status"], "pending")
        self.assertTrue(s.prepare_application(self.jid, out["id"]))
        bullet["source_texts"] = ["不存在的事实"]
        with self.assertRaises(s.ValidationError):
            r.compose(self.jid, data)

    def test_summary_and_title_can_be_rewritten_without_extra_confirmation(self):
        data = self.data()
        data["summary"] = "具备数据整理和报告交付经验"
        data["sections"][0]["title"] = "数据整理与报告项目"
        out = r.compose(self.jid, data)
        self.assertEqual(out["factual_status"], "draft")
        self.assertFalse(out["whole_draft_review_required"])
        text = Path(out["path"]).read_text(encoding="utf-8")
        self.assertIn(data["summary"], text)
        self.assertIn("数据整理与报告项目", text)
        self.assertNotIn("来源记录", text)
        self.assertNotIn("经历 ID", text)

    def test_tailor_packet_and_compose_keep_every_approved_experience_in_template_order(self):
        from oriward import experience_library
        other_id = experience_library.create({"event": "直播运营｜互动玩法设计", "actions": ["在5人直播团队中承担运营"],
            "outcomes": ["相关玩法已在视频号、抖音实际开播"], "context": "2023.10—2024.11",
            "evidence": [{"claim": "相关玩法实际开播", "source": "fictional test", "status": "user_confirmed"}],
            "approved_for_resume": False})
        packet = r.tailor_packet(self.jid)
        self.assertEqual(set(packet["required_experience_ids"]), set())
        self.assertEqual(set(packet["detail_requests"]["ids"]), {self.eid, other_id})
        self.assertEqual(packet["experience_details"], [])

        incomplete = self.data()
        repaired = r.compose(self.jid, incomplete)
        self.assertIn(other_id, repaired["automatically_retained_ids"])
        self.assertIn("直播运营", Path(repaired["path"]).read_text(encoding="utf-8"))

        complete = self.data()
        complete["sections"][0]["category"] = "工作经历"
        complete["sections"].append({"experience_id": other_id, "category": "项目经历", "bullets": [{
            "text": "在5人直播团队中承担运营，相关玩法已在视频号、抖音实际开播",
            "source_texts": ["在5人直播团队中承担运营", "相关玩法已在视频号、抖音实际开播"],
            "change_type": "wording_only", "new_facts": [], "change_reason": "突出玩法落地与协作"}]})
        out = r.compose(self.jid, complete)
        text = Path(out["path"]).read_text(encoding="utf-8")
        self.assertLess(text.index("## 工作经历"), text.index("## 项目经历"))
        self.assertIn("### 直播运营｜互动玩法设计", text)
        self.assertEqual({row["experience_id"] for row in out["coverage"]}, {self.eid, other_id})

    def test_education_excerpt_and_project_link_stay_in_their_own_sections(self):
        verified = "河海大学金融硕士（在读），预计2028年毕业。 项目链接：https://example.invalid/project"
        s.save_profile({"display_name": "虚构候选人", "contact": {"email": "fiction@example.invalid"},
                        "summary_verified": verified})
        data = self.data()
        data["profile_sections"] = [{"heading": "教育经历", "paragraphs": ["河海大学金融硕士（在读），预计2028年毕业。"]}]
        data["sections"][0]["links"] = [{"label": "数据项目主页", "url": "https://example.invalid/project"}]
        out = r.compose(self.jid, data)
        text = Path(out["path"]).read_text(encoding="utf-8")
        education = text.index("## 教育经历")
        experience = text.index("## 项目经历")
        project = text.index("### 数据项目")
        link = text.index("[数据项目主页](https://example.invalid/project)")
        self.assertLess(education, experience)
        self.assertLess(project, link)
        self.assertGreater(link, experience)
        self.assertEqual(out["factual_status"], "draft")

        data["profile_sections"][0]["paragraphs"] = ["金融硕士在读｜河海大学｜预计2028年毕业"]
        rewritten = r.compose(self.jid, data)
        self.assertIn("金融硕士在读", Path(rewritten["path"]).read_text(encoding="utf-8"))
        data["sections"][0]["links"][0]["url"] = "file:///private"
        with self.assertRaises(s.ValidationError):
            r.compose(self.jid, data)

    def test_education_and_chronology_are_restored_without_approval(self):
        from oriward import experience_library as e
        s.save_profile({"display_name": "虚构候选人", "education": [
            {"school": "虚构职业学院", "major": "物流管理", "degree": "专科", "period": "2004–2007"}]})
        old = e.create({"event": "仓储协调", "category": "工作经历", "time_period": "2008–2014",
                        "actions": ["协调供应商和补货"], "context": {"company": "虚构甲公司"}})
        recent = e.create({"event": "门店经营", "category": "经营经历", "time_period": "2015–2024",
                           "actions": ["负责进货和客户维护"]})
        out = r.compose(self.jid, {"reason": "突出库存与客户协作", "sections": [
            {"experience_id": recent, "category": "经营经历", "bullets": ["安排采购补货并维护客户关系"]}]})
        content = Path(out["path"]).read_text(encoding="utf-8")
        for value in ("教育经历", "虚构职业学院", "仓储协调", "2008–2014", "门店经营"):
            self.assertIn(value, content)
        self.assertIn(old, out["automatically_retained_ids"])
        revised = feedback.revise_resume({"base_resume_id": out["id"], "reason": "调整表达", "sections": [
            {"experience_id": recent, "category": "经营经历", "bullets": ["负责日常采购与客户服务"]}]})
        self.assertIn("虚构职业学院", Path(revised["path"]).read_text(encoding="utf-8"))
        self.assertIn("仓储协调", Path(revised["path"]).read_text(encoding="utf-8"))

    def test_grouped_sources_exclusion_and_general_resume(self):
        from oriward import experience_library as e
        second = e.create({"event": "补货优化", "actions": ["整理每日库存"], "time_period": "2025"})
        out = r.compose(None, {"reason": "同阶段整理", "sections": [
            {"experience_ids": [self.eid, second], "title": "数据与库存整理", "bullets": [
                {"text": "整理库存记录", "experience_ids": [second]}]}]})
        self.assertEqual(len(out["coverage"]), 2)
        self.assertNotIn("通用简历", str(s.list_objects("jobs")))
        with connect() as db:
            jid = db.execute("SELECT job_id FROM resumes WHERE id=?", (out["id"],)).fetchone()[0]
        with self.assertRaises(s.ValidationError):
            s.prepare_application(jid, out["id"])
        excluded = r.compose(self.jid, {**self.data(), "exclude_experience_ids": [second]})
        self.assertNotIn(second, [row["experience_id"] for row in excluded["coverage"]])
        partially_excluded = r.compose(self.jid, {"reason": "不展示第二段", "exclude_experience_ids": [second],
            "sections": [{"experience_ids": [self.eid, second], "bullets": [
                {"text": "保留数据报告表达", "experience_ids": [self.eid]},
                {"text": "不展示库存表达", "experience_ids": [second]}]}]})
        content = Path(partially_excluded["path"]).read_text(encoding="utf-8")
        self.assertIn("保留数据报告表达", content)
        self.assertNotIn("不展示库存表达", content)
        self.assertEqual([row["experience_id"] for row in partially_excluded["coverage"]], [self.eid])

    def test_packet_pagination_visits_large_library_without_all_details(self):
        from oriward import experience_library as e
        ids = {self.eid}
        for number in range(18):
            ids.add(e.create({"event": f"虚构经历{number}", "actions": ["库存协调" * 35]}))
        seen, offset = set(), 0
        for _ in range(30):
            packet = r.tailor_packet(None, offset=offset, budget=1100)
            seen.update(item["id"] for item in packet["experience_index"]["items"])
            self.assertLess(len(packet["experience_details"]), len(ids))
            if not packet["has_more"]:
                break
            self.assertGreater(packet["next_offset"], offset)
            offset = packet["next_offset"]
        self.assertEqual(seen, ids)

    def test_index_packet_does_not_embed_unbounded_experience_details(self):
        import json
        from oriward import experience_library as e
        e.create({"event": "长期工作记录", "actions": ["X" * 100000]})
        packet = r.tailor_packet(None, budget=1100)
        self.assertLess(len(json.dumps(packet, ensure_ascii=False)), 7000)
        self.assertEqual(packet["experience_details"], [])

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

    def test_purge_removes_all_registered_markdown_but_keeps_history_and_external_files(self):
        outputs = [r.compose(self.jid, self.data()) for _ in range(3)]
        pdf = self.root / "resumes" / "keep.pdf"
        pdf.write_bytes(b"resume export")
        dry_run = r.cleanup(purge=True)
        self.assertTrue(dry_run["dry_run"])
        self.assertEqual(len(dry_run["operations"]), 3)
        self.assertTrue(all(Path(item["path"]).is_file() for item in outputs))

        result = r.cleanup(apply=True, purge=True)
        self.assertEqual(len(result["operations"]), 3)
        self.assertFalse(list((self.root / "resumes").glob("*.md")))
        self.assertTrue(pdf.is_file())
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM resumes WHERE artifact_state='pruned'").fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM resume_versions").fetchone()[0], 3)

    def test_scoped_purge_never_removes_a_path_referenced_by_another_job(self):
        first = r.compose(self.jid, self.data())
        second_job = sources.import_records([{"source": "fixture", "source_id": "tailor2", "title": "Another role",
            "company": "Another company", "location": "Suzhou", "description": "Fixture", "url": "https://example.invalid/job/2"}])["job_ids"][0]
        second = r.compose(second_job, self.data())
        with connect() as db:
            db.execute("UPDATE resumes SET output_path=? WHERE id=?", (first["path"], second["id"]))
        result = r.cleanup(job_id=self.jid, apply=True, purge=True)
        self.assertIn("outside purge scope", str(result["skipped"]))
        self.assertTrue(Path(first["path"]).is_file())
        with connect() as db:
            self.assertEqual(db.execute("SELECT artifact_state FROM resumes WHERE id=?", (first["id"],)).fetchone()[0], "available")


if __name__ == "__main__":
    unittest.main()
