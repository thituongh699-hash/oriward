import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oriward.core.context import _fit, brief, section


class ContextRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.dict(os.environ, {"ORIWARD_DB": str(Path(self.temp.name) / "fictional.sqlite3")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_realistic_recovery_capsule_survives_optional_detail_truncation(self):
        recovery = {
            "focus": "课程项目",
            "current_topic": {"id": 41, "title": "课程项目", "status": "active", "next_action": "补充本人动作"},
            "identity": {"education": "虚构大学", "graduation_date": "2027", "location": "测试市", "availability": "每周三天"},
            "education_facts": [{"id": 30, "claim": "虚构大学", "status": "user_confirmed", "at": "2026-01-01"}],
            "availability": [{"id": 31, "claim": "每周三天，测试市", "status": "user_confirmed"}],
            "active_goal": {"id": 8, "title": "整理经历", "status": "active"},
            "next_or_review_or_blocker": {"action_id": 9, "title": "核实项目分工"},
            "experience_count": 12, "experience_index": "python -m oriward experience index",
            "job_ids": [3], "resume_ids": [5], "paused_count": 20, "paused_restore": [*range(1, 21)],
            "important_corrections": [{"assertion_id": 22, "change": "修订", "at": "2026-10-20"}],
            "conflicts": [{"assertion_id": 23, "status": "disputed"}],
        }
        data = {"recovery": recovery,
                "who_am_i": {"facts": [{"assertion_id": i, "claim": f"教育背景事实{i}"} for i in range(30)]},
                "continuation": {"paused_branches": [{"id": i, "title": f"历史分支{i}"} for i in range(20)]},
                "what_next": {"actions": [{"id": i, "title": f"待办{i}"} for i in range(8)]}, "_omitted": {}}
        fitted = _fit(data, 3200)
        rendered = json.dumps(fitted, ensure_ascii=False, indent=2)
        self.assertLessEqual(len(rendered), 3200)
        self.assertEqual(fitted["recovery"]["current_topic"]["id"], 41)
        for key in ("identity", "active_goal", "next_or_review_or_blocker", "experience_index",
                    "job_ids", "resume_ids", "paused_count", "paused_restore", "important_corrections", "conflicts"):
            self.assertIn(key, fitted["recovery"])
        self.assertEqual(fitted["recovery"]["education_facts"][0]["id"], 30)
        self.assertEqual(fitted["recovery"]["active_goal"]["id"], 8)
        self.assertEqual(fitted["recovery"]["next_or_review_or_blocker"]["action_id"], 9)
        self.assertFalse(fitted["context_budget"]["complete"])

    def test_tiny_budget_reports_overflow_without_claiming_complete(self):
        data = {"recovery": {"current_topic": {"id": 1, "status": "active", "next_action": "x"}},
                "_omitted": {}}
        fitted = _fit(data, 20)
        self.assertTrue(fitted["context_budget"]["over_budget"])
        self.assertFalse(fitted["context_budget"]["complete"])
        self.assertEqual(fitted["recovery"]["current_topic"]["id"], 1)

    def test_brief_and_section_apply_focus_and_expose_recovery(self):
        from oriward import onboarding
        onboarding.set_topic("虚构课程", next_action="补充本人动作")
        data = brief(focus="虚构课程")
        self.assertEqual(data["recovery"]["focus"], "虚构课程")
        self.assertEqual(data["recovery"]["current_topic"]["status"], "active")
        self.assertEqual(section("recovery", focus="项目经历")["focus"], "项目经历")

    def test_section_recovers_facts_omitted_from_whole_brief(self):
        from oriward.core import assertions
        for i in range(30):
            assertions.propose(subject="user", predicate=f"education{i}", value={"text": f"虚构学校学习记录{i}"},
                               assertion_type="fact", source_type="user_message")
        small = brief(max_chars=3200)
        details = section("who_am_i", max_chars=16000)
        self.assertLess(len(small["who_am_i"]["facts"]), 30)
        self.assertEqual(len(details["data"]["facts"]), 30)


if __name__ == "__main__":
    unittest.main()
