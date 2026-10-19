"""Anonymized audit regressions; every database and output is synthetic."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oriward import experience_library as lib, services as s, sources
from oriward.core import assertions
from oriward.db import connect


class ExperienceLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ORIWARD_DB": str(Path(self.tmp.name) / "synthetic.sqlite3"),
                                     "ORIWARD_OUTPUT_DIR": str(Path(self.tmp.name) / "outputs")})
        env.start()
        self.addCleanup(env.stop)

    def experience(self, **changes):
        d = {"event": "Community promotion", "actions": ["30人到院，是否付费未知"], "outcomes": [],
             "evidence": [{"claim": "30人到院，是否付费未知", "source": "user self-report", "status": "user_stated"}],
             "approved_for_resume": True}
        return lib.create({**d, **changes})

    def job(self):
        s.save_profile({"display_name": "Synthetic Candidate"})
        return sources.import_records([{"source": "fixture", "source_id": "1", "title": "Intern",
            "company": "Fictional", "description": "Support promotion", "availability": "listed",
            "url": "https://example.invalid/job"}])["job_ids"][0]

    def test_minimal_intake_allows_empty_arrays_and_no_documents(self):
        eid = s.add_object("experiences", {"event": "Coursework", "actions": [], "outcomes": [], "evidence": []}, ["approved_for_resume"])
        d = lib.get(eid)["data"]
        self.assertFalse(d["approved_for_resume"])
        self.assertEqual(lib.history(eid)[0]["version"], 1)
        self.assertNotIn("attachments", d)

    def test_user_self_report_suffices_for_resume(self):
        eid = self.experience()
        resume = s.build_resume(self.job(), [eid])
        self.assertIn("30人到院", Path(resume["path"]).read_text(encoding="utf-8"))

    def test_fact_correction_regenerates_authored_summary(self):
        eid = self.experience(summary="30 paid transactions", actions=["30 paid transactions"])
        lib.revise(eid, {"actions": ["30 arrivals; payment unknown"]}, reason="Correct result definition")
        item = lib.index(ids=[eid])["items"][0]
        self.assertNotIn("paid transactions", item["summary"])
        self.assertIn("30 arrivals", item["summary"])

    def test_skill_cards_group_current_modules_and_drop_excluded_sources(self):
        first = self.experience(tags=["活动协调"])
        second = self.experience(tags=[{"name": "活动协调", "source": "user_stated"}])
        card = lib.skills()["items"][0]
        self.assertEqual({r["id"] for r in card["experience_refs"]}, {first, second})
        self.assertEqual({r["label_source"] for r in card["experience_refs"]}, {"model_inference", "user_stated"})
        lib.exclude(first, reason="Not using this experience")
        card = lib.skills(query="协调")["items"][0]
        self.assertEqual([r["id"] for r in card["experience_refs"]], [second])
        self.assertNotIn("30人到院", json.dumps(card, ensure_ascii=False))

    def test_tight_index_budget_returns_a_directory_card_with_progress(self):
        self.experience(event="Very long fictional experience name " * 4, summary="s" * 130,
                        tags=["very long skill name " * 3] * 3)
        index = lib.index(budget=500)
        self.assertLessEqual(index["budget"]["actual"], 500)
        self.assertEqual(index["next_offset"], 1)
        self.assertTrue(index["items"][0]["compact_card"])

    def test_stable_id_correction_preserves_history_and_invalidates_old_resume(self):
        eid = self.experience(actions=["约30单成交"])
        jid = self.job()
        old = s.build_resume(jid, [eid])
        old_bytes = Path(old["path"]).read_bytes()
        lib.revise(eid, {"actions": ["30人到院，是否付费未知"]}, reason="Correct transaction scope", expected_version=1)
        self.assertEqual([r["version"] for r in lib.history(eid)], [1, 2])
        self.assertEqual(lib.get(eid)["data"]["actions"], ["30人到院，是否付费未知"])
        self.assertFalse(lib.get(eid)["data"]["approved_for_resume"])
        self.assertTrue(s.list_objects("resumes")[0]["needs_review"])
        self.assertEqual(Path(old["path"]).read_bytes(), old_bytes)
        with self.assertRaisesRegex(ValueError, "needs_review"):
            s.prepare_application(jid, old["id"])
        with self.assertRaisesRegex(ValueError, "version changed"):
            lib.revise(eid, {"actions": []}, reason="stale attempt", expected_version=1)
        self.assertEqual(len(lib.history(eid)), 2)

    def test_reverse_linked_assertion_revision_blocks_old_approved_experience(self):
        eid = self.experience(actions=["约30单成交"])
        aid = assertions.propose(subject="user", predicate="promotion_result", value={"text": "约30单成交"},
                                 assertion_type="fact", source_type="user_message", links=[
                                     {"ref_type": "experience", "ref_id": eid, "relation": "supports"}])["id"]
        revised = assertions.revise(aid, value={"text": "30人到院，是否付费未知"})["id"]
        self.assertTrue(lib.get(eid)["needs_review"])
        self.assertEqual(s.list_objects("experiences"), [])
        self.assertNotIn("约30单成交", json.dumps(lib.index(), ensure_ascii=False))
        with self.assertRaisesRegex(ValueError, "needs_review"):
            s.build_resume(self.job(), [eid])
        lib.revise(eid, {"actions": ["30人到院，是否付费未知"], "assertion_ids": [revised],
                         "approved_for_resume": True}, reason="User corrected and approved current scope")
        self.assertFalse(lib.get(eid)["needs_review"])
        self.assertTrue(s.build_resume(self.job(), [eid]))

    def test_exclusion_and_supersession_affect_all_default_selection(self):
        eid = self.experience()
        replacement = self.experience(event="Corrected same experience")
        lib.supersede(eid, replacement, reason="Legacy duplicate replaced")
        lib.exclude(replacement, reason="User excludes this work")
        self.assertEqual(lib.index()["items"], [])
        self.assertEqual(s.list_objects("experiences"), [])
        self.assertEqual(lib.detail(query="Community")["selected_count"], 0)
        with self.assertRaisesRegex(ValueError, "inactive"):
            lib.get(eid)
        self.assertEqual(lib.get(eid, include_inactive=True)["data"]["superseded_by_id"], replacement)
        self.assertEqual(len(lib.history(eid)), 2)
        self.assertFalse(lib.exclude(replacement, reason="Replay same exclusion")["changed"])
        with self.assertRaisesRegex(ValueError, "inactive"):
            s.build_resume(self.job(), [eid])

    def test_current_detail_selects_only_requested_sections_and_records_scope(self):
        first = self.experience(attachments=[{"path": "private-secret.pdf"}], context="private context " * 500)
        second = self.experience(event="Unrelated course")
        result = lib.detail(ids=[first], sections=["actions", "outcomes"])
        self.assertEqual(result["items"][0]["sections_read"], ["actions", "outcomes"])
        self.assertEqual(set(result["items"][0]["data"]), {"actions", "outcomes"})
        self.assertNotIn("private-secret", json.dumps(result))
        self.assertNotIn(str(second), str(result["selection"]["ids"]))
        with self.assertRaises(ValueError):
            lib.detail()
        with self.assertRaises(ValueError):
            lib.get(first, sections=["unknown"])

    def test_twenty_long_experiences_index_is_really_bounded_and_pageable(self):
        ids = []
        for number in range(20):
            ids.append(self.experience(event=f"课程项目 {number}", actions=["个人调研与协作" * 120],
                                       context="详细分工" * 1000,
                                       inferred_skills=[{"name": "活动协调", "reason": "exploratory", "confidence": "medium"}]))
        for budget in (1500, 2200, 2500):
            page = lib.index(budget=budget)
            actual = len(json.dumps(page, ensure_ascii=False, indent=2, default=str))
            self.assertLessEqual(actual, budget)
            self.assertEqual(page["budget"]["actual"], actual)
            self.assertFalse(page["complete"])
            self.assertEqual(page["omitted_count"] + len(page["items"]), 20)
            self.assertNotIn("详细分工", json.dumps(page, ensure_ascii=False))
        seen = []
        offset = 0
        for _ in range(20):
            page = lib.index(budget=1500, offset=offset)
            seen.extend(item["id"] for item in page["items"])
            offset = page["next_offset"]
            if offset >= 20:
                break
        self.assertEqual(set(seen), set(ids))
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(lib.index(query="课程项目 19")["items"][0]["id"], ids[-1])

    def test_index_uses_explicit_summary_and_available_time_fields(self):
        eid = self.experience(summary="协调社群活动并跟进到院反馈", time_period="2024年暑期",
                              actions=["长动作详情不进索引"], tags=[{"name": "活动协调", "source": "user_stated"}])
        item = lib.index(ids=[eid])["items"][0]
        self.assertEqual(item["period"], "2024年暑期")
        self.assertEqual(item["summary"], "协调社群活动并跟进到院反馈")
        self.assertEqual(item["tags"], [{"name": "活动协调", "source": "user_stated"}])
        self.assertEqual(lib.get(eid, sections=["summary", "time_period", "tags"])["data"]["summary"], item["summary"])
        lib.revise(eid, {"tags": [{"name": "协作", "source": "model_inference"}]}, reason="Exploratory label refinement")
        self.assertTrue(lib.get(eid)["data"]["approved_for_resume"])

    def test_inferred_capability_correction_does_not_invalidate_factual_experience(self):
        eid = self.experience()
        aid = assertions.propose(subject="user", predicate="coordination", value={"text": "coordination"},
                                 assertion_type="skill_hypothesis", source_type="model_inference", links=[
                                     {"ref_type": "experience", "ref_id": eid, "relation": "derived_from"}])["id"]
        assertions.revise(aid, value={"text": "coordination remains exploratory"}, source_type="model_inference")
        self.assertFalse(lib.get(eid)["needs_review"])

    def test_invalid_dependency_revision_rolls_back_history_and_current(self):
        eid = self.experience()
        with self.assertRaises(ValueError):
            lib.revise(eid, {"assertion_ids": [9999]}, reason="Invalid dependency")
        self.assertEqual(lib.get(eid)["version"], 1)
        self.assertEqual(len(lib.history(eid)), 1)
        with self.assertRaises(ValueError):
            lib.create({"event": "Bad", "actions": [1], "outcomes": [], "evidence": []})

    def test_legacy_row_lazy_snapshot_and_current_defaults(self):
        with connect() as db:
            eid = db.execute("INSERT INTO experiences(data,created_at) VALUES (?,?)", (
                json.dumps({"event": "Legacy", "actions": [], "outcomes": [], "evidence": [],
                            "approved_for_resume": False}), "2020-01-01T00:00:00+00:00")).lastrowid
        self.assertEqual(lib.get(eid)["version"], 1)
        lib.revise(eid, {"outcomes": ["Corrected"]}, reason="First current correction")
        self.assertEqual([r["version"] for r in lib.history(eid)], [1, 2])


if __name__ == "__main__":
    unittest.main()
