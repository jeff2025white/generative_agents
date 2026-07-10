import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

global_methods_module = sys.modules.setdefault("global_methods", ModuleType("global_methods"))
if not hasattr(global_methods_module, "check_if_file_exists"):
    global_methods_module.check_if_file_exists = lambda path: False


from persona.memory_structures.scratch import Scratch
from persona.cognitive_modules.motive_selector import build_default_motive_attributes


class MotiveMonitorLoggingTests(unittest.TestCase):
    def test_set_motive_attributes_writes_dedicated_monitor_log(self):
        scratch = Scratch("__missing__.json")
        scratch.name = "Maria Lopez"
        scratch.curr_step = 42
        scratch.curr_time = datetime(2026, 7, 8, 12, 30, 0)
        updated = scratch.get_motive_attributes_snapshot()
        updated["belonging"]["current_value"] = 20.0

        with patch("persona.memory_structures.scratch.append_debug_log") as append_log:
            scratch.set_motive_attributes(
                updated,
                source="skill_effect",
                reason="chat",
                metadata={"applied": {"belonging": -15.0}},
            )

        append_log.assert_called_once()
        log_name, payload = append_log.call_args[0]
        self.assertEqual(log_name, "motive_monitor.jsonl")
        self.assertEqual(payload["persona"], "Maria Lopez")
        self.assertEqual(payload["source"], "skill_effect")
        self.assertEqual(payload["reason"], "chat")
        self.assertEqual(payload["changed_motives"][0]["motive"], "belonging")
        self.assertEqual(payload["changed_motives"][0]["after"], 20.0)
        self.assertIn("dominant_urgency_band", payload)
        self.assertIn("dominant_pressure_score", payload)
        self.assertIn("dominant_strength", payload)
        self.assertIn("has_urgent_motive", payload)

    def test_creator_task_completion_grants_competence_plus_three(self):
        scratch = Scratch("__missing__.json")
        scratch.name = "Maria Lopez"
        scratch.curr_step = 99
        scratch.curr_time = datetime(2026, 7, 8, 18, 0, 0)
        scratch.motive_attributes = build_default_motive_attributes(
            overrides={"competence": {"current_value": 50.0}}
        )
        scratch.current_action_record = {"creator_instruction": "go to the kitchen"}

        with patch("persona.memory_structures.scratch.append_debug_log"):
            scratch.mark_action_completed(
                action_command={"skill_id": "work", "target": "kitchen", "source": "decision_translation"},
                action_description="going to the kitchen",
                action_address="the Ville:Dorm:kitchen",
            )

        self.assertEqual(scratch.motive_attributes["competence"]["current_value"], 53.0)

    def test_current_action_record_preserves_creator_instruction_across_status_updates(self):
        scratch = Scratch("__missing__.json")
        scratch.name = "Maria Lopez"
        scratch.curr_step = 430
        scratch.curr_time = datetime(2026, 7, 8, 19, 48, 6)
        scratch.act_address = "the Ville:Johnson Park:park:apple tree"
        scratch.act_description = "gathering apples from the apple tree"
        scratch.act_command = {
            "skill_id": "gather",
            "target": "apple tree",
            "source": "decision_translation",
        }
        scratch.act_event = ("Maria Lopez", "gather", "apple tree")
        scratch.act_duration = 10
        scratch.set_current_action_record(
            {
                "status": "resolved",
                "creator_instruction": "采集苹果",
                "resolved_target": "apple tree",
                "resolved_address": "the Ville:Johnson Park:park:apple tree",
            }
        )

        scratch.update_current_action_record_status(status="planned")

        self.assertEqual(scratch.current_action_record["creator_instruction"], "采集苹果")


if __name__ == "__main__":
    unittest.main()
