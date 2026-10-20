import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from oriward import discovery
from oriward.extras import liepin


class Response(io.BytesIO):
    headers = {"Content-Type": "application/json"}


class LiepinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ORIWARD_LIEPIN_CACHE": self.tmp.name, "LIEPIN_USER_TOKEN": "test-secret",
                                      "ORIWARD_ENABLE_LIEPIN": "1"})
        env.start()
        self.addCleanup(env.stop)

    def test_optional_extension_is_disabled_unless_opted_in(self):
        # Default posture: the extension module stays unloaded and nothing is sent.
        with patch.dict(os.environ, {"ORIWARD_ENABLE_LIEPIN": "", "LIEPIN_USER_TOKEN": "test-secret"}), \
                patch.object(liepin, "build_opener") as opener:
            result = discovery.search_local("产品经理", "苏州", "liepin")
        self.assertEqual(result["status"], "EXTENSION_DISABLED")
        self.assertFalse(result["executed"])
        self.assertEqual(result["module"], "oriward.extras.liepin")
        self.assertIn("ORIWARD_ENABLE_LIEPIN", result["enable_with"])
        self.assertTrue(result["terms"])
        opener.assert_not_called()

    def test_missing_auth_does_not_send_request(self):
        with patch.dict(os.environ, {"LIEPIN_USER_TOKEN": ""}), patch.object(liepin, "build_opener") as opener:
            result = discovery.search_local("产品经理", "苏州", "liepin")
        self.assertEqual(result["status"], "AUTH_REQUIRED")
        self.assertFalse(result["executed"])
        self.assertEqual(result["setup"], "docs/LIEPIN_INTEGRATION.md")
        self.assertEqual(result["credential_env"], "LIEPIN_USER_TOKEN")
        opener.assert_not_called()

    def test_only_fixed_search_endpoint_with_no_resume_and_no_assumed_success(self):
        with patch.object(liepin, "build_opener") as opener:
            opener.return_value.open.return_value = Response(b'{"code":999,"message":"business error"}')
            result = liepin.search("产品经理", "苏州")
            request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://open-agent.liepin.com/mcp/search-job")
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data), {"jobName": "产品经理", "address": "苏州", "page": 0})
        self.assertEqual(result["status"], "RESPONSE_REQUIRES_VALIDATION")
        self.assertFalse(result["executed"])
        self.assertEqual(result["imported"], 0)
        self.assertNotIn("test-secret", json.dumps(result))
        self.assertEqual(json.loads(Path(result["response_path"]).read_text())["code"], 999)

    def test_cache_preserves_fetch_time_and_is_account_separated(self):
        with patch.object(liepin, "build_opener") as opener:
            opener.return_value.open.return_value = Response(b'{}')
            original = liepin.search("产品经理")
            # Keep this cache-hit fixture inside the valid TTL interval. NTFS
            # mtimes can be sub-microseconds ahead of datetime.now()'s precision.
            for artifact in Path(self.tmp.name).glob("*.json"):
                stat = artifact.stat()
                os.utime(artifact, (stat.st_atime, stat.st_mtime - 1))
            cached = liepin.search("产品经理")
            self.assertEqual(opener.return_value.open.call_count, 1)
            self.assertTrue(cached["cache_hit"])
            self.assertEqual(cached["fetched_at"], original["fetched_at"])
            opener.return_value.open.return_value = Response(b'{}')
            with patch.dict(os.environ, {"LIEPIN_USER_TOKEN": "another-secret"}):
                other = liepin.search("产品经理")
            self.assertNotEqual(other["response_path"], original["response_path"])
            self.assertEqual(opener.return_value.open.call_count, 2)

    def test_http_errors_do_not_echo_body_or_token(self):
        for code in (401, 403, 302, 429, 500):
            with patch.object(liepin, "build_opener") as opener:
                opener.return_value.open.side_effect = HTTPError(liepin.ENDPOINT, code, "test-secret", {}, io.BytesIO(b'test-secret'))
                result = liepin.search("x", refresh=True)
            self.assertFalse(result["executed"])
            self.assertEqual(result["http_status"], code)
            self.assertNotIn("test-secret", json.dumps(result))

    def test_oversized_and_invalid_json_do_not_create_result_artifacts(self):
        for content in (b'x' * (liepin.MAX_BYTES + 1), b'<html>login</html>'):
            with patch.object(liepin, "build_opener") as opener:
                opener.return_value.open.return_value = Response(content)
                with self.assertRaises(ValueError):
                    liepin.search("x")
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_redirect_is_rejected(self):
        self.assertIsNone(liepin.NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid"))

    @staticmethod
    def _card(name, url, company="某公司"):
        return {"jobName": name, "company": company, "jobDetailUrl": url, "location": "苏州-工业园区",
                "salary": "4-5k", "education": "本科", "workYears": "经验不限", "industry": "互联网"}

    def _run(self, query, cards):
        body = json.dumps({"code": 0, "data": {"list": cards}}).encode()
        with patch.object(liepin, "build_opener") as opener:
            opener.return_value.open.return_value = Response(body)
            return liepin.search(query, "苏州", refresh=True)

    def test_unsupported_detail_url_is_skipped_instead_of_voiding_the_page(self):
        # A social-hire /a/ card used to make normalize() return None, discarding
        # every valid row on the same page. It is now counted and skipped.
        result = self._run("运营实习生", [
            self._card("新媒体运营实习生", "https://www.liepin.com/job/1985339817.shtml?mscid=soai_pc_001"),
            self._card("猎头顾问实习生", "https://www.liepin.com/a/80275619.shtml?mscid=soai_pc_001"),
        ])
        self.assertEqual(result["status"], "SEARCH_VERIFIED")
        self.assertTrue(result["executed"])
        self.assertEqual(result["returned_count"], 1)
        self.assertEqual(result["skipped_unsupported_url"], 1)
        self.assertEqual(result["records"][0]["url"], "https://www.liepin.com/job/1985339817.shtml")

    def test_page_with_only_unsupported_urls_is_not_a_verified_empty_result(self):
        result = self._run("项目管理实习生", [
            self._card("项目管理实习生", "https://www.liepin.com/a/79529233.shtml"),
        ])
        self.assertEqual(result["status"], "RESPONSE_REQUIRES_VALIDATION")
        self.assertFalse(result["executed"])
        self.assertEqual(result["imported"], 0)
        self.assertNotIn("records", result)

    def test_untrusted_host_still_rejects_the_whole_page(self):
        # Skipping is only for URL *shape*; an off-domain link means the payload
        # is not what this adapter claims to read, so nothing is imported.
        result = self._run("数据分析实习生", [
            self._card("数据分析实习生", "https://www.liepin.com/job/1983889857.shtml"),
            self._card("可疑岗位", "https://evil.example/job/1.shtml"),
        ])
        self.assertEqual(result["status"], "RESPONSE_REQUIRES_VALIDATION")
        self.assertFalse(result["executed"])
        self.assertEqual(result["imported"], 0)


if __name__ == "__main__":
    unittest.main()
