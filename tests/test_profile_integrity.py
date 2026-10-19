import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from careeros import services
from careeros.core import assertions, twin, context
from careeros.core.profile import read_profile
from careeros.db import connect


class ProfileIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"CAREEROS_DB": str(Path(self.tmp.name) / "db.sqlite3")})
        env.start()
        self.addCleanup(env.stop)

    def _legacy_profile(self, **data):
        with connect() as conn:
            conn.execute("INSERT INTO profile(id,data,updated_at) VALUES (1,?,?) "
                         "ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at",
                         (json.dumps(data, ensure_ascii=False), "2026-10-18T00:00:00+00:00"))

    def _claims(self, predicate):
        with connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM user_assertions WHERE subject='user' AND predicate=? ORDER BY id",
                (predicate,))]

    def test_sync_does_not_resurrect_revised_or_retracted_legacy_claims(self):
        for action in ("revise", "retract"):
            with self.subTest(action=action):
                with patch.dict(os.environ, {"CAREEROS_DB": str(Path(self.tmp.name) / f"{action}.sqlite3")}):
                    self._legacy_profile(values=["自主性"])
                    twin.sync_legacy()
                    claim = self._claims("value")[0]
                    if action == "revise":
                        assertions.revise(claim["id"], value={"text": "稳定性"}, reason="用户修正")
                    else:
                        assertions.retract(claim["id"], "用户撤回")
                    result = twin.sync_legacy()
                    self.assertEqual(result["assertions_created"], 0)
                    rows = self._claims("value")
                    self.assertEqual(len(rows), 2 if action == "revise" else 1)

    def test_profile_projection_uses_latest_user_backed_identity(self):
        self._legacy_profile(display_name="过期姓名", location="杭州", target_role="旧岗位")
        self.assertEqual(services.get_profile()["display_name"], "过期姓名")
        twin.sync_legacy()
        name = self._claims("display_name")[0]
        assertions.revise(name["id"], value={"text": "新姓名"}, reason="更新姓名")
        with connect() as conn:
            self.assertEqual(read_profile(conn)["display_name"], "新姓名")
        location = self._claims("location")[0]
        assertions.retract(location["id"], "不再提供")
        projected = services.get_profile()
        self.assertNotIn("location", projected)
        self.assertEqual(projected["target_role"], "旧岗位")

    def test_save_profile_versions_identity_and_preserves_omitted_lists(self):
        services.save_profile({"display_name": "候选人", "values": ["自主性"]})
        first = self._claims("display_name")[0]
        services.save_profile({"display_name": "新姓名"})
        second = self._claims("display_name")[-1]
        self.assertEqual(second["supersedes_id"], first["id"])
        profile = services.get_profile()
        self.assertEqual(profile["display_name"], "新姓名")
        self.assertEqual(profile["values"], ["自主性"])

    def test_save_profile_does_not_resurrect_retracted_identical_identity(self):
        services.save_profile({"display_name": "候选人"})
        name = self._claims("display_name")[0]
        assertions.retract(name["id"], "不再使用")
        with self.assertRaises(services.ValidationError):
            services.save_profile({"display_name": "候选人"})

    def test_late_profile_validation_failure_rolls_back_claims_and_cache(self):
        services.save_profile({"display_name": "候选人"})
        before = assertions.list_assertions(live_only=False)
        with self.assertRaises(services.ValidationError):
            services.save_profile({"display_name": "更新姓名", "values": ["新增价值观"], "contact": {}})
        self.assertEqual(assertions.list_assertions(live_only=False), before)
        self.assertEqual(services.get_profile()["display_name"], "候选人")

    def test_identity_correction_and_retraction_reach_both_profile_and_brief(self):
        services.save_profile({"display_name": "候选人", "location": "上海"})
        location = self._claims("location")[0]
        revised = assertions.revise(location["id"], value={"text": "杭州"}, reason="用户搬家")
        self.assertEqual(services.get_profile()["location"], "杭州")
        self.assertEqual(context.brief(max_chars=20000)["who_am_i"]["identity"]["location"], "杭州")
        with self.assertRaises(services.ValidationError):
            services.save_profile({"display_name": "候选人", "location": "上海"})
        assertions.retract(revised["id"], "不再分享位置")
        self.assertNotIn("location", context.brief(max_chars=20000)["who_am_i"]["identity"])
        twin.sync_legacy()
        self.assertNotIn("location", services.get_profile())

    def test_retracted_direction_does_not_reappear_in_fallback(self):
        services.add_object("career_directions", {"title": "数据运营", "rationale": "待探索",
                            "supporting_experience_ids": [], "gaps": [], "validation_status": "hypothesis"}, ["title"])
        twin.sync_legacy()
        claim = assertions.list_assertions(assertion_type="career_hypothesis")[0]
        assertions.retract(claim["id"], "用户不再探索此方向")
        self.assertEqual(context.brief(max_chars=20000)["who_could_i_become"]["directions"], [])
        self.assertEqual(twin.sync_legacy()["assertions_created"], 0)

    def test_retracted_legacy_experience_inference_is_not_resynced(self):
        services.add_object("experiences", {"event": "测试课程", "actions": [], "outcomes": [], "evidence": [],
                            "approved_for_resume": False, "inferred_skills": [{"name": "Python"}]}, ["event"])
        twin.sync_legacy()
        claim = assertions.list_assertions(assertion_type="skill_hypothesis")[0]
        assertions.retract(claim["id"], "只是兴趣")
        self.assertEqual(twin.sync_legacy()["assertions_created"], 0)


if __name__ == "__main__":
    unittest.main()
