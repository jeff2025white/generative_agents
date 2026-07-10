import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from persona.cognitive_modules.action_outcomes import (
    build_action_outcome_record,
    classify_reason,
    derive_progress_score_breakdown,
    derive_progress_score,
)
from persona.cognitive_modules.memory_effects import record_projected_action_outcome
from persona.memory_structures.scratch import Scratch


class ActionOutcomeRecordTests(unittest.TestCase):
    def _build_persona(self):
        scratch = SimpleNamespace(
            curr_step=161,
            curr_time=None,
            act_address="the Ville:Hobbs Cafe:cafe:refrigerator",
            act_description="opening the refrigerator to gather food items",
            act_command={
                "skill_id": "gather",
                "target": "refrigerator",
                "intent_family": "restore_satiety",
                "raw_action": "Gather",
            },
            inventory={},
            satiety=18.0,
            stamina=62.0,
            health=91.0,
            mood=55.0,
            current_action_record={
                "decision_id": "Isabella_Rodriguez-161-ab12cd34",
                "resolved_target": "refrigerator",
                "resolved_address": "the Ville:Hobbs Cafe:cafe:refrigerator",
                "resolution_kind": "known_object",
            },
        )
        return SimpleNamespace(name="Isabella Rodriguez", scratch=scratch)

    def test_classify_reason_maps_resource_empty(self):
        self.assertEqual(classify_reason("resource_empty"), "resource_state")

    def test_build_action_outcome_record_returns_mvp_fields(self):
        persona = self._build_persona()

        outcome = build_action_outcome_record(
            persona,
            result="failed",
            reason="resource_empty",
            payload={"effective_source": "refrigerator"},
        )

        self.assertEqual(outcome["schema_version"], 1)
        self.assertEqual(outcome["persona"], "Isabella Rodriguez")
        self.assertEqual(outcome["action"]["skill_id"], "gather")
        self.assertEqual(outcome["action"]["target"], "refrigerator")
        self.assertEqual(
            outcome["action"]["target_address"],
            "the Ville:Hobbs Cafe:cafe:refrigerator",
        )
        self.assertEqual(outcome["execution"]["result"], "failed")
        self.assertEqual(outcome["execution"]["reason"], "resource_empty")
        self.assertEqual(outcome["execution"]["reason_class"], "resource_state")
        self.assertEqual(
            outcome["resource_context"]["resource_instance_key"],
            "the ville:hobbs cafe:cafe:refrigerator",
        )

    def test_build_action_outcome_record_promotes_high_value_success_to_memory_projection(self):
        persona = self._build_persona()

        outcome = build_action_outcome_record(
            persona,
            result="success",
            reason=None,
            effects={
                "self_attribute_effects": {
                    "satiety": 12.0,
                    "stamina": 0.0,
                    "health": 0.0,
                    "mood": 1.0,
                },
                "inventory_delta": {"apple": 2},
                "progress_score": 0.8,
            },
        )

        self.assertGreaterEqual(outcome["experience_scoring"]["effective_score"], 0.55)
        self.assertTrue(outcome["experience_scoring"]["should_promote_to_experience"])
        self.assertEqual(outcome["memory_projection"]["object"], "execution_result")
        self.assertIn("gather", outcome["memory_projection"]["keywords"])
        self.assertIn("restore_satiety", outcome["memory_projection"]["keywords"])

    def test_record_action_outcome_builds_instance_avoid_experience(self):
        scratch = Scratch("Isabella Rodriguez")
        scratch.curr_step = 16
        outcome = {
            "persona": "Isabella Rodriguez",
            "curr_step": 16,
            "action": {
                "skill_id": "gather",
                "target": "refrigerator",
                "target_address": "the Ville:Hobbs Cafe:cafe:refrigerator",
                "intent_family": "restore_satiety",
            },
            "execution": {
                "result": "failed",
                "reason": "resource_empty",
                "reason_class": "resource_state",
            },
            "effects": {"progress_score": 0.0},
        }

        scratch.record_action_outcome(outcome)
        units = scratch.get_experience_priority_units(intent_family="restore_satiety")

        self.assertEqual(units[0]["experience_kind"], "avoid")
        self.assertEqual(units[0]["resource_scope"], "instance")
        self.assertEqual(
            units[0]["resource_instance_key"],
            "the ville:hobbs cafe:cafe:refrigerator",
        )
        self.assertEqual(units[0]["recommendation"], "avoid_this_instance")

    def test_record_action_outcome_builds_instance_prefer_experience(self):
        scratch = Scratch("Maria Lopez")
        scratch.curr_step = 117
        outcome = {
            "persona": "Maria Lopez",
            "curr_step": 117,
            "action": {
                "skill_id": "consume",
                "target": "apple",
                "target_address": "the Ville:Johnson Park:park:apple tree",
                "intent_family": "restore_satiety",
            },
            "execution": {
                "result": "success",
                "reason": None,
                "reason_class": "other",
            },
            "effects": {"progress_score": 0.95},
        }

        scratch.record_action_outcome(outcome)
        units = scratch.get_experience_priority_units(intent_family="restore_satiety")

        self.assertEqual(units[0]["experience_kind"], "prefer")
        self.assertEqual(
            units[0]["resource_instance_key"],
            "the ville:johnson park:park:apple tree",
        )
        self.assertEqual(units[0]["recommendation"], "prefer_this_instance")

    def test_derive_progress_score_prefers_direct_recovery_over_small_inventory_gain(self):
        gather_score = derive_progress_score(
            "gather",
            self_attribute_effects={"satiety": 0.0, "stamina": 0.0, "health": 0.0, "mood": 1.0},
            inventory_delta={"apple": 1},
        )
        consume_score = derive_progress_score(
            "consume",
            self_attribute_effects={"satiety": 12.0, "stamina": 0.0, "health": 0.0, "mood": 1.0},
            inventory_delta={"apple": -1},
        )

        self.assertGreater(consume_score, gather_score)
        self.assertGreaterEqual(consume_score, 0.9)

    def test_derive_progress_score_rewards_larger_inventory_gain(self):
        small_gain = derive_progress_score(
            "gather",
            self_attribute_effects={"satiety": 0.0, "stamina": 0.0, "health": 0.0, "mood": 0.0},
            inventory_delta={"apple": 1},
        )
        larger_gain = derive_progress_score(
            "gather",
            self_attribute_effects={"satiety": 0.0, "stamina": 0.0, "health": 0.0, "mood": 1.0},
            inventory_delta={"apple": 2},
        )

        self.assertGreater(larger_gain, small_gain)
        self.assertGreaterEqual(larger_gain, 0.55)

    def test_derive_progress_score_breakdown_exposes_component_scores(self):
        breakdown = derive_progress_score_breakdown(
            "consume",
            self_attribute_effects={"satiety": 12.0, "stamina": 0.0, "health": 5.0, "mood": 3.0},
            inventory_delta={"apple": -1},
        )

        self.assertEqual(breakdown["score"], 0.95)
        self.assertGreater(breakdown["attribute_score"], 0.0)
        self.assertEqual(breakdown["inventory_gain_score"], 0.0)
        self.assertEqual(breakdown["conversion_score"], 0.15)
        self.assertEqual(breakdown["skill_context_bonus"], 0.1)
        self.assertEqual(breakdown["satiety_gain"], 12.0)
        self.assertEqual(breakdown["consumed_inventory_units"], 1.0)

    @patch("persona.cognitive_modules.memory_effects.get_embedding", return_value=[1.0, 0.0])
    def test_record_projected_action_outcome_persists_promoted_memory(self, _mock_embedding):
        recorded = {}

        class DummyAssociativeMemory:
            def add_event(
                self,
                created,
                expiration,
                s,
                p,
                o,
                description,
                keywords,
                poignancy,
                embedding_pair,
                filling,
                attribute_effects=None,
            ):
                recorded["description"] = description
                recorded["keywords"] = set(keywords)
                recorded["poignancy"] = poignancy
                recorded["attribute_effects"] = attribute_effects
                return "node_1"

        persona = self._build_persona()
        persona.a_mem = DummyAssociativeMemory()
        persona.scratch.curr_time = "2026-07-10 12:00:00"

        outcome = build_action_outcome_record(
            persona,
            result="success",
            effects={
                "self_attribute_effects": {
                    "satiety": 10.0,
                    "stamina": 0.0,
                    "health": 0.0,
                    "mood": 1.0,
                },
                "inventory_delta": {"apple": 1},
                "progress_score": 0.7,
            },
        )

        node_id = record_projected_action_outcome(persona, outcome)

        self.assertEqual(node_id, "node_1")
        self.assertIn("successfully used gather", recorded["description"])
        self.assertIn("execution_result", recorded["keywords"])
        self.assertEqual(recorded["attribute_effects"]["satiety"], 10.0)


if __name__ == "__main__":
    unittest.main()
