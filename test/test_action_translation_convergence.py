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


class ActionTranslationConvergenceTests(unittest.TestCase):
    def test_translation_prompt_contains_convergence_guidance(self):
        captured = {}
        config = {"api_key": "cloud-key", "api_base": "https://api.example/v1", "model": "cloud-model"}

        def fake_generate_prompt(prompt_input, prompt_template):
            captured["prompt_input"] = prompt_input
            return "\n".join(str(item) for item in prompt_input)

        def fake_safe_generate_response(*args, **kwargs):
            captured["request_config"] = kwargs.get("request_config")
            return {
                "action": "Gather",
                "target": "cafe counter",
                "detail": "getting food from the cafe counter",
                "duration": 20,
                "reasoning": "Direct food source",
            }

        with patch.object(prompt_module, "generate_prompt", side_effect=fake_generate_prompt), \
             patch.object(
                 prompt_module,
                 "ChatGPT_safe_generate_response",
                 side_effect=fake_safe_generate_response,
             ):
            result = prompt_module.run_gpt_prompt_action_translation(
                "I am extremely hungry, so I want to go to Hobbs Cafe for some food.",
                ["cafe counter", "refrigerator"],
                "Maria",
                decision_convergence_hint=(
                    "The agent is still in transit, so preserve the current route unless the thought names a new urgent target."
                ),
                request_config=config,
            )

        self.assertEqual(result["action"], "Gather")
        self.assertEqual(captured["request_config"], config)
        joined_prompt = "\n".join(str(item) for item in captured["prompt_input"])
        self.assertIn("still in transit", joined_prompt)
        self.assertIn("preserve the current route", joined_prompt)

    def test_translation_prompt_uses_default_convergence_guidance(self):
        captured = {}

        def fake_generate_prompt(prompt_input, prompt_template):
            captured["prompt_input"] = prompt_input
            return "\n".join(str(item) for item in prompt_input)

        with patch.object(prompt_module, "generate_prompt", side_effect=fake_generate_prompt), \
             patch.object(
                 prompt_module,
                 "ChatGPT_safe_generate_response",
                 return_value={
                     "action": "Rest",
                     "target": "sofa",
                     "detail": "resting on the sofa",
                     "duration": 20,
                     "reasoning": "Simple immediate mapping",
                 },
             ):
            result = prompt_module.run_gpt_prompt_action_translation(
                "I want to rest on the sofa for a while.",
                ["sofa", "bed"],
                "Maria",
            )

        self.assertEqual(result["target"], "sofa")
        joined_prompt = "\n".join(str(item) for item in captured["prompt_input"])
        self.assertIn("Translate the intent faithfully", joined_prompt)

    def test_translation_uses_single_retry_by_default(self):
        captured = {}

        def fake_safe_generate_response(*args, **kwargs):
            captured["repeat"] = kwargs.get("repeat")
            return {
                "action": "Gather",
                "target": "refrigerator",
                "detail": "opening the refrigerator",
                "duration": 10,
                "reasoning": "Direct mapping",
            }

        with patch.object(prompt_module, "generate_prompt", return_value="translation prompt"), \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", side_effect=fake_safe_generate_response):
            result = prompt_module.run_gpt_prompt_action_translation(
                "I should open the refrigerator.",
                ["refrigerator (current state: idle/normal)", "refrigerator"],
                "Maria",
            )

        self.assertEqual(result["target"], "refrigerator")
        self.assertEqual(captured["repeat"], 1)

    def test_translation_prompt_reuses_stage1_capsule_context_when_persona_present(self):
        captured = {}
        persona = SimpleNamespace(
            name="Isabella Rodriguez",
            scratch=SimpleNamespace(
                curr_time=None,
                inventory={},
                satiety=39.9,
                stamina=80.0,
                health=95.0,
                mood=50.0,
            ),
        )
        compiled_context = {
            "dynamic_fields": {
                "world_rules_text": "Sandbox rules.",
                "drive_system_summary_text": "satiety=food pressure",
                "motive_guidance_text": "dominant=satiety urgency=warning secondary=mood",
                "other_people_prediction_text": (
                    "Other People / Predicted Behavior:\n"
                    "- Klaus Mueller\n"
                    "  - likely_current_motive: satiety (secondary mood)\n"
                    "  - suggested_use_now: Use as an indirect path to food access."
                ),
                "decision_social_context_text": "Klaus Mueller: trust=0.50",
                "relevant_experience_text": "No especially relevant prior experience was retrieved.",
                "strong_avoid_experience_text": "None.",
                "strong_prefer_experience_text": "None.",
                "experience_guidance_text": "Prioritize strong recent instance-level experience.",
                "action_schema_text": "ACTION_SCHEMA_TEXT",
            },
            "trace_payload": {"stage1_dynamic_fields": {"motive_guidance_text": "dominant=satiety"}},
        }

        def fake_generate_prompt(prompt_input, prompt_template):
            captured["prompt_input"] = prompt_input
            return "\n".join(str(item) for item in prompt_input)

        with patch.object(prompt_module, "compile_stage1_prompt_context", return_value=compiled_context), \
             patch.object(prompt_module, "generate_prompt", side_effect=fake_generate_prompt), \
             patch.object(
                 prompt_module,
                 "ChatGPT_safe_generate_response",
                 return_value={
                     "action": "Gather",
                     "target": "refrigerator",
                     "detail": "opening the refrigerator to gather food items",
                     "duration": 10,
                     "reasoning": "Direct food access",
                 },
             ):
            result = prompt_module.run_gpt_prompt_action_translation(
                "I should gather food from the refrigerator now.",
                ["refrigerator", "apple tree"],
                "Isabella",
                persona=persona,
                temporal_context="- Current Time: Saturday July 11, 2026, 08:00 AM",
                status_summary="Satiety is below the safe band.",
                rules="Gather food before consuming it.",
                cooperative_context="No special cooperative tasks are active nearby.",
                last_action_desc="standing near the cafe entrance",
                intent_memory_summary="No especially relevant prior experience was retrieved.",
                static_resource_context_text=(
                    "可达的资源/场所:\n"
                    "  refrigerator:\n"
                    "    用途: 可获取 / 储存食物"
                ),
            )

        self.assertEqual(result["target"], "refrigerator")
        self.assertEqual(captured["prompt_input"][2], "ACTION_SCHEMA_TEXT")
        joined_prompt = "\n".join(str(item) for item in captured["prompt_input"])
        self.assertIn("可达的资源/场所:", joined_prompt)
        self.assertIn("refrigerator:", joined_prompt)
        self.assertIn("Available People nearby:", joined_prompt)
        self.assertIn("Klaus Mueller", joined_prompt)
        self.assertIn("ExperienceGuard", joined_prompt)

    def test_translation_accepts_new_stage1_first_person_paragraph_style(self):
        captured = {}
        persona = SimpleNamespace(
            name="Isabella Rodriguez",
            scratch=SimpleNamespace(
                curr_time=None,
                inventory={},
                satiety=39.9,
                stamina=80.0,
                health=95.0,
                mood=50.0,
            ),
        )
        stage1_paragraph = (
            "I will go to the refrigerator now to get food, because hunger is my most urgent need. "
            "My mood is a little low too, but it should stay secondary until I secure a reliable way to eat."
        )

        def fake_generate_prompt(prompt_input, prompt_template):
            captured["prompt_input"] = prompt_input
            return "\n".join(str(item) for item in prompt_input)

        def fake_safe_generate_response(prompt, example_output, special_instruction, **kwargs):
            captured["special_instruction"] = special_instruction
            return {
                "action": "Gather",
                "target": "refrigerator",
                "detail": "opening the refrigerator to gather food items",
                "duration": 10,
                "reasoning": "The paragraph's first sentence names an immediate food-gathering action.",
            }

        with patch.object(prompt_module, "generate_prompt", side_effect=fake_generate_prompt), \
             patch.object(
                 prompt_module,
                 "ChatGPT_safe_generate_response",
                 side_effect=fake_safe_generate_response,
             ):
            result = prompt_module.run_gpt_prompt_action_translation(
                stage1_paragraph,
                ["refrigerator", "common room sofa"],
                "Isabella",
                persona=persona,
                temporal_context="- Current Time: Saturday July 11, 2026, 08:00 AM",
                status_summary="Satiety is below the safe band and mood is also below safe.",
                rules="Gather food before consuming it.",
                cooperative_context="No special cooperative tasks are active nearby.",
                last_action_desc="standing in the cafe before opening",
                intent_memory_summary="No especially relevant prior experience was retrieved.",
                static_resource_context_text=(
                    "可达的资源/场所:\n"
                    "  refrigerator:\n"
                    "    用途: 可获取 / 储存食物\n"
                    "  common room sofa:\n"
                    "    用途: 休息 / 放松"
                ),
            )

        self.assertEqual(result["action"], "Gather")
        self.assertEqual(result["target"], "refrigerator")
        self.assertEqual(captured["prompt_input"][0], stage1_paragraph)
        joined_prompt = "\n".join(str(item) for item in captured["prompt_input"])
        self.assertIn("hunger is my most urgent need", joined_prompt)
        self.assertIn("mood is a little low too", joined_prompt)
        self.assertIn("refrigerator:", joined_prompt)
        self.assertIn("common room sofa:", joined_prompt)
        self.assertIn("Do not invent a different immediate plan", captured["special_instruction"])


if __name__ == "__main__":
    unittest.main()
