"""Acceptance tests for the Career Twin Core (v0.2).

Each test maps to a rule the design must not violate: versioned beliefs, no
self-confirmation by the model, case-scoped feedback, opportunity state separate
from applications, bounded context, and proposals that never self-apply.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from careeros import migrations, services as s, sources
from careeros.core import actions, assertions, context, goals, pipeline, reflection, signals, twin
from careeros.core.errors import ConflictError, NotFoundError
from careeros.db import connect


class TwinCoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"CAREEROS_DB": str(self.root / "db.sqlite3"),
                                      "CAREEROS_OUTPUT_DIR": str(self.root / "resumes")})
        env.start()
        self.addCleanup(env.stop)

    # -- belief versioning -------------------------------------------------
    def test_revision_preserves_both_versions(self):
        first = assertions.propose(
            subject="work_conditions", predicate="hard_constraint",
            value={"text": "不接受长期出差"}, assertion_type="constraint",
            source_type="user_message")
        second = assertions.revise(first["id"], value={"text": "不接受每月超过两周的出差"},
                                   reason="用户修正")
        self.assertEqual(second["supersedes"], first["id"])
        history = assertions.history(subject="work_conditions", predicate="hard_constraint")
        self.assertEqual([v["id"] for v in history["versions"]], [first["id"], second["id"]])
        self.assertTrue(history["versions"][0]["valid_to"])
        self.assertEqual(history["versions"][1]["valid_to"], "")
        live = assertions.list_assertions(subject="work_conditions")
        self.assertEqual([row["id"] for row in live], [second["id"]])

    def test_model_inference_cannot_confirm_itself(self):
        with self.assertRaises(ValueError):
            assertions.propose(
                subject="skill:python", predicate="has_skill", value={"skill": "Python"},
                assertion_type="skill_hypothesis", source_type="model_inference",
                epistemic_status="user_confirmed")

    def test_history_of_unknown_assertion_raises(self):
        with self.assertRaises(NotFoundError):
            assertions.history(assertion_id=99)

    def test_confirmation_is_an_explicit_user_action(self):
        claim = assertions.propose(
            subject="skill:sql", predicate="has_skill", value={"skill": "SQL"},
            assertion_type="skill_hypothesis", source_type="model_inference")
        self.assertEqual(claim["created"], True)
        self.assertEqual(assertions.get(claim["id"])["epistemic_status"], "inferred")
        assertions.confirm(claim["id"])
        record = assertions.get(claim["id"])
        self.assertEqual(record["epistemic_status"], "user_confirmed")
        self.assertTrue(record["last_confirmed_at"])
        assertions.retract(claim["id"], "用户否认")
        with self.assertRaises(ValueError):
            assertions.confirm(claim["id"])

    def test_conflicting_restatement_needs_revise(self):
        claim = assertions.propose(
            subject="user", predicate="preferred_city", value={"text": "上海"},
            assertion_type="preference", source_type="user_message")
        assertions.confirm(claim["id"])
        with self.assertRaises(ConflictError):
            assertions.propose(
                subject="user", predicate="preferred_city", value={"text": "杭州"},
                assertion_type="preference", source_type="user_message")

    def test_user_statement_replaces_an_inference(self):
        inferred = assertions.propose(
            subject="user", predicate="preferred_city", value={"text": "上海"},
            assertion_type="preference", source_type="model_inference")
        replaced = assertions.propose(
            subject="user", predicate="preferred_city", value={"text": "杭州"},
            assertion_type="preference", source_type="user_message")
        self.assertTrue(replaced.get("auto_superseded_inference"))
        self.assertEqual(replaced["supersedes"], inferred["id"])
        self.assertEqual(assertions.get(inferred["id"])["epistemic_status"], "inferred")
        self.assertTrue(assertions.get(inferred["id"])["valid_to"])

    def test_dangling_provenance_link_is_rejected(self):
        with self.assertRaises(NotFoundError):
            assertions.propose(
                subject="skill:x", predicate="has_skill", value={"skill": "X"},
                assertion_type="skill_hypothesis", source_type="model_inference",
                links=[{"ref_type": "experience", "ref_id": 999, "relation": "derived_from"}])
        # The whole proposal must roll back, not leave an untraceable claim.
        self.assertEqual(assertions.list_assertions(), [])

    def test_set_valued_claims_coexist(self):
        first = assertions.propose(
            subject="work_conditions", predicate="hard_constraint",
            value={"text": "不接受长期出差"}, assertion_type="constraint",
            source_type="user_message")
        second = assertions.propose(
            subject="work_conditions", predicate="hard_constraint",
            value={"text": "不接受外包编制"}, assertion_type="constraint",
            source_type="user_message")
        self.assertTrue(first["created"] and second["created"])
        live = assertions.list_assertions(assertion_type="constraint")
        self.assertEqual(len(live), 2)

    def test_superseded_claim_is_history_only(self):
        first = assertions.propose(
            subject="user", predicate="preferred_city", value={"text": "上海"},
            assertion_type="preference", source_type="user_message")
        second = assertions.revise(first["id"], value={"text": "杭州"}, reason="用户修正")
        for action in (lambda: assertions.confirm(first["id"]),
                       lambda: assertions.dispute(first["id"], "再想想"),
                       lambda: assertions.retract(first["id"], "改主意")):
            with self.assertRaises(ValueError):
                action()
        live = assertions.list_assertions(subject="user")
        self.assertEqual([row["id"] for row in live], [second["id"]])
        self.assertEqual(assertions.get(second["id"])["epistemic_status"], "user_stated")

    def test_hedged_self_statement_stays_uncertain(self):
        claim = assertions.propose(
            subject="user", predicate="core_value", value={"text": "我可能比较看重自主性吧"},
            assertion_type="value", source_type="user_message", confidence="low")
        brief = context.brief()
        self.assertEqual(brief["who_am_i"]["values"], [])
        self.assertIn(claim["id"], [item["assertion_id"] for item in brief["uncertainties"]])
        # Confirming the wording is what turns it into a stable claim.
        assertions.confirm(claim["id"])
        self.assertEqual([item["claim"] for item in context.brief()["who_am_i"]["values"]],
                         ["我可能比较看重自主性吧"])

    def test_direction_evidence_uses_derived_from(self):
        experience_id = s.add_object("experiences", {
            "event": "课程项目", "actions": ["做报表"], "outcomes": [],
            "evidence": [{"claim": "做报表", "source": "自述", "status": "user_confirmed"}],
            "approved_for_resume": True,
        }, ["event", "actions", "outcomes", "evidence", "approved_for_resume"])
        claim = assertions.propose(
            subject="career:data-pm", predicate="direction_hypothesis",
            value={"direction": "数据产品经理"}, assertion_type="career_hypothesis",
            source_type="model_inference",
            links=[{"ref_type": "experience", "ref_id": experience_id, "relation": "derived_from"}])
        direction = next(item for item in context.brief()["who_could_i_become"]["directions"]
                         if item["hypothesis_id"] == claim["id"])
        self.assertEqual(len(direction["support"]), 1)
        self.assertIn("课程项目", direction["support"][0])

    # -- feedback ----------------------------------------------------------
    def test_feedback_is_case_scoped_until_promoted(self):
        job_id = sources.import_records([{
            "source": "zhiye", "source_id": "j1", "title": "数据产品经理", "company": "虚构科技",
            "location": "上海", "description": "负责数据产品。", "url": "https://example.com/j/1",
        }])["job_ids"][0]
        added = signals.add(target_type="job", target_id=job_id, feedback_type="not_interested",
                            reason="常驻出差")
        self.assertEqual(added["scope"], "this_case")
        self.assertTrue(assertions.list_assertions(assertion_type="constraint") == [])
        with self.assertRaises(ValueError):
            signals.promote(added["id"])
        promoted = signals.promote(added["id"], human_confirmed=True)
        constraints = assertions.list_assertions(assertion_type="constraint")
        self.assertEqual(len(constraints), 1)
        self.assertEqual(constraints[0]["epistemic_status"], "user_stated")
        self.assertEqual(constraints[0]["id"], promoted["assertion_id"])
        with self.assertRaises(ValueError):
            signals.promote(added["id"])

    def test_signal_must_point_at_a_stored_object(self):
        with self.assertRaises(NotFoundError):
            signals.add(target_type="job", target_id=999999, feedback_type="not_interested",
                        reason="不存在的岗位")

    # -- opportunity pipeline ---------------------------------------------
    def test_shortlist_without_resume_or_application(self):
        job_id = sources.import_records([{
            "source": "zhiye", "source_id": "j2", "title": "运营分析师", "company": "虚构科技",
            "description": "分析。", "url": "https://example.com/j/2",
        }])["job_ids"][0]
        self.assertEqual(pipeline.ensure(job_id)["discovery_status"], "discovered")
        pipeline.update(job_id, status="shortlisted", reason="方向契合")
        card = pipeline.show(job_id)
        self.assertEqual(card["pipeline"]["discovery_status"], "shortlisted")
        self.assertEqual(card["current_stage"], "discovery:shortlisted")
        self.assertEqual(card["applications"], [])
        self.assertEqual(pipeline.counts(), {"shortlisted": 1})
        with self.assertRaises(ValueError):
            pipeline.update(job_id, status="discovered", reason="跨越式回退")

    def test_pipeline_list_hides_discarded_by_default(self):
        job_ids = sources.import_records([
            {"source": "official", "source_id": "k1", "title": "控制算法实习生", "company": "Momenta",
             "location": "苏州", "description": "控制算法。", "url": "https://example.com/j/k1"},
            {"source": "official", "source_id": "k2", "title": "产品项目实习生", "company": "Momenta",
             "location": "苏州", "description": "项目管理。", "url": "https://example.com/j/k2"},
        ])["job_ids"]
        pipeline.ensure(job_ids[0])
        pipeline.ensure(job_ids[1])
        pipeline.update(job_ids[0], status="discarded", reason="专业门槛：仅计算机相关专业")
        active = pipeline.list_pipeline()
        self.assertEqual([row["job_id"] for row in active], [job_ids[1]])
        everything = pipeline.list_pipeline(include_discarded=True)
        self.assertEqual(len(everything), 2)

    def test_application_transition_is_an_immutable_event(self):
        s.save_profile({"display_name": "虚构候选人"})
        experience_id = s.add_object("experiences", {
            "event": "数据报表项目", "actions": ["用 Python 生成周报"], "outcomes": ["按时交付"],
            "evidence": [{"claim": "用 Python 生成周报", "source": "自述", "status": "user_confirmed"}],
            "approved_for_resume": True,
        }, ["event", "actions", "outcomes", "evidence", "approved_for_resume"])
        job_id = sources.import_records([{
            "source": "zhiye", "source_id": "j3", "title": "数据分析师", "company": "虚构科技",
            "description": "分析。", "url": "https://example.com/j/3",
        }])["job_ids"][0]
        resume = s.build_resume(job_id, [experience_id])
        application_id = s.prepare_application(job_id, resume["id"])
        with self.assertRaises(ValueError):
            s.update_application(application_id, "SUBMITTED")
        s.update_application(application_id, "SUBMITTED", human_confirmed=True)
        with connect() as conn:
            events = [dict(row) for row in conn.execute(
                "SELECT from_status,to_status,human_confirmed FROM application_events "
                "WHERE application_id=? ORDER BY id", (application_id,))]
        self.assertEqual(events[-1]["from_status"], "READY_FOR_USER")
        self.assertEqual(events[-1]["to_status"], "SUBMITTED")
        self.assertEqual(events[-1]["human_confirmed"], 1)

    # -- actions -----------------------------------------------------------
    def test_action_completion_needs_evidence_or_user(self):
        created = actions.propose(title="确认岗位是否仍在招", source_type="core", action_type="confirm",
                                  priority=2, suggestion_reason="岗位可能已关闭",
                                  requires_approval=True)
        with self.assertRaises(ValueError):
            actions.complete(created["id"])
        with self.assertRaises(ValueError):
            actions.complete(created["id"], evidence="看过了")
        actions.complete(created["id"], human_confirmed=True)
        self.assertEqual(actions.get(created["id"])["status"], "done")

    def test_ranking_is_explainable_and_ordered(self):
        soon = actions.propose(title="回复面试邀约", source_type="interview", action_type="follow_up",
                               due_at="2026-10-19T12:00:00+08:00", priority=2,
                               suggestion_reason="面试官要求 24 小时内确认")
        later = actions.propose(title="看一门课程", source_type="learning", action_type="learn",
                                priority=4, suggestion_reason="长期能力建设")
        listed = actions.list_actions()
        self.assertEqual([row["id"] for row in listed["ranked"]], [soon["id"], later["id"]])
        for row in listed["ranked"]:
            self.assertIn("urgency", row["factors"])
            self.assertTrue(row["why"])

    def test_goal_links_job_and_action_ranking(self):
        goal = goals.add(title="半年内转数据产品", priority=1, status="active")
        job_id = sources.import_records([{
            "source": "zhiye", "source_id": "j7", "title": "数据产品经理", "company": "虚构科技",
            "description": "负责数据产品。", "url": "https://example.com/j/7",
        }])["job_ids"][0]
        pipeline.ensure(job_id, status="shortlisted", goal_id=goal["id"])
        linked = actions.propose(title="补一份需求文档", source_type="job", source_id=job_id,
                                 action_type="prepare", priority=4, suggestion_reason="目标缺口")
        control = actions.propose(title="随便看看", source_type="core", action_type="other",
                                  priority=4, suggestion_reason="对照")
        ranked = {row["id"]: row for row in actions.list_actions()["ranked"]}
        self.assertEqual(ranked[linked["id"]]["factors"]["goal_priority"], 15)
        self.assertIn("服务目标", ranked[linked["id"]]["why"])
        self.assertGreater(ranked[linked["id"]]["score"], ranked[control["id"]]["score"])
        self.assertEqual(pipeline.show(job_id)["goal"]["title"], "半年内转数据产品")
        self.assertEqual(context.brief()["where_i_am_now"]["active"][0]["goal"], "半年内转数据产品")

    def test_effort_lowers_ranking_of_expensive_work(self):
        quick = actions.propose(title="改一版简历标题", source_type="core", action_type="prepare",
                                priority=3, suggestion_reason="低成本", effort_hours=1)
        heavy = actions.propose(title="从零做一个作品集", source_type="core", action_type="prepare",
                                priority=3, suggestion_reason="高成本", effort_hours=20)
        ranked = {row["id"]: row for row in actions.list_actions()["ranked"]}
        self.assertGreater(ranked[quick["id"]]["score"], ranked[heavy["id"]]["score"])
        self.assertIn("预计投入 1 小时", ranked[quick["id"]]["why"])

    def test_cancelled_prerequisite_keeps_successor_waiting(self):
        prerequisite = actions.propose(title="前置确认", source_type="goal", action_type="confirm",
                                       priority=1, suggestion_reason="前置")
        follow = actions.propose(title="后续准备", source_type="goal", action_type="prepare",
                                 priority=1, suggestion_reason="依赖前置",
                                 depends_on=[prerequisite["id"]])
        with connect() as conn:
            conn.execute("UPDATE next_actions SET status='cancelled' WHERE id=?", (prerequisite["id"],))
        listed = actions.list_actions()
        self.assertNotIn(follow["id"], [row["id"] for row in listed["ranked"]])
        waiting = {row["id"]: row for row in listed["waiting"]}
        self.assertIn(follow["id"], waiting)
        self.assertIn("已取消", waiting[follow["id"]]["why"])

    def test_blocked_action_cannot_be_completed(self):
        created = actions.propose(title="等导师回复", source_type="goal", action_type="prepare",
                                  priority=2, suggestion_reason="需要推荐信")
        actions.block(created["id"], "等导师回复")
        with self.assertRaises(ValueError):
            actions.complete(created["id"], human_confirmed=True)

    # -- context -----------------------------------------------------------
    def test_brief_is_bounded_and_traceable(self):
        for index in range(20):
            assertions.propose(
                subject=f"skill:tool{index}", predicate="has_skill",
                value={"skill": f"工具{index}"}, assertion_type="skill_hypothesis",
                source_type="user_message", confidence="high")
        brief = context.brief(max_chars=2000)
        rendered = json.dumps(brief, ensure_ascii=False)
        self.assertLessEqual(len(rendered), 2400)
        for section in ("who_am_i", "who_could_i_become", "where_i_am_now", "what_next", "why"):
            self.assertIn(section, brief)
        for item in brief["who_am_i"]["strengths"]:
            self.assertIn("assertion_id", item)
            self.assertIn("status", item)
        self.assertFalse(brief["context_budget"]["complete"])

    def test_retraction_disappears_from_brief(self):
        claim = assertions.propose(
            subject="work_conditions", predicate="hard_constraint",
            value={"text": "不接受外包岗位"}, assertion_type="constraint",
            source_type="user_message")
        assertions.confirm(claim["id"])
        self.assertEqual(len(context.brief()["who_am_i"]["constraints"]), 1)
        assertions.retract(claim["id"], "用户改主意了")
        self.assertEqual(context.brief()["who_am_i"]["constraints"], [])

    def test_why_exposes_basis_and_trajectory(self):
        job_id = sources.import_records([{
            "source": "zhiye", "source_id": "j4", "title": "数据产品经理", "company": "虚构科技",
            "description": "负责数据产品。", "url": "https://example.com/j/4",
        }])["job_ids"][0]
        claim = assertions.propose(
            subject="career:data-pm", predicate="direction_hypothesis",
            value={"direction": "数据产品经理"}, assertion_type="career_hypothesis",
            source_type="model_inference", explanation="经历中的产品协作",
            links=[{"ref_type": "job", "ref_id": job_id, "relation": "about"}])
        assertions.revise(claim["id"], value={"direction": "数据运营"}, reason="缩小方向")
        explanation = context.why(claim["id"])
        self.assertEqual(explanation["status"], "inferred")
        self.assertTrue(explanation["changed"])
        self.assertEqual(len(explanation["trajectory"]), 2)
        self.assertTrue(any(item["relation"] == "about" for item in explanation["basis"]))

    # -- operations --------------------------------------------------------
    def test_migrations_are_idempotent(self):
        with connect() as conn:
            first = migrations.apply(conn, Path(os.environ["CAREEROS_DB"]))
            second = migrations.apply(conn, Path(os.environ["CAREEROS_DB"]))
            self.assertEqual(second["applied"], [])
            self.assertGreaterEqual(migrations.current_version(conn), 2)
        self.assertEqual(first["to"], max(m["version"] for m in migrations.MIGRATIONS))

    def test_fresh_database_creates_no_backup(self):
        # A brand-new empty database has nothing worth restoring.
        with connect() as conn:
            migrations.apply(conn, Path(os.environ["CAREEROS_DB"]))
        backups = list(self.root.glob("db.sqlite3.bak-*"))
        self.assertEqual(backups, [])

    def test_existing_data_is_backed_up_before_upgrade(self):
        with connect() as conn:
            conn.execute("INSERT INTO profile(id,data,updated_at) VALUES (1,?,?)",
                         ('{"display_name":"虚构候选人"}', "2026-10-01T00:00:00+00:00"))
        # Simulate a v0.1 database that never recorded its baseline; the next
        # connection must back the file up before applying v2.
        with connect() as conn:
            conn.execute("DELETE FROM schema_migrations")
        with connect() as conn:
            self.assertGreaterEqual(migrations.current_version(conn), 2)
        backups = list(self.root.glob("db.sqlite3.bak-*"))
        self.assertEqual(len(backups), 1)

    def test_tiny_budget_is_reported_honestly(self):
        brief = context.brief(max_chars=300)
        self.assertTrue(brief["context_budget"]["over_budget"])
        self.assertFalse(brief["context_budget"]["complete"])
        for section in ("who_am_i", "who_could_i_become", "where_i_am_now", "what_next", "why"):
            self.assertIn(section, brief)

    def test_legacy_sync_is_repeatable(self):
        with connect() as conn:
            conn.execute("INSERT INTO profile(id,data,updated_at) VALUES (1,?,?)",
                         (json.dumps({"display_name": "虚构候选人",
                                      "values": ["自主性"], "hard_constraints": ["不接受长期出差"]},
                                     ensure_ascii=False), "2026-10-01T00:00:00+00:00"))
            conn.execute("INSERT INTO career_directions(data,created_at) VALUES (?,?)",
                         (json.dumps({"title": "数据产品经理", "rationale": "接口人角色",
                                      "supporting_experience_ids": [], "gaps": ["缺少 SQL 作品"]},
                                     ensure_ascii=False), "2026-10-01T00:00:00+00:00"))
        sources.import_records([{
            "source": "zhiye", "source_id": "j5", "title": "数据产品经理", "company": "虚构科技",
            "description": "负责数据产品。", "url": "https://example.com/j/5",
        }])
        first = twin.sync_legacy()
        self.assertEqual(first["pipeline_rows_added"], 1)
        self.assertGreater(first["assertions_created"], 0)
        second = twin.sync_legacy()
        self.assertEqual(second["assertions_created"], 0)
        self.assertEqual(second["pipeline_rows_added"], 0)
        direction = assertions.list_assertions(assertion_type="career_hypothesis")
        self.assertEqual(len(direction), 1)
        self.assertEqual(direction[0]["epistemic_status"], "inferred")

    def test_reflection_only_proposes(self):
        job_id = sources.import_records([{
            "source": "zhiye", "source_id": "j6", "title": "运营专员", "company": "虚构科技",
            "description": "运营。", "url": "https://example.com/j/6",
        }])["job_ids"][0]
        for _ in range(2):
            signals.add(target_type="job", target_id=job_id, feedback_type="not_interested",
                        reason="通勤时间太长")
        run = reflection.weekly()
        kinds = {proposal["kind"] for proposal in run["proposals"]}
        self.assertIn("promote_constraint", kinds)
        self.assertFalse(run["applied"])
        self.assertEqual(assertions.list_assertions(assertion_type="constraint"), [])
        self.assertEqual(reflection.list_runs()[0]["id"], run["run_id"])

    def test_reflection_decision_keeps_per_item_detail(self):
        job_id = sources.import_records([{
            "source": "zhiye", "source_id": "j8", "title": "运营专员", "company": "虚构科技",
            "description": "运营。", "url": "https://example.com/j/8",
        }])["job_ids"][0]
        for reason in ("通勤时间太长", "常驻出差"):
            for _ in range(2):
                signals.add(target_type="job", target_id=job_id, feedback_type="not_interested",
                            reason=reason)
        run = reflection.weekly()
        self.assertEqual(len(run["proposals"]), 2)
        decided = reflection.decide(run["run_id"], status="approved", accepted=[0])
        self.assertEqual(decided["status"], "partially_approved")
        stored = reflection.list_runs()[0]
        self.assertEqual(stored["approved_updates"]["accepted"], [0])
        self.assertEqual(len(stored["approved_updates"]["items"]), 1)

    def test_status_reports_health(self):
        status = twin.status()
        self.assertEqual(status["schema_version"], 4)
        self.assertIn("jobs_without_pipeline", status["health"])


if __name__ == "__main__":
    unittest.main()
