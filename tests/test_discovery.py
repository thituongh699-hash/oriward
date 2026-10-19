import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oriward import discovery as d, sources, services, cli
from oriward.db import now


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"ORIWARD_DB": str(self.root / "test.sqlite3"),
                                     "ORIWARD_CACHE_DIR": str(self.root / "cache")})
        env.start(); self.addCleanup(env.stop)

    def lead(self, **overrides):
        row = {"provider": "zhilian", "title": "数据分析师", "company": "虚构企业", "location": "上海",
               "url": "https://www.zhaopin.com/jobdetail/TEST.htm", "discovered_at": now(),
               "discovery_method": "web_index", "summary": "索引摘要", "query": "数据分析"}
        row.update(overrides)
        return row

    def test_plan_never_claims_execution(self):
        plan = d.search_plan("数据分析", "上海", ["boss", "zhilian"])
        self.assertFalse(plan["executed"])
        self.assertIn("site:zhipin.com", plan["channels"][0]["search_query"])
        out = d.search_local("数据分析", provider="boss")
        self.assertFalse(out["executed"])
        self.assertNotIn("leads", out)

    def test_leads_are_not_jobs_and_deduplicate(self):
        self.assertEqual(d.import_leads([self.lead()])["added"], 1)
        self.assertEqual(d.import_leads([self.lead()])["duplicate"], 1)
        self.assertEqual(len(services.list_objects("jobs")), 0)
        row = d.list_leads()[0]
        self.assertEqual(row["availability"], "unknown")
        self.assertEqual(row["evidence_level"], "lead_only")

    def test_forged_domain_rejected_atomically(self):
        with self.assertRaisesRegex(ValueError, "declared platform"):
            d.import_leads([self.lead(), self.lead(url="https://zhaopin.com.evil.invalid/jobdetail/x")])
        self.assertEqual(d.list_leads(), [])
        with self.assertRaises(ValueError):
            d.import_leads([self.lead(url="https://user:password@www.zhaopin.com/jobdetail/x")])

    def test_source_time_not_overwritten_by_old_observation(self):
        d.import_leads([self.lead()])
        with self.assertRaisesRegex(ValueError, "Older"):
            d.import_leads([self.lead(discovered_at="2020-01-01T00:00:00+00:00")])

    def test_observation_order_compares_instants_across_timezones(self):
        d.import_leads([self.lead(discovered_at="2020-01-01T10:00:00+08:00")])
        result = d.import_leads([self.lead(discovered_at="2020-01-01T03:00:00+00:00")])
        self.assertEqual(result["duplicate"], 1)
        self.assertEqual(d.list_leads()[0]["discovered_at"], "2020-01-01T03:00:00+00:00")

    def test_full_jd_promotion_and_identity(self):
        lid = d.import_leads([self.lead()])["lead_ids"][0]
        data = {"title": "数据分析师", "company": "虚构企业", "description": "职责：使用SQL。要求：本科。",
                "url": self.lead()["url"], "retrieved_at": now(), "read_method": "user_copy", "content_complete": True}
        with self.assertRaisesRegex(ValueError, "complete JD"):
            d.promote_lead(lid, dict(data, content_complete=False))
        with self.assertRaisesRegex(ValueError, "must match"):
            d.promote_lead(lid, dict(data, url="https://www.zhaopin.com/jobdetail/OTHER.htm"))
        result = d.promote_lead(lid, data)
        self.assertEqual(d.list_leads()[0]["job_id"], result["job_id"])
        self.assertEqual(services.get_job(result["job_id"])["evidence_level"], "full_jd")

    def test_listing_page_not_promoted_as_single_vacancy(self):
        row = self.lead(provider="boss", url="https://www.zhipin.com/zhaopin/demo/")
        lid = d.import_leads([row])["lead_ids"][0]
        with self.assertRaisesRegex(ValueError, "listing pages"):
            d.promote_lead(lid, dict(row, description="列表摘要", retrieved_at=now(), read_method="user_copy", content_complete=True))

    def test_local_search_persists_only_leads(self):
        with patch("oriward.public_search.search_zhiye", return_value={
            "records": [{"title": "数据分析", "company": "虚构", "location": "上海", "url": "https://zhiye.page/jobs/job_demo"}],
            "fetched_at": now(), "cache_hit": False, "search_url": "https://zhiye.page/jobs?q=test"}):
            result = d.search_local("数据分析", "上海")
        self.assertTrue(result["executed"])
        self.assertEqual(result["import"]["added"], 1)
        self.assertEqual(len(services.list_objects("jobs")), 0)

    def test_compact_keeps_complete_jd_and_evidence(self):
        packet = {"job": {"description": "必须持证\n熟练Python", "title": "分析", "raw_html": "x" * 10000,
                          "eligibility": "必须具备当地工作许可", "deadline": "2026-12-01"},
                  "approved_experiences": [{"id": 1, "evidence": ["所有原始证据"]}]}
        out = cli.compact_packet(packet)
        self.assertEqual(out["job"]["description"], packet["job"]["description"])
        self.assertEqual(out["approved_experiences"], packet["approved_experiences"])
        self.assertNotIn("raw_html", out["job"])
        self.assertEqual(out["job"]["eligibility"], packet["job"]["eligibility"])
        self.assertEqual(out["job"]["deadline"], packet["job"]["deadline"])
        self.assertLess(len(json.dumps(out)), len(json.dumps(packet)) / 10)
        history = {"prior_reviews": [{"id": 1, "review": {"red_findings": [{"issue": "真实缺口"}]}}]}
        self.assertEqual(cli.compact_packet(history)["prior_reviews"][0]["review"], history["prior_reviews"][0]["review"])

    def test_old_query_cache_preserves_newer_lead_and_other_results(self):
        url = "https://zhiye.page/jobs/job_demo"
        d.import_leads([self.lead(provider="zhiye", url=url, title="更新后的岗位")])
        with patch("oriward.public_search.search_zhiye", return_value={
            "records": [{"title": "旧标题", "url": url},
                        {"title": "另一岗位", "url": "https://zhiye.page/jobs/job_other"}],
            "fetched_at": "2020-01-01T00:00:00+00:00", "cache_hit": True, "search_url": "https://zhiye.page/jobs?q=test"}):
            result = d.search_local("数据分析")
        self.assertEqual(result["import"]["skipped_older"], 1)
        self.assertEqual(result["import"]["added"], 1)
        self.assertEqual(result["leads"][0]["title"], "更新后的岗位")

    def test_output_json_file_keeps_context_small(self):
        path = self.root / "channels.json"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            cli.run(["--output", str(path), "jobs", "channels"])
        manifest = json.loads(stdout.getvalue())
        self.assertEqual(manifest["bytes"], path.stat().st_size)
        self.assertEqual(len(json.loads(path.read_text(encoding="utf-8"))), len(d.CHANNELS))
        self.assertLess(len(stdout.getvalue()), len(path.read_text(encoding="utf-8")))

    def test_shortlist_filters_closed_location_and_exclusions_locally(self):
        sources.import_records([
            {"source": "fixture", "source_id": "1", "title": "数据分析", "company": "A", "location": "上海", "description": "SQL Python"},
            {"source": "fixture", "source_id": "2", "title": "数据分析外包", "company": "B", "location": "上海", "description": "SQL Python"},
            {"source": "fixture", "source_id": "3", "title": "数据分析", "company": "C", "location": "北京", "description": "SQL Python"},
            {"source": "fixture", "source_id": "4", "title": "数据分析", "company": "D", "location": "上海", "description": "SQL", "availability": "closed"},
        ])
        result = d.shortlist("数据分析 SQL", "上海", "外包")
        self.assertEqual([r["company"] for r in result["results"]], ["A"])
        self.assertNotIn("grade", result["results"][0])


if __name__ == "__main__":
    unittest.main()
