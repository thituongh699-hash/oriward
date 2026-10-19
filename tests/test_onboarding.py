import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oriward import onboarding as o, services
from oriward.db import connect, deserialize, now


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"ORIWARD_DB": str(Path(self.temp.name) / "fictional.sqlite3")})
        env.start()
        self.addCleanup(env.stop)

    def test_first_use_persists_lightweight_default_and_does_not_block_urgent_work(self):
        state = o.status()
        self.assertEqual(state["intent"], "experience_index")
        self.assertEqual(state["channels"], {})
        prompts = o.missing_prompts()
        self.assertFalse(prompts["blocks_search"])
        self.assertEqual(prompts["default_next_step"], "lightweight_experience_index")
        self.assertEqual({p["field"] for p in prompts["prompts"]}, {"intent", "companies", "roles", "constraints", "channels"})
        with connect() as conn:
            saved = deserialize(conn.execute("SELECT data FROM career_settings WHERE key='onboarding'").fetchone()[0])
        self.assertEqual(saved, state)
        o.update_preferences(intent="specific_jd")
        self.assertEqual(o.continuation()["intent"], "specific_jd")

    def test_explicit_empty_defer_and_decline_are_not_repeated(self):
        o.update_preferences(companies=[], roles=["虚构研究实习"], constraints={"location": "测试城市"})
        o.mark_prompt("intent", "later")
        o.set_channel_preference("liepin", "later")
        self.assertEqual(o.missing_prompts(before_search=True)["prompts"], [])
        o.set_channel_preference("liepin", "declined")
        self.assertEqual(o.missing_prompts()["prompts"], [])
        o.set_channel_preference("liepin", "unasked")
        self.assertEqual([p["field"] for p in o.missing_prompts(before_search=True)["prompts"]], ["channels"])

    def test_preference_does_not_enable_extension_or_establish_connection(self):
        with patch.dict(os.environ, {}, clear=True):
            # Preserve the isolated DB rather than touching default personal state.
            with patch.dict(os.environ, {"ORIWARD_DB": str(Path(self.temp.name) / "fictional.sqlite3")}):
                result = o.set_channel_preference("liepin", "connect_now")
                self.assertEqual(result["connection"], "not_connected")
                self.assertNotIn("ORIWARD_ENABLE_LIEPIN", os.environ)
                with self.assertRaisesRegex(ValueError, "validation_receipt"):
                    o.set_channel_connection("liepin", "connected")
                result = o.set_channel_connection("liepin", "connected", validation_receipt={
                    "checked_at": now(), "evidence": "Fictional adapter minimal read succeeded"})
                self.assertEqual(result["preference"], "connect_now")
                o.set_channel_preference("liepin", "later")
                self.assertEqual(o.status()["channels"]["liepin"]["connection"], "connected")
                self.assertNotIn("ORIWARD_ENABLE_LIEPIN", os.environ)

    def test_topic_switch_and_resume_keep_next_action_and_blocker(self):
        first = o.set_topic("虚构课程经历", next_action="补充本人动作", blocker="待回忆")
        second = o.set_topic("虚构JD", next_action="读取核心交付")
        state = o.continuation()
        self.assertEqual(state["current_topic"]["id"], second["id"])
        self.assertEqual(state["paused_branches"][0]["blocker"], "待回忆")
        resumed = o.resume_topic(first["id"])
        self.assertEqual(resumed["next_action"], "补充本人动作")
        self.assertEqual(o.continuation()["paused_branches"][0]["id"], second["id"])
        o.pause_topic(reason="用户暂缓")
        self.assertIsNone(o.continuation()["current_topic"])
        with self.assertRaisesRegex(ValueError, "not found"):
            o.resume_topic(999)

    def test_profile_targets_are_reused_and_changes_not_frozen(self):
        services.save_profile({"display_name": "虚构用户", "target_roles": ["虚构运营实习"], "location": "测试城市"})
        state = o.status()
        self.assertEqual(state["roles"], ["虚构运营实习"])
        self.assertEqual(state["constraints"]["location"], "测试城市")
        self.assertNotIn("roles", [p["field"] for p in o.missing_prompts()["prompts"]])
        services.save_profile({"display_name": "虚构用户", "target_roles": ["虚构分析实习"]})
        self.assertEqual(o.status()["roles"], ["虚构分析实习"])
        o.update_preferences(roles=[])
        self.assertEqual(o.status()["roles"], [])

    def test_invalid_update_rolls_back(self):
        o.update_preferences(roles=["虚构方向"])
        with self.assertRaises(ValueError):
            o.update_preferences(roles=["另一个方向"], intent="invented")
        self.assertEqual(o.status()["roles"], ["虚构方向"])

    def test_profile_arrangement_corrections_refresh_only_inherited_fields(self):
        services.save_profile({"display_name": "虚构用户", "location": "上海", "availability": "每周三天"})
        self.assertEqual(o.status()["constraints"]["location"], "上海")
        services.save_profile({"display_name": "虚构用户", "location": "杭州", "availability": "每周四天"})
        self.assertEqual(o.status()["constraints"]["location"], "杭州")
        self.assertEqual(o.status()["constraints"]["availability"], "每周四天")
        o.update_preferences(constraints={"location": "用户选择的地点"})
        services.save_profile({"display_name": "虚构用户", "location": "北京", "availability": "每周五天"})
        self.assertEqual(o.status()["constraints"]["location"], "用户选择的地点")
        self.assertEqual(o.status()["constraints"]["availability"], "每周五天")


if __name__ == "__main__":
    unittest.main()
