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


if __name__ == "__main__":
    unittest.main()
