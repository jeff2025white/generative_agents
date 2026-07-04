import os
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


import persona.cognitive_modules.plan as plan_module
import persona.prompt_template.run_gpt_prompt as prompt_module
from persona.cognitive_modules.decision_state_cache import clear_cached_decisions, put_cached_decision


class JointDecisionPromptTests(unittest.TestCase):
    def test_joint_decision_result_requires_thought_and_action_fields(self):
        captured = {}
        config = {"api_key": "cloud-key", "api_base": "https://api.example/v1", "model": "cloud-model"}

        def fake_generate_prompt(prompt_input, prompt_template):
            captured["prompt_input"] = prompt_input
            captured["prompt_template"] = prompt_template
            return "\n".join(str(item) for item in prompt_input)

        def fake_safe_generate_response(*args, **kwargs):
            captured["prompt_kind"] = kwargs.get("prompt_kind")
            captured["request_config"] = kwargs.get("request_config")
            return {
                "thought": "I am hungry and should get food now.",
                "action": "Gather",
                "target": "refrigerator",
                "detail": "opening the refrigerator to gather food items",
                "duration": 10,
                "reasoning": "Hunger is the dominant need.",
            }

        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                get_str_iss=lambda: "Klaus Mueller is a focused graduate student.",
                get_str_firstname=lambda: "Klaus",
            )
        )

        with patch.object(prompt_module, "generate_prompt", side_effect=fake_generate_prompt), \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", side_effect=fake_safe_generate_response):
            result = prompt_module.run_gpt_prompt_joint_decision(
                persona,
                nearby_resources=["refrigerator", "cafe counter"],
                temporal_context="- Current Time: Tuesday July 02, 2026, 12:10 PM",
                status_summary="Satiety is critically low, hunger is urgent.",
                rules="Must gather food from a valid source if inventory is empty.",
                cooperative_context="No special cooperative tasks.",
                last_action_desc="writing his research paper",
                intent_memory_summary="Standard food sources reduce replanning.",
                decision_convergence_hint="Choose the most immediate next action only.",
                request_config=config,
            )

        self.assertEqual(result["action"], "Gather")
        self.assertEqual(result["target"], "refrigerator")
        self.assertEqual(captured["prompt_kind"], "joint_decision")
        self.assertEqual(captured["request_config"], config)
        self.assertIn("joint_decision_v1.txt", captured["prompt_template"])
        joined_prompt = "\n".join(str(item) for item in captured["prompt_input"])
        self.assertIn("Choose the most immediate next action only.", joined_prompt)
        self.assertIn("Standard food sources reduce replanning.", joined_prompt)

    def test_joint_template_places_decision_capsule_before_identity(self):
        template_path = ROOT / "reverie" / "backend_server" / "persona" / "prompt_template" / "v2" / "joint_decision_v1.txt"
        template = template_path.read_text(encoding="utf-8")

        self.assertLess(template.index("Decision Capsule:"), template.index("Background Identity:"))
        self.assertIn("Do not weigh all information equally.", template)


