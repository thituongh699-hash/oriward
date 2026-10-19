import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oriward import search_runs as s, sources
from oriward.db import now


class SearchRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {"ORIWARD_DB": str(self.root / "fictional.sqlite3")})
        env.start()
        self.addCleanup(env.stop)

    def report(self, run_id):
        return Path(s.show(run_id)["report_path"]).read_text(encoding="utf-8")

    def test_mixed_routes_are_distinct_and_unknown_counts_never_become_zero(self):
        providers = ["official", "zhiye", "broken", "liepin", "boss", "unplanned", "empty"]
        run = s.create_run({"query": "虚构实习", "cities": ["测试城市"], "filters": {"type": "intern"},
                            "time_window": "最近7日"}, providers)
        self.assertTrue(Path(run["report_path"]).is_file())
        for provider in providers[:2]:
            s.record_channel(run["id"], provider, "success", counts={"leads": 1, "full_jds": 1, "imported": 1, "deduplicated": 1},
                             coverage="首屏，未分页", reason="单页读取完成")
        s.record_channel(run["id"], "broken", "failed", reason="Fictional timeout", next_action="换公开渠道")
        s.record_channel(run["id"], "liepin", "not_connected", reason="可选扩展未启用")
        s.record_channel(run["id"], "boss", "auth_required", reason="页面要求登录")
        s.record_channel(run["id"], "empty", "zero_results", reason="页面明确显示无结果")
        result = s.finish_run(run["id"])
        report = self.report(run["id"])
        for label in ("成功", "失败", "需登录/验证", "未接入", "未尝试", "确认零结果", "首屏，未分页", "Fictional timeout"):
            self.assertIn(label, report)
        self.assertIsNone(result["counts"]["leads"])
        self.assertIsNone(s.show(run["id"])["channels"]["broken"]["counts"]["leads"])
        self.assertEqual(s.show(run["id"])["channels"]["empty"]["counts"]["leads"], 0)
        self.assertEqual(s.list_runs()[0]["id"], run["id"])

    def test_candidate_dates_and_plans_do_not_masquerade_as_deadlines(self):
        run = s.create_run({"roles": ["虚构岗位"], "companies": ["虚构企业"]}, ["official"])
        s.add_candidates(run["id"], [{"company": "虚构企业", "title": "虚构岗位", "url": "https://jobs.example.invalid/1",
            "core_tasks": ["整理公开数据"], "fit_reason": "待核对课程经历", "uncertainties": ["到岗时间待核对"],
            "retrieved_at": "2026-10-19T10:00:00+08:00", "suggested_apply_date": "2026-10-21",
            "description": "DO_NOT_COPY_FULL_JD", "all_experiences": "DO_NOT_COPY_PRIVATE_LIBRARY"}])
        report = self.report(run["id"])
        self.assertIn("| 雇主正式截止 | 未披露 |", report)
        self.assertIn("| 发布 | 未披露 |", report)
        self.assertIn("建议准备/投递日期（个人计划） | 2026-10-21", report)
        self.assertIn("抓取/发现时间（不是发布） | 2026-10-19", report)
        self.assertIn("https://jobs.example.invalid/1", report)
        self.assertIn("整理公开数据", report)
        self.assertNotIn("DO_NOT_COPY", report)
        self.assertNotIn("description", s.show(run["id"])["candidates"][0])

    def test_failed_operation_writes_report_and_preserves_exception(self):
        error = ValueError("Fictional HTTP timeout")
        def operation():
            raise error
        with self.assertRaises(ValueError) as caught:
            s.execute_search("zhiye", {"query": "虚构岗位"}, operation)
        self.assertIs(caught.exception, error)
        self.assertTrue(Path(error.report_path).exists())
        self.assertEqual(s.show(error.search_run_id)["channels"]["zhiye"]["status"], "failed")
        self.assertIn("Fictional HTTP timeout", self.report(error.search_run_id))

    def test_successful_empty_and_unexecuted_plan_have_different_receipts(self):
        empty = s.execute_search("zhiye", {"query": "虚构岗位"}, lambda: {"executed": True, "leads": [], "scope": "first_public_result_page"})
        plan = s.execute_search("boss", {"query": "虚构岗位"}, lambda: {"executed": False, "status": "BROWSER_ACTION_REQUIRED"})
        self.assertEqual(s.show(empty["search_run_id"])["channels"]["zhiye"]["status"], "zero_results")
        self.assertEqual(s.show(plan["search_run_id"])["channels"]["boss"]["status"], "not_attempted")
        self.assertNotEqual(empty["report_path"], plan["report_path"])

    def test_full_jd_import_resolves_only_imported_summaries(self):
        record = {"source": "official", "source_id": "fiction-1", "title": "虚构分析实习", "company": "虚构企业",
                  "description": "DO_NOT_COPY_LONG_JD", "url": "https://jobs.example.invalid/fiction-1", "retrieved_at": now()}
        receipt = s.execute_search("official", {"company": "虚构企业"}, lambda: sources.import_records([record]))
        run = s.show(receipt["search_run_id"])
        self.assertEqual(run["channels"]["official"]["counts"], {"leads": 1, "full_jds": 1, "imported": 1, "deduplicated": 1})
        self.assertEqual(run["candidates"][0]["title"], "虚构分析实习")
        self.assertNotIn("DO_NOT_COPY", self.report(run["id"]))

    def test_official_import_wrapper_shape_with_nested_result_is_counted(self):
        from oriward import official
        record = {"source": "official", "source_id": "fiction-official-2", "title": "虛构策略实习", "company": "虚构单位",
                  "description": "策划并评估虚构项目。", "url": "https://jobs.example.invalid/fiction-2", "retrieved_at": now()}
        receipt = s.execute_search("official", {"company": "虚构单位"}, lambda: official.import_official(record))
        run = s.show(receipt["search_run_id"])
        self.assertEqual(run["channels"]["official"]["status"], "success")
        self.assertEqual(run["channels"]["official"]["counts"], {"leads": 1, "full_jds": 1, "imported": 1, "deduplicated": 1})
        self.assertEqual(run["candidates"][0]["title"], "虛构策略实习")

    def test_source_sync_empty_is_verified_zero_and_coverage_is_bounded(self):
        result = s.execute_search("greenhouse", {"board": "fictional"}, lambda: {
            "job_ids": [], "added": 0, "updated": 0, "duplicate": 0,
            "retrieval": {"returned_count": 0, "available_count": 0, "limit": 10}})
        channel = s.show(result["search_run_id"])["channels"]["greenhouse"]
        self.assertEqual(channel["status"], "zero_results")
        self.assertIn("requested_limit=10", channel["coverage"])

    def test_browser_observation_and_auth_are_not_full_jds(self):
        result = s.execute_search("boss", {"query": "虚构岗位"}, lambda: {
            "status": "search_verified", "visible_count": 3, "evidence": "看到3张虚构职位卡片", "recorded_only": True})
        counts = s.show(result["search_run_id"])["channels"]["boss"]["counts"]
        self.assertEqual(counts["leads"], 3)
        self.assertIsNone(counts["full_jds"])
        auth = s.execute_search("liepin", {"query": "虚构岗位"}, lambda: {"executed": False, "status": "AUTH_REQUIRED"})
        receipt = s.show(auth["search_run_id"])["channels"]["liepin"]
        self.assertEqual(receipt["status"], "auth_required")
        self.assertFalse(receipt["attempted"])
        self.assertIsNone(receipt["counts"]["leads"])

    def test_zero_needs_evidence_and_unexecuted_channels_cannot_claim_counts(self):
        run = s.create_run({}, ["fictional"])
        with self.assertRaisesRegex(ValueError, "evidence"):
            s.record_channel(run["id"], "fictional", "zero_results")
        with self.assertRaisesRegex(ValueError, "unknown counts"):
            s.record_channel(run["id"], "fictional", "not_connected", counts={"leads": 0})
        with self.assertRaisesRegex(ValueError, "Unknown scope"):
            s.create_run({"all_experiences": "sensitive"}, ["fictional"])

    def test_official_valid_through_keeps_deadline_and_source_field(self):
        from oriward import official
        record = {"source": "official", "source_id": "fiction-deadline", "title": "虚构实习",
            "company": "虚构公司", "description": "Reports", "url": "https://example.invalid/deadline",
            "retrieved_at": now(), "valid_through": "2026-11-30", "published_at": "2026-10-01"}
        receipt = s.execute_search("official", {}, lambda: official.import_official(record))
        candidate = s.show(receipt["search_run_id"])["candidates"][0]
        self.assertEqual(candidate["deadline"], "2026-11-30")
        self.assertEqual(candidate["time_sources"]["deadline"]["field"], "valid_through")
        self.assertIn("雇主正式截止 | 2026-11-30", self.report(receipt["search_run_id"]))


if __name__ == "__main__":
    unittest.main()
