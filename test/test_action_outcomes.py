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
    build_goal_evaluation,
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

    def test_build_action_outcome_record_uses_attached_persona_sim_code(self):
        persona = self._build_persona()
        persona.scratch._persona_ref = SimpleNamespace(sim_code="sim_test_123")

        outcome = build_action_outcome_record(
            persona,
            result="success",
            effects={"inventory_delta": {"apple": 1}},
        )

        self.assertEqual(outcome["sim_code"], "sim_test_123")

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

    def test_execution_success_without_effect_is_not_goal_success(self):
        persona = self._build_persona()

        outcome = build_action_outcome_record(persona, result="success")

        self.assertEqual(outcome["execution"]["result"], "success")
        self.assertEqual(outcome["goal"]["status"], "no_progress")
        self.assertTrue(outcome["goal"]["replan_required"])
        self.assertIn("goal_no_progress", outcome["memory_projection"]["keywords"])
        self.assertIn("no measurable progress", outcome["memory_projection"]["description"])

    def test_inventory_gain_is_partial_goal_progress(self):
        evaluation = build_goal_evaluation(
            "success",
            {"inventory_delta": {"apple": 1}, "progress_score": 0.25},
        )

        self.assertEqual(evaluation["status"], "advanced")
        self.assertTrue(evaluation["replan_required"])
        self.assertIn("inventory:apple:+1", evaluation["evidence"])

    @patch("persona.memory_structures.scratch.append_debug_log")
    def test_completed_action_without_progress_is_not_a_successful_resource(self, _mock_log):
        scratch = Scratch("/tmp/nonexistent_scratch_for_no_progress_outcome_test.json")
        scratch.name = "Klaus Mueller"
        scratch.curr_step = 22
        scratch.act_address = "<persona> Isabella Rodriguez"
        scratch.act_description = "requesting food from Isabella Rodriguez"
        scratch.act_command = {
            "skill_id": "request",
            "target": "Isabella Rodriguez",
            "intent_family": "restore_satiety",
            "raw_action": "Request",
        }

        scratch.mark_action_completed(outcome_effects={"progress_score": 0.0})

        self.assertEqual(scratch.last_action_observation["goal_status"], "no_progress")
        self.assertTrue(scratch.last_action_observation["replan_required"])
        self.assertEqual(scratch.successful_resource_instances, [])

    def test_failed_execution_is_blocked_even_if_effects_are_reported(self):
        evaluation = build_goal_evaluation(
            "failed",
            {"self_attribute_effects": {"mood": 1.0}, "progress_score": 0.7},
            reason="target_not_close",
        )

        self.assertEqual(evaluation["status"], "blocked")
        self.assertTrue(evaluation["replan_required"])

    def test_outcome_captures_ten_motive_effects_from_action_snapshots(self):
        persona = self._build_persona()
        before = {key: {"current_value": 50.0} for key in (
            "satiety", "stamina", "health", "safety", "mood", "belonging",
            "status", "autonomy", "competence", "meaning",
        )}
        after = {key: {"current_value": 50.0} for key in before}
        after["belonging"] = {"current_value": 58.0}
        after["competence"] = {"current_value": 46.0}
        persona.scratch.current_action_record["motive_values_before"] = before
        persona.scratch.get_motive_attributes_snapshot = lambda: after

        outcome = build_action_outcome_record(persona, result="success")

        self.assertEqual(len(outcome["effects"]["motive_effects"]), 10)
        self.assertEqual(outcome["effects"]["motive_effects"]["belonging"], 8.0)
        self.assertEqual(outcome["effects"]["motive_effects"]["competence"], -4.0)

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


class ScoreActionOutcomeFailureTests(unittest.TestCase):
    """Tests that persona-interaction failures are promoted to experience."""

    def test_target_inventory_empty_with_satiety_motive_promotes(self):
        from persona.cognitive_modules.action_outcomes import score_action_outcome
        scoring = score_action_outcome(
            effects={"self_attribute_effects": {}, "inventory_delta": {}, "progress_score": 0.0},
            reason="target_inventory_empty",
            dominant_motive="satiety",
            result="failed",
        )
        self.assertGreaterEqual(scoring["effective_score"], 0.55)
        self.assertTrue(scoring["should_promote_to_experience"])
        self.assertEqual(scoring["failure_learning_value"], 0.72)

    def test_target_not_close_with_satiety_motive_promotes(self):
        from persona.cognitive_modules.action_outcomes import score_action_outcome
        scoring = score_action_outcome(
            effects={"self_attribute_effects": {}, "inventory_delta": {}, "progress_score": 0.0},
            reason="target_not_close",
            dominant_motive="satiety",
            result="failed",
        )
        self.assertGreaterEqual(scoring["effective_score"], 0.55)
        self.assertTrue(scoring["should_promote_to_experience"])

    def test_recent_duplicate_action_promotes(self):
        from persona.cognitive_modules.action_outcomes import score_action_outcome
        scoring = score_action_outcome(
            effects={"self_attribute_effects": {}, "inventory_delta": {}, "progress_score": 0.0},
            reason="recent_duplicate_action",
            dominant_motive=None,
            result="failed",
        )
        self.assertGreaterEqual(scoring["effective_score"], 0.55)
        self.assertTrue(scoring["should_promote_to_experience"])

    def test_self_chat_target_promotes(self):
        from persona.cognitive_modules.action_outcomes import score_action_outcome
        scoring = score_action_outcome(
            effects={"self_attribute_effects": {}, "inventory_delta": {}, "progress_score": 0.0},
            reason="self_chat_target",
            dominant_motive=None,
            result="failed",
        )
        self.assertGreaterEqual(scoring["effective_score"], 0.55)
        self.assertTrue(scoring["should_promote_to_experience"])

    def test_invalid_food_source_promotes(self):
        from persona.cognitive_modules.action_outcomes import score_action_outcome
        scoring = score_action_outcome(
            effects={"self_attribute_effects": {}, "inventory_delta": {}, "progress_score": 0.0},
            reason="invalid_food_source",
            dominant_motive="satiety",
            result="failed",
        )
        self.assertGreaterEqual(scoring["effective_score"], 0.55)
        self.assertTrue(scoring["should_promote_to_experience"])

    def test_rest_target_missing_promotes(self):
        from persona.cognitive_modules.action_outcomes import score_action_outcome
        scoring = score_action_outcome(
            effects={"self_attribute_effects": {}, "inventory_delta": {}, "progress_score": 0.0},
            reason="rest_target_missing",
            dominant_motive="stamina",
            result="failed",
        )
        self.assertGreaterEqual(scoring["effective_score"], 0.55)
        self.assertTrue(scoring["should_promote_to_experience"])


