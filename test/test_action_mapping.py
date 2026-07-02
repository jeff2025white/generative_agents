import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from persona.cognitive_modules.action_command_utils import normalize_skill_id
from persona.cognitive_modules.action_target_resolver import (
    resolve_action_target_address,
    resolve_known_arena_address,
)
import persona.cognitive_modules.plan as plan_module


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


if __name__ == "__main__":
    unittest.main()
