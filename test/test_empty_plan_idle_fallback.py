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


import persona.cognitive_modules.execute as execute_module


class EmptyPlanIdleFallbackTests(unittest.TestCase):
    def test_execute_does_not_warn_or_pathfind_for_blank_plan(self):
        scratch = SimpleNamespace(
            planned_path=[(1, 1)],
            act_path_set=True,
            survival_applied=False,
            curr_tile=[3, 4],
            act_command={"skill_id": "chat with", "target": "Maria Lopez"},
            act_event=("Isabella Rodriguez", "chat with", "Maria Lopez"),
            act_description="having a conversation with Maria Lopez",
            act_pronunciatio="💬",
            act_address="",
        )
        persona = SimpleNamespace(name="Isabella Rodriguez", scratch=scratch)
        maze = SimpleNamespace(
            get_tile_path=lambda tile, level: "town square" if level == "game_object" else None,
        )

        with patch.object(execute_module, "append_debug_log") as debug_mock, \
             patch.object(execute_module, "path_finder") as path_finder_mock, \
             patch("builtins.print") as print_mock:
            next_step, emoji, description = execute_module.execute(persona, maze, {}, "")

        self.assertEqual(next_step, [3, 4])
        self.assertEqual(emoji, "💬")
        self.assertEqual(description, "idling @ town square")
        self.assertEqual(persona.scratch.planned_path, [])
        self.assertFalse(persona.scratch.act_path_set)
        self.assertFalse(path_finder_mock.called)
        self.assertTrue(debug_mock.called)
        self.assertFalse(print_mock.called)


if __name__ == "__main__":
    unittest.main()