class BuildActionRecordFieldTests(unittest.TestCase):
    """Tests that _build_action_record propagates decision_id and dominant_motive."""

    def test_decision_id_and_dominant_motive_in_record(self):
        sys.path.insert(0, str(BACKEND_ROOT))
        from persona.cognitive_modules.plan import _build_action_record
        persona = SimpleNamespace(scratch=SimpleNamespace(curr_step=135))
        record = _build_action_record(
            persona,
            skill_id="request",
            target="Isabella Rodriguez",
            act_desp="requesting food",
            act_dura=10,
            resolved_address="<persona> Isabella Rodriguez",
            reasoning="hungry",
            decision_id="Klaus_Mueller-135-abc123",
            dominant_motive="satiety",
        )
        self.assertEqual(record["decision_id"], "Klaus_Mueller-135-abc123")
        self.assertEqual(record["dominant_motive"], "satiety")

    def test_decision_id_defaults_to_none(self):
        from persona.cognitive_modules.plan import _build_action_record
        persona = SimpleNamespace(scratch=SimpleNamespace(curr_step=10))
        record = _build_action_record(
            persona, "gather", "refrigerator", "opening fridge", 5,
            "the Ville:cafe:refrigerator", "need food",
        )
        self.assertIsNone(record["decision_id"])
        self.assertIsNone(record["dominant_motive"])

    def test_dominant_motive_from_intent_family(self):
        from persona.cognitive_modules.plan import _dominant_motive_from_intent_family
        self.assertEqual(_dominant_motive_from_intent_family("restore_satiety"), "satiety")
        self.assertEqual(_dominant_motive_from_intent_family("restore_stamina"), "stamina")
        self.assertEqual(_dominant_motive_from_intent_family("restore_mood"), "mood")
        self.assertIsNone(_dominant_motive_from_intent_family(None))
        self.assertIsNone(_dominant_motive_from_intent_family(""))


class OutcomeRecordDecisionContextTests(unittest.TestCase):
    """Tests that build_action_outcome_record correctly reads decision_id and dominant_motive from current_action_record."""

    def test_outcome_record_reads_dominant_motive_from_action_record(self):
        scratch = SimpleNamespace(
            curr_step=135,
            curr_time=None,
            act_address="<persona> Isabella Rodriguez",
            act_description="requesting food from Isabella",
            act_command={
                "skill_id": "request",
                "target": "Isabella Rodriguez",
                "intent_family": "restore_satiety",
                "raw_action": "Request",
            },
            inventory={},
            satiety=39.9,
            stamina=62.0,
            health=91.0,
            mood=50.0,
            current_action_record={
                "decision_id": "Klaus_Mueller-135-abc123",
                "dominant_motive": "satiety",
                "resolved_target": "Isabella Rodriguez",
                "resolved_address": "<persona> Isabella Rodriguez",
                "resolution_kind": "persona",
            },
        )
        persona = SimpleNamespace(name="Klaus Mueller", scratch=scratch, sim_code="test")

        outcome = build_action_outcome_record(
            persona,
            result="failed",
            reason="target_inventory_empty",
        )

        self.assertEqual(outcome["decision_context"]["dominant_motive"], "satiety")
        self.assertEqual(outcome["decision_context"]["decision_id"], "Klaus_Mueller-135-abc123")
        self.assertGreaterEqual(outcome["experience_scoring"]["effective_score"], 0.55)
        self.assertTrue(outcome["experience_scoring"]["should_promote_to_experience"])
        self.assertEqual(outcome["experience_scoring"]["dominant_motive_alignment"], 0.95)


if __name__ == "__main__":
    unittest.main()
