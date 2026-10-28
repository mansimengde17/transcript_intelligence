import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "pipeline.py"
SPEC = importlib.util.spec_from_file_location("pipeline", MODULE_PATH)
pipeline = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(pipeline)


class PipelineTests(unittest.TestCase):
    def test_internal_call_classification(self):
        value, reason = pipeline.classify_call_type(
            "Engineering standup", ["a@aegiscloud.com", "b@aegiscloud.com"]
        )
        self.assertEqual(value, "Internal")
        self.assertIn("internal", reason.lower())

    def test_support_call_classification(self):
        value, _ = pipeline.classify_call_type(
            "Support Case #123 - SSO failure", ["a@aegiscloud.com", "c@customer.com"]
        )
        self.assertEqual(value, "Support")

    def test_external_call_classification(self):
        value, _ = pipeline.classify_call_type(
            "Quarterly business review", ["a@aegiscloud.com", "c@customer.com"]
        )
        self.assertEqual(value, "External")

    def test_theme_scoring_is_auditable(self):
        scored = pipeline.score_themes("renewal discussion after platform outage and sla breach")
        names = [row[0] for row in scored]
        self.assertIn("Reliability & incidents", names)
        self.assertIn("Commercial & renewal", names)
        reliability = next(row for row in scored if row[0] == "Reliability & incidents")
        self.assertIn("outage", reliability[2])


if __name__ == "__main__":
    unittest.main()
