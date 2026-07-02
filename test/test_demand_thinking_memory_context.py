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


class DemandThinkingMemoryContextTests(unittest.TestCase):
    def test_prompt_contains_intent_memory_summary(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                inventory={},
                curr_time=datetime.datetime(2026, 7, 2, 9, 30, 0),
                satiety=18.0,
                stamina=80.0,
                health=90.0,
                mood=65.0,
                get_str_iss=lambda: "Name: Maria Lopez",
                get_str_firstname=lambda: "Maria",
            )
        )
        captured = {}

        def fake_generate_prompt(prompt_input, prompt_template):
            captured["prompt_input"] = prompt_input
            return "\n".join(str(item) for item in prompt_input)

        with patch.object(prompt_module, "generate_prompt", side_effect=fake_generate_prompt), \
             patch.object(prompt_module, "ChatGPT_request", return_value="I want to gather food from the refrigerator."):
            result = prompt_module.run_gpt_prompt_demand_thinking(
                persona,
                ["refrigerator", "stove"],
                temporal_context="- Current Time: Wednesday July 02, 2026, 09:30 AM",
                status_summary="Satiety is low and food should become the top priority.",
                rules="Gathering food restores survival options.",
                cooperative_context="No special cooperative tasks are active nearby.",
                last_action_desc="walking through the dorm common room",
                intent_memory_summary="Relevant prior food-related experience:\n- Maria Lopez gathered apples from the refrigerator and restored her satiety effectively.",
            )

        self.assertIn("refrigerator", result.lower())
        joined_prompt = "\n".join(str(item) for item in captured["prompt_input"])
        self.assertIn("Relevant prior food-related experience", joined_prompt)
        self.assertIn("restored her satiety effectively", joined_prompt)

    def test_prompt_contains_convergence_guidance_for_in_transit_and_experience(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                inventory={},
                curr_time=datetime.datetime(2026, 7, 2, 9, 30, 0),
                satiety=18.0,
                stamina=80.0,
                health=90.0,
                mood=65.0,
                act_description="walking to the refrigerator",
                act_address="the Ville:Dorm:Kitchen:refrigerator",
                planned_path=[(10, 10), (10, 11)],
                pending_interrupt={
                    "reason": "alien_encounter",
                    "source": "perception",
                    "payload": {"entity": "alien", "distance": 2},
                },
                is_moving_to_action=lambda: True,
                get_str_iss=lambda: "Name: Maria Lopez",
                get_str_firstname=lambda: "Maria",
            )
        )
        captured = {}

        def fake_generate_prompt(prompt_input, prompt_template):
            captured["prompt_input"] = prompt_input
            return "\n".join(str(item) for item in prompt_input)

        with patch.object(prompt_module, "generate_prompt", side_effect=fake_generate_prompt), \
             patch.object(prompt_module, "ChatGPT_request", return_value="I want to keep moving toward the refrigerator unless the alien blocks the way."):
            prompt_module.run_gpt_prompt_demand_thinking(
                persona,
                ["refrigerator", "stove"],
                temporal_context="- Current Time: Wednesday July 02, 2026, 09:30 AM",
                status_summary="Satiety is low and food should become the top priority.",
                rules="Gathering food restores survival options.",
                cooperative_context="A strange alien has just appeared nearby.",
                last_action_desc="walking through the dorm common room",
                intent_memory_summary="Relevant prior food-related experience:\n- Maria Lopez gathered apples from the refrigerator and restored her satiety effectively.",
            )

        joined_prompt = "\n".join(str(item) for item in captured["prompt_input"])
        self.assertIn("still on the way to execute the previous decision result", joined_prompt)
        self.assertIn("focus only on the latest change", joined_prompt)
        self.assertIn("alien_encounter", joined_prompt)
        self.assertIn("Relevant prior experience has already narrowed the likely good options", joined_prompt)

    def test_prompt_contains_no_experience_convergence_guidance_when_memory_missing(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                inventory={},
                curr_time=datetime.datetime(2026, 7, 2, 9, 30, 0),
                satiety=55.0,
                stamina=45.0,
                health=90.0,
                mood=65.0,
                act_description=None,
                act_address=None,
                planned_path=[],
                pending_interrupt=None,
                is_moving_to_action=lambda: False,
                get_str_iss=lambda: "Name: Maria Lopez",
                get_str_firstname=lambda: "Maria",
            )
        )
        captured = {}

        def fake_generate_prompt(prompt_input, prompt_template):
            captured["prompt_input"] = prompt_input
            return "\n".join(str(item) for item in prompt_input)

        with patch.object(prompt_module, "generate_prompt", side_effect=fake_generate_prompt), \
             patch.object(prompt_module, "ChatGPT_request", return_value="I want to rest on the sofa for a while."):
            prompt_module.run_gpt_prompt_demand_thinking(
                persona,
                ["bed", "sofa"],
                temporal_context="- Current Time: Wednesday July 02, 2026, 09:30 AM",
                status_summary="Stamina is getting low.",
                rules="Resting can restore stamina.",
                cooperative_context="No special cooperative tasks are active nearby.",
                last_action_desc="finishing a long study session",
                intent_memory_summary=None,
            )

        joined_prompt = "\n".join(str(item) for item in captured["prompt_input"])
        self.assertIn("not currently committed to an in-progress travel route", joined_prompt)
        self.assertIn("No strongly relevant prior experience was retrieved", joined_prompt)

    def test_prompt_compacts_large_resource_context(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                inventory={},
                curr_time=datetime.datetime(2026, 7, 2, 9, 30, 0),
                satiety=42.0,
                stamina=65.0,
                health=90.0,
                mood=65.0,
                act_description=None,
                act_address=None,
                planned_path=[],
                pending_interrupt=None,
                is_moving_to_action=lambda: False,
                get_str_iss=lambda: "Name: Maria Lopez\nLifestyle: studying and part-time work",
                get_str_firstname=lambda: "Maria",
            )
        )
        captured = {}
        nearby_resources = [
            "refrigerator (current state: someone waiting nearby)",
            "refrigerator (current state: someone waiting nearby)",
            "stove (idle/normal)",
            "apple tree (idle/normal)",
            "cafe counter (idle/normal)",
            "sofa (idle/normal)",
            "bed (idle/normal)",
            "desk (idle/normal)",
            "bookshelf (idle/normal)",
            "tv (idle/normal)",
            "piano (idle/normal)",
            "blackboard (idle/normal)",
            "game console (idle/normal)",
            "library table (idle/normal)",
        ]

        def fake_generate_prompt(prompt_input, prompt_template):
            captured["prompt_input"] = prompt_input
            return "\n".join(str(item) for item in prompt_input)

        with patch.object(prompt_module, "generate_prompt", side_effect=fake_generate_prompt), \
             patch.object(prompt_module, "ChatGPT_request", return_value="I want to gather food from the refrigerator."):
            prompt_module.run_gpt_prompt_demand_thinking(
                persona,
                nearby_resources,
                temporal_context="- Current Time: Wednesday July 02, 2026, 09:30 AM\n- Extra line that should be compacted",
                status_summary="Satiety is stable.",
                rules="Rule 1\nRule 2\nRule 3\nRule 4\nRule 5\nRule 6\nRule 7",
                cooperative_context="No special cooperative tasks are active nearby.",
                last_action_desc="walking through the dorm common room while thinking about what to do next",
                intent_memory_summary="No especially relevant prior experience was retrieved.",
            )

        prompt_input = captured["prompt_input"]
        resource_context = prompt_input[6]
        temporal_context = prompt_input[7]
        rules_context = prompt_input[9]
        self.assertIn("refrigerator", resource_context)
        self.assertIn("additional known resources omitted", resource_context)
        self.assertEqual(resource_context.lower().count("refrigerator"), 1)
        self.assertIn("Current Time", temporal_context)
        self.assertNotIn("Extra line that should be compacted", temporal_context)
        self.assertIn("more lines omitted", rules_context)


if __name__ == "__main__":
    unittest.main()
