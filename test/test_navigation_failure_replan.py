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


from path_finder import path_finder
import persona.cognitive_modules.execute as execute_module
from persona.cognitive_modules.execute import _is_valid_navigation_path


class NavigationFailureReplanTests(unittest.TestCase):
    def test_path_finder_returns_empty_for_unreachable_target(self):
        maze = [
            ["X", "X", "X"],
            ["X", "X", "X"],
            ["X", "X", "X"],
        ]

        path = path_finder(maze, (0, 0), (2, 2), "X")

        self.assertEqual(path, [])

    def test_navigation_path_validator_rejects_single_tile_fake_path(self):
        self.assertFalse(
            _is_valid_navigation_path(
                curr_tile=[77, 16],
                target_tile=[24, 44],
                path=[(24, 44)],
            )
        )
        self.assertTrue(
            _is_valid_navigation_path(
                curr_tile=[24, 44],
                target_tile=[24, 44],
                path=[(24, 44)],
            )
        )

    def test_execute_records_navigation_failure_as_experience(self):
        scratch = SimpleNamespace(
            planned_path=[],
            act_path_set=False,
            survival_applied=False,
            curr_tile=[0, 0],
            act_command={"skill_id": "gather", "target": "refrigerator"},
            act_event=("Maria Lopez", "gather", "refrigerator"),
            act_description="walking to the refrigerator",
            act_pronunciatio="🥶",
            act_address="the Ville:Dorm:kitchen:refrigerator",
            note_navigation_failure=lambda **kwargs: None,
            clear_current_action=lambda keep_last_desc=False: None,
            social_dialogue_id=None,
        )
        persona = SimpleNamespace(name="Maria Lopez", scratch=scratch, a_mem=object())
        maze = SimpleNamespace(
            address_tiles={"the Ville:Dorm:kitchen:refrigerator": [[2, 2]]},
            collision_maze=[["X", "X", "X"], ["X", "X", "X"], ["X", "X", "X"]],
            access_tile=lambda tile: {"events": []},
        )

        with patch.object(execute_module, "record_execution_result_experience") as record_mock, \
             patch.object(execute_module, "path_finder", return_value=[]):
            execute_module.execute(persona, maze, {"Maria Lopez": persona}, "the Ville:Dorm:kitchen:refrigerator")

        self.assertTrue(record_mock.called)
        description = record_mock.call_args.args[1]
        keywords = record_mock.call_args.args[2]
        self.assertIn("could not find a reachable path", description)
        self.assertIn("path_not_found", keywords)
        self.assertIn("navigation_failure", keywords)

    def test_execute_uses_adjacent_approach_tile_for_blocked_object_tile(self):
        scratch = SimpleNamespace(
            planned_path=[],
            act_path_set=False,
            survival_applied=False,
            curr_tile=[0, 0],
            act_command={"skill_id": "gather", "target": "apple tree"},
            act_event=("Maria Lopez", "gather", "apple tree"),
            act_description="walking to the apple tree",
            act_pronunciatio="A",
            act_address="the Ville:Park:park:apple tree",
            note_navigation_failure=lambda **kwargs: None,
            clear_current_action=lambda keep_last_desc=False: None,
            social_dialogue_id=None,
        )
        persona = SimpleNamespace(name="Maria Lopez", scratch=scratch, a_mem=object())

        def access_tile(tile):
            x, y = tile
            return {
                "events": [],
                "collision": (x, y) == (1, 1),
                "game_object": "apple tree" if (x, y) == (1, 1) else "",
            }

        maze = SimpleNamespace(
            address_tiles={"the Ville:Park:park:apple tree": [(1, 1)]},
            collision_maze=[
                ["0", "0", "0"],
                ["0", "32125", "0"],
                ["0", "0", "0"],
            ],
            access_tile=access_tile,
            get_tile_path=lambda tile, level: "the Ville:Park:park:apple tree",
        )

        with patch.object(execute_module, "SKILL_REGISTRY", {}):
            next_step, _, description = execute_module.execute(
                persona,
                maze,
                {"Maria Lopez": persona},
                "the Ville:Park:park:apple tree",
            )

        self.assertIn(next_step, {(1, 0), (0, 1)})
        self.assertTrue(persona.scratch.act_path_set)
        self.assertIn("apple tree", description)


if __name__ == "__main__":
    unittest.main()
