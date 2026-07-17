import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from persona.cognitive_modules.structured_action_intent import (
    compile_action_intent,
    normalize_action_intent_contract,
    validate_action_intent_shape,
)


class StructuredActionIntentTests(unittest.TestCase):
    def setUp(self):
        klaus = SimpleNamespace(name="Klaus Mueller")
        self.personas = {klaus.name: klaus}

    def test_named_person_socialize_compiles_to_seek_and_chat(self):
        result = compile_action_intent(
            {
                "action": "Socialize",
                "target": "Klaus Mueller",
                "target_type": "persona",
                "mode": "conversation",
                "topic": "town news",
                "detail": "talking with Klaus",
            },
            personas=self.personas,
        )

        self.assertEqual(result["target_type"], "persona")
        self.assertEqual(result["compiled_skill_id"], "seek_and_chat")
        self.assertEqual(result["topic"], "town news")

    def test_park_cannot_compile_to_person_chat(self):
        result = compile_action_intent(
            {
                "action": "Socialize",
                "target": "park",
                "target_type": "persona",
                "mode": "conversation",
                "detail": "going to the park to relax around other people",
            },
            personas=self.personas,
        )

        self.assertEqual(result["target_type"], "location")
        self.assertEqual(result["compiled_skill_id"], "wander")
        self.assertIn("target_type:persona->location", result["contract_corrections"])

    def test_pub_socialize_compiles_to_venue_hangout(self):
        result = compile_action_intent(
            {
                "action": "Socialize",
                "target": "pub",
                "target_type": "location",
                "mode": "social_venue",
                "detail": "spending time around the pub patrons",
            },
            personas=self.personas,
        )

        self.assertEqual(result["compiled_skill_id"], "hangout_social_venue")

    def test_person_only_action_with_place_target_fails_safe_locally(self):
        result = compile_action_intent(
            {
                "action": "Request",
                "target": "park",
                "target_type": "location",
                "mode": "request",
                "detail": "requesting help from the park",
            },
            personas=self.personas,
        )

        self.assertEqual(result["compiled_skill_id"], "idle")
        self.assertIn("request_requires_persona", result["contract_corrections"])

    def test_legacy_joint_decision_remains_compilable(self):
        result = compile_action_intent(
            {
                "action": "Gather",
                "target": "refrigerator",
                "detail": "opening the refrigerator",
            },
            personas=self.personas,
        )

        self.assertEqual(result["compiled_skill_id"], "gather")
        self.assertEqual(result["schema_version"], 2)

    def test_typed_contract_rejects_unknown_target_type_and_mode(self):
        valid, errors = validate_action_intent_shape(
            {
                "thought": "I should do something.",
                "schema_version": 2,
                "action": "Idle",
                "target": "none",
                "target_type": "building",
                "mode": "improvise",
                "topic": "",
                "detail": "idling",
                "duration": 10,
                "reasoning": "No immediate need.",
            }
        )

        self.assertFalse(valid)
        self.assertIn("invalid_target_type", errors)
        self.assertIn("invalid_mode", errors)

    def test_underscore_modes_are_valid(self):
        for mode in ("seek_conversation", "social_venue", "solo_leisure"):
            with self.subTest(mode=mode):
                valid, errors = validate_action_intent_shape(
                    {
                        "thought": "I should relax nearby.",
                        "schema_version": 2,
                        "action": "Recreate",
                        "target": "common room sofa",
                        "target_type": "object",
                        "mode": mode,
                        "topic": "",
                        "detail": "relaxing nearby",
                        "duration": 30,
                        "reasoning": "Mood is low.",
                    }
                )
                self.assertTrue(valid, errors)

    def test_contract_normalizes_mode_aliases(self):
        cases = {
            "chat": "conversation",
            "chat with": "conversation",
            "request_resource": "request",
            "ask_for_help": "request",
            "social venue": "social_venue",
            "leisure_use": "solo_leisure",
        }
        for raw_mode, expected in cases.items():
            with self.subTest(raw_mode=raw_mode):
                result = normalize_action_intent_contract(
                    {"action": "Socialize", "target_type": "persona", "mode": raw_mode, "duration": 10}
                )
                self.assertEqual(result["mode"], expected)

    def test_none_mode_is_inferred_from_action(self):
        result = normalize_action_intent_contract(
            {
                "action": "Gather",
                "target": "apple tree",
                "target_type": "object",
                "mode": "none",
                "detail": "gathering apples",
                "duration": 10,
            }
        )

        self.assertEqual(result["mode"], "gather")

    def test_short_consume_and_request_duration_is_valid(self):
        for action, mode in (("Consume", "consume"), ("Request", "request")):
            with self.subTest(action=action):
                valid, errors = validate_action_intent_shape(
                    {
                        "thought": "I should act now.",
                        "schema_version": 2,
                        "action": action,
                        "target": "apple" if action == "Consume" else "Klaus Mueller",
                        "target_type": "inventory_item" if action == "Consume" else "persona",
                        "mode": mode,
                        "topic": "" if action == "Consume" else "food access",
                        "detail": "handling the immediate need",
                        "duration": 5,
                        "reasoning": "This is urgent.",
                    }
                )
                self.assertTrue(valid, errors)

    def test_inventory_item_target_type_is_preserved(self):
        result = normalize_action_intent_contract(
            {"action": "Consume", "target_type": "inventory_item", "mode": "consume", "duration": 5}
        )

        self.assertEqual(result["target_type"], "inventory_item")

    def test_non_short_duration_is_clamped_locally(self):
        result = normalize_action_intent_contract(
            {"action": "Recreate", "target_type": "object", "mode": "social_venue", "duration": 5}
        )

        self.assertEqual(result["duration"], 10)

    def test_all_model_facing_action_categories_compile_to_runtime_skills(self):
        cases = {
            "Consume": ("apple", "inventory_item", "consume", "consume"),
            "Gather": ("apple tree", "object", "gather", "gather"),
            "Rest": ("bed", "object", "rest", "rest"),
            "Treat": ("bandage", "inventory_item", "treat", "bandage"),
            "Work": ("desk", "object", "work", "work"),
            "Socialize": ("Klaus Mueller", "persona", "conversation", "seek_and_chat"),
            "Request": ("Klaus Mueller", "persona", "request", "request"),
            "Trade": ("Klaus Mueller", "persona", "trade", "trade"),
            "Coordinate": ("Klaus Mueller", "persona", "coordinate", "coordinate"),
            "Pressure": ("Klaus Mueller", "persona", "pressure", "pressure"),
            "Avoid": ("Klaus Mueller", "persona", "avoid", "avoid"),
            "Give": ("Klaus Mueller", "persona", "give", "give"),
            "Rob": ("Klaus Mueller", "persona", "rob", "rob"),
            "Recreate": ("game console", "object", "solo_leisure", "leisure_use"),
            "Idle": ("none", "none", "idle", "idle"),
        }
        for action, (target, target_type, mode, expected_skill) in cases.items():
            with self.subTest(action=action):
                result = compile_action_intent(
                    {
                        "action": action,
                        "target": target,
                        "target_type": target_type,
                        "mode": mode,
                        "detail": f"performing {action.lower()}",
                    },
                    personas=self.personas,
                    inventory={"apple": 1, "bandage": 1},
                )
                self.assertEqual(result["compiled_skill_id"], expected_skill)


if __name__ == "__main__":
    unittest.main()
