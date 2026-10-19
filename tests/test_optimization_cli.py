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

    def test_first_use_continuation_and_selective_output_are_real_cli_contracts(self):
        self.assertEqual(self.run_cli("init")[0]["schema_version"], 5)
        initial = self.run_cli("onboarding", "missing")[0]
        self.assertEqual(initial["default_next_step"], "lightweight_experience_index")
        self.assertIn("companies", [q["field"] for q in initial["prompts"]])
        self.run_cli("onboarding", "preferences", "--file", self.file({
            "companies": [], "roles": [], "constraints": {}, "intent": "experience_index"}))
        self.run_cli("onboarding", "channel-intent", "--provider", "liepin", "--preference", "later")
        self.assertEqual(self.run_cli("onboarding", "missing", "--before-search")[0]["prompts"], [])
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
