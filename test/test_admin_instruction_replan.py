import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).parent.parent
BACKEND = ROOT / "reverie" / "backend_server"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.chdir(str(BACKEND))

from persona.cognitive_modules.admin_console import handle_admin_console_instruction
from persona.cognitive_modules.plan import plan as run_plan
from persona.prompt_template.run_gpt_prompt import (
    run_gpt_prompt_action_translation,
    run_gpt_prompt_demand_thinking,
)


class AdminInstructionReplanTests(unittest.TestCase):
    def test_handle_admin_instruction_sets_override_and_interrupts_active_plan(self):
        scratch = SimpleNamespace(
            curr_step=12,
            active_execution_state=None,
            set_admin_override_intent=Mock(return_value=True),
            has_active_plan=Mock(return_value=True),
            interrupt_execution=Mock(),
        )
        persona = SimpleNamespace(name="Klaus Mueller", scratch=scratch)

        result = handle_admin_console_instruction(persona, "去摘苹果吃")

        scratch.set_admin_override_intent.assert_called_once_with("摘苹果吃", source="admin_console")
        scratch.interrupt_execution.assert_called_once()
        self.assertEqual(result["message_mode"], "instruction")
        self.assertEqual(result["next_action"], "摘苹果吃")
        self.assertIn("重新规划", result["reply"])

    def test_plan_skips_resume_when_admin_override_exists(self):
        scratch = SimpleNamespace(
            act_description="",
            act_event=("Klaus Mueller", None, None),
            act_address=None,
            chatting_with=None,
            chat=None,
            chatting_end_time=None,
            should_lock_high_level_planning=lambda: False,
            act_check_finished=lambda: True,
            should_resume_suspended_action=Mock(return_value=True),
            resume_suspended_action=Mock(),
            get_admin_override_intent=lambda: "摘苹果吃",
        )
        persona = SimpleNamespace(name="Klaus Mueller", scratch=scratch)

        with patch("persona.cognitive_modules.plan.decide_demand_action") as decide_mock, \
             patch("persona.cognitive_modules.plan._decrement_chatting_with_buffer"), \
             patch("persona.cognitive_modules.plan.clear_social_dialogue_state"):
            run_plan(persona, maze=SimpleNamespace(), personas={}, new_day=False, retrieved={})

        scratch.resume_suspended_action.assert_not_called()
        decide_mock.assert_called_once()

    def test_demand_thinking_prompt_mentions_admin_override(self):
        scratch = SimpleNamespace(
            curr_time=None,
            satiety=60.0,
            stamina=80.0,
            inventory={},
            get_str_iss=lambda: "Name: Klaus Mueller",
            get_str_firstname=lambda: "Klaus",
        )
        persona = SimpleNamespace(scratch=scratch)

        with patch("persona.prompt_template.run_gpt_prompt.ChatGPT_request", return_value="I should gather apples now.") as request_mock, \
             patch("persona.prompt_template.run_gpt_prompt._append_training_prep_prompt_log"):
            run_gpt_prompt_demand_thinking(
                persona,
                nearby_resources=["apple tree (idle/normal)"],
                admin_override_instruction="摘苹果吃",
            )

        prompt = request_mock.call_args.args[0]
        self.assertIn("摘苹果吃", prompt)
        self.assertIn("ADMIN OVERRIDE", prompt)

    def test_action_translation_special_instruction_mentions_admin_override(self):
        with patch(
            "persona.prompt_template.run_gpt_prompt.ChatGPT_safe_generate_response",
            return_value={"action": "Gather", "target": "apple tree", "detail": "gathering apples from the apple tree", "duration": 10, "reasoning": "admin override"},
        ) as safe_mock, patch("persona.prompt_template.run_gpt_prompt._append_training_prep_prompt_log"):
            run_gpt_prompt_action_translation(
                "I should gather apples now.",
                nearby_resources=["apple tree"],
                firstname="Klaus",
                admin_override_instruction="摘苹果吃",
                persona=None,
            )

        special_instruction = safe_mock.call_args.args[2]
        self.assertIn("摘苹果吃", special_instruction)
        self.assertIn("ADMIN OVERRIDE", special_instruction)


if __name__ == "__main__":
    unittest.main()
