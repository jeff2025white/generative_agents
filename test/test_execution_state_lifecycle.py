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


from persona.cognitive_modules.action_command_utils import build_action_command
from persona.memory_structures.scratch import Scratch


class ExecutionStateLifecycleTests(unittest.TestCase):
    def test_action_pathing_and_completion_update_active_execution_state(self):
        scratch = Scratch("/tmp/nonexistent_scratch_for_execution_state_test.json")
        scratch.name = "Maria Lopez"
        scratch.first_name = "Maria"
        scratch.curr_step = 10
        scratch.curr_time = datetime.datetime(2026, 7, 5, 8, 0, 0)

        with patch("persona.memory_structures.scratch.append_debug_log"):
            added = scratch.add_new_action(
                "the Ville:Johnson Park:park:apple tree",
                20,
                "gathering apples from the apple tree",
                "apple",
                ("Maria Lopez", "gather", "apple tree"),
                build_action_command("gather", "apple tree", source="test", raw_action="gather"),
                None,
                None,
                {},
                None,
                None,
                None,
                (None, None, None),
                scratch.curr_time,
            )

            self.assertTrue(added)
            self.assertEqual(scratch.active_execution_state["phase"], "planned")
            self.assertEqual(scratch.active_execution_state["address"], "the Ville:Johnson Park:park:apple tree")
            first_state_id = scratch.active_execution_state["id"]

            scratch.planned_path = [(1, 0), (2, 0)]
            scratch.act_path_set = True
            scratch.update_execution_state(phase="pathing")

            self.assertEqual(scratch.active_execution_state["phase"], "pathing")
            self.assertEqual(scratch.active_execution_state["path"], [(1, 0), (2, 0)])

            scratch.complete_execution()

            self.assertEqual(scratch.active_execution_state["phase"], "completed")
            self.assertEqual(scratch.active_execution_state["address"], "the Ville:Johnson Park:park:apple tree")
            self.assertEqual(scratch.planned_path, [])
            self.assertFalse(scratch.act_path_set)
            self.assertIsNone(scratch.act_address)

            scratch.curr_step = 11
            scratch.add_new_action(
                "the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
                20,
                "opening the refrigerator to gather food items",
                "apple",
                ("Maria Lopez", "gather", "refrigerator"),
                build_action_command("gather", "refrigerator", source="test", raw_action="gather"),
                None,
                None,
                {},
                None,
                None,
                None,
                (None, None, None),
                scratch.curr_time,
            )

        self.assertNotEqual(scratch.active_execution_state["id"], first_state_id)
        self.assertEqual(scratch.active_execution_state["phase"], "planned")
        self.assertEqual(scratch.active_execution_state["address"], "the Ville:Dorm for Oak Hill College:kitchen:refrigerator")


if __name__ == "__main__":
    unittest.main()
