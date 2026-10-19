"""Action source links resolve through applications, interviews and learning plans."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oriward import sources
from oriward.core import actions, goals, pipeline, relations
from oriward.core.errors import NotFoundError
from oriward.db import connect, now, serialize


class ActionLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ORIWARD_DB": str(Path(self.tmp.name) / "test.sqlite3")})
        env.start()
        self.addCleanup(env.stop)

    def job(self, key):
        return sources.import_records([{
            "source": "fixture", "source_id": key, "title": f"岗位 {key}", "company": "示例",
            "description": "测试岗位", "url": f"https://example.test/{key}",
        }])["job_ids"][0]

    def goal_for(self, job_id, *, title="目标", priority=3):
        goal_id = goals.add(title=title, priority=priority, status="active")["id"]
        pipeline.ensure(job_id, goal_id=goal_id)
        return goal_id

    def action(self, source_type, source_id, title="推进任务", depends_on=None):
        return actions.propose(title=title, source_type=source_type, source_id=source_id,
                               action_type="prepare", depends_on=depends_on,
                               suggestion_reason="推进关联事项")

    def application_for(self, job_id):
        with connect() as conn:
            cursor = conn.execute(
                "INSERT INTO resumes(job_id,experience_ids,output_path,sha256,created_at) "
                "VALUES (?,?,?,?,?)", (job_id, "[]", "", "", now()))
            cursor = conn.execute(
                "INSERT INTO applications(job_id,resume_id,status,created_at,updated_at) "
                "VALUES (?,?, 'READY_FOR_USER',?,?)", (job_id, cursor.lastrowid, now(), now()))
            return cursor.lastrowid

    def interview_for(self, job_id):
        with connect() as conn:
            cursor = conn.execute("INSERT INTO interviews(job_id,data,created_at) VALUES (?,?,?)",
                                  (job_id, "{}", now()))
            return cursor.lastrowid

    def test_application_and_interview_actions_resolve_job_and_goal(self):
        for kind in ("application", "interview"):
            job_id = self.job(kind)
            goal_id = self.goal_for(job_id, title=f"{kind}目标", priority=1)
            source_id = self.application_for(job_id) if kind == "application" else self.interview_for(job_id)
            action = self.action(kind, source_id)

            with connect() as conn:
                self.assertEqual(relations.source_context(conn, kind, source_id),
                                 {"job_ids": [job_id], "goal_ids": [goal_id]})
            ranked = next(row for row in actions.list_actions()["ranked"] if row["id"] == action["id"])
            self.assertEqual(ranked["factors"]["goal_priority"], 15)
            card = pipeline.show(job_id)
            self.assertEqual(card["next_action"]["id"], action["id"])
            self.assertEqual(card["next_action"]["source_type"], kind)
            self.assertIn("推进关联事项", card["next_action"]["suggestion_reason"])

    def test_learning_plan_resolves_multiple_jobs_and_goals_deterministically(self):
        first_job, second_job = self.job("learn-a"), self.job("learn-b")
        first_goal = self.goal_for(first_job, title="普通目标", priority=4)
        second_goal = self.goal_for(second_job, title="高优先级目标", priority=1)
        with connect() as conn:
            cursor = conn.execute("INSERT INTO learning_plans(data,created_at) VALUES (?,?)",
                                  (serialize({"job_ids": [second_job, first_job],
                                              "goal_id": first_goal}), now()))
            plan_id = cursor.lastrowid
            context = relations.source_context(conn, "learning", plan_id)
        self.assertEqual(context, {"job_ids": sorted([first_job, second_job]),
                                   "goal_ids": sorted([first_goal, second_goal])})
        action = self.action("learning", plan_id)
        ranked = next(row for row in actions.list_actions()["ranked"] if row["id"] == action["id"])
        self.assertEqual(ranked["factors"]["goal_priority"], 15)
        self.assertEqual(pipeline.show(first_job)["next_action"]["id"], action["id"])
        self.assertEqual(pipeline.show(second_job)["next_action"]["id"], action["id"])

    def test_dangling_concrete_source_is_rejected(self):
        with self.assertRaises(NotFoundError):
            self.action("application", 999)
        with self.assertRaises(NotFoundError):
            self.action("job", 999)

    def test_shared_goal_does_not_mix_job_specific_tasks(self):
        first, second = self.job("shared-a"), self.job("shared-b")
        goal_id = self.goal_for(first)
        pipeline.ensure(second, goal_id=goal_id)
        interview_task = self.action("interview", self.interview_for(first), "仅准备第一家面试")
        common_task = self.action("goal", goal_id, "通用作品准备")
        with connect() as conn:
            plan = conn.execute("INSERT INTO learning_plans(data,created_at) VALUES (?,?)",
                                (serialize({"goal_id": goal_id}), now())).lastrowid
        learning_task = self.action("learning", plan, "共同能力学习")
        first_ids = {row["id"] for row in pipeline.show(first)["open_actions"]}
        second_ids = {row["id"] for row in pipeline.show(second)["open_actions"]}
        self.assertIn(interview_task["id"], first_ids)
        self.assertNotIn(interview_task["id"], second_ids)
        self.assertTrue({common_task["id"], learning_task["id"]} <= first_ids & second_ids)

    def test_closed_opportunity_does_not_exclude_goal_level_preparation(self):
        job_id = self.job("closing")
        goal_id = self.goal_for(job_id)
        common = self.action("goal", goal_id, "准备通用项目案例")
        specific = self.action("job", job_id, "准备关闭岗位的投递")
        with connect() as conn:
            row = conn.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
            data = json.loads(row["data"])
            data["availability"] = "closed"
            conn.execute("UPDATE jobs SET data=? WHERE id=?", (serialize(data), job_id))
        result = actions.list_actions()
        self.assertIn(common["id"], {row["id"] for row in result["ranked"]})
        self.assertIn(specific["id"], {row["id"] for row in result["excluded"]})

    def test_job_card_skips_blocked_and_dependency_incomplete_actions(self):
        job_id = self.job("ready-choice")
        blocked = self.action("job", job_id, "被阻塞")
        actions.block(blocked["id"], "等反馈")
        prerequisite = self.action("job", job_id, "前置任务")
        dependent = self.action("job", job_id, "等待中的任务", [prerequisite["id"]])
        self.action("job", job_id, "可执行任务")
        for index in range(4):
            self.action("job", job_id, f"额外任务 {index}")

        card = pipeline.show(job_id)
        self.assertEqual(len(card["open_actions"]), 8)
        self.assertEqual(card["next_action"]["id"], prerequisite["id"])
        self.assertNotEqual(card["next_action"]["id"], blocked["id"])
        self.assertNotEqual(card["next_action"]["id"], dependent["id"])
        self.assertEqual(card["blocking_issue"]["action_id"], blocked["id"])

    def test_due_at_must_be_iso8601_and_effort_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "due_at"):
            actions.propose(title="坏日期", source_type="core", action_type="other",
                            due_at="next Tuesday", suggestion_reason="测试")
        with self.assertRaisesRegex(ValueError, "effort_hours"):
            actions.propose(title="过量工时", source_type="core", action_type="other",
                            effort_hours=201, suggestion_reason="测试")


if __name__ == "__main__":
    unittest.main()
