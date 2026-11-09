import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oriward import feedback, resume_content as resume, services, sources
from oriward.db import connect, deserialize, serialize


class ResumeTargetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"ORIWARD_DB": str(self.root / "test.sqlite3"),
                                     "ORIWARD_OUTPUT_DIR": str(self.root / "resumes")})
        env.start()
        self.addCleanup(env.stop)
        services.save_profile({"display_name": "虚构候选人"})
        self.experience_id = services.add_object("experiences", {
            "event": "虚构数据项目", "actions": ["整理业务数据并输出报告"],
            "evidence": [{"claim": "整理业务数据并输出报告", "source": "fictional fixture", "status": "user_confirmed"}],
        }, ["event"])
        self.job_ids = sources.import_records([
            {"source": "fixture", "source_id": "family-1", "title": "运营分析", "company": "虚构甲",
             "description": "分析运营指标并提出改进建议", "url": "https://example.invalid/1",
             "published_at": "2026-10-01"},
            {"source": "fixture", "source_id": "family-2", "title": "数据运营", "company": "虚构乙",
             "description": "整理业务数据并支持运营复盘", "url": "https://example.invalid/2",
             "listed_at": "2026-10-02"},
       ])["job_ids"]

    def data(self):
        return {"reason": "按目标方向整理已有经历", "sections": [
            {"experience_id": self.experience_id, "category": "项目经历",
             "bullets": ["整理业务数据并输出报告"]}]}

    def _composition(self, resume_id):
        return resume.composition_for_resume(resume_id)

    def test_primary_and_references_use_one_snapshot_with_explicit_roles(self):
        packet = resume.tailor_packet(self.job_ids[0], reference_job_ids=[self.job_ids[1]])
        target = packet["target"]
        self.assertEqual(target["type"], "job")
        self.assertEqual(target["primary_job_id"], self.job_ids[0])
        self.assertEqual(target["reference_job_ids"], [self.job_ids[1]])
        self.assertEqual([job["role"] for job in target["jobs"]], ["primary", "reference"])
        self.assertIn("改进建议", target["jobs"][0]["description"])
        self.assertIn("复盘", target["jobs"][1]["description"])
        self.assertIn("references are supplementary", packet["next"])

        result = resume.compose(self.job_ids[0], self.data(), reference_job_ids=[self.job_ids[1]])
        self.assertEqual(result["workflow"]["mode"], "job_targeted")
        with connect() as db:
            resume_row = db.execute("SELECT job_id FROM resumes WHERE id=?", (result["id"],)).fetchone()
        self.assertEqual(resume_row["job_id"], self.job_ids[0])
        snapshot = self._composition(result["id"])["_target_snapshot"]
        self.assertEqual(snapshot["primary_job_id"], self.job_ids[0])
        self.assertEqual(snapshot["reference_job_ids"], [self.job_ids[1]])

    def test_direction_with_one_reference_and_specialization_preserves_reference(self):
        packet = resume.tailor_packet(reference_job_ids=[self.job_ids[1]], target_title="数据运营方向")
        self.assertEqual(packet["target"]["type"], "direction")
        self.assertEqual(packet["target"]["reference_job_ids"], [self.job_ids[1]])
        direction = resume.compose(None, self.data(), reference_job_ids=[self.job_ids[1]], target_title="数据运营方向")
        self.assertEqual(direction["workflow"]["mode"], "direction_targeted")
        with connect() as db:
            row = db.execute("SELECT job_id FROM resumes WHERE id=?", (direction["id"],)).fetchone()
            context = deserialize(db.execute("SELECT data FROM jobs WHERE id=?", (row["job_id"],)).fetchone()["data"])
        self.assertEqual(context["kind"], "resume_context")
        self.assertFalse(context["is_vacancy"])

        specialized = resume.compose(self.job_ids[0], self._composition(direction["id"]))
        self.assertEqual(specialized["workflow"]["mode"], "job_targeted")
        snapshot = self._composition(specialized["id"])["_target_snapshot"]
        self.assertEqual(snapshot["primary_job_id"], self.job_ids[0])
        self.assertEqual(snapshot["reference_job_ids"], [self.job_ids[1]])
        self.assertEqual([job["role"] for job in snapshot["jobs"]], ["primary", "reference"])

    def test_revision_keeps_primary_and_reference_snapshot_after_live_changes(self):
        original = resume.compose(self.job_ids[0], self.data(), reference_job_ids=[self.job_ids[1]])
        frozen = self._composition(original["id"])["_target_snapshot"]
        with connect() as db:
            for job_id in self.job_ids:
                row = db.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
                job = deserialize(row["data"])
                job["description"] = "此为后来修改的实时描述"
                db.execute("UPDATE jobs SET data=? WHERE id=?", (serialize(job), job_id))
        revised = feedback.revise_resume({"base_resume_id": original["id"], "reason": "调整表达",
                                          "sections": [{"experience_id": self.experience_id,
                                                        "category": "项目经历",
                                                        "bullets": ["整理业务数据并交付分析报告"]}]})
        self.assertEqual(revised["workflow"]["mode"], "job_targeted")
        self.assertEqual(self._composition(revised["id"])["_target_snapshot"], frozen)
        self.assertNotIn("后来修改", str(self._composition(revised["id"])["_target_snapshot"]))

    def test_baseline_revision_and_invalid_non_vacancy_reference(self):
        baseline = resume.compose(None, self.data())
        revised = feedback.revise_resume({"base_resume_id": baseline["id"], "reason": "整理表达",
                                          "sections": [{"experience_id": self.experience_id,
                                                        "bullets": ["整理业务数据并输出报告"]}]})
        self.assertEqual(revised["workflow"]["mode"], "baseline_only")
        with connect() as db:
            context_id = db.execute("SELECT job_id FROM resumes WHERE id=?", (baseline["id"],)).fetchone()["job_id"]
        with self.assertRaises(services.ValidationError):
            resume.tailor_packet(reference_job_ids=[context_id], target_title="无效方向")
        with self.assertRaises(services.ValidationError):
            resume.tailor_packet(reference_job_ids=[self.job_ids[0]])
        with self.assertRaises(services.ValidationError):
            resume.tailor_packet(reference_job_ids=[99999], target_title="无效方向")

    def test_primary_can_also_be_referenced_and_duplicate_references_dedupe(self):
        packet = resume.tailor_packet(self.job_ids[0], reference_job_ids=[self.job_ids[0], self.job_ids[1], self.job_ids[1]])
        self.assertEqual(packet["target"]["reference_job_ids"], [self.job_ids[1]])
        self.assertEqual([job["role"] for job in packet["target"]["jobs"]], ["primary", "reference"])


if __name__ == "__main__":
    unittest.main()
