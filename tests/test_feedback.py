import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from careeros import services as s, sources, assessment as a, feedback as f
from careeros.db import now, connect


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"CAREEROS_DB": str(self.root / "db.sqlite3"),
                                     "CAREEROS_OUTPUT_DIR": str(self.root / "resumes")})
        env.start()
        self.addCleanup(env.stop)
        s.save_profile({"display_name": "Fictional Candidate"})
        self.exp = s.add_object("experiences", {
            "event": "Demo project", "actions": ["Built a Python report"], "outcomes": ["Delivered a report"],
            "evidence": [{"claim": "Built a Python report", "source": "fictional fixture", "status": "user_confirmed"}],
            "approved_for_resume": True,
        }, ["event", "actions", "outcomes", "evidence", "approved_for_resume"])
        self.job = sources.import_records([{"source": "fixture", "source_id": "1", "title": "Analyst",
            "company": "Fictional", "description": "Python required", "availability": "listed",
            "url": "https://example.invalid/job"}])["job_ids"][0]
        self.resume = s.build_resume(self.job, [self.exp])
        self.analysis = a.save_analysis({"job_id": self.job, "requirements": [{
            "id": "py", "text": "Python", "quote": "Python required", "kind": "core", "match": "met",
            "experience_ids": [self.exp], "rationale": "Fictional report evidence"}], "unknowns": [],
            "coverage_confirmed": True,
            "company_context": [{"url": "https://example.invalid/job", "retrieved_at": now(),
                "fact": "Fixture is listed", "inference": "", "availability": "listed"}]})

    def review(self, resume):
        return a.save_review({"resume_id": resume["id"], "analysis_id": self.analysis,
            "resume_sha256": resume["sha256"], "stages": {stage: {
                "verdict": "pass", "rationale": "Fictional simulation", "questions": [],
                "requirement_ids": ["py"]} for stage in a.STAGES}})

    def feedback(self, **overrides):
        d = {"job_id": self.job, "resume_id": self.resume["id"], "kind": "mock", "stage": "technical",
             "outcome": "pending", "observation": "Report ownership needs explanation", "source": "mock interviewer",
             "observed_at": now(), "actions": [{"category": "wording", "text": "Clarify report ownership"}]}
        d.update(overrides)
        return f.save_feedback(d)

    def revision(self, feedback_ids=None, rewrite=False, **overrides):
        d = {"base_resume_id": self.resume["id"], "reason": "Clarify relevant experience",
             "feedback_ids": feedback_ids or [], "sections": [{"experience_id": self.exp, "bullets": [{
                 "text": "Created the Python report" if rewrite else "Built a Python report",
                 "source_texts": ["Built a Python report"]}]}]}
        d.update(overrides)
        return f.revise_resume(d)

    def test_feedback_revision_review_resolution_loop(self):
        fid = self.feedback()["id"]
        self.assertEqual(f.feedback_plan(self.job)["open_count"], 1)
        revision = self.revision([fid])
        self.assertEqual(revision["factual_status"], "approved")
        rid = self.review(revision)["id"]
        result = f.resolve_feedback(fid, rid, "Rechecked exact revised version")
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(f.feedback_plan(self.job)["open_count"], 0)
        history = f.version_history(revision["id"])
        self.assertEqual(len(history), 2)
        self.assertEqual(history[-1]["version"]["feedback_ids"], [fid])
        self.assertEqual(history[-1]["version"]["base_resume_id"], self.resume["id"])

    def test_rewording_requires_confirmation_and_new_review(self):
        revision = self.revision(rewrite=True)
        self.assertEqual(revision["factual_status"], "pending")
        self.assertIsNone(self.review(revision)["grade"])
        with self.assertRaises(s.ValidationError):
            s.prepare_application(self.job, revision["id"])
        with self.assertRaises(s.ValidationError):
            f.confirm_revision(revision["id"])
        # Fixture confirmation only; never substitutes for a real user's acknowledgement.
        f.confirm_revision(revision["id"], human_confirmed=True)
        self.assertEqual(self.review(revision)["grade"], "A")
        self.assertTrue(s.prepare_application(self.job, revision["id"]))

    def test_actual_feedback_requires_submitted_matching_application(self):
        with self.assertRaisesRegex(s.ValidationError, "application_id"):
            self.feedback(kind="actual")
        app = s.prepare_application(self.job, self.resume["id"])
        with self.assertRaisesRegex(s.ValidationError, "unsubmitted"):
            self.feedback(kind="actual", application_id=app)
        s.update_application(app, "SUBMITTED", human_confirmed=True)
        self.feedback(kind="actual", application_id=app, outcome="reject")
        self.assertEqual(s.list_objects("applications")[0]["status"], "SUBMITTED")

    def test_cross_version_actual_feedback_rejected(self):
        revision = self.revision()
        app = s.prepare_application(self.job, revision["id"])
        s.update_application(app, "SUBMITTED", human_confirmed=True)
        with self.assertRaisesRegex(s.ValidationError, "application version"):
            self.feedback(kind="actual", application_id=app)

    def test_unmapped_rewrite_and_cross_job_feedback_rejected(self):
        with self.assertRaisesRegex(s.ValidationError, "source_texts"):
            self.revision(sections=[{"experience_id": self.exp, "bullets": [
                {"text": "Managed 100 people", "source_texts": ["Managed 100 people"]}]}])
        with self.assertRaisesRegex(s.ValidationError, "does not match"):
            self.feedback(job_id=999)

    def test_file_tamper_blocks_packet_revision_and_feedback(self):
        Path(self.resume["path"]).write_text("tampered", encoding="utf-8")
        for fn in (lambda: s.prepare_application(self.job, self.resume["id"]),
                   self.revision, self.feedback, lambda: a.review_packet(self.resume["id"])):
            with self.assertRaisesRegex(s.ValidationError, "changed"):
                fn()

    def test_resolution_requires_linked_new_review(self):
        fid = self.feedback()["id"]
        rid = self.review(self.resume)["id"]
        with self.assertRaisesRegex(s.ValidationError, "new review"):
            f.resolve_feedback(fid, rid, "Not fixed")
        revision = self.revision()
        rid = self.review(revision)["id"]
        with self.assertRaises(s.ValidationError):
            f.resolve_feedback(fid, rid, "No linkage")

    def test_pending_or_stale_review_cannot_close_feedback(self):
        fid = self.feedback()["id"]
        revision = self.revision([fid], rewrite=True)
        rid = self.review(revision)["id"]
        f.confirm_revision(revision["id"], human_confirmed=True)
        with self.assertRaisesRegex(s.ValidationError, "completed review"):
            f.resolve_feedback(fid, rid, "Old pending review")
        rid = self.review(revision)["id"]
        job = s.get_job(self.job)
        job["description"] += "\nNew hard requirement"
        sources.import_records([job])
        with self.assertRaisesRegex(s.ValidationError, "stale"):
            f.resolve_feedback(fid, rid, "JD already changed")

    def test_revision_bound_to_base_review_and_rejects_duplicate_sections(self):
        rid = self.review(self.resume)["id"]
        revision = self.revision(review_id=rid)
        self.assertEqual(f.version_history(revision["id"])[-1]["version"]["review_id"], rid)
        with self.assertRaises(s.ValidationError):
            self.revision(review_id=999)

    def test_empty_evidence_never_generates_resume(self):
        eid = s.add_object("experiences", {"event": "No evidence", "actions": ["Claim"], "outcomes": [],
            "evidence": [], "approved_for_resume": True}, ["event", "actions", "outcomes", "evidence", "approved_for_resume"])
        with self.assertRaisesRegex(s.ValidationError, "nonempty"):
            s.build_resume(self.job, [eid])

    def test_collision_does_not_delete_existing_file(self):
        collision = self.root / "resumes" / "resume_2_revision.md"
        collision.write_text("existing artifact", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.revision()
        self.assertEqual(collision.read_text(encoding="utf-8"), "existing artifact")
        self.assertEqual(len(s.list_objects("resumes")), 1)

    def test_cli_persistence_and_structured_errors(self):
        def run(*args):
            result = subprocess.run([sys.executable, "-m", "careeros", *args], capture_output=True,
                                    text=True, encoding="utf-8", cwd=Path(__file__).resolve().parents[1])
            return result, json.loads(result.stdout or result.stderr)
        result, packet = run("review", "packet", "--resume-id", str(self.resume["id"]))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(packet["resume"]["actual_sha256"], self.resume["sha256"])
        result, history = run("resume", "history", "--id", str(self.resume["id"]))
        self.assertEqual(len(history), 1)
        result, error = run("resume", "confirm", "--id", str(self.resume["id"]))
        self.assertEqual(result.returncode, 2)
        self.assertIn("error", error)
        result, sources_out = run("jobs", "snapshots", "--id", str(self.job))
        self.assertEqual(len(sources_out), 1)


if __name__ == "__main__":
    unittest.main()
