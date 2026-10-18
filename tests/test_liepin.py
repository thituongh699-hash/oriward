import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from careeros import discovery
from careeros.extras import liepin


class Response(io.BytesIO):
    headers = {"Content-Type": "application/json"}


class LiepinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"CAREEROS_LIEPIN_CACHE": self.tmp.name, "LIEPIN_USER_TOKEN": "test-secret",
                                      "CAREEROS_ENABLE_LIEPIN": "1"})
        env.start()
        self.addCleanup(env.stop)

    def test_optional_extension_is_disabled_unless_opted_in(self):
        # Default posture: the extension module stays unloaded and nothing is sent.
        with patch.dict(os.environ, {"CAREEROS_ENABLE_LIEPIN": "", "LIEPIN_USER_TOKEN": "test-secret"}), \
                patch.object(liepin, "build_opener") as opener:
            result = discovery.search_local("产品经理", "苏州", "liepin")
        self.assertEqual(result["status"], "EXTENSION_DISABLED")
        self.assertFalse(result["executed"])
        self.assertEqual(result["module"], "careeros.extras.liepin")
        self.assertIn("CAREEROS_ENABLE_LIEPIN", result["enable_with"])
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


if __name__ == "__main__":
    unittest.main()
