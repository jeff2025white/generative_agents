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
from persona.cognitive_modules.stage1_prompt_compiler import (
    WORLD_RULES_TEXT,
    build_background_identity_text,
    build_experience_priority_texts,
    build_motive_guidance_text,
    build_world_rules_text,
)


class DemandThinkingMemoryContextTests(unittest.TestCase):
    def test_build_experience_priority_texts_prefers_instance_failure_over_generic_success(self):
        scratch = SimpleNamespace(
            get_experience_priority_units=lambda intent_family=None: [
                {
                    "experience_kind": "avoid",
                    "intent_family": "restore_satiety",
                    "resource_instance_key": "the ville:hobbs cafe:cafe:refrigerator",
                    "resource_type": "refrigerator",
                    "recommendation": "avoid_this_instance",
                    "confidence": 0.88,
                    "evidence_summary": "refrigerator at Hobbs Cafe was empty recently.",
                },
                {
                    "experience_kind": "prefer",
                    "intent_family": "restore_satiety",
                    "resource_instance_key": "the ville:johnson park:park:apple tree",
                    "resource_type": "apple tree",
                    "recommendation": "prefer_this_instance",
                    "confidence": 0.79,
                    "evidence_summary": "apple tree worked well recently.",
                },
            ]
        )
        persona = SimpleNamespace(name="Isabella Rodriguez", scratch=scratch)

        blocks = build_experience_priority_texts(persona, intent_family="restore_satiety")

        self.assertIn("Hobbs Cafe", blocks["StrongAvoidExperience"])
        self.assertIn("apple tree", blocks["StrongPreferExperience"])
        self.assertIn("instance-level experience over older generic memories", blocks["ExperienceGuidance"])

    def test_static_resource_context_lists_key_resources_from_map(self):
        tile_data = {
            (1, 1): {"collision": False},
            (2, 2): {"collision": False},
            (3, 3): {"collision": False},
            (6, 6): {"collision": False},
            (7, 7): {"collision": False},
            (8, 8): {"collision": False},
            (9, 9): {"collision": False},
            (10, 10): {"collision": False},
            (11, 11): {"collision": False},
            (12, 12): {"collision": False},
            (13, 13): {"collision": False},
            (14, 14): {"collision": False},
            (4, 4): {"collision": True},
            (4, 3): {"collision": True},
            (4, 5): {"collision": True},
            (3, 4): {"collision": True},
            (5, 4): {"collision": True},
        }
        maze = SimpleNamespace(
            maze_name="unit_test_maze",
            address_tiles={
                "the Ville:park:green:apple tree": {(1, 1)},
                "the Ville:home:bedroom:bed": {(2, 2)},
                "the Ville:Hobbs Cafe:cafe:behind the cafe counter": {(3, 3)},
                "the Ville:community:center:common room sofa": {(6, 6)},
                "the Ville:library:study:computer desk": {(7, 7)},
                "the Ville:park:garden:garden chair": {(8, 8)},
                "the Ville:bar:service:behind the bar counter": {(9, 9)},
                "the Ville:bar:hall:bar customer seating": {(10, 10)},
                "the Ville:library:reading:library sofa": {(11, 11)},
                "the Ville:school:classroom:classroom student seating": {(12, 12)},
                "the Ville:school:classroom:classroom podium": {(13, 13)},
                "the Ville:home:recreation:game console": {(14, 14)},
                "the Ville:blocked room:kitchen:refrigerator": {(4, 4)},
            },
            access_tile=lambda tile: tile_data.get(tuple(tile), {"collision": True}),
        )
        persona = SimpleNamespace(scratch=SimpleNamespace())

        text = plan_module._build_static_resource_context_text(persona, maze)

        self.assertIn("可达的资源/场所:", text)
        self.assertIn("apple tree:", text)
        self.assertIn("用途: 可获取食物", text)
        self.assertIn("bed:", text)
        self.assertIn("用途: 休息 / 恢复体力", text)
        self.assertIn("behind the cafe counter:", text)
        self.assertIn("用途: 潜在食物来源 / 工作点位", text)
        self.assertIn("common room sofa:", text)
        self.assertIn("用途: 休息 / 放松", text)
        self.assertIn("computer desk:", text)
        self.assertIn("用途: 工作 / 学习", text)
        self.assertIn("behind the bar counter:", text)
        self.assertIn("用途: 社交服务 / 工作点位", text)
        self.assertIn("bar customer seating:", text)
        self.assertIn("用途: 社交 / 休息", text)
        self.assertIn("library sofa:", text)
        self.assertIn("用途: 休息 / 阅读", text)
        self.assertIn("classroom student seating:", text)
        self.assertIn("用途: 学习 / 听课", text)
        self.assertIn("classroom podium:", text)
        self.assertIn("用途: 教学 / 演讲", text)
        self.assertIn("game console:", text)
        self.assertIn("用途: 娱乐 / 情绪修复", text)
        self.assertNotIn("refrigerator:", text)

    def test_world_rules_text_uses_static_sandbox_rules(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                inventory={},
                get_recent_invalid_targets=lambda max_age_steps=6: ["apple tree"],
            )
        )

        rules_text = build_world_rules_text(
            persona,
            base_rules="Satiety<30 and inventory_empty => Gather(valid_food_source)",
        )

        self.assertEqual(rules_text, WORLD_RULES_TEXT)
        self.assertNotIn("Inventory is empty", rules_text)
        self.assertNotIn("apple tree", rules_text)

    def test_background_identity_omits_current_date(self):
        persona = SimpleNamespace(
            name="Maria Lopez",
            scratch=SimpleNamespace(
                curr_time=datetime.datetime(2026, 7, 9, 10, 30, 0),
                age=22,
                innate="kind and curious",
                learned="resourceful under pressure",
                currently="looking for breakfast",
                lifestyle="college student",
                daily_plan_req="attend class and finish homework",
            ),
        )

        background = build_background_identity_text(persona)

        self.assertIn("Name: Maria Lopez", background)
        self.assertNotIn("Current Date:", background)

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
            static_resource_context_text="可达的资源/场所:\n  apple tree:\n    用途: 可获取食物\n  bed:\n    用途: 休息",
        )

        self.assertIn("DecisionPriority:", capsule)
        self.assertIn("Rules:", capsule)
        self.assertIn("可达的资源/场所:", capsule)
        self.assertIn("apple tree:", capsule)
        self.assertIn("驱动力和满足方式:", capsule)
        self.assertIn("Experience:", capsule)
        self.assertIn("BackgroundRule:", capsule)
        self.assertNotIn("社交关系:", capsule)
        self.assertIn("LastAction: walking through the dorm common room | execution_status=unknown | failure_reason=none", capsule)
        self.assertNotIn("Observation:", capsule)
        self.assertNotIn("CurrentAction:", capsule)
        self.assertNotIn("Convergence:", capsule)
        self.assertNotIn("Status:", capsule)
        self.assertNotIn("Interpretation:", capsule)
        self.assertNotIn("DriveSystem:", capsule)
        self.assertNotIn("Social:", capsule)

    def test_build_motive_guidance_text_uses_neutral_text_for_stable_motives(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                satiety=91.4,
                stamina=94.4,
                health=88.0,
                mood=52.7,
                get_motive_attributes_snapshot=lambda: {
                    "satiety": {
                        "current_value": 91.4,
                        "initial_value": 62.0,
                        "safe_threshold": 50.0,
                        "critical_threshold": 25.0,
                        "decay_per_step": 0.08,
                    },
                    "stamina": {
                        "current_value": 94.4,
                        "initial_value": 100.0,
                        "safe_threshold": 45.0,
                        "critical_threshold": 20.0,
                        "decay_per_step": 0.04,
                    },
                    "health": {
                        "current_value": 88.0,
                        "initial_value": 90.0,
                        "safe_threshold": 55.0,
                        "critical_threshold": 25.0,
                        "priority_weight": 1.2,
                    },
                    "mood": {
                        "current_value": 52.7,
                        "initial_value": 60.0,
                        "safe_threshold": 50.0,
                        "critical_threshold": 30.0,
                        "decay_per_step": 0.03,
                    },
                },
            )
        )

        text = build_motive_guidance_text(persona)

        self.assertIn("dominant=satiety", text)
        self.assertIn("urgency=stable", text)
        self.assertIn("No urgent internal need dominates this step.", text)
        self.assertNotIn("secondary=unknown", text)
        self.assertNotIn("我很饿", text)

    def test_stable_motive_prompt_instruction_becomes_tie_breaker(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                satiety=91.4,
                stamina=94.4,
                health=88.0,
                mood=52.7,
                get_motive_attributes_snapshot=lambda: {
                    "satiety": {
                        "current_value": 91.4,
                        "initial_value": 62.0,
                        "safe_threshold": 50.0,
                        "critical_threshold": 25.0,
                        "decay_per_step": 0.08,
                    },
                    "stamina": {
                        "current_value": 94.4,
                        "initial_value": 100.0,
                        "safe_threshold": 45.0,
                        "critical_threshold": 20.0,
                        "decay_per_step": 0.04,
                    },
                    "health": {
                        "current_value": 88.0,
                        "initial_value": 90.0,
                        "safe_threshold": 55.0,
                        "critical_threshold": 25.0,
                        "priority_weight": 1.2,
                    },
                    "mood": {
                        "current_value": 52.7,
                        "initial_value": 60.0,
                        "safe_threshold": 50.0,
                        "critical_threshold": 30.0,
                        "decay_per_step": 0.03,
                    },
                },
            )
        )

        instruction = prompt_module._build_motive_prompt_instruction(persona)

        self.assertIn("internal motives are broadly stable", instruction)
        self.assertIn("light tie-breaker", instruction)
        self.assertNotIn("highest-priority internal guidance", instruction)

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
        self.assertIn("was not reachable", capsule)
        self.assertIn("Choose a different feasible target now.", capsule)
        self.assertIn("must not be selected", capsule)
        self.assertLess(capsule.index("NavigationFailure:"), capsule.index("LastAction:"))
        self.assertLess(capsule.index("DecisionPriority:"), capsule.index("LastAction:"))

    def test_decision_capsule_treats_empty_resource_as_execution_feedback(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                inventory={},
                curr_time=datetime.datetime(2026, 7, 2, 9, 35, 0),
                satiety=18.0,
                stamina=62.0,
                health=91.0,
                mood=55.0,
                get_recent_navigation_failure=lambda max_age_steps=6: {
                    "target": "refrigerator",
                    "target_address": "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
                    "reason": "resource_empty",
                    "curr_tile": [77, 16],
                    "payload": {"requested_target": "refrigerator"},
                },
                get_recent_action_observation=lambda max_age_steps=6: {
                    "result": "failed",
                    "target": "refrigerator",
                    "target_address": "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
                    "reason": "resource_empty",
                    "curr_step": 42,
                },
                recent_action_outcomes=[
                    {
                        "action": {
                            "skill_id": "gather",
                            "target": "refrigerator",
                            "target_address": "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
                        },
                        "execution": {
                            "result": "failed",
                            "reason": "resource_empty",
                        },
                        "effects": {},
                    }
                ],
            )
        )

        capsule = prompt_module.build_decision_capsule(
            persona,
            temporal_context="- Current Time: Wednesday July 02, 2026, 09:35 AM",
            status_summary="Satiety is low and food should become the top priority.",
            rules="If a resource is empty, use that result to choose the next immediate attempt.",
            cooperative_context="No special cooperative tasks are active nearby.",
            nearby_resources=["refrigerator (idle/normal)", "apple tree (idle/normal)"],
            last_action_desc="opening the refrigerator to gather food items",
            intent_memory_summary="Direct food sources reduce replanning.",
            decision_convergence_hint="Choose the immediate next action only.",
        )

        self.assertIn("ExecutionResult:", capsule)
        self.assertNotIn("Observation:", capsule)
        self.assertIn("RecentResult: failed gather -> refrigerator at kitchen / refrigerator: empty.", capsule)
        self.assertIn("Hint: try another refrigerator or another feasible option.", capsule)
        self.assertIn("LastAction: opening the refrigerator to gather food items | execution_status=failed | target=refrigerator | failure_reason=resource_empty", capsule)
        self.assertIn("refrigerator at kitchen / refrigerator was empty", capsule)
        self.assertIn("Try another instance or another feasible option.", capsule)
        self.assertNotIn("must not be selected", capsule)
        self.assertNotIn("InvalidTargets:", capsule)

    def test_decision_capsule_includes_completed_action_observation(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                inventory={"apple": 1},
                curr_time=datetime.datetime(2026, 7, 2, 9, 35, 0),
                satiety=58.0,
                stamina=62.0,
                health=91.0,
                mood=55.0,
                get_recent_navigation_failure=lambda max_age_steps=6: None,
                get_recent_action_observation=lambda max_age_steps=6: {
                    "result": "completed",
                    "target": "apple",
                    "target_address": "inventory",
                    "action_description": "eating the apple from inventory to restore satiety",
                    "curr_step": 43,
                },
                recent_action_outcomes=[
                    {
                        "action": {
                            "skill_id": "consume",
                            "target": "apple",
                            "target_address": "inventory",
                        },
                        "execution": {
                            "result": "success",
                            "reason": None,
                        },
                        "effects": {
                            "inventory_delta": {"apple": -1},
                        },
                    }
                ],
            )
        )

        capsule = prompt_module.build_decision_capsule(
            persona,
            temporal_context="- Current Time: Wednesday July 02, 2026, 09:35 AM",
            status_summary="Satiety has recovered.",
            rules="Use the latest execution feedback when choosing what to do next.",
            cooperative_context="No special cooperative tasks are active nearby.",
            nearby_resources=["apple tree (idle/normal)", "refrigerator (idle/normal)"],
            last_action_desc="eating the apple from inventory to restore satiety",
            intent_memory_summary="Direct food sources reduce replanning.",
            decision_convergence_hint="Choose the immediate next action only.",
        )

        self.assertNotIn("Observation:", capsule)
        self.assertIn("RecentResult: success consume -> apple.", capsule)
        self.assertIn("LastAction: eating the apple from inventory to restore satiety | execution_status=completed | target=apple | failure_reason=none", capsule)
        self.assertIn("outcome=eating the apple from inventory to restore satiety", capsule)
        self.assertIn("apple", capsule)

    def test_prompt_contains_intent_memory_summary(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                inventory={},
                curr_time=datetime.datetime(2026, 7, 2, 9, 30, 0),
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
                intent_memory_summary="Relevant prior food-related experience:\nSuccessful experience:\n- Maria Lopez gathered apples from the refrigerator and restored her satiety effectively.\nFailed attempts:\n- Maria Lopez reached an empty refrigerator and had to replan.",
            )

        self.assertIn("refrigerator", result.lower())
        joined_prompt = "\n".join(str(item) for item in captured["prompt_input"])
        self.assertIn("StrongAvoidExperience:", joined_prompt)
        self.assertIn("refrigerator at Dorm for Oak Hill College was empty recently.", joined_prompt)
        self.assertIn("StrongPreferExperience:", joined_prompt)
        self.assertIn("apple tree worked well recently.", joined_prompt)
        self.assertIn("ExperienceGuidance:", joined_prompt)
        self.assertIn("Experience:", joined_prompt)
        self.assertIn("restored her satiety effectively", joined_prompt)
        self.assertIn("Failed attempts:", joined_prompt)

    def test_prompt_places_social_context_after_other_people(self):
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

        compiled_context = {
            "background_identity_text": (
                "Name: Maria Lopez\n"
                "Age: 21\n"
                "其他人: Klaus Mueller: 天生特质=kind, calm"
            ),
            "dynamic_fields": {
                "world_rules_text": "Gathering food restores survival options.",
                "drive_system_summary_text": "satiety=food seeking",
                "motive_guidance_text": "dominant=satiety 我很饿，我很想进食。",
                "decision_social_context_text": "Klaus Mueller: 亲密程度=0.82，适合作为稳定社交对象。",
                "relevant_experience_text": "Relevant prior food-related experience.",
            },
        }

        with patch.object(prompt_module, "compile_stage1_prompt_context", return_value=compiled_context), \
             patch.object(prompt_module, "generate_prompt", side_effect=fake_generate_prompt), \
             patch.object(prompt_module, "ChatGPT_request", return_value="I want to gather food from the apple tree."):
            prompt_module.run_gpt_prompt_demand_thinking(
                persona,
                ["apple tree"],
                temporal_context="- Current Time: Wednesday July 02, 2026, 09:30 AM",
                status_summary="Satiety is low and food should become the top priority.",
                rules="Gathering food restores survival options.",
                cooperative_context="No special cooperative tasks are active nearby.",
                last_action_desc="walking outside",
                intent_memory_summary="Relevant prior food-related experience.",
            )

        identity_summary = captured["prompt_input"][0]
        decision_capsule = captured["prompt_input"][1]
        self.assertIn("其他人:", identity_summary)
        self.assertIn("社交关系:", identity_summary)
        self.assertLess(identity_summary.index("其他人:"), identity_summary.index("社交关系:"))
        self.assertNotIn("社交关系:", decision_capsule)

    def test_prompt_omits_convergence_guidance_for_in_transit_and_experience(self):
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
        self.assertNotIn("You are still on the way to execute the previous decision result", joined_prompt)
        self.assertNotIn("focus only on the latest change", joined_prompt)
        self.assertNotIn("alien_encounter", joined_prompt)
        self.assertNotIn("Relevant prior experience has already narrowed the likely good options", joined_prompt)

    def test_prompt_omits_convergence_guidance_when_memory_missing(self):
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
        self.assertNotIn("not currently committed to an in-progress travel route", joined_prompt)
        self.assertNotIn("No strongly relevant prior experience was retrieved", joined_prompt)

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
        self.assertIn("NavigationFailure: apple tree at park / apple tree was not reachable.", joined_prompt)
        self.assertIn("Choose a different feasible target now.", joined_prompt)
        self.assertNotIn("Decision Convergence Guidance:", joined_prompt)

    def test_prompt_includes_motive_guidance_text(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                inventory={},
                curr_time=datetime.datetime(2026, 7, 2, 9, 30, 0),
                satiety=62.0,
                stamina=72.0,
                health=90.0,
                mood=34.0,
                get_str_iss=lambda: "Name: Maria Lopez",
                get_str_firstname=lambda: "Maria",
            )
        )
        captured = {}

        def fake_generate_prompt(prompt_input, prompt_template):
            return "base-prompt"

        def fake_chatgpt_request(prompt, **kwargs):
            captured["prompt"] = prompt
            return "I want to take a calming walk."

        with patch.object(prompt_module, "generate_prompt", side_effect=fake_generate_prompt), \
             patch.object(prompt_module, "ChatGPT_request", side_effect=fake_chatgpt_request):
            prompt_module.run_gpt_prompt_demand_thinking(
                persona,
                ["park", "bench"],
                temporal_context="- Current Time: Wednesday July 02, 2026, 09:30 AM",
                status_summary="Mood is low and motivation is slipping.",
                rules="Restorative leisure can improve mood.",
                cooperative_context="No special cooperative tasks are active nearby.",
                last_action_desc="standing by the dorm entrance",
                intent_memory_summary="No especially relevant prior experience was retrieved.",
            )

        self.assertIn("Current motive guidance:", captured["prompt"])
        self.assertNotIn("Decision Convergence Guidance:", captured["prompt"])
        self.assertNotIn("Use this strict priority order:", captured["prompt"])
        self.assertNotIn("Write the answer in Maria's first-person voice.", captured["prompt"])

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
