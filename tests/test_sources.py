import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from oriward import sources
from oriward.db import connect, deserialize


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"ORIWARD_DB": str(Path(self.tmp.name) / "sources.sqlite3")})
        self.env.start()
        self.addCleanup(self.env.stop)

    def record(self, **overrides):
        value = {
            "source": "fixture",
            "source_id": "job-1",
            "title": "Data Analyst",
            "company": "Example Inc.",
            "description": "Build reports",
            "url": "https://example.invalid/jobs/1",
            "location": "Remote",
            "availability": "listed",
            "retrieved_at": "2026-10-01T00:00:00+00:00",
        }
        value.update(overrides)
        return value

    def test_import_idempotence_updates_retrieval_without_snapshot(self):
        first = sources.import_records([self.record()])
        second = sources.import_records([self.record(retrieved_at="2026-10-02T00:00:00Z")])
        self.assertEqual(first, {"added": 1, "updated": 0, "duplicate": 0, "job_ids": [1]})
        self.assertEqual(second, {"added": 0, "updated": 0, "duplicate": 1, "job_ids": [1]})
        snapshots = sources.list_snapshots(1)
        self.assertEqual(len(snapshots), 1)
        with connect() as db:
            current = deserialize(db.execute("SELECT data FROM jobs WHERE id=1").fetchone()["data"])
        self.assertEqual(current["retrieved_at"], "2026-10-02T00:00:00+00:00")
        self.assertEqual(current["content_hash"], snapshots[0]["content_hash"])

    def test_manual_record_has_unknown_retrieval_and_separate_import_time(self):
        manual = self.record()
        manual.pop("retrieved_at")
        result = sources.import_records([manual])
        self.assertEqual(result["added"], 1)
        with connect() as db:
            current = deserialize(db.execute("SELECT data FROM jobs WHERE id=1").fetchone()["data"])
        self.assertIsNone(current["retrieved_at"])
        self.assertTrue(current["imported_at"])
        self.assertEqual(sources.freshness(current)["status"], "unknown")
        self.assertEqual(sources.list_snapshots(1)[0]["retrieved_at"], "")

    def test_older_or_undated_observation_rejects_entire_batch(self):
        sources.import_records([self.record(retrieved_at="2026-10-03T00:00:00Z")])
        with self.assertRaisesRegex(ValueError, "stale or undated"):
            sources.import_records([self.record(retrieved_at="2026-10-02T00:00:00Z")])
        with self.assertRaisesRegex(ValueError, "stale or undated"):
            sources.import_records([
                self.record(source_id="job-2", retrieved_at="2026-10-04T00:00:00Z"),
                self.record(description="Older text", retrieved_at="2026-10-02T00:00:00Z"),
            ])
        with connect() as db:
            rows = db.execute("SELECT data FROM jobs ORDER BY id").fetchall()
        self.assertEqual(len(rows), 1)
        current = deserialize(rows[0]["data"])
        self.assertEqual(current["description"], "Build reports")
        self.assertEqual(current["retrieved_at"], "2026-10-03T00:00:00+00:00")

        undated = self.record()
        undated.pop("retrieved_at")
        with self.assertRaisesRegex(ValueError, "stale or undated"):
            sources.import_records([undated])
        with connect() as db:
            unchanged = deserialize(db.execute("SELECT data FROM jobs WHERE id=1").fetchone()["data"])
        self.assertEqual(unchanged["retrieved_at"], "2026-10-03T00:00:00+00:00")

    def test_changed_description_updates_job_and_adds_snapshot(self):
        sources.import_records([self.record()])
        result = sources.import_records([
            self.record(description="Build audited reports", retrieved_at="2026-10-03T00:00:00Z")
        ])
        self.assertEqual(result, {"added": 0, "updated": 1, "duplicate": 0, "job_ids": [1]})
        snapshots = sources.list_snapshots(1)
        self.assertEqual([row["data"]["description"] for row in snapshots], ["Build reports", "Build audited reports"])
        self.assertNotEqual(snapshots[0]["content_hash"], snapshots[1]["content_hash"])
        reverted = sources.import_records([
            self.record(description="Build reports", retrieved_at="2026-10-04T00:00:00Z")
        ])
        self.assertEqual(reverted["updated"], 1)
        self.assertEqual(len(sources.list_snapshots(1)), 3)

    def test_malformed_batch_rolls_back_entire_import(self):
        with self.assertRaisesRegex(ValueError, "Record 2.*description"):
            sources.import_records([self.record(), self.record(source_id="job-2", description="")])
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0)

    def test_snapshots_are_database_immutable(self):
        sources.import_records([self.record()])
        with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
            with connect() as db:
                db.execute("UPDATE job_source_snapshots SET availability='closed' WHERE id=1")

    def test_greenhouse_adapter_and_sync_metadata(self):
        payload = {
            "jobs": [{
                "id": 42,
                "title": "Platform Engineer",
                "content": "&lt;p&gt;Operate &amp;amp; secure systems&lt;/p&gt;",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/42",
                "location": {"name": "Shanghai"},
                "updated_at": "2026-10-01T00:00:00Z",
                "language": "en",
            }],
            "meta": {"total": 1},
        }
        with patch.object(sources, "_http_json", return_value=payload) as request:
            result = sources.sync_jobs("GREENHOUSE", "acme", company="Acme", limit=10)
        request.assert_called_once_with(
            "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
            "boards-api.greenhouse.io",
        )
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["retrieval"]["available_count"], 1)
        self.assertEqual(result["retrieval"]["returned_count"], 1)
        with connect() as db:
            job = deserialize(db.execute("SELECT data FROM jobs").fetchone()["data"])
        self.assertEqual(job["source"], "greenhouse")
        self.assertEqual(job["source_id"], "42")
        self.assertEqual(job["company"], "Acme")
        self.assertEqual(job["description"], "Operate & secure systems")
        self.assertIn("&lt;p&gt;", job["description_raw_html"])
        self.assertEqual(job["availability"], "listed")
        self.assertEqual(len(job["content_hash"]), 64)

    def test_lever_adapter_maps_public_model_and_limit(self):
        payload = [{
            "id": "abc",
            "text": "Researcher",
            "descriptionPlain": "Study markets",
            "description": "<p>Study markets</p>",
            "lists": [{"text": "Requirements", "content": "<ul><li>Python</li><li>SQL</li></ul>"}],
            "additionalPlain": "Apply thoughtfully",
            "hostedUrl": "https://jobs.lever.co/acme/abc",
            "categories": {
                "location": "Beijing",
                "commitment": "Full-time",
                "team": "Research",
                "allLocations": ["Beijing", "Remote"],
            },
            "workplaceType": "hybrid",
        }]
        with patch.object(sources, "_http_json", return_value=payload) as request:
            fetched = sources.fetch_jobs("lever", "acme", limit=1)
        request.assert_called_once_with(
            "https://api.lever.co/v0/postings/acme?mode=json&limit=1", "api.lever.co"
        )
        self.assertEqual(fetched["company"], "acme")
        self.assertEqual(fetched["records"][0]["title"], "Researcher")
        self.assertEqual(
            fetched["records"][0]["description"],
            "Study markets\n\nRequirements\nPython\nSQL\n\nApply thoughtfully",
        )
        self.assertEqual(fetched["records"][0]["employment_type"], "Full-time")
        self.assertEqual(fetched["records"][0]["all_locations"], ["Beijing", "Remote"])

    def test_provider_payload_errors_are_read_only(self):
        with patch.object(sources, "_http_json", return_value={"jobs": [{"id": 1}]}) :
            with self.assertRaisesRegex(sources.SourceError, "greenhouse job 1"):
                sources.fetch_jobs("greenhouse", "acme")
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0)

    def test_fetch_argument_and_redirect_guards(self):
        for board in ("../secret", "a/b", "", "a" * 101):
            with self.subTest(board=board):
                with self.assertRaises(ValueError):
                    sources.fetch_jobs("lever", board)
        for limit in (0, 1001, True, 1.5):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    sources.fetch_jobs("lever", "acme", limit=limit)
        handler = sources._ExactHostRedirectHandler("api.lever.co")
        request = sources.urllib.request.Request("https://api.lever.co/v0/postings/acme")
        with self.assertRaisesRegex(sources.SourceError, "approved HTTPS host"):
            handler.redirect_request(request, None, 302, "Found", {}, "https://evil.invalid/jobs")

    def test_http_reader_is_bounded_and_sends_no_credentials(self):
        class Response:
            headers = {"Content-Length": str(sources.MAX_RESPONSE_BYTES + 1)}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return "https://api.lever.co/v0/postings/acme?mode=json"
            def read(self, size): raise AssertionError("oversized body must not be read")

        class Opener:
            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return Response()

        opener = Opener()
        with patch.object(sources.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(sources.SourceError, "exceeds 5 MB"):
                sources._http_json("https://api.lever.co/v0/postings/acme?mode=json", "api.lever.co")
        self.assertEqual(opener.timeout, 15)
        headers = {key.casefold(): value for key, value in opener.request.header_items()}
        self.assertNotIn("authorization", headers)
        self.assertNotIn("cookie", headers)

    def test_freshness(self):
        fresh_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        stale_time = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        self.assertEqual(sources.freshness({})["status"], "unknown")
        self.assertEqual(sources.freshness({"retrieved_at": fresh_time})["status"], "fresh")
        self.assertEqual(sources.freshness({"retrieved_at": stale_time})["status"], "stale")
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.assertEqual(sources.freshness({"retrieved_at": future})["status"], "unknown")
        with self.assertRaisesRegex(ValueError, "future"):
            sources.import_records([self.record(retrieved_at=future)])


if __name__ == "__main__":
    unittest.main()
