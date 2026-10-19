"""Fictional end-to-end evidence and mission regressions; no personal records."""
import unittest
from pathlib import Path

import test_assessment as fixtures
from oriward import assessment as a, experience_library as library, services as s
from oriward.core import assertions
from oriward.db import connect, deserialize


class AssessmentFocusTests(unittest.TestCase):
    setUp = fixtures.AssessmentTests.setUp
    add_job = fixtures.AssessmentTests.add_job
    add_experience = fixtures.AssessmentTests.add_experience
    requirement = fixtures.AssessmentTests.requirement
    save_analysis = fixtures.AssessmentTests.save_analysis
    review = fixtures.AssessmentTests.review
    prepared = fixtures.AssessmentTests.prepared

    def assertion(self, predicate, value, *, source_type="user_message", source_ref="", confirm=True):
        result = assertions.propose(subject="candidate", predicate=predicate, value=value,
            assertion_type="fact", source_type=source_type, source_ref=source_ref)
        if confirm and source_type != "document":
            assertions.confirm(result["id"], note="Fictional candidate explicitly confirmed")
        return result["id"]

    def saved(self, identifier):
        with connect() as db:
            return deserialize(db.execute("SELECT data FROM job_analyses WHERE id=?", (identifier,)).fetchone()[0])

    def test_education_and_attendance_use_current_assertions_without_fabricated_experience(self):
        job = self.add_job("Bachelor degree required\nAvailable three days required")
        edu = self.assertion("education", "Bachelor degree")
        days = self.assertion("attendance", "Three days per week")
        requirements = []
        for identifier, quote, evidence in [("degree", "Bachelor degree required", edu),
                                            ("days", "Available three days required", days)]:
            req = self.requirement(identifier, quote, "hard_gate", "met")
            req["evidence_refs"] = [{"type": "assertion", "id": evidence}]
            requirements.append(req)
        analysis = self.save_analysis(job, requirements)
        self.assertEqual(self.saved(analysis)["recommendation"], "apply")
        self.assertTrue(all(not req["experience_ids"] for req in self.saved(analysis)["requirements"]))
        resume = s.build_resume(job, [self.add_experience()])
        self.assertEqual(a.save_review(self.review(resume, analysis, ["degree", "days"]))["grade"], "A")

    def test_vague_inferred_retracted_and_superseded_assertions_rejected(self):
        job = self.add_job("Attendance required")
        unknown = assertions.propose(subject="candidate", predicate="unknown_attendance", value="Maybe three days",
            assertion_type="fact", source_type="user_message", confidence="low")["id"]
        inferred = assertions.propose(subject="candidate", predicate="inferred_attendance", value="Three days",
            assertion_type="fact", source_type="model_inference")["id"]
        retracted = self.assertion("retracted_attendance", "Three days")
        assertions.retract(retracted, "Unavailable")
        superseded = self.assertion("changed_attendance", "Three days")
        assertions.revise(superseded, value="One day", reason="Correction")
        for identifier in [unknown, inferred, retracted, superseded, 99999]:
            with self.subTest(identifier=identifier), self.assertRaises(s.ValidationError):
                req = self.requirement("attendance", "Attendance required", "hard_gate", "met")
                req["evidence_refs"] = [{"type": "assertion", "id": identifier}]
                self.save_analysis(job, [req])

    def test_clear_self_report_does_not_need_repeated_confirmation_or_attachment(self):
        job = self.add_job("Attendance required")
        identifier = self.assertion("self_reported_attendance", "Three days", confirm=False)
        req = self.requirement("attendance", "Attendance required", "hard_gate", "met")
        req["evidence_refs"] = [{"type": "assertion", "id": identifier}]
        analysis = self.save_analysis(job, [req])
        self.assertEqual(self.saved(analysis)["requirements"][0]["match"], "met")

    def test_participation_and_timely_are_words_not_compound_tasks(self):
        self.assertFalse(a._is_compound("参与团队活动"))
        self.assertFalse(a._is_compound("及时反馈"))
        self.assertTrue(a._is_compound("差旅安排与员工考勤"))

    def test_assertion_correction_invalidates_saved_analysis_at_review_time(self):
        job = self.add_job("Attendance required")
        evidence = self.assertion("attendance", "Three days")
        req = self.requirement("attendance", "Attendance required", "hard_gate", "met")
        req["evidence_refs"] = [{"type": "assertion", "id": evidence}]
        analysis = self.save_analysis(job, [req])
        resume = s.build_resume(job, [self.add_experience()])
        assertions.revise(evidence, value="One day", reason="Schedule correction")
        with self.assertRaisesRegex(s.ValidationError, "current"):
            a.save_review(self.review(resume, analysis, ["attendance"]))

    def test_document_reference_requires_verified_ledger_source_and_binds_local_bytes(self):
        job = self.add_job("License required")
        path = Path(self.tmp.name) / "fictional-license.txt"
        path.write_text("Fictional certificate", encoding="utf-8")
        document = self.assertion("license", "Valid license", source_type="document", source_ref=str(path))
        req = self.requirement("license", "License required", "hard_gate", "met")
        req["evidence_refs"] = [{"type": "document", "id": document}]
        analysis = self.save_analysis(job, [req])
        saved = self.saved(analysis)
        self.assertIn("document_sha256", saved["requirements"][0]["evidence_refs"][0])
        path.write_text("Changed certificate", encoding="utf-8")
        with self.assertRaisesRegex(s.ValidationError, "stale"):
            a.save_analysis(saved)
        req["evidence_refs"] = [{"type": "document", "id": self.assertion("not_document", "License exists")}]
        with self.assertRaisesRegex(s.ValidationError, "document-verified"):
            self.save_analysis(job, [req])

    def test_experience_version_and_legacy_ids_are_frozen_and_revalidated(self):
        job, (exp, _), analysis, resume, _ = self.prepared([
            self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"])])
        ref = self.saved(analysis)["requirements"][0]["evidence_refs"][0]
        self.assertEqual((ref["type"], ref["id"], ref["version"]), ("experience_version", exp, 1))
        library.revise(exp, {"outcomes": ["Corrected outcome"], "approved_for_resume": True}, reason="Fictional correction")
        with self.assertRaisesRegex(s.ValidationError, "stale"):
            a.save_analysis(self.saved(analysis))
        with self.assertRaisesRegex(s.ValidationError, "needs_review"):
            a.save_review(self.review(resume, analysis, ["python"]))

    def test_unknown_health_certificate_blocker_remains_unknown(self):
        _, _, analysis, resume, _ = self.prepared([
            self.requirement("health", "Python is required", "hard_gate", "unknown")])
        finding = {"id": "health-unknown", "stage": "hr", "severity": "blocker",
            "issue": "Health certificate not confirmed", "evidence": "No answer yet", "requirement_ids": ["health"]}
        result = a.save_review(self.review(resume, analysis, ["health"], findings=[finding]))
        self.assertIsNone(result["grade"])
        self.assertEqual(result["status"], "NEEDS_EVIDENCE")
        review = self.review(resume, analysis, ["health"], findings=[finding])
        review["stages"]["hr"].update(verdict="fail", requirement_ids=["health"])
        self.assertIsNone(a.save_review(review)["grade"])

    def test_unknown_gate_with_independent_proven_disqualification_still_d(self):
        _, _, analysis, resume, _ = self.prepared([
            self.requirement("health", "Python is required", "hard_gate", "unknown")])
        evidence = self.assertion("legal_ineligibility", "Required professional registration was revoked")
        finding = {"id": "known-veto", "stage": "hr", "severity": "blocker", "issue": "Registration revoked",
            "evidence": "Candidate explicitly confirmed revocation", "requirement_ids": [],
            "evidence_basis": "verified_disqualification", "evidence_refs": [{"type": "assertion", "id": evidence}]}
        self.assertEqual(a.save_review(self.review(resume, analysis, ["health"], findings=[finding]))["grade"], "D")

    def test_compound_travel_does_not_cover_attendance(self):
        job = self.add_job("差旅安排与员工考勤")
        exp = self.add_experience(claim="Arranged travel")
        req = self.requirement("admin", "差旅安排与员工考勤", "core", "met", [exp])
        with self.assertRaisesRegex(s.ValidationError, "Compound"):
            self.save_analysis(job, [req])
        req["components"] = [self.requirement("travel", "差旅安排", "core", "met", [exp]),
                             self.requirement("attendance", "员工考勤", "core", "unknown")]
        with self.assertRaisesRegex(s.ValidationError, "complete"):
            self.save_analysis(job, [req])
        req["match"] = "unknown"
        saved = self.saved(self.save_analysis(job, [req]))
        self.assertEqual([c["match"] for c in saved["requirements"][0]["components"]], ["met", "unknown"])
        req["match"] = "met"
        req["components"][1] = self.requirement("duplicated-travel", "差旅安排", "core", "met", [exp])
        with self.assertRaisesRegex(s.ValidationError, "omits"):
            self.save_analysis(job, [req])

    def test_supported_complete_compound_coverage_can_be_met(self):
        job = self.add_job("差旅安排与员工考勤")
        travel, attendance = self.add_experience(), self.add_experience(claim="Recorded attendance")
        req = self.requirement("admin", "差旅安排与员工考勤", "core", "met")
        req["components"] = [self.requirement("travel", "差旅安排", "core", "met", [travel]),
                             self.requirement("attendance", "员工考勤", "core", "met", [attendance])]
        self.assertEqual(self.saved(self.save_analysis(job, [req]))["requirements"][0]["experience_ids"], [travel, attendance])

    def test_hypothetical_competitors_do_not_deterministically_cap_grade(self):
        _, _, analysis, resume, _ = self.prepared([
            self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"])])
        finding = {"id": "rival", "stage": "competition", "severity": "structural", "issue": "Rivals may have internships",
            "evidence": "Hypothesis without candidate-pool evidence", "requirement_ids": ["python"]}
        result = a.save_review(self.review(resume, analysis, ["python"], verdicts={"competition": "fail"}, findings=[finding]))
        self.assertEqual(result["grade"], "A")
        saved_review = a.list_reviews(resume["id"])[0]["review"]
        self.assertEqual(saved_review["stages"]["competition"]["evidence_basis"], "hypothetical")
        self.assertEqual(saved_review["red_findings"][0]["issue"], finding["issue"])

    def test_candidate_pool_basis_requires_sources(self):
        _, _, analysis, resume, _ = self.prepared([
            self.requirement("python", "Python is required", "hard_gate", "met", ["EXP1"])])
        review = self.review(resume, analysis, ["python"], verdicts={"competition": "risk"})
        review["stages"]["competition"].update(evidence_basis="candidate_pool", sources=[])
        with self.assertRaisesRegex(s.ValidationError, "sources"):
            a.save_review(review)

    def test_mission_focus_keeps_ancillary_gap_and_downstream_themes(self):
        job = self.add_job("Python delivery\nCommunication\nOffice decoration")
        exp = self.add_experience()
        requirements = [self.requirement("delivery", "Python delivery", "core", "met", [exp]),
                        self.requirement("comms", "Communication", "core", "met", [exp]),
                        self.requirement("decor", "Office decoration", "core", "gap")]
        data = a.draft_analysis(job)
        data.update(requirements=requirements, unknowns=[], coverage_confirmed=True, role_focus={
            "mission": "Support reliable project delivery", "hiring_motive": {"fact": "", "inference": "Team may need execution support", "sources": []},
            "core_deliverables": [{"id": "delivery", "text": "Delivered project", "requirement_ids": ["delivery"]},
                                  {"id": "handover", "text": "Clear handover", "requirement_ids": ["comms"]}],
            "resume_themes": ["Lead with delivery"], "interview_themes": ["Explain ownership"]})
        analysis = a.save_analysis(data)
        self.assertEqual(self.saved(analysis)["recommendation"], "apply")
        self.assertEqual(a.analysis_packet(job)["role_focus"]["resume_themes"], ["Lead with delivery"])
        resume = s.build_resume(job, [exp])
        self.assertEqual(a.review_packet(resume["id"])["role_focus"]["interview_themes"], ["Explain ownership"])
        result = a.save_review(self.review(resume, analysis, ["delivery", "comms", "decor"]))
        self.assertEqual(result["grade"], "B")
        self.assertIn("ancillary", " ".join(result["reasons"]))
        self.assertEqual(a.list_reviews(resume["id"])[0]["review"]["role_focus"], data["role_focus"])
        data["role_focus"]["hiring_motive"]["fact"] = "Company is expanding its team"
        with self.assertRaisesRegex(s.ValidationError, "requires sources"):
            a.save_analysis(data)
        data["role_focus"]["hiring_motive"]["fact"] = ""
        data["role_focus"]["core_deliverables"] = data["role_focus"]["core_deliverables"][:1]
        with self.assertRaisesRegex(s.ValidationError, "2-4"):
            a.save_analysis(data)

    def test_packet_contains_index_and_explicit_scope_without_full_evidence_dump(self):
        job = self.add_job()
        for i in range(20):
            self.add_experience(claim="PRIVATE FULL DETAIL " + str(i) + "x" * 500)
        packet = a.analysis_packet(job)
        self.assertLessEqual(packet["experience_index"]["budget"]["actual"], 2200)
        self.assertGreater(packet["experience_index"]["omitted_count"], 0)
        self.assertNotIn("evidence", packet["approved_experiences"][0])


if __name__ == "__main__":
    unittest.main()
