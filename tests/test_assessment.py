import csv
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from careeros import assessment as a
from careeros import services as s
from careeros.db import connect, deserialize, serialize


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {
            "CAREEROS_DB": str(root / "test.sqlite3"),
            "CAREEROS_OUTPUT_DIR": str(root / "resumes"),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        s.save_profile({"display_name": "Candidate"})

    def add_experience(self, *, approved=True, status="user_confirmed", claim="Built Python service"):
        return s.add_object("experiences", {
            "event": "Delivery project",
            "context": "Internal project",
            "actions": ["Built a Python service"],
            "outcomes": ["Delivered the service"],
            "evidence": [{"claim": claim, "source": "user statement", "status": status}],
            "approved_for_resume": approved,
        }, ["event", "actions", "outcomes", "evidence", "approved_for_resume"])

    def add_job(self, description="Python is required\nCommunication is preferred", source_id=None):
        source_id = source_id or f"job-{len(s.list_objects('jobs')) + 1}"
        path = Path(self.tmp.name) / f"{source_id}.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["source", "source_id", "title", "company", "description", "url"])
            writer.writeheader()
            writer.writerow({
                "source": "test",
                "source_id": source_id,
                "title": "Engineer",
                "company": "Example",
                "description": description,
                "url": f"https://example.invalid/{source_id}",
            })
        s.import_jobs(path)
        return s.list_objects("jobs")[0]["id"]

    def requirement(self, requirement_id, quote, kind, match, experience_ids=None):
        return {
            "id": requirement_id,
            "text": quote,
            "kind": kind,
            "quote": quote,
            "match": match,
            "experience_ids": experience_ids or [],
            "rationale": "Reviewed against approved evidence.",
        }

    def save_analysis(self, job_id, requirements, *, unknowns=None, sourced=True, coverage_confirmed=True):
        context = []
        if sourced:
            context.append({
                "url": s.get_job(job_id)["url"],
                "retrieved_at": datetime.now(timezone.utc).date().isoformat(),
                "fact": "The vacancy page is available.",
                "inference": "The role appears open at retrieval time.",
                "availability": "listed",
            })
        return a.save_analysis({
            "job_id": job_id,
            "requirements": requirements,
            "unknowns": unknowns or [],
            "company_context": context,
            "coverage_confirmed": coverage_confirmed,
            "recommendation": "skip",  # ignored: the module computes this
            "confidence": "high",
        })

    def review(self, resume, analysis_id, requirement_ids, *, verdicts=None, findings=None, actions=None):
        verdicts = verdicts or {}
        stages = {
            stage: {
                "verdict": verdicts.get(stage, "pass"),
                "rationale": f"{stage} was evaluated in this simulation.",
                "questions": [],
                "requirement_ids": list(requirement_ids) if stage == "ats" else [],
            }
            for stage in a.STAGES
        }
        return {
            "resume_id": resume["id"],
            "analysis_id": analysis_id,
            "resume_sha256": resume["sha256"],
            "stages": stages,
            "red_findings": findings or [],
            "blue_actions": actions or [],
        }

    def prepared(self, requirements, *, unknowns=None, sourced=True, selected_ids=None):
        job_id = self.add_job()
        exp1 = self.add_experience()
        exp2 = self.add_experience(claim="Presented project results")
        resolved = []
        for item in requirements:
            copied = dict(item)
            if copied["experience_ids"] == ["EXP1"]:
                copied["experience_ids"] = [exp1]
            elif copied["experience_ids"] == ["EXP2"]:
                copied["experience_ids"] = [exp2]
            resolved.append(copied)
        analysis_id = self.save_analysis(job_id, resolved, unknowns=unknowns, sourced=sourced)
        selected = selected_ids or [exp1, exp2]
        selected = [exp1 if value == "EXP1" else exp2 if value == "EXP2" else value for value in selected]
        resume = s.build_resume(job_id, selected)
        return job_id, (exp1, exp2), analysis_id, resume, resolved

    def test_draft_is_line_based_unknown_and_quotes_exact_jd(self):
        job_id = self.add_job("Must hold license\nSQL preferred")
        draft = a.draft_analysis(job_id)
        self.assertEqual([r["match"] for r in draft["requirements"]], ["unknown", "unknown"])
        self.assertEqual([r["kind"] for r in draft["requirements"]], ["hard_gate", "preferred"])
        self.assertEqual(draft["requirements"][0]["quote"], "Must hold license")
        self.assertEqual(draft["recommendation"], "explore")
        self.assertFalse(draft["coverage_confirmed"])

    def test_review_packet_without_analysis_returns_actionable_null_template(self):
        job_id = self.add_job()
        experience_id = self.add_experience()
        resume = s.build_resume(job_id, [experience_id])
        packet = a.review_packet(resume["id"])
        self.assertIsNone(packet["latest_analysis"])
        self.assertIsNone(packet["review_template"]["analysis_id"])

    def test_save_analysis_computes_outcome_and_packet_filters_evidence(self):
        job_id = self.add_job()
        approved = self.add_experience()
        self.add_experience(approved=False)
        analysis_id = self.save_analysis(job_id, [
            self.requirement("python", "Python is required", "hard_gate", "met", [approved]),
            self.requirement("communication", "Communication is preferred", "preferred", "gap"),
        ])
        with connect() as db:
            saved = deserialize(db.execute("SELECT data FROM job_analyses WHERE id=?", (analysis_id,)).fetchone()["data"])
        self.assertEqual(saved["recommendation"], "apply")
        self.assertEqual(saved["confidence"], "medium")
        packet = a.analysis_packet(job_id)
        self.assertEqual(packet["latest_analysis"]["id"], analysis_id)
        self.assertEqual([item["id"] for item in packet["approved_experiences"]], [approved])

    def test_analysis_rejects_unapproved_or_unverified_met_evidence(self):
        job_id = self.add_job()
        unapproved = self.add_experience(approved=False)
        with self.assertRaisesRegex(s.ValidationError, "not approved"):
            self.save_analysis(job_id, [
                self.requirement("python", "Python is required", "hard_gate", "met", [unapproved])
            ])
        unverified = self.add_experience(status="unverified")
        with self.assertRaisesRegex(s.ValidationError, "verified non-empty evidence"):
            self.save_analysis(job_id, [
                self.requirement("python", "Python is required", "hard_gate", "met", [unverified])
            ])

    def test_grades_a_b_c_d(self):
        cases = [
            ("A", [
                self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"]),
                self.requirement("communication", "Communication is preferred", "preferred", "met", ["EXP2"]),
            ], True),
            ("B", [
                self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"]),
                self.requirement("communication", "Communication is preferred", "preferred", "met", ["EXP2"]),
            ], False),
            ("C", [
                self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"]),
                self.requirement("communication", "Communication is preferred", "preferred", "gap"),
            ], True),
            ("D", [
                self.requirement("python", "Python is required", "hard_gate", "gap"),
                self.requirement("communication", "Communication is preferred", "preferred", "met", ["EXP2"]),
            ], True),
        ]
        for expected, requirements, sourced in cases:
            with self.subTest(expected=expected):
                _, _, analysis_id, resume, resolved = self.prepared(requirements, sourced=sourced)
                result = a.save_review(self.review(resume, analysis_id, [r["id"] for r in resolved]))
                self.assertEqual(result["grade"], expected)
                self.assertEqual(a.list_reviews(resume["id"])[0]["result_label"], a.RESULT_LABEL)

    def test_unknown_hard_gate_needs_evidence(self):
        _, _, analysis_id, resume, resolved = self.prepared([
            self.requirement("python", "Python is required", "hard_gate", "unknown")
        ], unknowns=["Confirm required Python depth"])
        result = a.save_review(self.review(resume, analysis_id, [resolved[0]["id"]]))
        self.assertIsNone(result["grade"])
        self.assertEqual(result["status"], "NEEDS_EVIDENCE")

    def test_closed_target_cannot_be_upgraded_by_listed_company_context(self):
        job_id = self.add_job()
        exp = self.add_experience()
        with connect() as db:
            row = db.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
            data = deserialize(row["data"])
            data["availability"] = "closed"
            db.execute("UPDATE jobs SET data=? WHERE id=?", (serialize(data), job_id))
        analysis_id = self.save_analysis(job_id, [
            self.requirement("python", "Python is required", "hard_gate", "met", [exp])])
        resume = s.build_resume(job_id, [exp])
        result = a.save_review(self.review(resume, analysis_id, ["python"]))
        self.assertEqual(result["grade"], "D")
        self.assertIn("the sourced vacancy is closed", result["reasons"])
        self.assertEqual(a.analysis_packet(job_id)["latest_analysis"]["data"]["recommendation"], "skip")

    def test_unrelated_company_page_cannot_prove_vacancy_is_open(self):
        job_id = self.add_job()
        exp = self.add_experience()
        analysis = a.draft_analysis(job_id)
        for requirement in analysis["requirements"]:
            requirement.update(match="met", experience_ids=[exp])
        analysis.update(coverage_confirmed=True, unknowns=[], company_context=[{
            "url": "https://example.invalid/company-news", "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "fact": "Unrelated company page is online", "inference": "", "availability": "listed"}])
        analysis_id = a.save_analysis(analysis)
        resume = s.build_resume(job_id, [exp])
        result = a.save_review(self.review(resume, analysis_id, [r["id"] for r in analysis["requirements"]]))
        self.assertEqual(result["grade"], "B")
        self.assertEqual(result["status"], "PROVISIONAL")

    def test_known_d_blocker_precedes_unknown_gate_evidence(self):
        _, _, analysis_id, resume, resolved = self.prepared([
            self.requirement("license", "Python is required", "hard_gate", "gap"),
            self.requirement("communication", "Communication is preferred", "hard_gate", "unknown"),
        ], unknowns=["Confirm communication gate"])
        result = a.save_review(self.review(
            resume, analysis_id, [r["id"] for r in resolved], verdicts={"ats": "unknown"}
        ))
        self.assertEqual(result["grade"], "D")

    def test_unconfirmed_full_jd_coverage_caps_grade_at_provisional_b(self):
        job_id = self.add_job()
        experience_id = self.add_experience()
        analysis_id = self.save_analysis(job_id, [
            self.requirement("python", "Python is required", "hard_gate", "met", [experience_id]),
            self.requirement("communication", "Communication is preferred", "preferred", "met", [experience_id]),
        ], coverage_confirmed=False)
        resume = s.build_resume(job_id, [experience_id])
        result = a.save_review(self.review(resume, analysis_id, ["python", "communication"]))
        self.assertEqual(result["grade"], "B")
        self.assertEqual(result["status"], "PROVISIONAL")

    def test_structural_red_finding_caps_grade_despite_wording_action(self):
        _, _, analysis_id, resume, resolved = self.prepared([
            self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"]),
            self.requirement("communication", "Communication is preferred", "preferred", "met", ["EXP2"]),
        ])
        finding = {
            "id": "f-1",
            "stage": "technical",
            "severity": "structural",
            "issue": "Evidence demonstrates use but not ownership.",
            "evidence": "The resume only states participation.",
            "requirement_ids": ["python"],
        }
        action = {"finding_id": "f-1", "action": "Rewrite the bullet.", "type": "wording"}
        result = a.save_review(self.review(
            resume, analysis_id, [r["id"] for r in resolved], findings=[finding], actions=[action]
        ))
        self.assertEqual(result["grade"], "C")
        self.assertIn("structural", " ".join(result["reasons"]))

    def test_stage_failures_cannot_receive_a_and_background_failure_is_d(self):
        _, _, analysis_id, resume, resolved = self.prepared([
            self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"]),
            self.requirement("communication", "Communication is preferred", "preferred", "met", ["EXP2"]),
        ])
        technical = a.save_review(self.review(
            resume, analysis_id, [r["id"] for r in resolved], verdicts={"technical": "fail"}
        ))
        self.assertEqual(technical["grade"], "C")
        background = a.save_review(self.review(
            resume, analysis_id, [r["id"] for r in resolved], verdicts={"background": "fail"}
        ))
        self.assertEqual(background["grade"], "D")

    def test_missing_stage_or_requirement_coverage_is_rejected(self):
        _, _, analysis_id, resume, resolved = self.prepared([
            self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"])
        ])
        missing_stage = self.review(resume, analysis_id, ["python"])
        del missing_stage["stages"]["pressure"]
        with self.assertRaisesRegex(s.ValidationError, "exactly"):
            a.save_review(missing_stage)
        missing_role = self.review(resume, analysis_id, [])
        with self.assertRaisesRegex(s.ValidationError, "do not cover"):
            a.save_review(missing_role)

    def test_red_finding_cannot_self_declare_resolution(self):
        _, _, analysis_id, resume, resolved = self.prepared([
            self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"])
        ])
        finding = {
            "id": "f-1", "stage": "technical", "severity": "structural",
            "issue": "Ownership missing", "evidence": "Resume text", "requirement_ids": ["python"],
            "resolved": True,
        }
        with self.assertRaisesRegex(s.ValidationError, "Do not mark"):
            a.save_review(self.review(resume, analysis_id, [resolved[0]["id"]], findings=[finding]))

    def test_review_rejects_met_evidence_not_selected_into_resume(self):
        _, _, analysis_id, resume, resolved = self.prepared([
            self.requirement("python", "Python is required", "hard_gate", "met", ["EXP2"])
        ], selected_ids=["EXP1"])
        with self.assertRaisesRegex(s.ValidationError, "not selected"):
            a.save_review(self.review(resume, analysis_id, [resolved[0]["id"]]))

    def test_review_rejects_cross_job_analysis(self):
        job1 = self.add_job(source_id="one")
        job2 = self.add_job(source_id="two")
        exp = self.add_experience()
        analysis_id = self.save_analysis(job1, [
            self.requirement("python", "Python is required", "hard_gate", "met", [exp])
        ])
        resume = s.build_resume(job2, [exp])
        with self.assertRaisesRegex(s.ValidationError, "different jobs"):
            a.save_review(self.review(resume, analysis_id, ["python"]))

    def test_review_rejects_changed_resume_and_stale_job(self):
        job_id, _, analysis_id, resume, resolved = self.prepared([
            self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"])
        ])
        Path(resume["path"]).write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(s.ValidationError, "missing or changed"):
            a.save_review(self.review(resume, analysis_id, [resolved[0]["id"]]))

        # Build a fresh resume, then mutate the stored JD after the analysis snapshot.
        fresh = s.build_resume(job_id, [1])
        with connect() as db:
            row = db.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
            job = deserialize(row["data"])
            job["description"] += "\nNew requirement"
            db.execute("UPDATE jobs SET data=? WHERE id=?", (serialize(job), job_id))
        with self.assertRaisesRegex(s.ValidationError, "stale"):
            a.save_review(self.review(fresh, analysis_id, [resolved[0]["id"]]))

    def test_retrieval_timestamp_refresh_does_not_stale_analysis(self):
        job_id, _, analysis_id, resume, resolved = self.prepared([
            self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"])
        ])
        with connect() as db:
            row = db.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
            job = deserialize(row["data"])
            job["retrieved_at"] = "2030-01-01T00:00:00+00:00"
            db.execute("UPDATE jobs SET data=? WHERE id=?", (serialize(job), job_id))
        result = a.save_review(self.review(resume, analysis_id, [resolved[0]["id"]]))
        self.assertEqual(result["grade"], "A")

    def test_pending_revision_needs_evidence(self):
        _, _, analysis_id, resume, resolved = self.prepared([
            self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"])
        ])
        from careeros.feedback import ensure_schema
        with connect() as db:
            ensure_schema(db)
            db.execute(
                "INSERT INTO resume_versions VALUES (?,?,?,?,?,?,?,?)",
                (resume["id"], resume["id"], None, "[]", "rewrite", "[]", "pending", "2026-01-01T00:00:00+00:00"),
            )
        result = a.save_review(self.review(resume, analysis_id, [resolved[0]["id"]]))
        self.assertIsNone(result["grade"])
        self.assertEqual(result["status"], "NEEDS_EVIDENCE")
        self.assertIn("pending factual confirmation", result["reasons"][0])

    def test_review_packet_returns_exact_content_hash_template_and_history(self):
        _, _, analysis_id, resume, resolved = self.prepared([
            self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"])
        ])
        a.save_review(self.review(resume, analysis_id, [resolved[0]["id"]]))
        packet = a.review_packet(resume["id"])
        self.assertEqual(packet["resume"]["content"], Path(resume["path"]).read_text(encoding="utf-8"))
        self.assertEqual(packet["resume"]["actual_sha256"], resume["sha256"])
        self.assertEqual(set(packet["review_template"]["stages"]), set(a.STAGES))
        self.assertEqual(packet["latest_analysis"]["id"], analysis_id)
        self.assertEqual(len(packet["prior_reviews"]), 1)

    def test_manual_grade_is_rejected(self):
        _, _, analysis_id, resume, resolved = self.prepared([
            self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"])
        ])
        review = self.review(resume, analysis_id, [resolved[0]["id"]])
        review["grade"] = "A"
        with self.assertRaisesRegex(s.ValidationError, "computed"):
            a.save_review(review)

    def test_stale_supplied_resume_hash_is_rejected(self):
        _, _, analysis_id, resume, resolved = self.prepared([
            self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"])
        ])
        review = self.review(resume, analysis_id, [resolved[0]["id"]])
        review["resume_sha256"] = "0" * 64
        with self.assertRaisesRegex(s.ValidationError, "hash is stale"):
            a.save_review(review)


if __name__ == "__main__":
    unittest.main()
