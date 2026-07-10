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


from persona.cognitive_modules.decision_constraints import build_invalid_targets, filter_invalid_resources
from persona.cognitive_modules.skill_packs.gather_skill import GatherSkillPack
from persona.cognitive_modules.world_resource_state import WorldResourceState
import persona.cognitive_modules.plan as plan_module


class GatherEmptySourceReplanTests(unittest.TestCase):
    def test_empty_town_food_source_is_marked_invalid_for_immediate_replan(self):
        navigation_failures = []
        scratch = SimpleNamespace(
            curr_tile=[0, 0],
            curr_time=None,
            inventory={},
            act_address="the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
            act_event=("Klaus Mueller", "gather", "refrigerator"),
            act_description="opening the refrigerator to gather food items",
            act_command={"skill_id": "gather", "target": "refrigerator"},
            planned_path=[[0, 1]],
            act_path_set=True,
            note_navigation_failure=lambda **kwargs: navigation_failures.append(kwargs),
        )
        persona = SimpleNamespace(
            name="Klaus Mueller",
            scratch=scratch,
            world_resource_state=WorldResourceState(
                {
                    "the Ville:Dorm for Oak Hill College:kitchen:refrigerator": {
                        "target": "refrigerator",
                        "stock": 0,
                        "kind": "town_food",
                    },
                    "the Ville:Johnson Park:park:apple tree": {
                        "target": "apple tree",
                        "stock": -1,
                        "kind": "wild_food",
                    },
                }
            ),
            s_mem=SimpleNamespace(
                find_nearest_object=lambda target: {
                    "refrigerator": "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
                    "apple tree": "the Ville:Johnson Park:park:apple tree",
                }.get(target)
            ),
            a_mem=None,
        )
        maze = SimpleNamespace(get_tile_path=lambda tile, key: "refrigerator" if key == "game_object" else None)

        GatherSkillPack().on_arrive(persona, "refrigerator", maze, {})

        self.assertEqual(len(navigation_failures), 1)
        self.assertEqual(navigation_failures[0]["target"], "refrigerator")
        self.assertEqual(navigation_failures[0]["reason"], "resource_empty")
        self.assertIsNone(persona.scratch.act_address)
        invalid_targets = build_invalid_targets(
            SimpleNamespace(
                get_recent_invalid_targets=lambda max_age_steps=6: ["refrigerator"]
            )
        )
        filtered = filter_invalid_resources(
            [
                "refrigerator (idle/normal; stock: empty)",
                "apple tree (idle/normal; stock: infinite)",
            ],
            invalid_targets,
        )
        self.assertEqual(filtered, ["apple tree (idle/normal; stock: infinite)"])

    def test_resolve_preferred_experience_food_source_prefers_strong_instance(self):
        tree = {
            "the Ville": {
                "Dorm for Oak Hill College": {
                    "kitchen": {"refrigerator": {}},
                },
                "Johnson Park": {
                    "park": {"apple tree": {}},
                },
            }
        }
        scratch = SimpleNamespace(
            get_experience_priority_units=lambda intent_family=None: [
                {
                    "experience_kind": "avoid",
                    "intent_family": "restore_satiety",
                    "resource_instance_key": "the ville:dorm for oak hill college:kitchen:refrigerator",
                    "resource_type": "refrigerator",
                    "recommendation": "avoid_this_instance",
                    "confidence": 0.91,
                },
                {
                    "experience_kind": "prefer",
                    "intent_family": "restore_satiety",
                    "resource_instance_key": "the ville:johnson park:park:apple tree",
                    "resource_type": "apple tree",
                    "recommendation": "prefer_this_instance",
                    "confidence": 0.82,
                },
            ]
        )
        persona = SimpleNamespace(
            scratch=scratch,
            s_mem=SimpleNamespace(
                tree=tree,
                find_all_objects=lambda target: {
                    "refrigerator": ["the Ville:Dorm for Oak Hill College:kitchen:refrigerator"],
                    "apple tree": ["the Ville:Johnson Park:park:apple tree"],
                }.get(target, []),
            ),
            world_resource_state=WorldResourceState(
                {
                    "the Ville:Dorm for Oak Hill College:kitchen:refrigerator": {
                        "target": "refrigerator",
                        "stock": 3,
                        "kind": "town_food",
                    },
                    "the Ville:Johnson Park:park:apple tree": {
                        "target": "apple tree",
                        "stock": -1,
                        "kind": "wild_food",
                    },
                }
            ),
        )

        preferred = plan_module._resolve_preferred_experience_food_source(persona, "refrigerator")

        self.assertEqual(preferred, "the Ville:Johnson Park:park:apple tree")

    def test_resolve_food_source_address_skips_blocked_experience_instance(self):
        persona = SimpleNamespace(
            s_mem=SimpleNamespace(
                find_all_objects=lambda target: [
                    "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
                    "the Ville:Dorm for Oak Hill College:lobby kitchen:refrigerator",
                ],
                find_nearest_object=lambda target: "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
            ),
            world_resource_state=WorldResourceState(
                {
                    "the Ville:Dorm for Oak Hill College:kitchen:refrigerator": {
                        "target": "refrigerator",
                        "stock": 5,
                        "kind": "town_food",
                    },
                    "the Ville:Dorm for Oak Hill College:lobby kitchen:refrigerator": {
                        "target": "refrigerator",
                        "stock": 2,
                        "kind": "town_food",
                    },
                }
            ),
        )

        address = plan_module._resolve_food_source_address(
            persona,
            "refrigerator",
            blocked_addresses=["the ville:dorm for oak hill college:kitchen:refrigerator"],
        )

        self.assertEqual(address, "the Ville:Dorm for Oak Hill College:lobby kitchen:refrigerator")

    def test_resolve_food_source_address_ranks_by_experience_and_logs(self):
        persona = SimpleNamespace(
            name="Klaus Mueller",
            scratch=SimpleNamespace(
                sim_code="sim_task4",
                curr_step=12,
                curr_time="2026-07-10 18:00:00",
                get_experience_priority_units=lambda intent_family=None: [
                    {
                        "experience_kind": "avoid",
                        "intent_family": "restore_satiety",
                        "resource_instance_key": "the ville:dorm for oak hill college:kitchen:refrigerator",
                        "resource_type": "refrigerator",
                        "recommendation": "avoid_this_instance",
                        "confidence": 0.92,
                    },
                    {
                        "experience_kind": "prefer",
                        "intent_family": "restore_satiety",
                        "resource_instance_key": "the ville:dorm for oak hill college:lobby kitchen:refrigerator",
                        "resource_type": "refrigerator",
                        "recommendation": "prefer_this_instance",
                        "confidence": 0.81,
                    },
                ],
            ),
            s_mem=SimpleNamespace(
                find_all_objects=lambda target: [
                    "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
                    "the Ville:Dorm for Oak Hill College:lobby kitchen:refrigerator",
                ],
                find_nearest_object=lambda target: "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
            ),
            world_resource_state=WorldResourceState(
                {
                    "the Ville:Dorm for Oak Hill College:kitchen:refrigerator": {
                        "target": "refrigerator",
                        "stock": 5,
                        "kind": "town_food",
                    },
                    "the Ville:Dorm for Oak Hill College:lobby kitchen:refrigerator": {
                        "target": "refrigerator",
                        "stock": 2,
                        "kind": "town_food",
                    },
                }
            ),
        )

        with patch.object(plan_module, "append_debug_log") as append_log:
            address = plan_module._resolve_food_source_address(persona, "refrigerator")

        self.assertEqual(address, "the Ville:Dorm for Oak Hill College:lobby kitchen:refrigerator")
        append_log.assert_called_once()
        log_name, payload = append_log.call_args.args[:2]
        self.assertEqual(log_name, "translation_verify.jsonl")
        self.assertEqual(payload["event"], "experience_ranked_candidates")
        self.assertEqual(payload["target"], "refrigerator")
        self.assertEqual(
            payload["candidate_addresses"],
            [
                "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
                "the Ville:Dorm for Oak Hill College:lobby kitchen:refrigerator",
            ],
        )
        self.assertEqual(
            payload["ranked_addresses"][0],
            "the Ville:Dorm for Oak Hill College:lobby kitchen:refrigerator",
        )
        self.assertEqual(payload["sim_code"], "sim_task4")


if __name__ == "__main__":
    unittest.main()
