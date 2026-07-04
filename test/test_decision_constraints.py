import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from persona.cognitive_modules.decision_constraints import (
    build_retry_feedback,
    build_invalid_targets,
    filter_invalid_resources,
    validate_decision_target,
)


class InvalidTargetTests(unittest.TestCase):
    """Covers recent failed target blacklist construction."""

    def test_build_invalid_targets_from_recent_navigation_failure(self):
        scratch = type("Scratch", (), {
            "get_recent_navigation_failure": lambda self, max_age_steps=6: {
                "target": "apple tree",
                "target_address": "the Ville:Johnson Park:park:apple tree",
                "reason": "path_not_found",
            }
        })()

        invalid_targets = build_invalid_targets(scratch)

        self.assertEqual(invalid_targets, ["apple tree"])

    def test_filter_invalid_resources_removes_recent_failed_target(self):
        resources = ["apple tree", "refrigerator", "behind the cafe counter"]

        filtered = filter_invalid_resources(resources, ["apple tree"])

        self.assertEqual(filtered, ["refrigerator", "behind the cafe counter"])

    def test_validate_decision_target_requests_retry_for_invalid_target(self):
        decision = {"action": "Gather", "target": "apple tree", "detail": "picking apples"}

        should_retry, reason = validate_decision_target(decision, ["apple tree"])

        self.assertTrue(should_retry)
        self.assertIn("invalid for this step", reason)

    def test_build_retry_feedback_tells_model_to_choose_different_plan(self):
        feedback = build_retry_feedback("The target apple tree is invalid for this step.")

        self.assertIn("Choose another feasible immediate target", feedback)


if __name__ == "__main__":
    unittest.main()
