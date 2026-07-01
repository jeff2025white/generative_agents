import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.dot = lambda *args, **kwargs: 0.0
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda *args, **kwargs: 1.0
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub
sys.modules.setdefault("openai", SimpleNamespace(api_key=None, api_base=None))

from persona.cognitive_modules.plan import plan


class PlanActEventGuardTests(unittest.TestCase):
    def test_plan_handles_none_act_event_during_social_cleanup(self):
        scratch = SimpleNamespace(
            act_event=None,
            act_address="the Ville:Dorm",
            act_description="idling briefly to stabilize after eating",
            chatting_with="Maria Lopez",
            chat=["hello"],
            chatting_end_time=123,
            curr_step=1,
            act_check_finished=lambda: False,
        )
        persona = SimpleNamespace(name="Klaus Mueller", scratch=scratch)

        with patch("persona.cognitive_modules.plan.clear_social_dialogue_state") as clear_mock, \
             patch("persona.cognitive_modules.plan._decrement_chatting_with_buffer") as decrement_mock:
            result = plan(persona, maze=None, personas={}, new_day="", retrieved={})

        self.assertEqual(result, "the Ville:Dorm")
        self.assertIsNone(persona.scratch.chatting_with)
        self.assertIsNone(persona.scratch.chat)
        self.assertIsNone(persona.scratch.chatting_end_time)
        clear_mock.assert_called_once_with(persona)
        decrement_mock.assert_called_once_with(persona)


if __name__ == "__main__":
    unittest.main()
