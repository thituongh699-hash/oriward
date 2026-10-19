"""Regression tests for assertion provenance and feedback promotion boundaries."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from careeros.core import assertions, signals
from careeros.core.errors import NotFoundError


class AssertionIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.dict(os.environ, {
            "CAREEROS_DB": str(Path(self.tmp.name) / "db.sqlite3"),
            "CAREEROS_OUTPUT_DIR": str(Path(self.tmp.name) / "outputs"),
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def propose(self, **kwargs):
        params = {
            "subject": "user", "predicate": "preferred_city", "value": {"text": "上海"},
            "assertion_type": "preference", "source_type": "user_message",
        }
        params.update(kwargs)
        return assertions.propose(**params)

    def test_non_user_sources_cannot_claim_any_user_backed_status(self):
        for source in assertions.NON_USER_SOURCES:
            for status in assertions.USER_BACKED:
                with self.subTest(source=source, status=status), self.assertRaises(ValueError):
                    self.propose(source_type=source, epistemic_status=status)
            with self.subTest(source=source, status="disputed"), self.assertRaises(ValueError):
                self.propose(source_type=source, epistemic_status="disputed")

    def test_unknown_source_and_status_are_rejected(self):
        with self.assertRaises(ValueError):
            self.propose(source_type="unverified_import")
        with self.assertRaises(ValueError):
            self.propose(epistemic_status="verified_by_magic")

    def test_source_defaults_and_explicit_experience_inference_remain_compatible(self):
        expected = {
            "user_message": "user_stated", "document": "document_verified",
            "experience": "user_confirmed", "model_inference": "inferred",
        }
        for source, status in expected.items():
            with self.subTest(source=source):
                claim = self.propose(source_type=source, predicate=f"claim_{source}")
                self.assertEqual(claim["epistemic_status"], status)
        inferred = self.propose(source_type="experience", predicate="experience_inference",
                                epistemic_status="inferred")
        self.assertEqual(inferred["epistemic_status"], "inferred")

    def test_revision_inherits_provenance_and_history_keeps_each_version(self):
        first = self.propose(
            source_ref="message:42", explanation="原始说明",
            links=[{"ref_type": "document", "ref_id": "resume.pdf", "relation": "supports"}],
        )
        second = assertions.revise(first["id"], value={"text": "杭州"}, reason="用户缩小范围")
        current = assertions.get(second["id"])
        self.assertEqual(current["source_ref"], "message:42")
        self.assertEqual(current["explanation"], "原始说明")
        self.assertEqual([(link["ref_type"], link["ref_id"]) for link in current["links"]],
                         [("document", "resume.pdf")])
        versions = assertions.history(assertion_id=first["id"])["versions"]
        self.assertEqual([v["explanation"] for v in versions], ["原始说明", "原始说明"])
        self.assertEqual([v["source_ref"] for v in versions], ["message:42", "message:42"])
        self.assertEqual(len(versions[0]["links"]), 1)
        self.assertEqual(len(versions[1]["links"]), 1)
        self.assertTrue(any(item["kind"] == "assertion.revised" for item in versions[1]["audit"]))
        self.assertTrue(any("用户缩小范围" in item["detail"] for item in versions[1]["audit"]))

    def test_revision_can_clear_or_replace_links(self):
        first = self.propose(links=[{"ref_type": "document", "ref_id": "old.pdf"}])
        cleared = assertions.revise(first["id"], links=[])
        self.assertEqual(assertions.get(cleared["id"])["links"], [])

        replaced = assertions.revise(
            cleared["id"], links=[{"ref_type": "message", "ref_id": "new-message"}],
        )
        links = assertions.get(replaced["id"])["links"]
        self.assertEqual([(link["ref_type"], link["ref_id"]) for link in links],
                         [("message", "new-message")])

    def test_invalid_revision_links_do_not_partially_supersede(self):
        first = self.propose(links=[{"ref_type": "document", "ref_id": "kept.pdf"}])
        with self.assertRaises(NotFoundError):
            assertions.revise(first["id"], value={"text": "杭州"}, links=[
                {"ref_type": "document", "ref_id": "valid.pdf"},
                {"ref_type": "experience", "ref_id": 99999},
            ])
        self.assertEqual([row["id"] for row in assertions.list_assertions()], [first["id"]])
        original = assertions.get(first["id"])
        self.assertEqual(original["valid_to"], "")
        self.assertEqual([link["ref_id"] for link in original["links"]], ["kept.pdf"])

    def test_auto_superseding_inference_keeps_its_evidence_in_history(self):
        inferred = self.propose(source_type="model_inference", links=[
            {"ref_type": "document", "ref_id": "evidence.pdf", "relation": "derived_from"},
        ])
        stated = self.propose(value={"text": "杭州"})
        self.assertEqual(stated["supersedes"], inferred["id"])
        versions = assertions.history(assertion_id=stated["id"])["versions"]
        self.assertEqual(versions[0]["links"][0]["ref_id"], "evidence.pdf")
        self.assertEqual(versions[1]["links"], [])
        self.assertTrue(versions[0]["valid_to"])

    def add_feedback(self, *, reason="", feedback_type="not_interested"):
        return signals.add(target_type="system", target_id=1, feedback_type=feedback_type,
                           reason=reason)

    def test_promotion_requires_specific_rule_and_valid_type(self):
        empty = self.add_feedback()
        with self.assertRaises(ValueError):
            signals.promote(empty["id"], human_confirmed=True)
        with self.assertRaises(ValueError):
            signals.promote(empty["id"], human_confirmed=True, value="not_interested")

        reasoned = self.add_feedback(reason="常驻出差不适合我")
        with self.assertRaises(ValueError):
            signals.promote(reasoned["id"], human_confirmed=True, assertion_type="skill_hypothesis")
        self.assertFalse(assertions.list_assertions(assertion_type="constraint"))

    def test_promotion_preserves_low_confidence_self_report_and_positive_preferences(self):
        cautious = self.add_feedback(reason="我可能不太接受长期出差")
        promoted = signals.promote(cautious["id"], human_confirmed=True, confidence="low")
        claim = assertions.get(promoted["assertion_id"])
        self.assertEqual(claim["epistemic_status"], "user_stated")
        self.assertEqual(claim["confidence"], "low")

        positive = self.add_feedback(reason="更偏好能持续学习的团队", feedback_type="interested")
        pref = signals.promote(positive["id"], human_confirmed=True, assertion_type="preference",
                               subject="user", predicate="team_preference", value="持续学习")
        self.assertEqual(assertions.get(pref["assertion_id"])["assertion_type"], "preference")

    def test_human_confirmation_gate_is_unchanged(self):
        feedback = self.add_feedback(reason="不接受长期出差")
        with self.assertRaises(ValueError):
            signals.promote(feedback["id"])


if __name__ == "__main__":
    unittest.main()
