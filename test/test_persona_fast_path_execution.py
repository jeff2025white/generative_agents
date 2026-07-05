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


import persona.persona as persona_module


class PersonaFastPathExecutionTests(unittest.TestCase):
    def test_fast_path_executes_current_action_address_instead_of_none(self):
        persona = persona_module.Persona.__new__(persona_module.Persona)
        persona.name = "Maria Lopez"
        persona.scratch = SimpleNamespace(
            curr_tile=None,
            curr_step=None,
            health=100.0,
            curr_time=datetime.datetime(2026, 7, 5, 8, 0, 0),
            planned_path=[(2, 3), (2, 4)],
            act_address="the Ville:Johnson Park:park:apple tree",
            should_interrupt_for_physiological_crisis=lambda: False,
            get_active_decision_signature=lambda: {"skill_id": "gather", "target": "apple tree"},
        )
        persona.get_step_debug_snapshot = lambda: {
            "satiety": 39.92,
            "stamina": 99.96,
            "active_signature": {"skill_id": "gather", "target": "apple tree"},
            "planned_path_len": len(persona.scratch.planned_path),
        }
        persona.perceive = lambda maze: []
        persona.retrieve = lambda perceived: {}
        persona.plan = lambda maze, personas, new_day, retrieved: None
        persona.reflect = lambda: None

        execute_calls = []

        def fake_execute(maze, personas, plan):
            execute_calls.append(plan)
            return (2, 3), "🍎", "gathering apples from the apple tree"

        persona.execute = fake_execute

        with patch.object(persona_module, "should_run_periodic_social_scan", return_value=False), \
             patch.object(persona_module, "append_debug_log"):
            next_tile, emoji, description, step_info = persona.move(
                maze=SimpleNamespace(),
                personas={},
                curr_tile=(2, 2),
                curr_time=datetime.datetime(2026, 7, 5, 8, 1, 0),
                step=1,
            )

        self.assertEqual(execute_calls, ["the Ville:Johnson Park:park:apple tree"])
        self.assertEqual(next_tile, (2, 3))
        self.assertEqual(emoji, "🍎")
        self.assertEqual(description, "gathering apples from the apple tree")
        self.assertEqual(step_info["mode"], "fast_path")
        self.assertEqual(step_info["destination"], "the Ville:Johnson Park:park:apple tree")


if __name__ == "__main__":
    unittest.main()
