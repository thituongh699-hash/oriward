import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from careeros import official, tracking
from careeros.services import ValidationError
from careeros.sources import SourceError

POSTING_URL = "https://careers.acme-demo.com/jobs/123"

PAGE = """<!doctype html><html><head><title>数据产品经理 - 示例科技</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting",
 "title":"数据产品经理","datePosted":"2026-10-01","validThrough":"2026-11-01",
 "description":"<p>岗位职责：负责数据产品规划与指标体系。</p><p>任职要求：本科以上，三年经验。</p>",
 "hiringOrganization":{"@type":"Organization","name":"示例科技有限公司"},
 "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"上海"}},
 "url":"https://careers.acme-demo.com/jobs/123",
 "directApply":true}
</script></head><body><h1>数据产品经理</h1><p>岗位职责：负责数据产品规划。</p></body></html>"""

LISTING_PAGE = """<!doctype html><html><head><title>职位列表</title></head>
<body><h1>全部职位</h1><p>共 3 个职位。</p></body></html>"""


class OfficialChannelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"CAREEROS_DB": str(self.root / "db.sqlite3"),
                                     "CAREEROS_OFFICIAL_CACHE": str(self.root / "cache")})
        env.start()
        self.addCleanup(env.stop)

    def serve(self, page=PAGE, robots="User-agent: *\nAllow: /\n"):
        def fake_get(url, accept):
            return robots if url.endswith("/robots.txt") else page
        return patch("careeros.official._get", side_effect=fake_get)

    def test_only_public_https_hosts_are_read(self):
        self.assertEqual(official.require_public_https(POSTING_URL), "careers.acme-demo.com")
        for bad in ("http://careers.acme-demo.com/jobs/1", "https://127.0.0.1/jobs/1",
                    "https://localhost/jobs/1", "https://user:pw@careers.acme-demo.com/jobs/1",
                    "https://careers.acme-demo.com:8443/jobs/1", "https://jobs.internal/jobs/1",
                    "https://example.invalid/jobs/1"):
            with self.assertRaises(ValidationError, msg=bad):
                official.require_public_https(bad)

    def test_json_ld_posting_becomes_full_jd_record(self):
        with self.serve():
            record = official.fetch(POSTING_URL, company="示例科技")
        self.assertEqual(record["source"], "official")
        self.assertEqual(record["title"], "数据产品经理")
        self.assertEqual(record["company"], "示例科技有限公司")
        self.assertEqual(record["location"], "上海")
        self.assertEqual(record["published_at"], "2026-10-01")
        self.assertEqual(record["availability"], "listed")
        self.assertEqual(record["parser"], "json_ld")
        self.assertEqual(record["apply_url"], POSTING_URL)
        self.assertTrue(record["direct_apply"])
        self.assertIn("岗位职责", record["description"])
        self.assertNotIn("<p>", record["description"])

    def test_listing_or_empty_page_is_not_imported_as_jd(self):
        with self.serve(page=LISTING_PAGE):
            with self.assertRaisesRegex(SourceError, "readable JD"):
                official.fetch(POSTING_URL)

    def test_robots_disallow_refuses_the_read(self):
        with self.serve(robots="User-agent: *\nDisallow: /\n"):
            with self.assertRaisesRegex(SourceError, "robots.txt"):
                official.fetch(POSTING_URL)

    def test_import_links_jd_published_at_and_channel(self):
        with self.serve():
            record = official.fetch(POSTING_URL)
        imported = official.import_official(record)
        card = tracking.job_card(imported["job_id"])
        self.assertEqual(card["job"]["source"], "official")
        self.assertEqual(card["job"]["published_at"], "2026-10-01")
        self.assertEqual(card["job"]["availability"], "listed")
        self.assertEqual(card["channels"][0]["channel"], "official")
        self.assertIn("analysis draft", card["next_commands"][0])

    def test_cache_is_reused_without_a_second_read(self):
        with self.serve() as fake:
            first = official.fetch(POSTING_URL)
            second = official.fetch(POSTING_URL)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(fake.call_count, 2)

    def test_plan_never_claims_a_search_was_executed(self):
        plan = official.plan("示例科技", "数据产品经理")
        self.assertFalse(plan["executed"])
        self.assertEqual(plan["provider"], "official")
        self.assertTrue(plan["search_queries"])
        self.assertIn("official fetch", " ".join(plan["steps"]))
        with self.assertRaises(ValidationError):
            official.plan("示例科技", url="http://careers.acme-demo.com/jobs/1")


if __name__ == "__main__":
    unittest.main()
