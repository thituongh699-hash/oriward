import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from careeros import public_search
from careeros.sources import SourceError


ROBOTS_ALLOW = "User-agent: *\nAllow: /\n"
SEARCH_HTML = """<!doctype html><html><body>
<form class="filter-form" method="get"><input name="q"></form>
<a class="job-card" href="/jobs/job_abc123">
  <div class="company-identity"><span class="company-label">甲科技</span></div>
  <h2>数据分析师</h2>
  <div class="tags"><span class="tag">上海</span><span class="tag">Python</span></div>
  <span class="freshness">50天前验证</span>
</a>
<a class="job-card" href="/jobs/job_def456">
  <div class="company-identity"><span class="company-label">乙科技</span></div><h2>数据工程师</h2>
  <div class="tags"><span class="tag">北京</span><span class="tag">SQL</span></div>
  <span class="freshness">3天前验证</span>
</a>
</body></html>"""
DETAIL_HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<a href="/companies/acme"><span class="company-label">甲科技 <!-- --> →</span></a>
<h1>数据分析师</h1>
<div class="tags"><span class="tag">上海市、北京市</span><span class="tag">数据</span></div>
<h2>职位说明</h2>
<div class="job-description"><p>分析业务数据。</p><p>要求 SQL 与 Python。</p></div>
<dl>
  <div><dt>最近验证</dt><dd>2026/08/29 00:36</dd></div>
  <div><dt>官方来源</dt><dd><a href="https://jobs.example.cn/role/7">查看原始页面 ↗</a></dd></div>
