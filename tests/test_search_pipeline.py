import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oriward import discovery, experience_library, search_cli, search_runs, sources


class SearchPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ORIWARD_DB": str(Path(self.tmp.name) / "fixture.sqlite3")})
        env.start()
        self.addCleanup(env.stop)

    def test_registry_custom_route_disabled_and_restored_persistently(self):
        route = discovery.set_route("campus_board", url="https://jobs.example.invalid/", name="Campus Board")
        self.assertTrue(route["discovered"])
        self.assertFalse(discovery.search_plan("analyst", providers=["campus_board"])["executed"])
        run = search_cli.start({"query": "demo"}, ["campus_board"])
        search_cli.record_attempt(run["run_id"], "campus_board", "failed", reason="timeout", attempted=True)
        search_cli.record_attempt(run["run_id"], "campus_board", "failed", stage="repair", repair_action="alternate_site",
                                  query="demo jobs", reason="second timeout", attempted=True)
        search_cli.record_attempt(run["run_id"], "campus_board", "failed", stage="repair", repair_action="different_browser",
                                  query="demo jobs company", reason="third timeout", attempted=True)
        discovery.request_route_assistance("campus_board")
        discovery.set_route("campus_board", enabled=False, resolution="declined")
        discovery.set_route("campus_board", enabled=False)
        self.assertFalse(discovery.route_registry()["campus_board"]["enabled"])
        discovery.set_route("campus_board", enabled=True)
        self.assertTrue(discovery.route_registry()["campus_board"]["enabled"])

    def test_same_day_query_reuses_prior_receipt_and_auth_disable_needs_handoff(self):
        first = search_cli.start({"query": "审计实习"}, ["zhiye"])
        search_cli.record_attempt(first["run_id"], "zhiye", "success", reason="真实结果", attempted=True)
        second = search_cli.start({"query": "  审计实习 "}, ["zhiye"])
        reused = search_cli.record_attempt(second["run_id"], "zhiye", "success", reason="不应发起", attempted=True)
        self.assertTrue(reused["reused"])
        self.assertFalse(reused["executed"])
        attempts = search_runs.show(second["run_id"])["channels"]["zhiye"]["attempts"]
        self.assertEqual(attempts[-1]["reused_from"], first["run_id"])
        self.assertEqual(reused["next"]["stage"], "expansion")

        third = search_cli.start({"query": "市场实习"}, ["zhiye"])
        search_cli.record_attempt(third["run_id"], "zhiye", "failed", reason="超时", attempted=True)
        search_cli.record_attempt(third["run_id"], "zhiye", "failed", query="市场实习公开页", stage="repair",
                                  repair_action="alternate_public_route", reason="仍超时", attempted=True)
        search_cli.record_attempt(third["run_id"], "zhiye", "failed", query="市场实习站内", stage="repair",
                                  repair_action="browser_route", reason="仍超时", attempted=True)
        discovery.request_route_assistance("zhiye")
        with self.assertRaisesRegex(ValueError, "resolved/declined"):
            discovery.set_route("zhiye", enabled=False)
        result = discovery.set_route("zhiye", enabled=False, resolution="declined")
        self.assertFalse(result["enabled"])
        discovery.set_route("zhiye", enabled=True)

    def test_city_scope_and_base_query_cannot_be_reused_incorrectly(self):
        first = search_cli.start({"query": "分析", "location": "", "cities": ["上海"]}, ["zhiye"])
        search_cli.record_attempt(first["run_id"], "zhiye", "success", attempted=True)
        second = search_cli.start({"query": "分析", "location": "", "cities": ["杭州"]}, ["zhiye"])
        result = search_cli.record_attempt(second["run_id"], "zhiye", "success", attempted=True)
        self.assertNotIn("reused", result)
        with self.assertRaisesRegex(ValueError, "distinct"):
            search_cli.record_attempt(second["run_id"], "zhiye", "success", query="分析", stage="expansion", refresh=True)
        with self.assertRaisesRegex(ValueError, "Unknown"):
            search_cli.start({"query": "测试"}, ["does_not_exist"])

    def test_every_channel_first_and_every_attempt_is_append_only(self):
        started = search_cli.start({"query": "实习", "location": "上海"}, ["zhiye", "boss"])
        run_id = started["run_id"]
        self.assertEqual(started["next"]["provider"], "zhiye")
        search_cli.record_attempt(run_id, "zhiye", "success", reason="首屏读取", attempted=True,
                                  counts={"leads": 1}, stage="coverage")
        self.assertEqual(search_cli.next_packet(run_id)["provider"], "boss")
        search_cli.record_attempt(run_id, "boss", "auth_required", reason="登录墙", attempted=False, stage="coverage")
        first = search_runs.show(run_id)["channels"]["boss"]["attempts"]
        self.assertEqual(len(first), 1)
        packet = search_cli.next_packet(run_id)
        self.assertEqual(packet["stage"], "expansion")
        self.assertEqual(search_cli._read_plan(run_id)["waiting_for_user"], ["boss"])
        search_cli.record_attempt(run_id, "boss", "failed", query="实习 登录恢复", repair_action="clear_session", reason="人工恢复后仍报错", attempted=True, stage="repair")
        attempts = search_runs.show(run_id)["channels"]["boss"]["attempts"]
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["status"], "auth_required")
        self.assertEqual(attempts[1]["status"], "failed")
        report = Path(search_runs.show(run_id)["report_path"]).read_text(encoding="utf-8")
        self.assertIn("流程阶段", report)

    def test_two_expansions_then_catalogue_packet_are_explicitly_unexecuted(self):
        started = search_cli.start({"query": "产品实习"}, ["zhiye"])
        run_id = started["run_id"]
        search_cli.record_attempt(run_id, "zhiye", "zero_results", reason="页面明确显示无结果", attempted=True,
                                  stage="coverage")
        first = search_cli.next_packet(run_id)
        self.assertEqual(first["query_family"], "alias_or_tasks")
        self.assertFalse(first["executed"])
        search_cli.record_attempt(run_id, "zhiye", "success", query="产品实习 别名职责", reason="真实检索",
                                  attempted=True, stage="expansion")
        second = search_cli.next_packet(run_id)
        self.assertEqual(second["query_family"], "industry_scenario_company_tools")
        search_cli.record_attempt(run_id, "zhiye", "success", query="产品实习 行业工具", reason="真实检索",
                                  attempted=True, stage="expansion")
        catalogue = search_cli.next_packet(run_id)
        self.assertEqual(catalogue["stage"], "company_catalogue")
        self.assertFalse(catalogue["executed"])
        self.assertEqual(catalogue["targets"]["target_companies"], 10)
        self.assertEqual(catalogue["targets"]["max_items"], 200)

    def test_complete_pipeline_requires_sourced_companies_scans_full_jds_and_current_experience(self):
        started = search_cli.start({"query": "数据分析实习", "location": "上海"}, ["zhiye"], output_dir=self.tmp.name)
        run_id = started["run_id"]
        search_cli.record_attempt(run_id, "zhiye", "success", reason="虚构夹具实际回执", attempted=True)
        search_cli.record_attempt(run_id, "zhiye", "success", query="数据分析实习 同义任务", reason="扩展一回执", attempted=True, stage="expansion")
        search_cli.record_attempt(run_id, "zhiye", "success", query="数据分析实习 行业工具场景", reason="扩展二回执", attempted=True, stage="expansion")

        companies = []
        for n in range(1, 11):
            company = {"name": f"虚构公司{n}", "reason": "测试目录来源提及该公司招聘",
                       "reason_url": "https://jobs.example.invalid/catalogue",
                       "local_presence_url": "https://example.invalid/locations/shanghai"}
            companies.append(company)
            search_cli.record_stage(run_id, "catalogue-page", {
                "company": company["name"], "companies": [company], "items": [{"title": f"线索{n}"}],
                "source_url": "https://jobs.example.invalid/catalogue"})
        with self.assertRaisesRegex(ValueError, "five pages"):
            for _ in range(6):
                search_cli.record_stage(run_id, "catalogue-page", {"company": companies[0]["name"],
                    "companies": [companies[0]], "items": [{"title": "续页"}], "source_url": "https://jobs.example.invalid/catalogue"})

        job_ids = []
        for n in range(1, 4):
            imported = sources.import_records([{"source": "fictional", "source_id": f"pipe-{n}",
                "title": f"数据分析实习{n}", "company": companies[n-1]["name"], "location": "上海",
                "description": "职责：整理数据并制作分析报告。要求：掌握表格工具。",
                "url": f"https://jobs.example.invalid/jobs/{n}"}])
            job_ids.append(imported["job_ids"][0])
        for n, company in enumerate(companies, 1):
            search_cli.record_stage(run_id, "company-scan", {"company": company["name"], "status": "complete",
                "reason": "已检查公开目录首屏并耗尽本查询结果", "source_url": "https://jobs.example.invalid/catalogue",
                "pages": 1, "items": 1, "continuation": "exhausted"})
            if n <= 3:
                if n == 1:
                    with self.assertRaisesRegex(ValueError, "belong to"):
                        search_cli.record_stage(run_id, "company-jd", {"company": companies[9]["name"], "job_id": job_ids[0]})
                search_cli.record_stage(run_id, "company-jd", {"company": company["name"], "job_id": job_ids[n-1]})

        active_id = experience_library.create({"event": "虚构数据分析课程项目", "actions": ["整理公开数据"],
            "outcomes": ["完成图表"], "evidence": [{"claim": "参与项目", "source": "user_report", "status": "user_stated"}]})
        inactive_id = experience_library.create({"event": "后续排除经历", "actions": [], "outcomes": [], "evidence": []})
        experience_library.exclude(inactive_id, reason="测试排除")
        with self.assertRaisesRegex(ValueError, "current experience"):
            search_cli.record_stage(run_id, "direction", {"name": "无效方向", "job_ids": job_ids[:1], "experience_ids": [inactive_id]})
        for idx, job_id in enumerate(job_ids, 1):
            search_cli.record_stage(run_id, "direction", {"name": f"方向假设{idx}", "job_ids": [job_id],
                "experience_ids": [active_id]})
        self.assertEqual(search_cli.next_packet(run_id)["stage"], "complete")
        result = search_cli.finish(run_id)
        self.assertEqual(result["run_id"], run_id)
        self.assertIn("全部要求阶段均有本地记录", Path(result["report_path"]).read_text(encoding="utf-8"))
        search_cli.record_stage(run_id, "company-scan", {"company": companies[0]["name"], "status": "incomplete",
            "reason": "页面上限，尚有后续职位", "source_url": "https://jobs.example.invalid/catalogue",
            "pages": 5, "items": 200, "continuation": "more_available"})
        self.assertEqual(search_cli.next_packet(run_id)["stage"], "partial_coverage")
        with self.assertRaisesRegex(ValueError, "partial finish"):
            search_cli.finish(run_id)
        search_cli.finish(run_id, partial=True, reason="目录达到本轮读取上限")

    def test_expansion_requires_distinct_query_and_partial_finish_requires_reason(self):
        started = search_cli.start({"query": "分析实习"}, ["zhiye"])
        run_id = started["run_id"]
        search_cli.record_attempt(run_id, "zhiye", "success", reason="实际搜索", attempted=True)
        search_cli.record_attempt(run_id, "zhiye", "success", query="分析实习别名", reason="实际搜索",
                                  attempted=True, stage="expansion")
        with self.assertRaisesRegex(ValueError, "distinct"):
            search_cli.record_attempt(run_id, "zhiye", "success", query="分析实习别名", reason="重用",
                                      attempted=True, stage="expansion", refresh=True)
        with self.assertRaisesRegex(ValueError, "partial finish"):
            search_cli.finish(run_id, partial=True)
        with self.assertRaisesRegex(ValueError, "partial finish"):
            search_runs.finish_run(run_id)


if __name__ == "__main__":
    unittest.main()
