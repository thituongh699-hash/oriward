import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from careeros import cli, discovery as d, services
from careeros.db import now


class BrowserWorkflowTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {"CAREEROS_DB": tmp.name + "/browser.sqlite3"})
        env.start()
        self.addCleanup(env.stop)

    def observation(self, **changes):
        result = dict(provider="zhilian", query="产品经理", location="苏州",
                      source_url="https://www.zhaopin.com/jobs/?kw=test", observed_at=now(),
                      status="needs_login", evidence="搜索结果可见，详情显示登录查看完整内容", visible_count=20)
        result.update(changes)
        return result

    def test_search_routes_both_channels_to_browser_without_fabricated_execution(self):
        for provider in ("boss", "zhilian"):
            result = d.search_local("产品经理", "苏州", provider)
            self.assertEqual(result["status"], "BROWSER_ACTION_REQUIRED")
            self.assertFalse(result["executed"])
            self.assertIn("browser-search.md", result["workflow"])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.run(["jobs", "browser-plan", "--provider", "boss", "--query", "产品经理"])
        self.assertFalse(json.loads(out.getvalue())["executed"])

    def test_observations_preserve_blocker_and_do_not_create_jobs(self):
        result = d.record_browser_observation(self.observation())
        self.assertEqual(d.browser_runs()[0]["id"], result["id"])
        self.assertTrue(result["recorded_only"])
        self.assertEqual(d.list_leads(), [])
        self.assertEqual(services.list_objects("jobs"), [])
        error = d.record_browser_observation(self.observation(provider="boss", source_url="https://www.zhipin.com/",
                                                             status="browser_error", visible_count=0, evidence="页面空白"))
        self.assertEqual(error["status"], "browser_error")

    def test_contradictory_success_or_wrong_provider_rejected(self):
        for changes in [dict(status="search_verified", visible_count=0), dict(status="no_results", visible_count=20),
                        dict(source_url="https://evil.invalid/"), dict(source_url="https://www.zhaopin.com.evil.invalid/"),
                        dict(source_url="https://user:pass@www.zhaopin.com/"), dict(visible_count=True)]:
            with self.assertRaises(ValueError):
                d.record_browser_observation(self.observation(**changes))
        self.assertEqual(d.browser_runs(), [])

    def test_browser_preview_cannot_be_promoted_as_complete_jd(self):
        row = dict(provider="zhilian",title="示例产品经理",company="虚构公司",url="https://www.zhaopin.com/jobdetail/TEST.htm",
                   discovered_at=now(),discovery_method="browser_ui",access_state="visible_preview")
        lid = d.import_leads([row])["lead_ids"][0]
        self.assertEqual(d.list_leads()[0]["access_state"], "visible_preview")
        data = dict(row,description="完整职责与要求",retrieved_at=now(),read_method="browser_ui",content_complete=True)
        with self.assertRaisesRegex(ValueError,"full_detail"):
            d.promote_lead(lid,data)
        self.assertEqual(services.list_objects("jobs"), [])
        result = d.promote_lead(lid,dict(data,access_state="full_detail"))
        self.assertEqual(services.get_job(result["job_id"])["description"], data["description"])

    def test_browser_lead_requires_explicit_access_state(self):
        with self.assertRaisesRegex(ValueError,"access_state"):
            d.import_leads([dict(provider="boss",title="示例",url="https://www.zhipin.com/job_detail/test.html",
                                 discovered_at=now(),discovery_method="browser_ui")])


if __name__ == "__main__":
    unittest.main()
