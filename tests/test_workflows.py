import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oriward import services as s
from oriward.db import connect


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"ORIWARD_DB": str(Path(self.tmp.name) / "test.sqlite3")})
        self.env.start()
        self.addCleanup(self.env.stop)
        s.save_profile({"display_name": "Test Person", "contact": {"email": "test@example.invalid"}})

    def add_exp(self, approved=True, evidence_status="user_confirmed"):
        return s.add_object("experiences", {
            "event": "Course project", "context": "Demo", "actions": ["Cleaned a dataset with Python"],
            "outcomes": ["Delivered a report"],
            "evidence": [{"claim": "Used Python", "source": "user statement", "status": evidence_status}],
            "inferred_skills": [{"name": "data analysis", "reason": "project", "confidence": "medium"}],
            "approved_for_resume": approved,
        }, ["event", "actions", "outcomes", "evidence", "approved_for_resume"])

    def add_job(self):
        path = Path(self.tmp.name) / "jobs.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["source", "source_id", "title", "company", "description", "url"])
            writer.writeheader()
            writer.writerow({"source": "demo", "source_id": "44", "title": "Intern", "company": "Example Inc.", "description": "Python", "url": "https://example.com/post?utm_source=sample"})
        return path

    def test_job_import_is_idempotent(self):
        path = self.add_job()
        self.assertEqual(s.import_jobs(path), {"added": 1, "duplicate": 0})
        self.assertEqual(s.import_jobs(path), {"added": 0, "duplicate": 1})
        self.assertEqual(len(s.list_objects("jobs")), 1)
        self.assertEqual(s.get_job(1)["url"], "https://example.com/post")

    def test_bad_url_rejected(self):
        self.assertRaises(s.ValidationError, s.clean_url, "file:///private/pwd")
        self.assertRaises(s.ValidationError, s.clean_url, "javascript:alert(1)")

    def test_resume_accepts_self_reports_without_approval(self):
        self.add_exp(approved=False)
        s.import_jobs(self.add_job())
        result = s.build_resume(1, [1])
        self.assertIn("Cleaned a dataset", Path(result["path"]).read_text(encoding="utf-8"))

    def test_one_uncertain_claim_does_not_block_known_actions(self):
        self.add_exp(approved=True, evidence_status="unverified")
        s.import_jobs(self.add_job())
        result = s.build_resume(1, [1])
        text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("Cleaned a dataset with Python", text)
        self.assertNotIn("Used Python", text)

    def test_evidence_linked_resume_and_submit_gate(self):
        exp_id = self.add_exp()
        s.import_jobs(self.add_job())
        res = s.build_resume(1, [exp_id], "Internship")
        text = Path(res["path"]).read_text(encoding="utf-8")
        self.assertIn("Cleaned a dataset with Python", text)
        self.assertNotIn("经历 ID", text)
        self.assertNotIn("expert", text.lower())
        application_id = s.prepare_application(1, res["id"])
        app = s.list_objects("applications")[0]
        self.assertEqual(app["status"], "READY_FOR_USER")
        with self.assertRaisesRegex(s.ValidationError, "user confirms"):
            s.update_application(application_id, "SUBMITTED")
        self.assertEqual(s.list_objects("applications")[0]["status"], "READY_FOR_USER")
        with self.assertRaisesRegex(s.ValidationError, "not allowed"):
            s.update_application(application_id, "INTERVIEW")
        self.assertEqual(s.update_application(application_id, "SUBMITTED", human_confirmed=True), "SUBMITTED")
        self.assertEqual(s.update_application(application_id, "INTERVIEW"), "INTERVIEW")
        self.assertEqual(s.update_application(application_id, "OFFER"), "OFFER")

    def test_job_analysis_evidence_must_exist(self):
        s.import_jobs(self.add_job())
        d = {"job_id": 1, "strengths": [{"requirement": "Python", "evidence": "claim", "experience_ids": [999]}],
             "gaps": [], "unknowns": [], "recommendation": "apply", "confidence": "medium"}
        with self.assertRaisesRegex(ValueError, "not found"):
            s.add_object("job_analyses", d, ["job_id", "strengths", "gaps", "unknowns", "recommendation", "confidence"])

    def test_profile_and_audit(self):
        self.assertEqual(s.get_profile()["display_name"], "Test Person")
        with connect() as db:
            kinds = [r["kind"] for r in db.execute("SELECT kind FROM audit_events")]
        self.assertIn("profile.updated", kinds)


if __name__ == "__main__":
    unittest.main()
