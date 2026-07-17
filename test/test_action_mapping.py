import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from persona.cognitive_modules.action_command_utils import (
    build_decision_signature,
    infer_intent_family,
    normalize_skill_id,
)
from persona.cognitive_modules.action_target_resolver import (
    resolve_action_target_address,
    resolve_known_arena_address,
)
from persona.cognitive_modules.skill_packs.seek_and_chat_skill import SeekAndChatSkillPack
import persona.cognitive_modules.plan as plan_module
import persona.prompt_template.run_gpt_prompt as prompt_module


class DummyMaze:
    def __init__(self, addresses):
        self.address_tiles = {address: {(0, 0)} for address in addresses}

    def get_tile_path(self, tile, level):
        if level == "world":
            return "the Ville"
        if level == "sector":
            return "Hobbs Cafe"
        if level == "arena":
            return "cafe"
        if level == "game_object":
            return "cafe customer seating"
        return None


class DummySpatialMemory:
    def __init__(self):
        self.tree = {
            "the Ville": {
                "Dorm for Oak Hill College": {
                    "kitchen": {"refrigerator": {}},
                    "lobby kitchen": {"refrigerator": {}},
                    "music room": {"piano": {}},
                    "common room": {"sofa": {}},
                }
            }
        }

    def find_nearest_object(self, obj_name):
        lookup = {
            "refrigerator": "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
            "piano": "the Ville:Dorm for Oak Hill College:music room:piano",
            "sofa": "the Ville:Dorm for Oak Hill College:common room:sofa",
        }
        return lookup.get(str(obj_name).strip().lower())

    def find_all_objects(self, obj_name):
        lookup = {
            "refrigerator": [
                "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
                "the Ville:Dorm for Oak Hill College:lobby kitchen:refrigerator",
            ],
            "piano": ["the Ville:Dorm for Oak Hill College:music room:piano"],
            "sofa": ["the Ville:Dorm for Oak Hill College:common room:sofa"],
        }
        return list(lookup.get(str(obj_name).strip().lower(), []))


