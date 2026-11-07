"""Fictional visible job pages; no external sites or user sessions."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oriward import browser_jobs as b, discovery, search_runs


def snapshot(provider="boss", text="岗位列表", links=None):
    domains = {"boss": "www.zhipin.com", "zhilian": "sou.zhaopin.com", "liepin": "www.liepin.com"}
    return {"url": f"https://{domains[provider]}/search", "text": text,
            "links": links or [], "filters": []}


def card(url="https://www.zhipin.com/job_detail/fictional.html", title="虚构产品经理"):
    return {"url": url, "anchor": title, "company": "虚构公司", "location": "苏州", "summary": "虚构测试岗位"}


class BrowserJobsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"ORIWARD_DB": str(self.root / "test.sqlite3")})
        env.start()
        self.addCleanup(env.stop)

    def test_three_platforms_extract_only_job_links_and_dedupe(self):
        for provider, url in [("boss", "https://www.zhipin.com/job_detail/fictional.html"),
                              ("zhilian", "https://jobs.zhaopin.com/CC123456789J00000000001.htm"),
                              ("liepin", "https://www.liepin.com/a/123456.shtml")]:
            result = b.parse_snapshot(provider, snapshot(provider, links=[card(url), card(url + "?tracking=1"),
                                                        card("https://example.invalid/not-job")]), "产品", "苏州")
            self.assertEqual(len(result["records"]), 1)
            self.assertEqual(result["records"][0]["access_state"], "visible_preview")
            self.assertEqual(result["records"][0]["url"], url)

    def test_empty_loading_and_login_are_not_zero_results(self):
        for text, expected in [("正在加载", "browser_error"), ("扫码登录", "needs_login"),
                               ("正在验证连接安全性", "needs_verification"), ("暂无相关职位", "no_results")]:
            self.assertEqual(b.parse_snapshot("boss", snapshot(text=text))["status"], expected)
        self.assertEqual(b.parse_snapshot("boss", snapshot(text="扫码登录", links=[card()]))["status"], "search_verified")

    def test_partial_browser_results_stay_in_report(self):
        from unittest.mock import MagicMock
        page = MagicMock()
        page.evaluate.side_effect = [snapshot(links=[card()]), snapshot(text="人机验证")]
        button = MagicMock()
        button.get_attribute.return_value = ""
        page.locator.return_value.all.return_value = [button]
        page.get_by_text.return_value.all.return_value = []
        result = b.collect_pages(page, "boss", pages=3)
        self.assertTrue(result["partial"])
        self.assertEqual(len(result["records"]), 1)
        receipt = search_runs.execute_search("boss", {"query": "产品"}, lambda: result)
        report = Path(receipt["report_path"]).read_text(encoding="utf-8")
        self.assertIn("needs_verification", report)
        self.assertIn("部分完成", report)
        self.assertIn("虚构产品经理", report)

    def test_cli_route_dispatches_browser_without_calling_official_api(self):
        with patch.object(b, "collect", return_value={"status": "NOT_CONNECTED"}) as collect:
            result = discovery.search_local("产品", "苏州", "liepin", cdp_url="http://localhost:9331",
                                            url="https://www.liepin.com/search", pages=2)
        self.assertEqual(result["status"], "NOT_CONNECTED")
        self.assertEqual(collect.call_args.kwargs["pages"], 2)

    @unittest.skipUnless(importlib.util.find_spec("playwright"), "Optional browser dependency unavailable")
    def test_real_browser_dom_and_next_page_on_fictional_site(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            # Install Chromium with Playwright on CI; locally use installed Edge.
            try:
                browser = pw.chromium.launch(headless=True, channel="msedge" if os.name == "nt" else None)
            except Exception as exc:
                if os.environ.get("ORIWARD_REQUIRE_BROWSER_TESTS") == "1":
                    raise
                self.skipTest(f"Browser runtime unavailable: {type(exc).__name__}")
            try:
                page = browser.new_page()
                page.route("**/*", lambda route: route.fulfill(content_type="text/html; charset=utf-8", body='''
                    <ul><li><a class="job-name" href="/job_detail/first.html">虚构产品经理</a>
                    <span class="company-name">虚构公司</span><span class="job-area">苏州</span></li></ul>
                    <button aria-label="下一页" onclick="document.querySelector('a').href='/job_detail/second.html';this.disabled=true">下一页</button>'''))
                page.goto("https://www.zhipin.com/search")
                result = b.collect_pages(page, "boss", pages=3)
                self.assertEqual(len(result["records"]), 2, result)
                self.assertEqual(result["stop_reason"], "no_visible_next_page")
                self.assertEqual(result["records"][0]["company"], "虚构公司")
                self.assertFalse(result["filters"]["applied_by_collector"])
                self.assertNotIn("cookie", json.dumps(result))
            finally:
                browser.close()
