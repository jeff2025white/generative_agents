import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from persona.cognitive_modules.action_command_utils import normalize_skill_id
from persona.cognitive_modules.action_target_resolver import resolve_known_arena_address


class DummyMaze:
    def __init__(self, addresses):
        self.address_tiles = {address: {(0, 0)} for address in addresses}


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


if __name__ == "__main__":
    unittest.main()
