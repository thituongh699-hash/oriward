import unittest

from oriward.core.workflow_map import map_workflows


class WorkflowMapTests(unittest.TestCase):
    def test_five_modules_connect_across_three_layers(self):
        result = map_workflows()
        layers = {item["id"] for item in result["layers"]}
        modules = {item["id"]: item for item in result["modules"]}
        self.assertEqual(layers, {"long_term", "mid_term", "short_term"})
        self.assertEqual(len(modules), 5)
        for module in modules.values():
            self.assertIn(module["primary_layer"], layers)
            self.assertTrue(module["reads"] and module["writes"] and module["entry"])
            self.assertTrue(set(module["feeds"]) <= modules.keys())
        self.assertIn("experience_id", modules["resume_creation"]["reads"])
        self.assertIn("resume_id", modules["job_search_application"]["reads"])
        self.assertIn("experience_discovery", modules["personal_growth"]["feeds"])

    def test_default_journey_places_market_analysis_before_resume(self):
        result = map_workflows()
        self.assertEqual([step["skill"] for step in result["default_journey"]], [
            "career-discovery", "career-mapping", "job-search", "job-analysis",
            "resume-builder", "interview-coach", "document-export", "application-assistant"])
        self.assertIn("显式任务", result["routing"])
