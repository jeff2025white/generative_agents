import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from persona.cognitive_modules.decision_constraints import (
    build_retry_feedback,
    build_invalid_targets,
    filter_invalid_resources,
    validate_decision,
    validate_decision_target,
)
from persona.cognitive_modules.action_target_resolver import (
    rank_candidate_addresses_by_experience,
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

    def test_build_invalid_targets_ignores_empty_resource_results(self):
        scratch = type("Scratch", (), {
            "get_recent_navigation_failure": lambda self, max_age_steps=6: {
                "target": "refrigerator",
                "target_address": "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
                "reason": "resource_empty",
            }
        })()

        invalid_targets = build_invalid_targets(scratch)

        self.assertEqual(invalid_targets, [])

    def test_build_invalid_targets_from_failed_resource_instances(self):
        scratch = type("Scratch", (), {
            "curr_step": 12,
            "failed_resource_instances": [
                {
                    "target": "apple tree",
                    "target_address": "the Ville:Johnson Park:park:apple tree",
                    "reason": "path_not_found",
                    "curr_step": 10,
                    "expires_after_step": 16,
                }
            ],
            "get_recent_navigation_failure": lambda self, max_age_steps=6: None,
        })()

        invalid_targets = build_invalid_targets(scratch)

        self.assertEqual(invalid_targets, ["apple tree"])

    def test_filter_invalid_resources_removes_recent_failed_target(self):
        resources = ["apple tree", "refrigerator", "behind the cafe counter"]

        filtered = filter_invalid_resources(resources, ["apple tree"])

        self.assertEqual(filtered, ["refrigerator", "behind the cafe counter"])

    def test_filter_invalid_resources_removes_normalized_resource_labels(self):
        resources = [
            "refrigerator (idle/normal; stock: empty)",
            "apple tree (idle/normal; stock: infinite)",
            "behind the cafe counter (idle/normal; stock: empty)",
        ]

        filtered = filter_invalid_resources(resources, ["refrigerator", "cafe counter"])

        self.assertEqual(filtered, ["apple tree (idle/normal; stock: infinite)"])

    def test_validate_decision_target_requests_retry_for_invalid_target(self):
        decision = {"action": "Gather", "target": "apple tree", "detail": "picking apples"}

        should_retry, reason = validate_decision_target(decision, ["apple tree"])

        self.assertTrue(should_retry)
        self.assertIn("invalid for this step", reason)

    def test_build_retry_feedback_returns_evidence_without_selecting_replacement(self):
        feedback = build_retry_feedback({
            "valid": False,
            "reason_code": "resource_empty",
            "message": "The apple tree is empty.",
            "evidence": {"selected_target": "apple tree", "stock": "empty"},
        })

        self.assertIn("VALIDATION_FEEDBACK", feedback)
        self.assertIn('"reason_code": "resource_empty"', feedback)
        self.assertIn('"stock": "empty"', feedback)
        self.assertIn("will not choose an action or target for you", feedback)
        self.assertNotIn("refrigerator", feedback)
        self.assertNotIn("idle", feedback.lower())

    def test_validate_consume_rejects_missing_inventory_without_replacement(self):
        validation = validate_decision(
            {"action": "Consume", "target": "apple"},
            inventory={},
            object_states=["apple tree (idle/normal; stock: infinite)"],
        )

        self.assertFalse(validation["valid"])
        self.assertEqual(validation["reason_code"], "inventory_missing")
        self.assertEqual(validation["evidence"]["inventory"], {})
        self.assertNotIn("recommended_action", validation)

    def test_validate_gather_rejects_observed_empty_resource(self):
        validation = validate_decision(
            {"action": "Gather", "target": "refrigerator"},
            inventory={},
            object_states=["refrigerator (idle/normal; stock: empty)"],
        )

        self.assertFalse(validation["valid"])
        self.assertEqual(validation["reason_code"], "resource_empty")
        self.assertIn("stock: empty", validation["evidence"]["observed_resource_state"])

    def test_validate_request_reports_empty_target_inventory_without_alternative(self):
        helper = type("Persona", (), {
            "name": "Isabella Rodriguez",
            "scratch": type("Scratch", (), {"inventory": {}})(),
        })()

        validation = validate_decision(
            {"action": "Request", "target": "Isabella Rodriguez"},
            persona_name="Klaus Mueller",
            known_personas={"Isabella Rodriguez": helper},
        )

        self.assertFalse(validation["valid"])
        self.assertEqual(validation["reason_code"], "target_inventory_empty")
        self.assertEqual(validation["evidence"]["target_inventory"], {})
        self.assertNotIn("recommended_target", validation)

    def test_rank_candidate_addresses_by_experience_demotes_recent_empty_instance(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                get_experience_priority_units=lambda intent_family=None: [
                    {
                        "experience_kind": "avoid",
                        "intent_family": "restore_satiety",
                        "resource_instance_key": "the ville:hobbs cafe:cafe:refrigerator",
                        "resource_type": "refrigerator",
                        "recommendation": "avoid_this_instance",
                        "confidence": 0.9,
                    },
                    {
                        "experience_kind": "prefer",
                        "intent_family": "restore_satiety",
                        "resource_instance_key": "the ville:johnson park:park:apple tree",
                        "resource_type": "apple tree",
                        "recommendation": "prefer_this_instance",
                        "confidence": 0.8,
                    },
                ]
            )
        )

        ranked = rank_candidate_addresses_by_experience(
            persona,
            [
                "the Ville:Hobbs Cafe:cafe:refrigerator",
                "the Ville:Johnson Park:park:apple tree",
            ],
            intent_family="restore_satiety",
            target="refrigerator",
        )

        self.assertEqual(ranked[0], "the Ville:Johnson Park:park:apple tree")
        self.assertEqual(ranked[-1], "the Ville:Hobbs Cafe:cafe:refrigerator")


if __name__ == "__main__":
    unittest.main()