class DecisionPipelineFallbackTests(unittest.TestCase):
    def tearDown(self):
        clear_cached_decisions()

    def setUp(self):
        self.persona = SimpleNamespace(
            name="Klaus Mueller",
            scratch=SimpleNamespace(
                satiety=24.0,
                stamina=62.0,
                health=91.0,
                mood=55.0,
                get_str_firstname=lambda: "Klaus",
                pending_interrupt=None,
                planned_path=[],
                is_moving_to_action=lambda: False,
            ),
        )

    def test_joint_pipeline_uses_joint_result_when_enabled(self):
        config = {"api_key": "cloud-key", "api_base": "https://api.example/v1", "model": "cloud-model"}
        with patch.dict(os.environ, {"ENABLE_JOINT_DECISION_PIPELINE": "1"}, clear=False), \
             patch.object(plan_module, "get_default_decision_request_config", return_value=config), \
             patch.object(plan_module, "run_gpt_prompt_joint_decision", return_value={
                 "thought": "I should gather food from the refrigerator now.",
                 "action": "Gather",
                 "target": "refrigerator",
                 "detail": "opening the refrigerator to gather food items",
                 "duration": 10,
                 "reasoning": "Hunger is urgent.",
             }) as joint_mock, \
             patch.object(plan_module, "run_gpt_prompt_demand_thinking", side_effect=AssertionError("should not fallback to demand thinking")), \
             patch.object(plan_module, "run_gpt_prompt_action_translation", side_effect=AssertionError("should not fallback to action translation")):
            thinking_text, decision, hint, used_joint, timing_meta, cache_signature = plan_module._run_decision_pipeline(
                self.persona,
                object_states=["refrigerator", "cafe counter"],
                temporal_context="- Current Time: Tuesday July 02, 2026, 12:10 PM",
                status_summary="Hunger is the dominant need.",
                physiological_rules="Must gather food from a valid nearby source.",
                cooperative_context="No special cooperative tasks.",
                last_action_desc="writing his research paper",
                intent_memory_summary="Direct food sources reduce delay.",
            )

        self.assertTrue(used_joint)
        self.assertEqual(thinking_text, "I should gather food from the refrigerator now.")
        self.assertEqual(decision["action"], "Gather")
        self.assertGreaterEqual(timing_meta["joint_decision"], 0.0)
        self.assertEqual(timing_meta["demand_thinking"], 0.0)
        self.assertIsNone(cache_signature)
        self.assertIn("Relevant experience already helped narrow the choice", hint)
        joint_mock.assert_called_once()
        self.assertEqual(joint_mock.call_args.kwargs["request_config"], config)

    def test_joint_pipeline_falls_back_when_joint_result_missing_action(self):
        config = {"api_key": "cloud-key", "api_base": "https://api.example/v1", "model": "cloud-model"}
        with patch.dict(os.environ, {"ENABLE_JOINT_DECISION_PIPELINE": "1"}, clear=False), \
             patch.object(plan_module, "get_default_decision_request_config", return_value=config), \
             patch.object(plan_module, "run_gpt_prompt_joint_decision", return_value={"thought": "I should get food."}) as joint_mock, \
             patch.object(plan_module, "run_gpt_prompt_demand_thinking", return_value="I should get food from the cafe counter now.") as thinking_mock, \
             patch.object(plan_module, "run_gpt_prompt_action_translation", return_value={
                 "action": "Gather",
                 "target": "cafe counter",
                 "detail": "getting prepared food from the cafe counter",
                 "duration": 10,
                 "reasoning": "Fallback translation path.",
             }) as translation_mock:
            thinking_text, decision, hint, used_joint, timing_meta, cache_signature = plan_module._run_decision_pipeline(
                self.persona,
                object_states=["refrigerator", "cafe counter"],
                temporal_context="- Current Time: Tuesday July 02, 2026, 12:10 PM",
                status_summary="Hunger is the dominant need.",
                physiological_rules="Must gather food from a valid nearby source.",
                cooperative_context="No special cooperative tasks.",
                last_action_desc="writing his research paper",
                intent_memory_summary="No especially relevant prior experience was retrieved.",
            )

        self.assertFalse(used_joint)
        self.assertEqual(thinking_text, "I should get food from the cafe counter now.")
        self.assertEqual(decision["target"], "cafe counter")
        self.assertGreaterEqual(timing_meta["joint_decision"], 0.0)
        self.assertGreaterEqual(timing_meta["demand_thinking"], 0.0)
        self.assertGreaterEqual(timing_meta["action_translation"], 0.0)
        self.assertIsNone(cache_signature)
        self.assertIn("Preserve the immediate intent", hint)
        joint_mock.assert_called_once()
        thinking_mock.assert_called_once()
        translation_mock.assert_called_once()
        self.assertEqual(joint_mock.call_args.kwargs["request_config"], config)
        self.assertEqual(thinking_mock.call_args.kwargs["request_config"], config)
        self.assertEqual(translation_mock.call_args.kwargs["request_config"], config)

    def test_semantic_cache_hit_skips_llm_pipeline(self):
        with patch.dict(os.environ, {"ENABLE_SEMANTIC_DECISION_CACHE": "1"}, clear=False), \
             patch.object(plan_module, "get_default_decision_request_config", return_value={"api_key": "cloud-key", "api_base": "https://api.example/v1", "model": "cloud-model"}):
            cache_signature = plan_module._build_decision_state_signature(
                self.persona,
                "restore_satiety",
                ["refrigerator", "cafe counter"],
                "No special cooperative tasks or wait states are active nearby.",
            )
            put_cached_decision(
                cache_signature,
                {
                    "thought": "I should gather food from the refrigerator now.",
                    "action": "Gather",
                    "target": "refrigerator",
                    "detail": "opening the refrigerator to gather food items",
                    "duration": 10,
                    "reasoning": "Cached hunger decision.",
                },
            )
            with patch.object(plan_module, "run_gpt_prompt_joint_decision", side_effect=AssertionError("should not call joint llm")), \
                 patch.object(plan_module, "run_gpt_prompt_demand_thinking", side_effect=AssertionError("should not call thinking llm")), \
                 patch.object(plan_module, "run_gpt_prompt_action_translation", side_effect=AssertionError("should not call translation llm")):
                thinking_text, decision, hint, used_joint, timing_meta, returned_signature = plan_module._run_decision_pipeline(
                    self.persona,
                    object_states=["refrigerator", "cafe counter"],
                    temporal_context="- Current Time: Tuesday July 02, 2026, 12:10 PM",
                    status_summary="Hunger is the dominant need.",
                    physiological_rules="Must gather food from a valid nearby source.",
                    cooperative_context="No special cooperative tasks or wait states are active nearby.",
                    last_action_desc="writing his research paper",
                    intent_memory_summary="Direct food sources reduce delay.",
                    intent_family="restore_satiety",
                )

        self.assertFalse(used_joint)
        self.assertEqual(decision["target"], "refrigerator")
        self.assertEqual(thinking_text, "I should gather food from the refrigerator now.")
        self.assertEqual(timing_meta["decision_cache_hit"], 1.0)
        self.assertEqual(returned_signature, cache_signature)

    def test_invalid_target_triggers_single_retry(self):
        self.persona.scratch.get_recent_invalid_targets = lambda max_age_steps=6: ["apple tree"]
        config = {"api_key": "cloud-key", "api_base": "https://api.example/v1", "model": "cloud-model"}

        with patch.dict(os.environ, {"ENABLE_JOINT_DECISION_PIPELINE": "1"}, clear=False), \
             patch.object(plan_module, "get_default_decision_request_config", return_value=config), \
             patch.object(plan_module, "run_gpt_prompt_joint_decision", side_effect=[
                 {
                     "thought": "I should gather apples from the apple tree now.",
                     "action": "Gather",
                     "target": "apple tree",
                     "detail": "gathering apples from the apple tree",
                     "duration": 10,
                     "reasoning": "Apples are food.",
                 },
                 {
                     "thought": "I should gather food from the refrigerator now.",
                     "action": "Gather",
                     "target": "refrigerator",
                     "detail": "opening the refrigerator to gather food items",
                     "duration": 10,
                     "reasoning": "The refrigerator is still feasible.",
                 },
             ]) as joint_mock, \
             patch.object(plan_module, "run_gpt_prompt_demand_thinking", side_effect=AssertionError("should stay on joint pipeline")), \
             patch.object(plan_module, "run_gpt_prompt_action_translation", side_effect=AssertionError("should stay on joint pipeline")), \
             patch.object(plan_module, "append_debug_log") as log_mock:
            thinking_text, decision, hint, used_joint, timing_meta, cache_signature = plan_module._run_decision_pipeline(
                self.persona,
                object_states=["apple tree", "refrigerator", "cafe counter"],
                temporal_context="- Current Time: Tuesday July 02, 2026, 12:10 PM",
                status_summary="Hunger is the dominant need.",
                physiological_rules="Must gather food from a valid nearby source.",
                cooperative_context="No special cooperative tasks.",
                last_action_desc="walking toward Johnson Park",
                intent_memory_summary="Direct food sources reduce delay.",
            )

        self.assertTrue(used_joint)
        self.assertEqual(thinking_text, "I should gather food from the refrigerator now.")
        self.assertEqual(decision["target"], "refrigerator")
        self.assertEqual(joint_mock.call_count, 2)
        self.assertIsNone(cache_signature)
        self.assertGreaterEqual(timing_meta["joint_decision"], 0.0)
        self.assertIn("invalid for this step", joint_mock.call_args_list[1].kwargs["decision_convergence_hint"])
        self.assertEqual(joint_mock.call_args_list[0].kwargs["request_config"], config)
        self.assertEqual(joint_mock.call_args_list[1].kwargs["request_config"], config)
        log_mock.assert_called()
        constraint_log = log_mock.call_args.args[1]
        self.assertEqual(constraint_log["pipeline"], "joint_decision")
        self.assertEqual(constraint_log["minimal_filter_enabled"], True)
        self.assertEqual(constraint_log["minimal_filter_applied"], True)
        self.assertEqual(constraint_log["minimal_filter_summary"]["invalid_targets"], ["apple tree"])


if __name__ == "__main__":
    unittest.main()
