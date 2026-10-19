"""Decisions retain the reasoning at the time and react to changed evidence."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oriward import migrations, sources
from oriward.core import actions, assertions, context, decisions, goals, pipeline
from oriward.db import connect, now


class DecisionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"ORIWARD_DB": str(self.root / "db.sqlite3"),
                                      "ORIWARD_OUTPUT_DIR": str(self.root / "resumes")})
        env.start()
        self.addCleanup(env.stop)
        self.job = sources.import_records([{
            "source": "fictional", "source_id": "analyst", "title": "数据分析助理", "company": "虚构公司",
            "description": "使用 SQL 清洗数据，不出差", "url": "https://example.com/j/1",
            "availability": "listed", "retrieved_at": now(),
        }])["job_ids"][0]
        self.goal = goals.add(title="探索数据分析", priority=1, status="active", time_budget_hours=2)["id"]
        pipeline.ensure(self.job, status="shortlisted", goal_id=self.goal)
        self.capability = assertions.propose(subject="skill:sql", predicate="has_skill", value={"skill": "SQL"},
                                             assertion_type="skill_hypothesis", source_type="user_message")["id"]
        assertions.confirm(self.capability)
        self.action = actions.propose(title="准备该岗位案例", source_type="job", source_id=self.job,
                                      effort_hours=1, suggestion_reason="SQL 课程项目对应真实岗位要求")["id"]

    def factors(self):
        result = {name: {"status": "supports", "reason": name + " 的具体判断依据"}
                  for name in decisions.FACTOR_NAMES}
        result["capability"]["assertion_ids"] = [self.capability]
        result["deadline"] = {"status": "not_applicable", "reason": "未披露截止，需另行核实"}
        result["cost"]["planned_weekly_hours"] = 1
        return result

    def decision(self, **kwargs):
        params = {"action_id": self.action, "reason": "真实课程项目与岗位要求相符，先低成本验证",
                  "factors": self.factors(), "alternatives": [{"title": "先做作品集", "reason": "投入更大"}]}
        params.update(kwargs)
        return decisions.record(**params)

    def constraint(self):
        rid = assertions.propose(subject="work_conditions", predicate="hard_constraint",
                                 value={"text": "不接受长期出差"}, assertion_type="constraint",
                                 source_type="user_message")["id"]
        assertions.confirm(rid)
        return rid

    def test_constraint_requires_assessment_before_recommendation(self):
        rid = self.constraint()
        pending = actions.list_actions()
        self.assertEqual(pending["ranked"], [])
        self.assertEqual(pending["review"][0]["id"], self.action)
        with self.assertRaisesRegex(ValueError, "every current"):
            self.decision()
        decision = self.decision(constraint_checks=[{"assertion_id": rid, "status": "satisfied",
                                                    "reason": "岗位原文明确不出差"}])
        self.assertEqual(decision["assessment"]["status"], "eligible")
        self.assertEqual(pipeline.show(self.job)["next_action"]["id"], self.action)

    def test_unknown_and_conflicting_constraints_are_not_recommendations(self):
        rid = self.constraint()
        self.decision(constraint_checks=[{"assertion_id": rid, "status": "unknown", "reason": "需询问企业"}])
        self.assertEqual(len(actions.list_actions()["review"]), 1)
        conflicting = self.decision(constraint_checks=[{"assertion_id": rid, "status": "conflict",
                                                       "reason": "需要全年驻场"}])
        self.assertEqual(conflicting["assessment"]["status"], "excluded")
        self.assertIsNone(pipeline.show(self.job)["next_action"])

    def test_versions_freeze_goals_preferences_and_job_snapshots(self):
        first = self.decision()
        frozen = decisions.get(first["id"])["context"]
        goals.update(self.goal, target_date="2026-12-31", rationale="毕业前准备",
                     time_budget_hours=3, success_criteria=["拿到一轮面试"], note="考试结束，增加可用时间")
        state = decisions.get(first["id"])
        self.assertEqual(state["context"], frozen)
        self.assertEqual(state["current_assessment"]["status"], "review")
        second = self.decision()
        self.assertEqual(second["previous_id"], first["id"])
        history = decisions.history(self.action)["versions"]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["context"]["goals"][0]["time_budget_hours"], 2)
        self.assertEqual(history[1]["context"]["goals"][0]["time_budget_hours"], 3)
        self.assertTrue(history[0]["context"]["jobs"][0]["snapshots"])
        changes = goals.history(self.goal)["versions"]
        self.assertEqual(changes[0]["snapshot"]["target_date"], "")
        self.assertEqual(changes[1]["snapshot"]["target_date"], "2026-12-31")
        self.assertIn("考试结束", changes[1]["reason"])

    def test_user_choice_and_completion_are_append_only_results(self):
        decision = self.decision()
        with self.assertRaises(ValueError):
            decisions.outcome(decision["id"], kind="accepted", note="用户同意")
        decisions.outcome(decision["id"], kind="accepted", note="用户明确选择", human_confirmed=True)
        with self.assertRaises(ValueError):
            actions.complete(self.action)
        actions.complete(self.action, evidence="local:case-study.md")
        events = decisions.get(decision["id"])["events"]
        self.assertEqual([e["kind"] for e in events], ["accepted", "completed"])
        self.assertEqual(events[1]["evidence"], "local:case-study.md")
        with connect() as conn, self.assertRaises(sqlite3.IntegrityError):
            conn.execute("UPDATE decision_records SET reason='改写旧决定' WHERE id=?", (decision["id"],))
        with self.assertRaises(ValueError):
            self.decision()

    def test_rejected_choice_does_not_erase_reason_and_requires_new_decision(self):
        first = self.decision()
        decisions.outcome(first["id"], kind="rejected", note="临近期末，暂时不考虑", human_confirmed=True)
        self.assertEqual(len(actions.list_actions()["excluded"]), 1)
        second = self.decision(reason="期末考试结束，重新安排")
        self.assertEqual(second["assessment"]["status"], "eligible")
        self.assertIn("期末", decisions.get(first["id"])["events"][0]["note"])

    def test_inferred_ability_cannot_be_used_as_established_support(self):
        inferred = assertions.propose(subject="skill:python", predicate="has_skill", value={"skill": "Python"},
                                      assertion_type="skill_hypothesis", source_type="model_inference")["id"]
        factors = self.factors()
        factors["capability"]["assertion_ids"] = [inferred]
        with self.assertRaisesRegex(ValueError, "unconfirmed"):
            self.decision(factors=factors)
        factors["capability"]["status"] = "unknown"
        self.assertEqual(self.decision(factors=factors)["assessment"]["status"], "review")

    def test_unrelated_confirmed_preference_is_not_capability_evidence(self):
        preference = assertions.propose(subject="user", predicate="preferred_city", value={"text": "杭州"},
                                        assertion_type="preference", source_type="user_message")["id"]
        assertions.confirm(preference)
        factors = self.factors()
        factors["capability"]["assertion_ids"] = [preference]
        with self.assertRaisesRegex(ValueError, "skill_hypothesis"):
            self.decision(factors=factors)
        mislabeled = assertions.propose(subject="user", predicate="preferred_city", value={"text": "广州"},
                                        assertion_type="skill_hypothesis", source_type="user_message", unique=False)["id"]
        assertions.confirm(mislabeled)
        factors["capability"]["assertion_ids"] = [mislabeled]
        with self.assertRaisesRegex(ValueError, "has_skill"):
            self.decision(factors=factors)

    def test_budget_needs_explicit_feasible_weekly_plan(self):
        heavy = actions.propose(title="完成作品集", source_type="job", source_id=self.job,
                                 effort_hours=20, suggestion_reason="补足作品证据")["id"]
        self.assertTrue(any(r["id"] == heavy for r in actions.list_actions()["review"]))
        decision = self.decision(action_id=heavy)
        self.assertEqual(decision["assessment"]["status"], "eligible")
        factors = self.factors()
        factors["cost"]["planned_weekly_hours"] = 3
        self.assertEqual(self.decision(action_id=heavy, factors=factors)["assessment"]["status"], "review")

    def test_new_claim_or_retracted_evidence_requires_reassessment(self):
        first = self.decision()
        assertions.retract(self.capability, "发现此前只是兴趣，缺少能力证据")
        self.assertEqual(decisions.get(first["id"])["current_assessment"]["status"], "review")
        self.assertEqual(actions.list_actions()["ranked"], [])
        factors = self.factors()
        factors["capability"].update(status="unknown", reason="用户已撤回此前能力判断")
        self.assertEqual(self.decision(factors=factors)["assessment"]["status"], "review")

    def test_brief_keeps_substantive_reason_and_decision_link(self):
        decision = self.decision()
        brief = context.brief(max_chars=20000)
        next_action = brief["what_next"]["actions"][0]
        self.assertEqual(next_action["decision_id"], decision["id"])
        self.assertIn("SQL", next_action["suggestion_reason"])
        self.assertEqual(brief["where_i_am_now"]["open_actions"], 1)

    def test_all_six_factors_and_explicit_reasons_are_required(self):
        factors = self.factors()
        del factors["preference"]
        with self.assertRaises(ValueError):
            self.decision(factors=factors)
        factors = self.factors()
        factors["job"]["reason"] = ""
        with self.assertRaises(ValueError):
            self.decision(factors=factors)
        self.assertEqual(decisions.history(self.action)["versions"], [])

    def test_research_can_clarify_unknown_without_claiming_fit(self):
        self.constraint()
        research = actions.propose(title="查证出差要求", source_type="job", source_id=self.job,
                                    action_type="research", effort_hours=1,
                                    suggestion_reason="核实用户约束是否满足")["id"]
        row = next(r for r in actions.list_actions()["ranked"] if r["id"] == research)
        self.assertEqual(row["assessment"]["status"], "validation")
        self.assertIn("尚未证明", row["why"])

    def test_explicit_evidence_change_invalidates_old_decision(self):
        with connect() as conn:
            exp = conn.execute("INSERT INTO experiences(data,created_at) VALUES (?,?)",
                               (json.dumps({"approved_for_resume": True, "evidence": [
                                   {"status": "user_confirmed", "claim": "SQL 项目"}]}), now())).lastrowid
        factors = self.factors()
        factors["capability"].pop("assertion_ids")
        factors["capability"]["experience_ids"] = [exp]
        decision = self.decision(factors=factors)
        with connect() as conn:
            conn.execute("UPDATE experiences SET data='{}' WHERE id=?", (exp,))
        self.assertEqual(decisions.get(decision["id"])["current_assessment"]["status"], "review")


class MigrationIntegrityTests(unittest.TestCase):
    def test_v3_upgrade_preserves_and_backs_up_existing_goal(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "v3.sqlite3"
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            with patch.object(migrations, "MIGRATIONS", migrations.MIGRATIONS[:3]):
                migrations.apply(conn, path)
            conn.execute("INSERT INTO career_goals(title,status,created_at,updated_at) VALUES ('旧目标','active',?,?)",
                         (now(), now()))
            conn.commit()
            result = migrations.apply(conn, path)
            self.assertTrue(Path(result["backup"]).is_file())
            snapshot = json.loads(conn.execute("SELECT snapshot_json FROM goal_revisions").fetchone()[0])
            self.assertEqual(snapshot["title"], "旧目标")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_goals").fetchone()[0], 1)
            self.assertEqual(migrations.apply(conn, path)["applied"], [])
            conn.close()

    def test_failed_migration_rolls_back_ddl_and_version(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "failed.sqlite3"
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            migrations.apply(conn, path)
            current = max(m["version"] for m in migrations.MIGRATIONS)
            broken = {"version": current + 1, "name": "broken_test", "sql": "CREATE TABLE partial_test (id INTEGER);",
                      "post": lambda conn: conn.execute("SELECT * FROM missing_table_for_test")}
            with patch.object(migrations, "MIGRATIONS", migrations.MIGRATIONS + [broken]):
                with self.assertRaises(sqlite3.OperationalError):
                    migrations.apply(conn, path)
            self.assertEqual(migrations.current_version(conn), current)
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='partial_test'").fetchone())
            conn.close()


if __name__ == "__main__":
    unittest.main()