class ActionMappingTests(unittest.TestCase):
    def test_recreate_maps_to_specific_skills(self):
        self.assertEqual(
            normalize_skill_id("Recreate", target="piano", detail="singing at the piano"),
            "sing",
        )
        self.assertEqual(
            normalize_skill_id("Recreate", target="sofa", detail="taking a nap on the sofa"),
            "rest",
        )
        self.assertEqual(
            normalize_skill_id("Recreate", target="Maria Lopez", detail="chatting with Maria Lopez"),
            "chat with",
        )
        self.assertEqual(
            normalize_skill_id("Recreate", target="TV", detail="watching TV to relax"),
            "leisure_use",
        )
        self.assertEqual(
            normalize_skill_id("Recreate", target="pub", detail="hanging out at the pub to relax"),
            "hangout_social_venue",
        )

    def test_request_and_trade_map_to_resource_exchange_skills(self):
        self.assertEqual(
            normalize_skill_id("Request", target="Klaus Mueller", detail="asking Klaus Mueller for a snack"),
            "request",
        )
        self.assertEqual(
            normalize_skill_id("Trade", target="Isabella Rodriguez", detail="trading for food with Isabella Rodriguez"),
            "trade",
        )
        self.assertEqual(
            infer_intent_family(skill_id="Request", target="Klaus Mueller", detail="asking Klaus Mueller for a snack"),
            "restore_satiety",
        )
        self.assertEqual(
            infer_intent_family(skill_id="Trade", target="Isabella Rodriguez", detail="trading for food with Isabella Rodriguez"),
            "restore_satiety",
        )

    def test_coordinate_pressure_and_avoid_map_to_social_control_skills(self):
        self.assertEqual(
            normalize_skill_id("Coordinate", target="Klaus Mueller", detail="teaming up with Klaus Mueller"),
            "coordinate",
        )
        self.assertEqual(
            normalize_skill_id("Pressure", target="Isabella Rodriguez", detail="demanding compliance from Isabella Rodriguez"),
            "pressure",
        )
        self.assertEqual(
            normalize_skill_id("Avoid", target="Maria Lopez", detail="leaving to avoid Maria Lopez"),
            "avoid",
        )
        self.assertEqual(
            infer_intent_family(skill_id="Coordinate", target="Klaus Mueller", detail="teaming up with Klaus Mueller"),
            "communication",
        )
        self.assertEqual(
            infer_intent_family(skill_id="Pressure", target="Isabella Rodriguez", detail="demanding compliance from Isabella Rodriguez"),
            "communication",
        )
        self.assertEqual(
            infer_intent_family(skill_id="Avoid", target="Maria Lopez", detail="leaving to avoid Maria Lopez"),
            "avoid",
        )

    def test_socialize_with_place_targets_does_not_turn_into_chat(self):
        self.assertEqual(
            normalize_skill_id("Socialize", target="park", detail="going to the park to socialize and relax"),
            "wander",
        )
        self.assertEqual(
            normalize_skill_id("Socialize", target="pub", detail="hanging out at the pub with other patrons"),
            "hangout_social_venue",
        )
        self.assertEqual(
            normalize_skill_id("Socialize", target="Klaus Mueller", detail="chatting with Klaus Mueller about town gossip"),
            "chat with",
        )

    def test_work_and_use_map_to_stable_skill_ids(self):
        self.assertEqual(
            normalize_skill_id("Work", target="blackboard", detail="studying at the blackboard"),
            "study",
        )
        self.assertEqual(
            normalize_skill_id("Work", target="fitness machine", detail="using the fitness machine"),
            "use",
        )
        self.assertEqual(
            normalize_skill_id("use", target="piano", detail="using the piano to sing"),
            "sing",
        )
        self.assertEqual(
            normalize_skill_id("use", target="game console", detail="using the game console"),
            "use",
        )

    def test_internal_skill_ids_remain_stable_through_signature_building(self):
        self.assertEqual(
            normalize_skill_id("leisure_use", target="TV", detail="watching TV to relax"),
            "leisure_use",
        )
        self.assertEqual(
            normalize_skill_id("hangout_social_venue", target="bar customer seating", detail="relaxing at the bar customer seating"),
            "hangout_social_venue",
        )
        self.assertEqual(
            infer_intent_family(skill_id="leisure_use", target="TV", detail="watching TV to relax"),
            "leisure",
        )

        signature = build_decision_signature(
            action_command={
                "skill_id": "leisure_use",
                "target": "TV",
                "detail": "watching TV to relax",
            },
            action_description="watching TV to relax",
            action_address="the Ville:Hobbs Cafe:cafe",
        )

        self.assertEqual(signature["skill_id"], "leisure_use")
        self.assertEqual(signature["target"], "tv")
        self.assertEqual(signature["intent_family"], "leisure")

    def test_fitness_machine_prefers_gym_like_arena(self):
        maze = DummyMaze(
            [
                "the Ville:Hobbs Cafe:cafe",
                "the Ville:Dorm for Oak Hill College:gym",
                "the Ville:Dorm for Oak Hill College:common room",
            ]
        )
        address, resolved_name, resolved_kind = resolve_known_arena_address(
            maze,
            target="fitness machine",
            detail="using the fitness machine for a workout",
        )
        self.assertEqual(address, "the Ville:Dorm for Oak Hill College:gym")
        self.assertEqual(resolved_name, "gym")
        self.assertEqual(resolved_kind, "known_arena")

    def test_known_arena_resolution_skips_recent_failed_parent_arena(self):
        maze = DummyMaze(
            [
                "the Ville:Dorm for Oak Hill College:common room",
                "the Ville:Dorm for Oak Hill College:music room",
            ]
        )
        persona = type(
            "Persona",
            (),
            {
                "scratch": type(
                    "Scratch",
                    (),
                    {
                        "failed_resource_instances": [
                            {
                                "target": "piano",
                                "target_address": "the Ville:Dorm for Oak Hill College:music room:piano",
                                "reason": "path_not_found",
                                "curr_step": 12,
                                "expires_after_step": 18,
                            }
                        ],
                        "successful_resource_instances": [],
                    },
                )(),
            },
        )()

        address, resolved_name, resolved_kind = resolve_known_arena_address(
            maze,
            target="piano",
            detail="using the piano to sing",
            persona=persona,
        )

        self.assertEqual(address, "the Ville:Dorm for Oak Hill College:common room")
        self.assertEqual(resolved_kind, "known_arena")

    def test_unified_resolver_matches_direct_object_without_llm(self):
        maze = DummyMaze(
            [
                "the Ville:Dorm for Oak Hill College:kitchen",
                "the Ville:Dorm for Oak Hill College:music room",
            ]
        )
        persona = type("Persona", (), {"s_mem": DummySpatialMemory()})()
        address, meta = resolve_action_target_address(
            persona,
            maze,
            "gather",
            target="refrigerator",
            detail="opening the refrigerator to gather food items",
        )
        self.assertEqual(address, "the Ville:Dorm for Oak Hill College:kitchen:refrigerator")
        self.assertEqual(meta["kind"], "known_object")

    def test_unified_resolver_returns_parent_arena_for_arena_only_skills(self):
        maze = DummyMaze(
            [
                "the Ville:Dorm for Oak Hill College:kitchen",
                "the Ville:Dorm for Oak Hill College:music room",
            ]
        )
        persona = type("Persona", (), {"s_mem": DummySpatialMemory()})()
        address, meta = resolve_action_target_address(
            persona,
            maze,
            "use",
            target="piano",
            detail="using the piano to sing",
        )
        self.assertEqual(address, "the Ville:Dorm for Oak Hill College:music room")
        self.assertIn("parent_arena", meta["kind"])

    def test_unified_resolver_skips_recent_failed_resource_instance(self):
        maze = DummyMaze(
            [
                "the Ville:Dorm for Oak Hill College:kitchen",
                "the Ville:Dorm for Oak Hill College:lobby kitchen",
            ]
        )
        persona = type(
            "Persona",
            (),
            {
                "s_mem": DummySpatialMemory(),
                "scratch": type(
                    "Scratch",
                    (),
                    {
                        "failed_resource_instances": [
                            {
                                "target": "refrigerator",
                                "target_address": "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
                                "reason": "resource_empty",
                                "curr_step": 20,
                                "expires_after_step": 32,
                            }
                        ],
                        "successful_resource_instances": [],
                    },
                )(),
            },
        )()

        address, meta = resolve_action_target_address(
            persona,
            maze,
            "gather",
            target="refrigerator",
            detail="opening the refrigerator to gather food items",
        )

        self.assertEqual(address, "the Ville:Dorm for Oak Hill College:lobby kitchen:refrigerator")
        self.assertEqual(meta["kind"], "known_object")

    def test_unified_resolver_prefers_recent_successful_resource_instance(self):
        maze = DummyMaze(
            [
                "the Ville:Dorm for Oak Hill College:kitchen",
                "the Ville:Dorm for Oak Hill College:lobby kitchen",
            ]
        )
        persona = type(
            "Persona",
            (),
            {
                "s_mem": DummySpatialMemory(),
                "scratch": type(
                    "Scratch",
                    (),
                    {
                        "failed_resource_instances": [],
                        "successful_resource_instances": [
                            {
                                "target": "refrigerator",
                                "target_address": "the Ville:Dorm for Oak Hill College:lobby kitchen:refrigerator",
                                "progress_score": 0.8,
                                "curr_step": 21,
                                "expires_after_step": 40,
                            }
                        ],
                    },
                )(),
            },
        )()

        address, meta = resolve_action_target_address(
            persona,
            maze,
            "gather",
            target="refrigerator",
            detail="opening the refrigerator to gather food items",
        )

        self.assertEqual(address, "the Ville:Dorm for Oak Hill College:lobby kitchen:refrigerator")
        self.assertEqual(meta["kind"], "known_object")

    def test_unified_resolver_prefers_higher_progress_score_over_more_recent_success(self):
        maze = DummyMaze(
            [
                "the Ville:Dorm for Oak Hill College:kitchen",
                "the Ville:Dorm for Oak Hill College:lobby kitchen",
            ]
        )
        persona = type(
            "Persona",
            (),
            {
                "s_mem": DummySpatialMemory(),
                "scratch": type(
                    "Scratch",
                    (),
                    {
                        "failed_resource_instances": [],
                        "successful_resource_instances": [
                            {
                                "target": "refrigerator",
                                "target_address": "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
                                "progress_score": 0.9,
                                "curr_step": 18,
                                "expires_after_step": 40,
                            },
                            {
                                "target": "refrigerator",
                                "target_address": "the Ville:Dorm for Oak Hill College:lobby kitchen:refrigerator",
                                "progress_score": 0.2,
                                "curr_step": 22,
                                "expires_after_step": 42,
                            },
                        ],
                    },
                )(),
            },
        )()

        address, meta = resolve_action_target_address(
            persona,
            maze,
            "gather",
            target="refrigerator",
            detail="opening the refrigerator to gather food items",
        )

        self.assertEqual(address, "the Ville:Dorm for Oak Hill College:kitchen:refrigerator")
        self.assertEqual(meta["kind"], "known_object")

    def test_unified_resolver_prefers_successful_parent_arena_for_arena_skill(self):
        maze = DummyMaze(
            [
                "the Ville:Dorm for Oak Hill College:common room",
                "the Ville:Dorm for Oak Hill College:music room",
            ]
        )
        persona = type(
            "Persona",
            (),
            {
                "s_mem": DummySpatialMemory(),
                "scratch": type(
                    "Scratch",
                    (),
                    {
                        "failed_resource_instances": [],
                        "successful_resource_instances": [
                            {
                                "target": "piano",
                                "target_address": "the Ville:Dorm for Oak Hill College:music room:piano",
                                "progress_score": 0.7,
                                "curr_step": 21,
                                "expires_after_step": 40,
                            }
                        ],
                    },
                )(),
            },
        )()

        address, meta = resolve_action_target_address(
            persona,
            maze,
            "use",
            target="piano",
            detail="using the piano to sing",
        )

        self.assertEqual(address, "the Ville:Dorm for Oak Hill College:music room")
        self.assertIn("parent_arena", meta["kind"])

    def test_unified_resolver_prefers_higher_progress_arena_over_more_recent_one(self):
        maze = DummyMaze(
            [
                "the Ville:North Park:park garden",
                "the Ville:South Park:park garden",
            ]
        )
        persona = type(
            "Persona",
            (),
            {
                "scratch": type(
                    "Scratch",
                    (),
                    {
                        "failed_resource_instances": [],
                        "successful_resource_instances": [
                            {
                                "target": "park garden",
                                "target_address": "the Ville:North Park:park garden:bench",
                                "progress_score": 0.95,
                                "curr_step": 17,
                                "expires_after_step": 38,
                            },
                            {
                                "target": "park garden",
                                "target_address": "the Ville:South Park:park garden:bench",
                                "progress_score": 0.25,
                                "curr_step": 23,
                                "expires_after_step": 44,
                            },
                        ],
                    },
                )(),
            },
        )()

        address, meta = resolve_action_target_address(
            persona,
            maze,
            "wander",
            target="park garden",
            detail="walking through the park garden to relax",
        )

        self.assertEqual(address, "the Ville:North Park:park garden")
        self.assertIn(meta["kind"], {"known_arena", "direct_arena_match"})

    def test_chat_with_non_person_target_resolves_to_location_not_person(self):
        persona = type("Persona", (), {"s_mem": DummySpatialMemory()})()
        maze = DummyMaze(
            [
                "the Ville:Hobbs Cafe:cafe",
                "the Ville:Hobbs Cafe:cafe:cafe customer seating",
            ]
        )
        address, meta = resolve_action_target_address(
            persona,
            maze,
            "chat with",
            target="bar customer seating",
            detail="chatting with bar customers at Hobbs Cafe",
        )

        self.assertEqual(address, "the Ville:Hobbs Cafe:cafe")
        self.assertNotEqual(address, "<persona> bar customer seating")
        self.assertIn(meta["kind"], {"known_arena", "direct_arena_match"})

    def test_collective_social_target_is_detected(self):
        self.assertTrue(plan_module._is_collective_social_target("customers"))
        self.assertTrue(plan_module._is_collective_social_target("The Rose and Crown Pub", "socializing with pub patrons"))
        self.assertFalse(plan_module._is_collective_social_target("Maria Lopez"))

    def test_build_action_translation_experience_guard_exposes_avoid_and_prefer_units(self):
        scratch = type(
            "Scratch",
            (),
            {
                "get_experience_priority_units": staticmethod(
                    lambda intent_family=None: [
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
            },
        )()
        persona = type("Persona", (), {"name": "Isabella Rodriguez", "scratch": scratch})()

        guard = prompt_module.build_action_translation_experience_guard(
            persona,
            intent_family="restore_satiety",
        )

        self.assertIn("ExperienceGuard", guard)
        self.assertIn("Avoid exact instance", guard)
        self.assertIn("Hobbs Cafe", guard)
        self.assertIn("Preferred alternate sources", guard)
        self.assertIn("apple tree", guard)

    def test_action_translation_prompt_includes_experience_guard(self):
        captured = {}
        scratch = type(
            "Scratch",
            (),
            {
                "get_experience_priority_units": staticmethod(
                    lambda intent_family=None: [
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
            },
        )()
        persona = type("Persona", (), {"name": "Isabella Rodriguez", "scratch": scratch})()

        def fake_generate_prompt(prompt_input, prompt_template):
            captured["prompt_input"] = prompt_input
            return "\n".join(str(item) for item in prompt_input)

        with patch.object(prompt_module, "generate_prompt", side_effect=fake_generate_prompt), \
             patch.object(
                 prompt_module,
                 "ChatGPT_safe_generate_response",
                 return_value={
                     "action": "Gather",
                     "target": "apple tree",
                     "detail": "gathering apples from the apple tree",
                     "duration": 10,
                     "reasoning": "Recent success points to the apple tree.",
                 },
             ):
            result = prompt_module.run_gpt_prompt_action_translation(
                "I should gather food now.",
                ["refrigerator", "apple tree"],
                "Isabella",
                persona=persona,
                intent_family="restore_satiety",
            )

        self.assertEqual(result["target"], "apple tree")
        joined_prompt = "\n".join(str(item) for item in captured["prompt_input"])
        self.assertIn("ExperienceGuard", joined_prompt)
        self.assertIn("Hobbs Cafe", joined_prompt)
        self.assertIn("Preferred alternate sources", joined_prompt)

    def test_collective_social_target_routes_to_hangout_skill(self):
        action, target, detail, reasoning, rerouted = plan_module._coerce_collective_social_hangout(
            "Socialize",
            "The Rose and Crown Pub",
            "socializing with pub patrons at The Rose and Crown Pub",
            "Mood is low and social comfort would help.",
        )

        self.assertTrue(rerouted)
        self.assertEqual(action, "hangout_social_venue")
        self.assertEqual(target, "pub")
        self.assertIn("people-watching", detail)
        self.assertIn("collective social target routed", reasoning)

    def test_collective_social_target_at_cafe_does_not_route_to_hangout_skill(self):
        action, target, detail, reasoning, rerouted = plan_module._coerce_collective_social_hangout(
            "Socialize",
            "Hobbs Cafe",
            "socializing with customers at Hobbs Cafe",
            "Mood is low and social comfort would help.",
        )

        self.assertFalse(rerouted)
        self.assertEqual(action, "Socialize")
        self.assertEqual(target, "Hobbs Cafe")
        self.assertEqual(detail, "socializing with customers at Hobbs Cafe")
        self.assertEqual(reasoning, "Mood is low and social comfort would help.")

    def test_explicit_persona_chat_routes_to_seek_and_chat(self):
        personas = {
            "Klaus Mueller": type("P", (), {"name": "Klaus Mueller"})(),
        }
        action, target, detail, reasoning, rerouted = plan_module._coerce_explicit_persona_chat(
            "Socialize",
            "Klaus Mueller",
            "chatting with Klaus Mueller",
            "Mood is low and I want to catch Klaus.",
            personas=personas,
        )

        self.assertTrue(rerouted)
        self.assertEqual(action, "seek_and_chat")
        self.assertEqual(target, "Klaus Mueller")
        self.assertIn("seek_and_chat", reasoning)

    def test_seek_and_chat_builds_purposeful_objective(self):
        skill = SeekAndChatSkillPack()
        persona = type(
            "Persona",
            (),
            {
                "scratch": type(
                    "Scratch",
                    (),
                    {
                        "act_command": {"detail": "asking Klaus Mueller about the missing cafe supplies"},
                        "act_description": "asking Klaus Mueller about the missing cafe supplies",
                    },
                )(),
            },
        )()

        objective = skill._build_conversation_objective(persona, "Klaus Mueller")

        self.assertIn("missing cafe supplies", objective)


if __name__ == "__main__":
    unittest.main()
