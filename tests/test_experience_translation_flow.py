"""Fictional conversations exercise drafts, correction and source continuity."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oriward import experience_library as lib, feedback, resume_content, services, sources
from oriward.db import connect, serialize, now


class ExperienceTranslationFlowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = patch.dict(os.environ, {"ORIWARD_DB": str(self.root / "fictional.sqlite3"),
                                     "ORIWARD_OUTPUT_DIR": str(self.root / "resumes")})
        env.start()
        self.addCleanup(env.stop)
        services.save_profile({"display_name": "虚构候选人"})
        self.job = sources.import_records([{"source": "fixture", "source_id": "operations",
            "title": "运营", "company": "虚构公司", "description": "协调采购与客户事务",
            "availability": "listed", "url": "https://example.invalid/job"}])["job_ids"][0]

    def test_conversation_without_attachments_or_approval_produces_reusable_draft(self):
        eid = lib.create({"event": "经营社区门店", "actions": ["负责进货", "处理顾客咨询"]})
        draft = resume_content.compose(self.job, {"reason": "将真实经历转化为岗位表达", "sections": [{"experience_id": eid,
            "bullets": ["负责日常采购与补货安排，并跟进顾客需求"]}]})
        self.assertIn("采购与补货", Path(draft["path"]).read_text(encoding="utf-8"))
        self.assertFalse(lib.get(eid)["data"]["approved_for_resume"])
        self.assertFalse(draft["whole_draft_review_required"])
        self.assertTrue(services.prepare_application(self.job, draft["id"]))
        self.assertEqual(lib.get(eid)["data"]["actions"], ["负责进货", "处理顾客咨询"])

    def test_uncertain_metric_does_not_block_known_responsibility(self):
        eid = lib.create({"event": "门店经营", "actions": ["负责采购", "降低成本30%"],
                          "evidence": [{"claim": "降低成本30%", "source": "待厘清的估计", "status": "unverified"}]})
        draft = services.build_resume(self.job, [eid])
        body = Path(draft["path"]).read_text(encoding="utf-8")
        self.assertIn("负责采购", body)
        self.assertNotIn("降低成本30%", body)
        with connect() as db:
            material = lib.validate_for_resume(db, eid)
        self.assertEqual(material["actions"], ["负责采购"])
        self.assertIn("降低成本30%", lib.get(eid)["data"]["actions"])

    def test_legacy_false_approval_with_self_report_is_usable_without_rewriting_history(self):
        with connect() as db:
            eid = db.execute("INSERT INTO experiences(data,created_at) VALUES (?,?)", (
                serialize({"event": "旧自述", "actions": ["协调配送"], "outcomes": [],
                           "evidence": [{"claim": "协调配送", "source": "用户对话", "status": "user_stated"}],
                           "approved_for_resume": False}), now())).lastrowid
        draft = services.build_resume(self.job, [eid])
        self.assertIn("协调配送", Path(draft["path"]).read_text(encoding="utf-8"))
        self.assertFalse(lib.get(eid)["data"]["approved_for_resume"])
        self.assertNotIn("provenance_status", lib.get(eid)["data"])

    def test_unknown_legacy_and_model_import_are_not_upgraded(self):
        with connect() as db:
            old = db.execute("INSERT INTO experiences(data,created_at) VALUES (?,?)", (
                serialize({"event": "旧导入", "actions": ["使用未知工具"], "outcomes": [],
                           "evidence": [], "approved_for_resume": True}), now())).lastrowid
        model = lib.create({"event": "AI建议", "actions": ["使用Python"], "source_type": "model_inference"})
        self.assertEqual(lib.usable_facts(lib.get(old)["data"]), [])
        self.assertEqual(lib.usable_facts(lib.get(model)["data"]), [])
        self.assertNotIn("provenance_status", lib.get(old)["data"])

    def test_correction_is_immediate_and_history_is_preserved(self):
        eid = lib.create({"event": "客户跟进", "actions": ["30单成交"],
                          "evidence": [{"claim": "30单成交", "source": "用户对话", "status": "user_stated"}]})
        old = services.build_resume(self.job, [eid])
        lib.revise(eid, {"actions": ["30人到店，是否成交未知"]}, reason="用户更正结果口径")
        current = services.build_resume(self.job, [eid])
        self.assertIn("30人到店", Path(current["path"]).read_text(encoding="utf-8"))
        self.assertNotIn("30单成交", lib.usable_facts(lib.get(eid)["data"]))
        self.assertEqual(lib.history(eid)[0]["data"]["evidence"][0]["claim"], "30单成交")
        self.assertEqual(len(lib.history(eid)), 2)
        self.assertFalse(lib.get(eid)["data"]["approved_for_resume"])
        with self.assertRaisesRegex(ValueError, "needs_review"):
            services.prepare_application(self.job, old["id"])

    def test_general_draft_is_not_a_vacancy_or_application(self):
        eid = lib.create({"event": "门店经营", "actions": ["负责采购"]})
        draft = resume_content.compose(None, {"reason": "先整理通用简历", "sections": [
            {"experience_id": eid, "bullets": ["负责日常采购安排"]}]})
        self.assertEqual(len(services.list_objects("jobs")), 1)
        with connect() as db:
            job_id = db.execute("SELECT job_id FROM resumes WHERE id=?", (draft["id"],)).fetchone()[0]
        self.assertEqual(services.get_job(job_id)["kind"], "resume_context")
        with self.assertRaisesRegex(ValueError, "no vacancy"):
            services.prepare_application(job_id, draft["id"])

    def test_limited_trusted_claim_does_not_adopt_model_metadata(self):
        eid = lib.create({"event": "虚构公司财务总监", "context": "虚构集团 2020-2025",
                          "period": "2020-2025", "source_type": "model_inference",
                          "actions": ["管理百人团队"],
                          "evidence": [{"claim": "安排采购", "source": "用户补充", "status": "user_stated"}]})
        draft = services.build_resume(self.job, [eid])
        body = Path(draft["path"]).read_text(encoding="utf-8")
        self.assertIn("安排采购", body)
        for invented in ("虚构公司财务总监", "虚构集团", "2020-2025", "管理百人团队"):
            self.assertNotIn(invented, body)
        with connect() as db:
            material = lib.validate_for_resume(db, eid)
        self.assertEqual(material["event"], "相关经历")
        self.assertNotIn("period", material)
        with connect() as db:
            raw = lib.get(eid)["data"]
            raw.pop("provenance_status", None)
            raw.pop("needs_review", None)
            raw.pop("stale_assertion_ids", None)
            db.execute("UPDATE experiences SET data=? WHERE id=?", (serialize(raw), eid))
            legacy = lib.validate_for_resume(db, eid)
        self.assertEqual(legacy["event"], "相关经历")
        self.assertEqual(legacy["actions"], ["安排采购"])

    def test_general_resume_does_not_create_pipeline_health_work(self):
        from oriward.core import twin
        eid = lib.create({"event": "门店经营", "actions": ["负责采购"]})
        initial = twin.status()["health"]["jobs_without_pipeline"]
        resume_content.compose(None, {"reason": "通用简历", "sections": [{"experience_id": eid}]})
        before = twin.status()["health"]["jobs_without_pipeline"]
        twin.sync_legacy()
        with connect() as db:
            contexts = db.execute("SELECT COUNT(*) FROM job_pipeline p JOIN jobs j ON j.id=p.job_id "
                                  "WHERE j.source_key LIKE 'oriward:resume-context:%'").fetchone()[0]
        self.assertEqual(contexts, 0)
        self.assertEqual(before, initial)

    def test_grouped_revision_preserves_unaffected_source_bullet_and_title(self):
        first = lib.create({"event": "同店采购", "actions": ["负责采购"]})
        second = lib.create({"event": "同店服务", "actions": ["处理咨询"]})
        base = resume_content.compose(self.job, {"reason": "同一职业阶段整合", "sections": [{
            "experience_ids": [first, second], "title": "社区门店运营", "category": "经营经历",
            "bullets": [{"text": "规划日常采购与补货", "experience_ids": [first]},
                        {"text": "跟进顾客咨询", "experience_ids": [second]}]}]})
        revised = feedback.revise_resume({"base_resume_id": base["id"], "reason": "调整服务表述",
            "sections": [{"experience_id": second, "bullets": ["整理并回应顾客咨询"]}]})
        body = Path(revised["path"]).read_text(encoding="utf-8")
        self.assertIn("社区门店运营", body)
        self.assertIn("规划日常采购与补货", body)
        self.assertIn("整理并回应顾客咨询", body)
        self.assertNotIn("跟进顾客咨询", body)
        mapping = feedback.version_history(revised["id"])[-1]["version"]["claim_map"]
        self.assertTrue(any(m.get("field") == "title" for m in mapping))

    def test_partial_group_rewording_preserves_natural_shared_prose(self):
        first = lib.create({"event": "同店采购", "actions": ["负责采购"]})
        second = lib.create({"event": "同店服务", "actions": ["处理咨询"]})
        base = resume_content.compose(self.job, {"reason": "整合门店经历", "sections": [{
            "experience_ids": [first, second], "title": "社区门店运营", "category": "经营经历",
            "bullets": ["规划日常采购与补货", "协调采购与服务工作",
                        {"text": "旧版客户跟进", "experience_ids": [second]}]}]})
        revised = feedback.revise_resume({"base_resume_id": base["id"], "reason": "改善客户工作表达",
            "sections": [{"experience_id": second, "bullets": ["整理并回应顾客咨询"]}]})
        body = Path(revised["path"]).read_text(encoding="utf-8")
        for text in ("社区门店运营", "规划日常采购与补货", "协调采购与服务工作", "整理并回应顾客咨询"):
            self.assertIn(text, body)
        self.assertNotIn("旧版客户跟进", body)
        composition = resume_content.composition_for_resume(revised["id"])
        self.assertEqual(len(composition["sections"]), 1)
        self.assertEqual(composition["sections"][0]["experience_ids"], [first, second])
        self.assertEqual(composition["sections"][0]["bullets"][-1]["experience_ids"], [second])

    def test_revision_rebuilds_corrected_source_and_preserves_full_compose_map(self):
        eid = lib.create({"event": "客户工作", "actions": ["30单成交"]})
        base = resume_content.compose(self.job, {"reason": "初稿", "sections": [
            {"experience_id": eid, "bullets": ["完成30单成交"]}],
            "summary": {"text": "累计成交30单", "experience_ids": [eid]}})
        lib.revise(eid, {"actions": ["30人到店，成交未知"]}, reason="用户更正")
        revised = feedback.revise_resume({"base_resume_id": base["id"], "reason": "使用更正结果",
            "sections": [{"experience_id": eid, "title": "客户跟进经历",
                          "title_claim": {"text": "客户跟进经历", "change_type": "new_facts",
                                          "new_facts": ["职责归属尚待说明"]},
                          "bullets": ["记录30人到店，成交情况未知"]}]})
        body = Path(revised["path"]).read_text(encoding="utf-8")
        self.assertNotIn("累计成交30单", body)
        self.assertNotIn("完成30单成交", body)
        self.assertIn("30人到店", body)
        self.assertEqual(revised["factual_status"], "pending")
        stored = feedback.version_history(revised["id"])[-1]["version"]
        self.assertEqual(stored["factual_status"], "pending")
        self.assertTrue(any(m.get("field") == "title" and m["change_type"] == "new_facts"
                            for m in stored["claim_map"]))

    def test_profile_correction_replaces_stale_education_without_losing_other_prose(self):
        services.save_profile({"display_name": "虚构候选人", "education": "虚构学院 本科", "skills": ["采购"]})
        eid = lib.create({"event": "门店经营", "actions": ["负责采购"]})
        base = resume_content.compose(self.job, {"reason": "首次整理", "sections": [{"experience_id": eid}],
            "profile_sections": [{"heading": "教育经历", "paragraphs": ["虚构学院 本科（精简表述）"]},
                                 {"heading": "专业技能", "paragraphs": ["日常采购与补货安排"]}]})
        services.save_profile({"display_name": "虚构候选人", "education": "虚构学院 专科",
                               "skills": ["采购"], "contact": {"email": "fiction@example.invalid"}})
        revised = feedback.revise_resume({"base_resume_id": base["id"], "reason": "更正学历并修改正文",
                                         "sections": [{"experience_id": eid, "bullets": ["安排日常采购"]}]})
        body = Path(revised["path"]).read_text(encoding="utf-8")
        self.assertIn("专科", body)
        self.assertNotIn("本科", body)
        self.assertIn("日常采购与补货安排", body)

    def test_subset_wording_revision_preserves_other_career_stages(self):
        first = lib.create({"event": "早期门店工作", "actions": ["负责采购"]})
        second = lib.create({"event": "近期服务工作", "actions": ["跟进客户反馈"]})
        base = resume_content.compose(self.job, {"reason": "将真实经历转化为岗位表达", "sections": [
            {"experience_id": first, "bullets": ["安排日常采购"]},
            {"experience_id": second, "bullets": ["持续跟进客户反馈"]}]})
        revised = feedback.revise_resume({"base_resume_id": base["id"], "reason": "改善表达",
            "sections": [{"experience_id": second, "bullets": ["整理客户反馈并持续跟进"]}]})
        body = Path(revised["path"]).read_text(encoding="utf-8")
        self.assertIn("安排日常采购", body)
        self.assertIn("整理客户反馈并持续跟进", body)
        self.assertEqual(revised["factual_status"], "draft")
        self.assertEqual(revised["pending_new_facts"], [])
        self.assertFalse(revised["requires_new_review"])
        self.assertTrue(services.prepare_application(self.job, revised["id"]))


if __name__ == "__main__":
    unittest.main()
