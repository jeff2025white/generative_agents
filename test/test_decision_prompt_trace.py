import datetime
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


if "openai" not in sys.modules:
    openai_stub = SimpleNamespace(
        api_key=None,
        api_base=None,
        ChatCompletion=SimpleNamespace(create=lambda **kwargs: {"choices": [{"message": {"content": "stub"}}]}),
        Embedding=SimpleNamespace(create=lambda **kwargs: {"data": [{"embedding": [1.0, 0.0]}]}),
    )
    sys.modules["openai"] = openai_stub

if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda a: sum(x * x for x in a) ** 0.5
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub


import persona.prompt_template.run_gpt_prompt as prompt_module
import persona.cognitive_modules.plan as plan_module


class DecisionPromptTraceTests(unittest.TestCase):
    def test_demand_thinking_writes_prompt_trace(self):
        persona = SimpleNamespace(
            name="Maria Lopez",
            sim_code="sim_20260709_103000",
            scratch=SimpleNamespace(
                curr_step=12,
                curr_time=datetime.datetime(2026, 7, 9, 10, 30, 0),
                inventory={},
                satiety=18.0,
                stamina=80.0,
                health=90.0,
                mood=65.0,
                get_experience_priority_units=lambda intent_family=None: [
                    {
                        "experience_kind": "avoid",
                        "intent_family": "restore_satiety",
                        "resource_instance_key": "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
                        "resource_type": "refrigerator",
                        "recommendation": "avoid_this_instance",
                        "confidence": 0.91,
                        "evidence_summary": "refrigerator at Dorm for Oak Hill College was empty recently.",
                    },
                    {
                        "experience_kind": "prefer",
                        "intent_family": "restore_satiety",
                        "resource_instance_key": "the Ville:Johnson Park:park:apple tree",
                        "resource_type": "apple tree",
                        "recommendation": "prefer_this_instance",
                        "confidence": 0.78,
                        "evidence_summary": "apple tree worked well recently.",
                    },
                ],
                get_str_iss=lambda: "Name: Maria Lopez",
                get_str_firstname=lambda: "Maria",
            ),
        )

        with patch.object(prompt_module, "generate_prompt", return_value="PROMPT"), \
             patch.object(prompt_module, "ChatGPT_request", return_value="I should gather food now."), \
             patch.object(prompt_module, "append_debug_log") as log_mock:
            result = prompt_module.run_gpt_prompt_demand_thinking(
                persona,
                ["refrigerator", "stove"],
                temporal_context="- Current Time: Wednesday July 09, 2026, 10:30 AM",
                status_summary="Satiety is low.",
                rules="Gather food.",
                cooperative_context="No special cooperative tasks.",
                last_action_desc="walking",
                intent_memory_summary="Relevant food experience.",
                decision_id="Maria-12-abc123",
            )

        self.assertEqual(result, "I should gather food now.")
        trace_calls = [call.args for call in log_mock.call_args_list if call.args and call.args[0] == "decision_prompt_trace.jsonl"]
        self.assertEqual(len(trace_calls), 1)
        payload = trace_calls[0][1]
        self.assertEqual(payload["event"], "prompt_response")
        self.assertEqual(payload["stage"], "demand_thinking")
        self.assertEqual(payload["persona"], "Maria Lopez")
        self.assertEqual(payload["sim_code"], "sim_20260709_103000")
        self.assertEqual(payload["curr_step"], 12)
        self.assertEqual(payload["sim_time"], "2026-07-09 10:30:00")
        self.assertEqual(payload["decision_id"], "Maria-12-abc123")
        self.assertIn("PROMPT", payload["final_prompt"])
        self.assertIn("Answer:", payload["final_prompt"])
        self.assertEqual(payload["llm_response"], "I should gather food now.")
        self.assertIn("stage1_prompt_profile", payload)
        self.assertIn("stage1_dynamic_fields", payload)
        self.assertEqual(
            payload["stage1_dynamic_fields"]["relevant_experience_text"],
            "Relevant food experience.",
        )
        self.assertIn(
            "- Consume |",
            payload["stage1_dynamic_fields"]["action_schema_text"],
        )
        self.assertIn(
            "effects=",
            payload["stage1_dynamic_fields"]["action_schema_text"],
        )
        self.assertIn(
            "satiety:+58",
            payload["stage1_dynamic_fields"]["action_schema_text"],
        )
        self.assertIn(
            "mood:-2",
            payload["stage1_dynamic_fields"]["action_schema_text"],
        )
        self.assertIn(
            "- Request |",
            payload["stage1_dynamic_fields"]["action_schema_text"],
        )
        self.assertIn(
            "- Coordinate |",
            payload["stage1_dynamic_fields"]["action_schema_text"],
        )
        self.assertIn(
            "- Pressure |",
            payload["stage1_dynamic_fields"]["action_schema_text"],
        )
        self.assertEqual(
            payload["stage1_dynamic_fields"]["strong_avoid_experience_text"],
            "- refrigerator at Dorm for Oak Hill College was empty recently.",
        )
        self.assertEqual(
            payload["stage1_dynamic_fields"]["strong_prefer_experience_text"],
            "- apple tree worked well recently.",
        )
        self.assertIn(
            "instance-level experience over older generic memories",
            payload["stage1_dynamic_fields"]["experience_guidance_text"],
        )
        self.assertIn(
            "long_term_goals_text",
            payload["stage1_prompt_profile"]["fields"],
        )

    def test_action_translation_writes_prompt_trace(self):
        persona = SimpleNamespace(
            name="Klaus Mueller",
            sim_code="sim_20260709_110000",
            scratch=SimpleNamespace(
                curr_step=21,
                curr_time=datetime.datetime(2026, 7, 9, 11, 0, 0),
                inventory={},
                satiety=22.0,
                stamina=70.0,
                health=95.0,
                mood=60.0,
            ),
        )
        decision = {
            "action": "Gather",
            "target": "refrigerator",
            "detail": "opening the refrigerator to gather food items",
            "duration": 10,
            "reasoning": "Hunger is dominant.",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="TRANSLATION PROMPT"), \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=decision), \
             patch.object(prompt_module, "append_debug_log") as log_mock:
            result = prompt_module.run_gpt_prompt_action_translation(
                "I should gather food now.",
                ["refrigerator", "stove"],
                "Klaus",
                decision_id="Klaus-21-xyz987",
                persona=persona,
            )

        self.assertEqual(result, decision)
        trace_calls = [call.args for call in log_mock.call_args_list if call.args and call.args[0] == "decision_prompt_trace.jsonl"]
        self.assertEqual(len(trace_calls), 1)
        payload = trace_calls[0][1]
        self.assertEqual(payload["stage"], "action_translation")
        self.assertEqual(payload["sim_code"], "sim_20260709_110000")
        self.assertEqual(payload["sim_time"], "2026-07-09 11:00:00")
        self.assertEqual(payload["decision_id"], "Klaus-21-xyz987")
        self.assertEqual(payload["final_prompt"], "TRANSLATION PROMPT")
        self.assertEqual(payload["llm_response"], decision)
        self.assertEqual(payload["prompt_template"], "persona/prompt_template/v2/action_translation_v1.txt")

    def test_final_decision_trace_contains_routed_decision(self):
        persona = SimpleNamespace(
            name="Isabella Rodriguez",
            sim_code="sim_20260709_121500",
            scratch=SimpleNamespace(
                curr_step=33,
                curr_time=datetime.datetime(2026, 7, 9, 12, 15, 0),
                satiety=30.0,
                stamina=55.0,
                health=88.0,
                mood=72.0,
                inventory={"apple": 1},
            ),
        )

        with patch.object(plan_module, "append_debug_log") as log_mock:
            plan_module._append_step_decision_trace(
                persona,
                "Isabella-33-final01",
                "I should eat the apple now.",
                "Satiety is the dominant need.",
                {
                    "action": "Consume",
                    "target": "apple",
                    "detail": "eating the apple from inventory",
                    "duration": 10,
                    "reasoning": "Satiety is the dominant need.",
                },
                "Consume",
                "apple",
                "eating the apple from inventory",
                {"dominant_motive": "satiety"},
                {"enabled": True, "applied": False},
            )

        log_mock.assert_called_once()
        log_name, payload = log_mock.call_args.args
        self.assertEqual(log_name, "decision_prompt_trace.jsonl")
        self.assertEqual(payload["event"], "final_decision")
        self.assertEqual(payload["stage_order"], 30)
        self.assertEqual(payload["sim_code"], "sim_20260709_121500")
        self.assertEqual(payload["sim_time"], "2026-07-09 12:15:00")
        self.assertEqual(payload["decision_id"], "Isabella-33-final01")
        self.assertEqual(payload["llm_decision_text"]["thought"], "I should eat the apple now.")
        self.assertEqual(payload["decision_routed_action"], "Consume")
        self.assertEqual(payload["decision_routed_target"], "apple")


if __name__ == "__main__":
    unittest.main()
