"""Exercise actual CLI output, receipts and continuation on fictional state."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oriward import cli


class OptimizationCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"ORIWARD_DB": str(self.root / "test.sqlite3"),
                                      "ORIWARD_OUTPUT_DIR": str(self.root / "resumes")})
        env.start()
        self.addCleanup(env.stop)
        self.sequence = 0

    def file(self, data):
        self.sequence += 1
        path = self.root / f"input-{self.sequence}.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def run_cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            cli.run(list(map(str, args)))
        return json.loads(output.getvalue()), output.getvalue().rstrip("\n")

    def test_onboarding_schedule_and_discovery_cli_routes(self):
        self.run_cli("init")
        direct = self.run_cli("onboarding", "missing", "--before-search", "--existing-resume",
                              "--direct-search-and-apply")[0]
        self.assertIn("discovery_offer", {row["field"] for row in direct["prompts"]})
        self.assertEqual(self.run_cli("intake", "discovery-offer", "--answer", "now")[0]["next_action"],
                         "intake next")
        self.assertEqual(self.run_cli("intake", "next")[0]["next_action"], "offer_history_recovery")
        self.assertEqual(self.run_cli("intake", "learning-schedule", "--answer", "later")[0]["answer"],
                         "later")

    def test_first_use_continuation_and_selective_output_are_real_cli_contracts(self):
        self.assertEqual(self.run_cli("init")[0]["schema_version"], 7)
        initial = self.run_cli("onboarding", "missing")[0]
        self.assertEqual(initial["default_next_step"], "deep_experience_discovery")
        self.assertEqual([q["field"] for q in initial["prompts"]], ["history_intake"])
        self.run_cli("onboarding", "preferences", "--file", self.file({
            "companies": [], "roles": [], "constraints": {}, "intent": "experience_index"}))
        self.run_cli("onboarding", "channel-intent", "--provider", "liepin", "--preference", "later")
        self.run_cli("intake", "history-consent", "--answer", "later")
        self.assertEqual(self.run_cli("onboarding", "missing", "--before-search")[0]["default_next_step"],
                         "deep_experience_discovery")
        first = self.run_cli("onboarding", "topic", "--title", "课程项目", "--next-action", "补充本人动作")[0]
        current = self.run_cli("onboarding", "topic", "--title", "研究任务", "--next-action", "说明分析过程")[0]
        for i in range(20):
            self.run_cli("experience", "add", "--file", self.file({"event": f"测试经历{i}",
                "actions": [f"本人完成资料整理{i}"], "outcomes": [], "evidence": [],
                "context": "DO_NOT_READ_WHOLE_DOSSIER" * 500,
                "inferred_skills": [{"name": "资料整理", "source": "model_inference"}]}))
        index, raw = self.run_cli("experience", "list")
        self.assertLessEqual(len(raw), 2200)
        self.assertEqual(len(raw), index["budget"]["actual"])
        self.assertNotIn("DO_NOT_READ_WHOLE_DOSSIER", raw)
        self.assertFalse(index["complete"])
        cards = self.run_cli("experience", "skills", "--query", "资料整理")[0]
        self.assertEqual(cards["items"][0]["name"], "资料整理")
        self.assertGreater(cards["items"][0]["omitted_refs"], 0)
        detail, raw = self.run_cli("experience", "detail", "--ids", "1", "--sections", "actions,outcomes")
        self.assertNotIn("DO_NOT_READ_WHOLE_DOSSIER", raw)
        self.assertEqual(detail["items"][0]["sections_read"], ["actions", "outcomes"])
        brief, raw = self.run_cli("context", "brief", "--max-chars", "3200")
        self.assertLessEqual(len(raw), 3200)
        self.assertEqual(brief["continuation"]["current_topic"]["id"], current["id"])
        self.assertEqual(brief["continuation"]["paused_branches"][0]["id"], first["id"])
        self.run_cli("experience", "revise", "--id", "1", "--file", self.file({"actions": ["更正后的本人动作"]}),
                     "--reason", "更正范围", "--expected-version", "1")
        self.assertEqual(self.run_cli("experience", "show", "--id", "1", "--sections", "actions")[0]["version"], 2)
        self.run_cli("experience", "exclude", "--id", "1", "--reason", "暂不使用")
        self.assertEqual(self.run_cli("experience", "index", "--ids", "1")[0]["items"], [])

    def test_discovery_history_save_followup_and_resume(self):
        self.run_cli("init")
        source = self.file([
            {"role": "user", "timestamp": "2026-01-01", "content": "我帮家里看店"},
            {"role": "assistant", "content": "假设你管理过十个人，这不能当成事实"},
            {"role": "user", "content": "我通常负责补货"}])
        self.run_cli("intake", "history-consent", "--answer", "allow", "--scope", source)
        first = self.run_cli("intake", "next")[0]
        self.assertEqual(first["history_action"]["files"][0]["offset"], 0)
        receipt = self.run_cli("history", "extract", "--file", source, "--source", "user", "--max-chars", "8")[0]
        next_step = self.run_cli("intake", "next")[0]
        self.assertEqual(next_step["history_action"]["files"][0]["offset"], receipt["next_offset"])
        while not receipt["complete"]:
            receipt = self.run_cli("history", "extract", "--file", source, "--source", "user",
                                   "--max-chars", "8", "--offset", receipt["next_offset"])[0]
        self.assertIsNone(self.run_cli("intake", "next")[0]["history_action"])
        self.assertEqual(self.run_cli("experience", "index")[0]["items"], [])
        # The Agent separately saves only the explicit user report.
        self.run_cli("experience", "add", "--file", self.file({"event": "虚构店铺协助", "actions": ["负责补货"]}))
        eid = self.run_cli("experience", "index")[0]["items"][0]["id"]
        data = {"title": "补货", "question": "通常怎么判断该补哪些货？", "reason": "恢复具体判断过程",
                "source": source + " user record 3", "experience_id": eid}
        clue = self.run_cli("intake", "clue", "--file", self.file(data))[0]
        self.assertEqual(self.run_cli("onboarding", "missing")[0]["prompts"][0]["question"], data["question"])
        # A fresh process must recover the same stored next question.
        import subprocess, sys
        recovered = subprocess.run([sys.executable, "-m", "oriward", "intake", "next"],
                                   capture_output=True, text=True, encoding="utf-8", check=True,
                                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(json.loads(recovered.stdout)["clue_id"], clue["id"])
        self.run_cli("experience", "revise", "--id", eid, "--file", self.file({"actions": ["负责补货", "每天核对库存"]}),
                     "--reason", "用户补充", "--expected-version", 1)
        self.run_cli("intake", "clue-state", "--id", clue["id"], "--state", "answered", "--note", "已保存经历 version 2")
        repeated = self.run_cli("intake", "clue", "--file", self.file(data))[0]
        self.assertEqual(repeated["status"], "answered")
        self.assertIsNone(self.run_cli("intake", "next")[0]["prompt"])
        self.assertFalse(self.run_cli("intake", "next")[0]["library_complete"])

    def test_discovery_deferred_excluded_and_urgent_tasks(self):
        self.run_cli("init")
        self.run_cli("intake", "history-consent", "--answer", "decline")
        self.run_cli("experience", "add", "--file", self.file({"event": "虚构活动"}))
        eid = self.run_cli("experience", "index")[0]["items"][0]["id"]
        ids = []
        for priority in (3, 1, 2):
            row = self.run_cli("intake", "clue", "--file", self.file({"title": f"线索{priority}",
                "question": f"具体问题{priority}？", "reason": "恢复事件", "source": "用户当前发言",
                "experience_id": eid, "priority": priority}))[0]
            ids.append(row["id"])
        self.assertEqual(self.run_cli("intake", "next")[0]["clue_id"], ids[1])
        self.run_cli("intake", "clue-state", "--id", ids[1], "--state", "later")
        self.run_cli("intake", "clue-state", "--id", ids[2], "--state", "declined")
        brief = self.run_cli("context", "brief")[0]
        self.assertEqual(brief["recovery"]["experience_discovery"]["clue_id"], ids[0])
        self.assertEqual(brief["recovery"]["experience_discovery"]["deferred_count"], 1)
        self.run_cli("onboarding", "preferences", "--file", self.file({"intent": "specific_jd"}))
        self.assertIsNone(self.run_cli("intake", "next")[0]["prompt"])
        self.run_cli("onboarding", "preferences", "--file", self.file({"intent": "experience_index"}))
        self.run_cli("experience", "exclude", "--id", eid, "--reason", "用户不使用")
        self.assertIsNone(self.run_cli("intake", "next")[0]["prompt"])
        first = self.run_cli("intake", "clues", "--limit", 2)[0]
        second = self.run_cli("intake", "clues", "--offset", first["next_offset"])[0]
        self.assertEqual(len(first["items"]) + len(second["items"]), 3)

    def test_history_skipped_page_does_not_certify_full_coverage(self):
        self.run_cli("init")
        path = self.file([{"role": "user", "content": "甲乙丙丁" * 10}])
        self.run_cli("intake", "history-consent", "--answer", "allow", "--scope", path)
        self.run_cli("history", "extract", "--file", path, "--source", "user", "--max-chars", 8, "--offset", 9)
        self.assertEqual(self.run_cli("intake", "next")[0]["history_action"]["files"][0]["offset"], 0)

        self.run_cli("history", "extract", "--file", path, "--source", "user", "--max-chars", 100)
        self.assertIsNone(self.run_cli("intake", "next")[0]["history_action"])
        Path(path).write_text(json.dumps([{"role": "user", "content": "新的记录" * 20}]), encoding="utf-8")
        self.run_cli("history", "extract", "--file", path, "--source", "user", "--max-chars", 8, "--offset", 2)
        self.assertEqual(self.run_cli("intake", "next")[0]["history_action"]["files"][0]["offset"], 0)

    def test_multiple_channels_make_one_honest_report(self):
        run = self.run_cli("search-run", "start", "--file", self.file({
            "scope": {"query": "虚构实习", "companies": ["测试公司"]},
            "planned_channels": ["official", "zhiye", "boss", "liepin"]}))[0]
        for provider, status, reason, counts in [
            ("official", "success", "完整读取两条虚构JD", {"leads": 2, "full_jds": 2, "imported": 2, "deduplicated": 2}),
            ("zhiye", "success", "读取首屏线索", {"leads": 3, "full_jds": 0, "imported": 0, "deduplicated": 3}),
            ("boss", "failed", "浏览器超时", {}), ("liepin", "not_connected", "用户暂缓", {})]:
            self.run_cli("search-run", "record", "--id", run["id"], "--file", self.file({
                "provider": provider, "status": status, "reason": reason, "counts": counts}))
        self.run_cli("search-run", "candidates", "--id", run["id"], "--file", self.file([{
            "title": "虚构实习", "company": "测试公司", "url": "https://example.invalid/jobs/1",
            "core_tasks": "整理资料", "retrieved_at": "2026-10-19", "deadline": None,
            "suggested_apply_date": "2026-10-21", "description": "PRIVATE_DETAILS_NOT_COPIED"}]))
        receipt = self.run_cli("search-run", "finish", "--id", run["id"])[0]
        report = Path(receipt["report_path"]).read_text(encoding="utf-8")
        self.assertIn("浏览器超时", report)
        self.assertIn("未接入", report)
        self.assertIn("雇主正式截止 | 未披露", report)
        self.assertIn("2026-10-21", report)
        self.assertNotIn("PRIVATE_DETAILS_NOT_COPIED", report)
        self.assertIsNone(receipt["counts"]["leads"])

    def test_new_pipeline_cli_requires_actual_rounds_and_honest_partial_finish(self):
        registry = self.run_cli("jobs", "channels")[0]
        self.assertTrue({"boss", "shixiseng", "nowcoder", "gaodun"} <= {r["id"] for r in registry})
        planned = self.run_cli("search-run", "plan", "--file", self.file({
            "scope": {"query": "数据分析", "cities": ["虚构市"]}, "planned_channels": ["zhiye"],
            "output_dir": str(self.root / "reports")}))[0]
        rid = planned["run_id"]
        self.assertEqual(self.run_cli("search-run", "next", "--id", rid)[0]["stage"], "coverage")
        for stage, query in (("coverage", "数据分析"), ("expansion", "统计报告"), ("expansion", "运营数据工具")):
            self.run_cli("search-run", "record", "--id", rid, "--file", self.file({
                "provider": "zhiye", "status": "zero_results", "attempted": True, "query": query,
                "stage": stage, "reason": "虚构页面已明确展示当前查询无结果"}))
        self.assertEqual(self.run_cli("search-run", "next", "--id", rid)[0]["stage"], "company_catalogue")
        with self.assertRaisesRegex(ValueError, "partial finish"):
            self.run_cli("search-run", "finish", "--id", rid)
        out = self.run_cli("search-run", "finish", "--id", rid, "--file", self.file({
            "partial": True, "reason": "本轮尚未完成公司职位目录"}))[0]
        self.assertTrue(Path(out["report_path"]).resolve().is_relative_to((self.root / "reports").resolve()))
        self.assertIn("部分完成", Path(out["report_path"]).read_text(encoding="utf-8"))

    def test_search_errors_and_disabled_routes_also_return_report_paths(self):
        with patch.dict(os.environ, {"ORIWARD_ENABLE_LIEPIN": "0"}):
            receipt = self.run_cli("jobs", "search", "--provider", "liepin", "--query", "虚构岗位")[0]
        self.assertTrue(Path(receipt["report_path"]).is_file())
        self.assertEqual(self.run_cli("search-run", "show", "--id", receipt["search_run_id"])[0]
                         ["channels"]["liepin"]["status"], "not_connected")
        output, error = io.StringIO(), io.StringIO()
        with patch("oriward.discovery.search_local", side_effect=ValueError("Fictional timeout")), \
                patch("sys.argv", ["oriward", "jobs", "search", "--query", "测试岗位"]), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            with self.assertRaises(SystemExit) as stopped:
                cli.main()
        self.assertEqual(stopped.exception.code, 2)
        failed = json.loads(error.getvalue())
        self.assertTrue(Path(failed["report_path"]).is_file())
        self.assertIn("Fictional timeout", failed["error"])


if __name__ == "__main__":
    unittest.main()
