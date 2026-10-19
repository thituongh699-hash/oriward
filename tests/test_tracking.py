import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from oriward import services as s, sources, tracking


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"ORIWARD_DB": str(self.root / "db.sqlite3"),
                                     "ORIWARD_OUTPUT_DIR": str(self.root / "resumes")})
        env.start()
        self.addCleanup(env.stop)
        s.save_profile({"display_name": "Fictional Candidate"})
        self.exp = s.add_object("experiences", {
            "event": "Demo project", "actions": ["Built a Python report"], "outcomes": ["Delivered it"],
            "evidence": [{"claim": "Built a Python report", "source": "fixture", "status": "user_confirmed"}],
            "approved_for_resume": True,
        }, ["event", "actions", "outcomes", "evidence", "approved_for_resume"])

    def two_platforms(self):
        return sources.import_records([
            {"source": "zhiye", "source_id": "a", "title": "数据产品经理",
             "company": "北京三快在线科技有限公司", "location": "上海市", "description": "岗位职责：负责数据产品。",
             "url": "https://zhiye.page/jobs/job_a", "published_at": "2026-10-01", "availability": "unknown"},
            {"source": "boss", "source_id": "b", "title": "数据产品经理（急招）",
             "company": "北京三快在线科技", "location": "上海", "description": "岗位职责：负责数据产品规划与落地。",
             "url": "https://www.zhipin.com/job_detail/b.html", "published_at": "2026-09-20T09:00:00+08:00"},
        ])["job_ids"]

    def test_same_vacancy_on_two_platforms_is_grouped(self):
        first, second = self.two_platforms()
        card = tracking.job_card(first)
        self.assertEqual(card["vacancy_group"]["members"], 2)
        self.assertEqual({c["channel"] for c in card["channels"]}, {"zhiye", "boss"})
        self.assertEqual(card["channels"][0]["channel"], "zhiye")
        listed = tracking.groups()
        self.assertEqual(listed["multi_channel_groups"], 1)
        self.assertEqual(listed["groups"][0]["applied"], [])
        self.assertEqual(listed["decision"], "user_decides")
        self.assertEqual(tracking.job_card(second)["vacancy_group"]["id"], card["vacancy_group"]["id"])

    def test_normalization_matches_legal_suffix_city_and_noise_brackets(self):
        self.assertEqual(tracking.normalize_company("北京三快在线科技有限公司"), tracking.normalize_company("北京三快在线科技"))
        self.assertEqual(tracking.normalize_title("数据产品经理（急招）"), tracking.normalize_title("数据产品经理"))
        self.assertEqual(tracking.normalize_location("上海市"), tracking.normalize_location("上海"))
        self.assertNotEqual(tracking.vacancy_key("A公司", "产品经理", "上海")[0],
                            tracking.vacancy_key("A公司", "产品经理", "北京")[0])

    def test_card_carries_published_at_jd_channels_and_gaps(self):
        first, _ = self.two_platforms()
        card = tracking.job_card(first)
        self.assertEqual(card["job"]["published_at"], "2026-10-01")
        self.assertEqual(card["job"]["published_at_source"], "published_at")
        self.assertGreater(card["jd"]["characters"], 0)
        self.assertEqual(card["gaps"], [])
        only = sources.import_records([{"source": "fixture", "source_id": "c", "title": "运营",
                                        "company": "Fictional", "description": "JD",
                                        "url": "https://example.invalid/c"}])["job_ids"][0]
        self.assertIn("published_at_missing", tracking.job_card(only)["gaps"])

    def test_application_records_channel_timeline_and_agenda(self):
        job, _ = self.two_platforms()
        resume = s.build_resume(job, [self.exp])
        app_id = s.prepare_application(job, resume["id"], channel="boss", apply_url="https://www.zhipin.com/job_detail/b.html")
        prepared = s.list_objects("applications")[0]
        self.assertEqual(prepared["channel"], "boss")
        self.assertEqual(prepared["apply_url"], "https://www.zhipin.com/job_detail/b.html")
        s.update_application(app_id, "SUBMITTED", human_confirmed=True)
        submitted = s.list_objects("applications")[0]
        self.assertTrue(submitted["applied_at"])
        timeline = tracking.list_events(app_id)
        self.assertEqual([event["kind"] for event in timeline], ["applied"])
        when = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(timespec="seconds")
        tracking.log_event(app_id, "interview", "一面", scheduled_at=when)
        self.assertEqual([event["kind"] for event in tracking.list_events(app_id)], ["applied", "interview"])
        agenda = tracking.agenda()
        self.assertEqual(agenda["scheduled"][0]["label"], "一面")
        card = tracking.job_card(job)
        self.assertEqual(card["applications"][0]["channel"], "boss")
        self.assertEqual(len(card["applications"][0]["timeline"]), 2)

    def test_repeat_application_is_reported_but_never_blocked(self):
        job, sibling = self.two_platforms()
        resume = s.build_resume(job, [self.exp])
        app_id = s.prepare_application(job, resume["id"], channel="boss")
        s.update_application(app_id, "SUBMITTED", human_confirmed=True)
        hints = s.repeat_application_hints(sibling)
        self.assertEqual(len(hints["already_applied_in_group"]), 1)
        self.assertEqual(hints["decision"], "user_decides")
        self.assertEqual(len(tracking.pipeline()["repeat_application_risk"]), 1)
        sibling_resume = s.build_resume(sibling, [self.exp])
        second = s.prepare_application(sibling, sibling_resume["id"], channel="zhilian")
        self.assertTrue(second)
        self.assertEqual(len(tracking.job_card(sibling)["applications"]), 1)

    def test_channel_backfill_and_validation(self):
        job, _ = self.two_platforms()
        resume = s.build_resume(job, [self.exp])
        app_id = s.prepare_application(job, resume["id"])
        self.assertEqual(s.list_objects("applications")[0]["channel"], "")
        self.assertIn("application_channel_missing", tracking.job_card(job)["gaps"])
        with self.assertRaisesRegex(s.ValidationError, "channel must be one of"):
            s.prepare_application(job, resume["id"], channel="not-a-channel")
        self.assertEqual(s.set_application_channel(app_id, "official")["channel"], "official")
        self.assertEqual(tracking.pipeline()["data_gaps"]["application_channel_missing"], 0)

    def test_pipeline_funnel_counts(self):
        self.two_platforms()
        data = tracking.pipeline()
        self.assertEqual(data["stages"]["jobs"], 2)
        self.assertEqual(data["jobs_by_channel"], {"zhiye": 1, "boss": 1})
        self.assertEqual(data["stages"]["prepared"], 0)
        self.assertEqual(data["rule"], "同一岗位多平台只做归并展示；是否重复投递由用户判断，系统不拦截。")

    def test_invalid_published_at_rejected(self):
        with self.assertRaisesRegex(sources.ValidationError, "published_at"):
            sources.import_records([{"source": "x", "title": "t", "company": "c", "description": "d",
                                     "published_at": "2026-13-01"}])
        with self.assertRaisesRegex(sources.ValidationError, "timezone"):
            sources.import_records([{"source": "x", "title": "t", "company": "c", "description": "d",
                                     "published_at": "2026-10-01T10:00:00"}])


if __name__ == "__main__":
    unittest.main()
