"""Rebranding must not hide existing local state or reverse explicit opt-outs."""
from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from oriward import cli, db, discovery, services
from oriward.legacy import LEGACY_DATABASE_NAME, LEGACY_ENV_PREFIX, environment


class RebrandingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="oriward-rename-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for setting in (patch.dict(os.environ, {}, clear=True),
                        patch.object(db, "PROJECT_ROOT", self.root),
                        patch.object(services, "PROJECT_ROOT", self.root)):
            setting.start()
            self.addCleanup(setting.stop)

    def test_existing_database_is_reused_without_empty_replacement(self):
        previous = self.root / "data/private" / LEGACY_DATABASE_NAME
        previous.parent.mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(previous)) as conn, conn:
            conn.execute("CREATE TABLE rename_sentinel(value TEXT)")
            conn.execute("INSERT INTO rename_sentinel VALUES ('preserve-existing-state')")
        with contextlib.redirect_stdout(io.StringIO()):
            cli.run(["init"])
        self.assertEqual(db.database_path(), previous)
        self.assertFalse(previous.with_name("oriward.sqlite3").exists())
        with contextlib.closing(sqlite3.connect(previous)) as conn:
            self.assertEqual(conn.execute("SELECT value FROM rename_sentinel").fetchone()[0],
                             "preserve-existing-state")

    def test_fresh_install_uses_new_database_name(self):
        self.assertEqual(db.database_path(), self.root / "data/private/oriward.sqlite3")
        self.assertFalse(self.root.joinpath("data").exists())

    def test_explicit_new_database_and_output_take_precedence(self):
        os.environ[LEGACY_ENV_PREFIX + "DB"] = str(self.root / "previous.sqlite3")
        os.environ[LEGACY_ENV_PREFIX + "OUTPUT_DIR"] = str(self.root / "previous-resumes")
        os.environ["ORIWARD_DB"] = str(self.root / "current.sqlite3")
        os.environ["ORIWARD_OUTPUT_DIR"] = str(self.root / "current-resumes")
        self.assertEqual(db.database_path(), self.root / "current.sqlite3")
        self.assertEqual(services.resume_output_dir(), self.root / "current-resumes")

    def test_old_isolated_database_does_not_write_shared_outputs(self):
        os.environ[LEGACY_ENV_PREFIX + "DB"] = str(self.root / "isolated/state.sqlite3")
        self.assertEqual(services.resume_output_dir(), self.root / "isolated/outputs/resumes")

    def test_new_explicit_opt_out_overrides_previous_extension_setting(self):
        os.environ[LEGACY_ENV_PREFIX + "ENABLE_LIEPIN"] = "1"
        self.assertTrue(discovery.extension_enabled("liepin"))
        for value in ("0", ""):
            os.environ["ORIWARD_ENABLE_LIEPIN"] = value
            self.assertFalse(discovery.extension_enabled("liepin"))

    def test_previous_cache_setting_can_be_overridden_by_new_one(self):
        os.environ[LEGACY_ENV_PREFIX + "CACHE_DIR"] = "previous-cache"
        self.assertEqual(environment("ORIWARD_CACHE_DIR"), "previous-cache")
        os.environ["ORIWARD_CACHE_DIR"] = "current-cache"
        self.assertEqual(environment("ORIWARD_CACHE_DIR"), "current-cache")


if __name__ == "__main__":
    unittest.main()