</dl>
</body></html>"""


class PublicSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"CAREEROS_CACHE_DIR": self.temp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_search_returns_filtered_leads_and_reuses_raw_cache(self):
        fetched_at = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat(timespec="seconds")
        robots_at = (datetime.now(timezone.utc) - timedelta(seconds=3)).isoformat(timespec="seconds")
        with (
            patch.object(public_search, "_download", side_effect=[ROBOTS_ALLOW, SEARCH_HTML]) as download,
            patch.object(public_search, "now", side_effect=[robots_at, fetched_at]),
        ):
            first = public_search.search_zhiye("数据", location="上海", limit=10)

        self.assertEqual(download.call_count, 2)
        self.assertEqual(first["provider"], "zhiye")
        self.assertEqual(first["fetched_at"], fetched_at)
        self.assertFalse(first["cache_hit"])
        self.assertIn("q=%E6%95%B0%E6%8D%AE+%E4%B8%8A%E6%B5%B7", first["search_url"])
        self.assertEqual(
            first["records"],
            [{
                "title": "数据分析师",
                "company": "甲科技",
                "location": "上海",
                "url": "https://zhiye.page/jobs/job_abc123",
                "summary": "Python",
                "source_verified_label": "50天前验证",
            }],
        )
        self.assertFalse(first["has_more"])
        self.assertRegex(first["content_digest"], r"^[0-9a-f]{64}$")

        with patch.object(public_search, "_download") as no_download:
            second = public_search.search_zhiye("数据", location="上海", limit=10)
        no_download.assert_not_called()
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["fetched_at"], fetched_at)
        self.assertEqual(second["content_digest"], first["content_digest"])

        cache_files = list(Path(self.temp.name).iterdir())
        self.assertEqual(len(cache_files), 4)
        meta = json.loads(next(path for path in cache_files if path.name.startswith("search-") and path.suffix == ".json").read_text("utf-8"))
        self.assertEqual(meta["fetched_at"], fetched_at)

    def test_limit_sets_has_more_without_detail_fetches(self):
        records, has_more = public_search._search_records(SEARCH_HTML, "", 1)
        self.assertEqual(len(records), 1)
        self.assertTrue(has_more)
        self.assertNotIn("description", records[0])

    def test_detail_normalizes_description_but_never_visits_official_url(self):
        fetched_at = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat(timespec="seconds")
        robots_at = (datetime.now(timezone.utc) - timedelta(seconds=3)).isoformat(timespec="seconds")
        with (
            patch.object(public_search, "_download", side_effect=[ROBOTS_ALLOW, DETAIL_HTML]) as download,
            patch.object(public_search, "now", side_effect=[robots_at, fetched_at]),
        ):
            record = public_search.fetch_zhiye_detail("https://zhiye.page/jobs/job_abc123")

        self.assertEqual(download.call_count, 2)
        called_urls = [call.args[0] for call in download.call_args_list]
        self.assertEqual(called_urls, [public_search.ROBOTS_URL, "https://zhiye.page/jobs/job_abc123"])
        self.assertEqual(record["source"], "zhiye")
        self.assertEqual(record["source_id"], "job_abc123")
        self.assertEqual(record["title"], "数据分析师")
        self.assertEqual(record["company"], "甲科技")
        self.assertEqual(record["location"], "上海市、北京市")
        self.assertEqual(record["description"], "分析业务数据。 要求 SQL 与 Python。")
        self.assertEqual(record["official_url"], "https://jobs.example.cn/role/7")
        self.assertEqual(record["retrieved_at"], fetched_at)
        self.assertEqual(record["availability"], "unknown")
        self.assertEqual(record["upstream_verified_at"], "2026/08/29 00:36")
        self.assertEqual(record["upstream_verified_label"], "最近验证 2026/08/29 00:36")
        self.assertNotIn("cache_hit", record)

        with patch.object(public_search, "_download") as no_download:
            cached = public_search.fetch_zhiye_detail("https://zhiye.page/jobs/job_abc123")
        no_download.assert_not_called()
        self.assertEqual(cached["retrieved_at"], fetched_at)
        self.assertNotIn("cache_hit", cached)

    def test_challenge_page_is_an_explicit_error_and_is_not_cached(self):
        challenge = "<html><title>安全验证</title><body>captcha</body></html>"
        with patch.object(public_search, "_download", side_effect=[ROBOTS_ALLOW, challenge]):
            with self.assertRaisesRegex(SourceError, "challenge page"):
                public_search.search_zhiye("产品经理")
        self.assertFalse(any(path.name.startswith("search-") for path in Path(self.temp.name).iterdir()))

    def test_unrecognized_html_is_not_reported_as_an_empty_search(self):
        with patch.object(public_search, "_download", side_effect=[ROBOTS_ALLOW, "<html><body>Sign in</body></html>"]):
            with self.assertRaisesRegex(SourceError, "expected public result structure"):
                public_search.search_zhiye("产品经理")
        records, has_more = public_search._search_records(
            '<form class="filter-form" method="get"><input name="q"><p>暂无职位</p></form>', "", 10
        )
        self.assertEqual(records, [])
        self.assertFalse(has_more)

    def test_robots_disallow_fails_closed_before_page_request(self):
        with patch.object(public_search, "_download", return_value="User-agent: *\nDisallow: /jobs\n") as download:
            with self.assertRaisesRegex(SourceError, "robots.txt disallows"):
                public_search.search_zhiye("产品经理")
        self.assertEqual(download.call_count, 1)

    def test_future_cache_metadata_is_rejected(self):
        url = "https://zhiye.page/jobs?q=future"
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
        public_search._write_cache("search", url, SEARCH_HTML, future)
        self.assertIsNone(public_search._read_cache("search", url, public_search.SEARCH_TTL))

    def test_robots_html_or_challenge_fails_closed_and_is_not_cached(self):
        bad_bodies = (
            "<!doctype html><html><body>Temporary response</body></html>",
            "Please complete captcha verification",
        )
        for body in bad_bodies:
            with self.subTest(body=body):
                with patch.object(public_search, "_download", return_value=body) as download:
                    with self.assertRaisesRegex(SourceError, "robots.txt returned HTML or a challenge"):
                        public_search.search_zhiye("产品经理")
                self.assertEqual(download.call_count, 1)
        self.assertFalse(any(path.name.startswith("robots-") for path in Path(self.temp.name).iterdir()))

    def test_detail_rejects_external_or_non_job_urls(self):
        invalid = (
            "https://example.com/jobs/job_abc",
            "http://zhiye.page/jobs/job_abc",
            "https://zhiye.page/jobs",
            "https://zhiye.page/jobs/job_abc?next=https://example.com",
        )
        for url in invalid:
            with self.subTest(url=url):
                with self.assertRaises((SourceError, ValueError)):
                    public_search.fetch_zhiye_detail(url)

    def test_http_reader_is_bounded_credential_free_and_redirect_locked(self):
        class Response:
            headers = {"Content-Length": str(public_search.MAX_RESPONSE_BYTES + 1)}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return "https://zhiye.page/jobs?q=test"
            def read(self, size): raise AssertionError("oversized body must not be read")

        class Opener:
            def open(self, request, timeout):
                self.request, self.timeout = request, timeout
                return Response()

        opener = Opener()
        with (
            patch.object(public_search.urllib.request, "build_opener", return_value=opener),
            patch.object(public_search, "_last_request_at", 9.0),
            patch.object(public_search.time, "monotonic", side_effect=[10.0, 12.0]),
            patch.object(public_search.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(SourceError, "exceeds 2 MB"):
                public_search._download("https://zhiye.page/jobs?q=test", "text/html")
        sleep.assert_called_once_with(1.0)
        self.assertEqual(opener.timeout, 15)
        headers = {key.casefold(): value for key, value in opener.request.header_items()}
        self.assertNotIn("authorization", headers)
        self.assertNotIn("cookie", headers)

        handler = public_search._SameHostRedirectHandler()
        request = public_search.urllib.request.Request("https://zhiye.page/jobs?q=test")
        with self.assertRaisesRegex(SourceError, "approved HTTPS host"):
            handler.redirect_request(request, None, 302, "Found", {}, "https://evil.invalid/jobs")

    def test_argument_validation_is_bounded(self):
        for query in ("", "   ", "x" * 201):
            with self.subTest(query=query):
                with self.assertRaises(ValueError):
                    public_search.search_zhiye(query)
        for limit in (True, 0, 51):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    public_search.search_zhiye("开发", limit=limit)
        with self.assertRaises(ValueError):
            public_search.search_zhiye("开发", refresh="yes")


if __name__ == "__main__":
    unittest.main()
