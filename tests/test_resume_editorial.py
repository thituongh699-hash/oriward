import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oriward import services as s, resume_content, resume_editorial as editorial, experience_library


class EditorialTests(unittest.TestCase):
    def test_readback_review_and_new_version_do_not_claim_automatic_review(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "ORIWARD_DB": str(Path(folder) / "fixture.sqlite3"),
            "ORIWARD_OUTPUT_DIR": str(Path(folder) / "resumes"),
        }):
            s.save_profile({"display_name": "虚构候选人"})
            eid = s.add_object("experiences", {"event": "反馈整理", "actions": ["整理用户反馈"]}, ["event"])
            other = s.add_object("experiences", {"event": "大学兼职", "actions": ["布置会场"]}, ["event"])
            data = {"reason": "说明产品反馈经验", "sections": [{"experience_id": eid,
                    "bullets": ["整理用户反馈，归纳需要改进的交互问题"]}]}
            first = resume_content.compose(None, data)
            packet = editorial.packet(first["id"])
            self.assertIn("归纳需要改进", packet["content"])
            self.assertEqual([item["id"] for item in packet["selected_sources"]], [eid])
            self.assertIn(other, [item["id"] for item in packet["timeline"] if not item["selected"]])
            self.assertIsNone(packet["latest_editorial_review"])
            review = {"resume_id": first["id"], "verdict": "ready", "findings": [],
                      "checked": {key: True for key in editorial.CHECKS}}
            review["checked"]["factuality"] = False
            with self.assertRaises(s.ValidationError):
                editorial.save_review(review)
            review["checked"]["factuality"] = True
            self.assertTrue(editorial.save_review(review)["recorded"])
            self.assertTrue(editorial.packet(first["id"])["latest_editorial_review"]["current"])
            Path(first["path"]).write_text("Changed outside review", encoding="utf-8")
            self.assertFalse(editorial.packet(first["id"])["latest_editorial_review"]["current"])
            second = resume_content.compose(None, data)
            self.assertIsNone(editorial.packet(second["id"])["latest_editorial_review"])
            review["resume_id"] = second["id"]
            editorial.save_review(review)
            s.save_profile({"display_name": "虚构候选人", "education": "示例大学新专业"})
            self.assertFalse(editorial.packet(second["id"])["latest_editorial_review"]["current"])
            experience_library.revise(eid, {"actions": ["仅旁听反馈会议"]}, reason="纠正个人贡献")
            self.assertTrue(editorial.packet(second["id"])["source_validity"]["needs_review"])
            with self.assertRaises(s.ValidationError):
                editorial.save_review(review)


if __name__ == "__main__":
    unittest.main()
