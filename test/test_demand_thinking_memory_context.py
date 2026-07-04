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
    def test_demand_thinking_forwards_request_config(self):
        captured = {}
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
        config = {"api_key": "cloud-key", "api_base": "https://api.example/v1", "model": "cloud-model"}

        def fake_chatgpt_request(*args, **kwargs):
            captured["request_config"] = kwargs.get("request_config")
            return "I want to gather food from the refrigerator."

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "ChatGPT_request", side_effect=fake_chatgpt_request):
            prompt_module.run_gpt_prompt_demand_thinking(
                persona,
                ["refrigerator", "stove"],
                temporal_context="- Current Time: Wednesday July 02, 2026, 09:30 AM",
                status_summary="Satiety is low and food should become the top priority.",
                rules="Gathering food restores survival options.",
                cooperative_context="No special cooperative tasks are active nearby.",
                last_action_desc="walking through the dorm common room",
                intent_memory_summary="Relevant food experience.",
                request_config=config,
            )

        self.assertEqual(captured["request_config"], config)

    def test_decision_capsule_contains_status_rules_resources_and_memory(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                inventory={},
                curr_time=datetime.datetime(2026, 7, 2, 9, 30, 0),
                satiety=24.0,
                stamina=62.0,
                health=91.0,
                mood=55.0,
                get_recent_navigation_failure=lambda max_age_steps=6: None,
            )
        )

        capsule = prompt_module.build_decision_capsule(
            persona,
            temporal_context="- Current Time: Wednesday July 02, 2026, 09:30 AM",
            status_summary="Satiety is low and food should become the top priority.",
            rules="Satiety<30 and inventory_empty => Gather(valid_food_source)",
            cooperative_context="No special cooperative tasks are active nearby.",
            nearby_resources=["refrigerator (idle/normal)", "cafe counter (idle/normal)", "apple tree (idle/normal)"],
            last_action_desc="walking through the dorm common room",
            intent_memory_summary="Direct food sources reduce replanning.",
            decision_convergence_hint="Choose the immediate next action only.",
        )

        self.assertIn("DecisionPriority:", capsule)
        self.assertIn("Status:", capsule)
        self.assertIn("Rules:", capsule)
        self.assertIn("Resources:", capsule)
        self.assertIn("Experience:", capsule)
        self.assertIn("BackgroundRule:", capsule)

    def test_decision_capsule_includes_recent_navigation_failure(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                inventory={"apple": 24},
                curr_time=datetime.datetime(2026, 7, 2, 9, 35, 0),
                satiety=99.0,
                stamina=62.0,
                health=91.0,
                mood=55.0,
                get_recent_navigation_failure=lambda max_age_steps=6: {
                    "target": "apple tree",
                    "target_address": "the Ville:Johnson Park:park:apple tree",
                    "reason": "path_not_found",
                    "curr_tile": [77, 16],
                    "payload": {"target_tiles": [[24, 44], [25, 44]]},
                },
            )
        )

        capsule = prompt_module.build_decision_capsule(
            persona,
            temporal_context="- Current Time: Wednesday July 02, 2026, 09:35 AM",
            status_summary="Satiety is full and gathering more food is not urgent.",
            rules="Unreachable targets require replanning.",
            cooperative_context="No special cooperative tasks are active nearby.",
            nearby_resources=["apple tree (idle/normal)", "cafe counter (idle/normal)"],
            last_action_desc="heading toward the apple tree",
            intent_memory_summary="Gathering more apples is optional, not urgent.",
            decision_convergence_hint="Choose a different immediate action if the same target is unreachable.",
        )

        self.assertIn("NavigationFailure:", capsule)
        self.assertIn("InvalidTargets:", capsule)
        self.assertIn("apple tree", capsule)
        self.assertIn("unreachable", capsule.lower())
        self.assertIn("must choose a new feasible target", capsule)
        self.assertIn("must not be selected", capsule)
        self.assertLess(capsule.index("NavigationFailure:"), capsule.index("LastAction:"))
        self.assertLess(capsule.index("DecisionPriority:"), capsule.index("Status:"))

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
        self.assertIn("Experience:", joined_prompt)
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
        self.assertIn("You are still on the way to execute the previous decision result", joined_prompt)
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

    def test_prompt_contains_hard_replan_guidance_after_navigation_failure(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                inventory={"apple": 24},
                curr_time=datetime.datetime(2026, 7, 2, 9, 30, 0),
                satiety=98.6,
                stamina=97.1,
                health=100.0,
                mood=99.6,
                act_description="walking toward Johnson Park",
                act_address="the Ville:Johnson Park:park:apple tree",
                planned_path=[],
                pending_interrupt=None,
                is_moving_to_action=lambda: False,
                get_recent_navigation_failure=lambda max_age_steps=6: {
                    "target": "apple tree",
                    "target_address": "the Ville:Johnson Park:park:apple tree",
                    "reason": "path_not_found",
                    "curr_tile": [77, 16],
                    "payload": {"target_tiles": [[24, 44], [25, 44]]},
                },
                get_str_iss=lambda: "Name: Isabella Rodriguez",
                get_str_firstname=lambda: "Isabella",
            )
        )
        captured = {}

        def fake_generate_prompt(prompt_input, prompt_template):
            captured["prompt_input"] = prompt_input
            return "\n".join(str(item) for item in prompt_input)

        with patch.object(prompt_module, "generate_prompt", side_effect=fake_generate_prompt), \
             patch.object(prompt_module, "ChatGPT_request", return_value="I should try a different reachable option right now."):
            prompt_module.run_gpt_prompt_demand_thinking(
                persona,
                ["apple tree", "refrigerator", "cafe counter"],
                temporal_context="- Current Time: Wednesday July 02, 2026, 09:30 AM",
                status_summary="Satiety is already high and gathering more apples is not urgent.",
                rules="If the previous target is unreachable, choose a different feasible next step.",
                cooperative_context="No special cooperative tasks are active nearby.",
                last_action_desc="walking toward the apple tree",
                intent_memory_summary="No especially relevant prior experience was retrieved.",
            )

        joined_prompt = "\n".join(str(item) for item in captured["prompt_input"])
        self.assertIn("previous immediate action failed", joined_prompt)
        self.assertIn("must choose a new feasible target or a materially different plan right now", joined_prompt)

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
        decision_capsule = prompt_input[1]
        self.assertIn("Time: Current Time", decision_capsule)
        self.assertIn("Rules:", decision_capsule)
        resource_context = decision_capsule
        self.assertIn("refrigerator", resource_context)
        self.assertIn("additional known resources omitted", resource_context)
        self.assertEqual(resource_context.lower().count("refrigerator"), 1)
        self.assertNotIn("Extra line that should be compacted", decision_capsule)
        self.assertIn("more lines omitted", decision_capsule)

    def test_demand_template_places_decision_capsule_before_identity(self):
        template_path = ROOT / "reverie" / "backend_server" / "persona" / "prompt_template" / "v2" / "demand_decision_thinking_v1.txt"
        template = template_path.read_text(encoding="utf-8")

        self.assertLess(template.index("Decision Capsule:"), template.index("Background Identity:"))
        self.assertIn("Do not weigh all information equally.", template)


if __name__ == "__main__":
    unittest.main()
