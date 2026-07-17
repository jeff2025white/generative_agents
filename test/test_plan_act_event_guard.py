import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.dot = lambda *args, **kwargs: 0.0
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda *args, **kwargs: 1.0
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub
sys.modules.setdefault("openai", SimpleNamespace(api_key=None, api_base=None))

import persona.cognitive_modules.plan as plan_module
from persona.cognitive_modules.plan import plan


class PlanActEventGuardTests(unittest.TestCase):
    def test_plan_handles_none_act_event_during_social_cleanup(self):
        scratch = SimpleNamespace(
            act_event=None,
            act_address="the Ville:Dorm",
            act_description="idling briefly to stabilize after eating",
            chatting_with="Maria Lopez",
            chat=["hello"],
            chatting_end_time=123,
            curr_step=1,
            act_check_finished=lambda: False,
        )
        persona = SimpleNamespace(name="Klaus Mueller", scratch=scratch)

        with patch("persona.cognitive_modules.plan.clear_social_dialogue_state") as clear_mock, \
             patch("persona.cognitive_modules.plan._decrement_chatting_with_buffer") as decrement_mock:
            result = plan(persona, maze=None, personas={}, new_day="", retrieved={})

        self.assertEqual(result, "the Ville:Dorm")
        self.assertIsNone(persona.scratch.chatting_with)
        self.assertIsNone(persona.scratch.chat)
        self.assertIsNone(persona.scratch.chatting_end_time)
        clear_mock.assert_called_once_with(persona)
        decrement_mock.assert_called_once_with(persona)

    def test_build_act_obj_state_uses_fast_rule_for_gather(self):
        desc, event = plan_module.build_act_obj_state(
            "refrigerator",
            "opening the refrigerator to gather food items",
            SimpleNamespace(name="Maria Lopez"),
        )

        self.assertEqual(desc, "refrigerator is being opened")
        self.assertEqual(event, ("refrigerator", "is", "being opened"))

    def test_generate_act_obj_state_does_not_call_llm_helpers(self):
        persona = SimpleNamespace(name="Maria Lopez")
        with patch.object(plan_module, "run_gpt_prompt_act_obj_desc", side_effect=AssertionError("should not call llm desc")), \
             patch.object(plan_module, "run_gpt_prompt_act_obj_event_triple", side_effect=AssertionError("should not call llm event")):
            desc = plan_module.generate_act_obj_desc(
                "library table",
                "working quietly at the desk",
                persona,
            )
            event = plan_module.generate_act_obj_event_triple(
                "library table",
                desc,
                persona,
            )

        self.assertEqual(desc, "library table is being used for work")
        self.assertEqual(event, ("library table", "is", "being used for work"))

    def test_structured_action_event_preserves_validated_gather_semantics(self):
        persona = SimpleNamespace(name="Klaus Mueller")
        with patch.object(
            plan_module,
            "generate_action_event_triple",
            side_effect=AssertionError("validated skill events must not be rewritten by an LLM"),
        ):
            event = plan_module.build_structured_action_event(
                persona,
                "gather",
                "apple tree",
                action_description="gathering apples from the apple tree",
            )

        self.assertEqual(event, ("Klaus Mueller", "gather", "apple tree"))

    def test_create_react_clamps_hourly_schedule_tail_index(self):
        add_calls = []
        scratch = SimpleNamespace(
            f_daily_schedule_hourly_org=[["reading", 60]],
            f_daily_schedule=[["reading quietly", 60]],
            curr_step=7,
            get_f_daily_schedule_hourly_org_index=lambda advance=0: 1,
            add_new_action=lambda *args, **kwargs: add_calls.append((args, kwargs)),
        )
        persona = SimpleNamespace(name="Klaus Mueller", scratch=scratch)

        with patch.object(plan_module, "generate_new_decomp_schedule", return_value=[["chatting with Maria", 10]]):
            plan_module._create_react(
                persona,
                inserted_act="chatting with Maria",
                inserted_act_dur=10,
                act_address="<persona> Maria Lopez",
                act_event=("Klaus Mueller", "chat with", "Maria Lopez"),
                chatting_with="Maria Lopez",
                chat=[["Klaus Mueller", "Hi"]],
                chatting_with_buffer={},
                chatting_end_time=None,
                act_pronunciatio="💬",
                act_obj_description=None,
                act_obj_pronunciatio=None,
                act_obj_event=(None, None, None),
            )

        self.assertEqual(scratch.f_daily_schedule, [["chatting with Maria", 10]])
        self.assertEqual(len(add_calls), 1)


if __name__ == "__main__":
    unittest.main()
