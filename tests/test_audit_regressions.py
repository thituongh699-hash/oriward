"""Isolated regressions for the cross-workflow audit findings."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oriward import migrations, sources
from oriward.core import actions, assertions, context, decisions
from oriward.db import connect, now


class AuditRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"ORIWARD_DB": str(self.root / "db.sqlite3"),
                                      "ORIWARD_OUTPUT_DIR": str(self.root / "outputs")})
        env.start()
        self.addCleanup(env.stop)

    def constraint(self, index, text=None):
        return assertions.propose(subject="work_conditions", predicate="hard_constraint",
                                  value={"text": text or f"限制条件{index}"},
                                  assertion_type="constraint", source_type="user_message")["id"]

    def test_fourth_constraint_is_not_silently_lost(self):
        ids = [self.constraint(i) for i in range(4)]
        brief = context.brief(max_chars=20000)
        self.assertEqual({r["assertion_id"] for r in brief["who_am_i"]["constraints"]}, set(ids))
        self.assertTrue(brief["context_budget"]["complete"])

    def test_real_transport_budget_and_omission_metadata(self):
        for i in range(30):
            self.constraint(i, f"条件{i}：" + "很长的已确认约束" * 30)
        brief = context.brief(max_chars=3200)
        rendered = json.dumps(brief, ensure_ascii=False, indent=2, default=str)
        self.assertLessEqual(len(rendered), 3200)
        self.assertEqual(brief["context_budget"]["chars"], len(rendered))
        self.assertFalse(brief["context_budget"]["complete"])
        self.assertTrue(brief["context_budget"]["truncated"])
        self.assertFalse(brief["context_budget"]["over_budget"])
        self.assertEqual(brief["why"], {})

    def test_document_cannot_self_confirm_user_agreement(self):
        with self.assertRaisesRegex(ValueError, "belief confirm"):
            assertions.propose(subject="user", predicate="education", value={"text": "在读"},
                               assertion_type="fact", source_type="document",
                               epistemic_status="user_confirmed")
        claim = assertions.propose(subject="user", predicate="education", value={"text": "在读"},
                                   assertion_type="fact", source_type="document")
        self.assertEqual(assertions.get(claim["id"])["last_confirmed_at"], "")
        assertions.confirm(claim["id"])
        self.assertTrue(assertions.get(claim["id"])["last_confirmed_at"])

    def test_withdrawn_application_excludes_old_action(self):
        jid = sources.import_records([{"source": "fictional", "source_id": "one", "title": "助理",
                                       "company": "虚构公司", "description": "整理资料", "availability": "listed",
                                       "url": "https://example.com/job/one", "retrieved_at": now()}])["job_ids"][0]
        with connect() as db:
            rid = db.execute("INSERT INTO resumes(job_id,experience_ids,output_path,sha256,created_at) "
                             "VALUES (?,'[]','fixture.md','fixture',?)", (jid, now())).lastrowid
            aid = db.execute("INSERT INTO applications(job_id,resume_id,status,created_at,updated_at) "
                             "VALUES (?,?,'READY_FOR_USER',?,?)", (jid, rid, now(), now())).lastrowid
        action = actions.propose(title="跟进申请", source_type="application", source_id=aid,
                                 action_type="follow_up", suggestion_reason="核对处理结果")["id"]
        factors = {key: {"status": "not_applicable", "reason": "此处仅核对申请状态"}
                   for key in decisions.FACTOR_NAMES}
        decision = decisions.record(action_id=action, reason="先核对处理情况", factors=factors)
        self.assertEqual(decision["assessment"]["status"], "eligible")
        with connect() as db:
            db.execute("UPDATE applications SET status='WITHDRAWN' WHERE id=?", (aid,))
        state = decisions.get(decision["id"])
        self.assertEqual(state["current_assessment"]["status"], "excluded")
        self.assertEqual(actions.list_actions()["ranked"], [])
        self.assertEqual(state["context"]["application"]["status"], "READY_FOR_USER")


class WalBackupRegression(unittest.TestCase):
    def test_upgrade_backup_restores_committed_wal_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "wal.sqlite3"
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            with patch.object(migrations, "MIGRATIONS", migrations.MIGRATIONS[:4]):
                migrations.apply(conn, path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA wal_autocheckpoint=0")
            conn.execute("INSERT INTO career_goals(title,status,created_at,updated_at) "
                         "VALUES ('已提交到WAL的目标','active',?,?)", (now(), now()))
            conn.commit()
            result = migrations.apply(conn, path)
            self.assertTrue(result["backup"])
            restored = sqlite3.connect(result["backup"])
            try:
                self.assertEqual(restored.execute("PRAGMA quick_check").fetchone()[0], "ok")
                self.assertEqual(restored.execute("SELECT title FROM career_goals").fetchone()[0], "已提交到WAL的目标")
                self.assertEqual(migrations.current_version(restored), 4)
                self.assertIsNone(restored.execute("SELECT name FROM sqlite_master WHERE name='career_settings'").fetchone())
            finally:
                restored.close()
                conn.close()


if __name__ == "__main__":
    unittest.main()
