import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sys.modules.setdefault("openai", SimpleNamespace(api_key=None, api_base=None))
if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.dot = lambda *args, **kwargs: 0.0
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda *args, **kwargs: 1.0
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub

from persona.memory_structures.scratch import Scratch


class ScratchLegacyLoadTests(unittest.TestCase):
    def _build_legacy_payload(self):
        return {
            "vision_r": 4,
            "att_bandwidth": 3,
            "retention": 5,
            "curr_time": "July 02, 2026, 17:09:29",
            "curr_tile": [10, 12],
            "daily_plan_req": "stay healthy",
            "name": "Klaus Mueller",
            "first_name": "Klaus",
            "last_name": "Mueller",
            "age": 28,
            "innate": "kind",
            "learned": "likes reading",
            "currently": "testing compatibility",
            "lifestyle": "regular",
            "living_area": "Dorm",
            "satiety": 55.0,
            "stamina": 80.0,
            "health": 90.0,
            "mood": 75.0,
            "concept_forget": 100,
            "daily_reflection_time": 180,
            "daily_reflection_size": 5,
            "overlap_reflect_th": 2,
            "kw_strg_event_reflect_th": 4,
            "kw_strg_thought_reflect_th": 4,
            "recency_w": 1,
            "relevance_w": 1,
            "importance_w": 1,
            "recency_decay": 0.99,
            "importance_trigger_max": 150,
            "importance_trigger_curr": 150,
            "importance_ele_n": 0,
            "thought_count": 5,
            "daily_req": [],
            "f_daily_schedule": [],
            "f_daily_schedule_hourly_org": [],
            "act_address": None,
            "act_start_time": None,
            "act_duration": None,
            "act_description": None,
            "act_pronunciatio": None,
            "act_event": None,
            "act_obj_description": None,
            "act_obj_pronunciatio": None,
            "act_obj_event": None,
            "act_path_set": False,
            "planned_path": [],
        }

    def test_load_legacy_scratch_with_none_act_event(self):
        payload = self._build_legacy_payload()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp)
            temp_path = tmp.name

        try:
            scratch = Scratch(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

        self.assertEqual(scratch.act_event, ("Klaus Mueller", None, None))
        self.assertEqual(scratch.act_obj_event, (None, None, None))

    def test_load_legacy_empty_act_address_normalizes_to_none(self):
        payload = self._build_legacy_payload()
        payload["act_address"] = "   "
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp)
            temp_path = tmp.name

        try:
            scratch = Scratch(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

        self.assertIsNone(scratch.act_address)

    @patch(
        "persona.memory_structures.scratch.generate_innate_traits_from_motives",
        return_value="reflective, inquisitive, steady",
    )
    def test_load_legacy_scratch_refreshes_innate_traits_from_motives(self, _mock_refresh):
        payload = self._build_legacy_payload()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp)
            temp_path = tmp.name

        try:
            scratch = Scratch(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

        self.assertEqual(scratch.innate, "reflective, inquisitive, steady")
        self.assertEqual(
            scratch.get_prompt_profile_field("innate_traits_text"),
            "reflective, inquisitive, steady",
        )
        self.assertEqual(
            scratch.prompt_profile["fields"]["innate_traits_text"]["source"],
            "motive_llm_refresh",
        )

    def test_resume_suspended_action_normalizes_empty_address(self):
        scratch = Scratch(str(ROOT / "test" / "__missing_scratch__.json"))
        scratch.suspended_action = {
            "act_address": " ",
            "act_duration": 10,
            "act_description": "having a conversation with Maria Lopez",
            "act_pronunciatio": "💬",
            "act_event": ["Klaus Mueller", "chat with", "Maria Lopez"],
            "act_command": {"skill_id": "chat with", "target": "Maria Lopez"},
            "act_obj_description": None,
            "act_obj_pronunciatio": None,
            "act_obj_event": [None, None, None],
            "chatting_with": "Maria Lopez",
            "chat": None,
            "chatting_with_buffer": {},
            "chatting_end_time": None,
        }

        self.assertTrue(scratch.resume_suspended_action())
        self.assertIsNone(scratch.act_address)

    def test_missing_file_uses_lower_default_mood(self):
        scratch = Scratch(str(ROOT / "test" / "__missing_scratch__.json"))
        self.assertEqual(scratch.mood, 50.0)
        self.assertIn("mood", scratch.motive_attributes)
        self.assertEqual(scratch.motive_attributes["mood"]["current_value"], 50.0)

    def test_motive_attributes_persist_across_save_and_load(self):
        scratch = Scratch(str(ROOT / "test" / "__missing_scratch__.json"))
        scratch.curr_time = datetime(2026, 7, 8, 12, 0, 0)
        scratch.act_start_time = datetime(2026, 7, 8, 12, 0, 0)
        scratch.motive_attributes["status"]["current_value"] = 33.0
        scratch.motive_attributes["status"]["skill_flat_modifiers"] = {"sing": 5.0}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            temp_path = tmp.name

        try:
            scratch.save(temp_path)
            reloaded = Scratch(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

        self.assertEqual(reloaded.motive_attributes["status"]["current_value"], 33.0)
        self.assertEqual(reloaded.motive_attributes["status"]["skill_flat_modifiers"]["sing"], 5.0)

    def test_action_outcome_runtime_views_persist_across_save_and_load(self):
        scratch = Scratch(str(ROOT / "test" / "__missing_scratch__.json"))
        scratch.curr_time = datetime(2026, 7, 10, 12, 0, 0)
        scratch.act_start_time = datetime(2026, 7, 10, 12, 0, 0)
        scratch.curr_step = 161

        outcome = {
            "schema_version": 1,
            "outcome_id": "Isabella-161-abc",
            "persona": "Isabella Rodriguez",
            "curr_step": 161,
            "action": {
                "skill_id": "gather",
                "target": "refrigerator",
                "target_address": "the Ville:Hobbs Cafe:cafe:refrigerator",
            },
            "execution": {
                "result": "failed",
                "reason": "resource_empty",
                "reason_class": "resource_state",
            },
            "effects": {
                "self_attribute_effects": {
                    "satiety": 0.0,
                    "stamina": 0.0,
                    "health": 0.0,
                    "mood": 0.0,
                },
                "inventory_delta": {},
                "progress_score": 0.0,
            },
            "resource_context": {
                "resource_instance_key": "the ville:hobbs cafe:cafe:refrigerator",
            },
        }

        scratch.record_action_outcome(outcome)

        self.assertEqual(scratch.last_action_outcome["outcome_id"], "Isabella-161-abc")
        self.assertEqual(len(scratch.recent_action_outcomes), 1)
        self.assertEqual(scratch.failed_resource_instances[0]["reason"], "resource_empty")
        self.assertEqual(scratch.successful_resource_instances, [])

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            temp_path = tmp.name

        try:
            scratch.save(temp_path)
            reloaded = Scratch(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

        self.assertEqual(reloaded.last_action_outcome["outcome_id"], "Isabella-161-abc")
        self.assertEqual(len(reloaded.recent_action_outcomes), 1)
        self.assertEqual(
            reloaded.failed_resource_instances[0]["target_address"],
            "the Ville:Hobbs Cafe:cafe:refrigerator",
        )

    @patch("persona.memory_structures.scratch.append_debug_log")
    def test_record_action_outcome_appends_action_outcome_log(self, mock_log):
        scratch = Scratch(str(ROOT / "test" / "__missing_scratch__.json"))
        scratch.curr_time = datetime(2026, 7, 10, 12, 0, 0)
        scratch.act_start_time = datetime(2026, 7, 10, 12, 0, 0)
        scratch.curr_step = 161

        outcome = {
            "schema_version": 1,
            "outcome_id": "Isabella-161-log",
            "persona": "Isabella Rodriguez",
            "curr_step": 161,
            "sim_time": "2026-07-10 12:00:00",
            "action": {
                "skill_id": "gather",
                "target": "refrigerator",
                "target_address": "the Ville:Hobbs Cafe:cafe:refrigerator",
            },
            "execution": {
                "result": "failed",
                "reason": "resource_empty",
                "reason_class": "resource_state",
            },
            "effects": {
                "self_attribute_effects": {
                    "satiety": 0.0,
                    "stamina": 0.0,
                    "health": 0.0,
                    "mood": 0.0,
                },
                "inventory_delta": {},
                "progress_score": 0.0,
            },
        }

        scratch.record_action_outcome(outcome)

        self.assertTrue(mock_log.called)
        self.assertEqual(mock_log.call_args.args[0], "action_outcome")

    @patch("persona.memory_structures.scratch.record_projected_action_outcome")
    @patch("persona.memory_structures.scratch.append_debug_log")
    def test_record_action_outcome_projects_promoted_experience_when_persona_attached(self, _mock_log, mock_record):
        scratch = Scratch(str(ROOT / "test" / "__missing_scratch__.json"))
        scratch.name = "Maria Lopez"
        scratch.curr_time = datetime(2026, 7, 10, 12, 0, 0)
        scratch.act_start_time = datetime(2026, 7, 10, 12, 0, 0)
        scratch.curr_step = 161
        persona = SimpleNamespace(name="Maria Lopez", scratch=scratch, a_mem=object())
        scratch.attach_persona_ref(persona)

        outcome = {
            "schema_version": 1,
            "outcome_id": "Maria-161-projection",
            "persona": "Maria Lopez",
            "curr_step": 161,
            "sim_time": "2026-07-10 12:00:00",
            "action": {
                "skill_id": "consume",
                "target": "apple",
                "target_address": "inventory",
            },
            "execution": {
                "result": "success",
                "reason": None,
                "reason_class": "other",
            },
            "effects": {
                "self_attribute_effects": {
                    "satiety": 12.0,
                    "stamina": 0.0,
                    "health": 0.0,
                    "mood": 1.0,
                },
                "inventory_delta": {"apple": -1},
                "progress_score": 1.0,
            },
            "experience_scoring": {
                "effective_score": 0.9,
                "should_promote_to_experience": True,
            },
            "memory_projection": {
                "description": "Maria Lopez successfully used consume on apple at inventory.",
            },
        }

        scratch.record_action_outcome(outcome)

        mock_record.assert_called_once_with(persona, outcome)

    @patch("persona.memory_structures.scratch.append_debug_log")
    def test_mark_action_completed_records_successful_action_outcome(self, _mock_log):
        scratch = Scratch(str(ROOT / "test" / "__missing_scratch__.json"))
        scratch.name = "Maria Lopez"
        scratch.curr_time = datetime(2026, 7, 10, 12, 0, 0)
        scratch.act_start_time = datetime(2026, 7, 10, 12, 0, 0)
        scratch.curr_step = 161
        scratch.act_address = "the Ville:Johnson Park:park:apple tree"
        scratch.act_description = "gathering apples from the apple tree"
        scratch.act_command = {
            "skill_id": "gather",
            "target": "apple tree",
            "intent_family": "restore_satiety",
            "raw_action": "Gather",
        }

        scratch.mark_action_completed(
            action_command=scratch.act_command,
            action_event=("Maria Lopez", "gather", "apple tree"),
            action_description=scratch.act_description,
            action_address=scratch.act_address,
            outcome_effects={
                "self_attribute_effects": {
                    "satiety": 0.0,
                    "stamina": 0.0,
                    "health": 0.0,
                    "mood": 1.0,
                },
                "inventory_delta": {"apple": 2},
                "progress_score": 0.6,
            },
        )

        self.assertEqual(scratch.last_action_observation["result"], "completed")
        self.assertEqual(scratch.last_action_outcome["execution"]["result"], "success")
        self.assertEqual(
            scratch.last_action_outcome["effects"]["inventory_delta"]["apple"],
            2,
        )
        self.assertEqual(
            scratch.successful_resource_instances[0]["target_address"],
            "the Ville:Johnson Park:park:apple tree",
        )
        self.assertEqual(
            scratch.successful_resource_instances[0]["progress_score"],
            0.6,
        )

    def test_prompt_profile_defaults_and_persists(self):
        scratch = Scratch(str(ROOT / "test" / "__missing_scratch__.json"))
        scratch.name = "Klaus Mueller"
        scratch.first_name = "Klaus"
        scratch.age = 28
        scratch.innate = "kind"
        scratch.learned = "likes reading"
        scratch.currently = "testing prompt profile persistence"
        scratch.lifestyle = "regular"
        scratch.daily_plan_req = "stay healthy"
        scratch.curr_time = datetime(2026, 7, 8, 12, 0, 0)
        scratch.act_start_time = datetime(2026, 7, 8, 12, 0, 0)

        profile = scratch.get_prompt_profile()
        self.assertEqual(
            profile["fields"]["innate_traits_text"]["value"],
            "kind",
        )
        self.assertEqual(
            profile["fields"]["daily_plan_text"]["value"],
            "stay healthy",
        )

        scratch.set_prompt_profile_field(
            "long_term_goals_text",
            "First stay alive, then build a steady life through reading and calm routines.",
            source="unit_test",
        )

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            temp_path = tmp.name

        try:
            scratch.save(temp_path)
            reloaded = Scratch(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

        self.assertEqual(
            reloaded.get_prompt_profile_field("long_term_goals_text"),
            "First stay alive, then build a steady life through reading and calm routines.",
        )
        self.assertEqual(
            reloaded.prompt_profile["fields"]["long_term_goals_text"]["source"],
            "unit_test",
        )

    @patch(
        "persona.memory_structures.scratch.generate_innate_traits_from_motives",
        return_value="independent, capable, reflective",
    )
    def test_set_motive_attributes_can_refresh_innate_traits(self, _mock_refresh):
        scratch = Scratch(str(ROOT / "test" / "__missing_scratch__.json"))
        scratch.name = "Klaus Mueller"
        scratch.curr_time = datetime(2026, 7, 8, 12, 0, 0)
        scratch.act_start_time = datetime(2026, 7, 8, 12, 0, 0)

        updated = scratch.get_motive_attributes_snapshot()
        updated["autonomy"]["current_value"] = 18.0

        scratch.set_motive_attributes(
            updated,
            source="unit_test_motive_profile",
            refresh_innate=True,
        )

        self.assertEqual(scratch.innate, "independent, capable, reflective")
        self.assertEqual(
            scratch.get_prompt_profile_field("innate_traits_text"),
            "independent, capable, reflective",
        )
        self.assertEqual(
            scratch.prompt_profile["fields"]["innate_traits_text"]["source"],
            "unit_test_motive_profile_innate_refresh",
        )


if __name__ == "__main__":
    unittest.main()
